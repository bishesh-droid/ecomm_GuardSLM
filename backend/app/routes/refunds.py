from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, schemas
from ..database import get_db
from ..models import Order, OrderItem, Payment, Refund, User
from ..permissions import (
    deny, require_authenticated_user, require_order_owner, require_refund_permission,
)
from ..services import (
    active_refund_exists, complete_refund, get_or_404, item_delivered_at, log, money, restore_order_state,
    transition, within_days,
)

router = APIRouter(prefix="/refunds", tags=["refunds"])


def refund_dict(r: Refund) -> dict:
    return {"id": r.id, "order_id": r.order_id, "order_item_id": r.order_item_id, "amount": money(r.amount),
            "reason": r.reason, "status": r.status, "decision_note": r.decision_note, "requested_by": r.requested_by,
            "product_name": r.item.product_name if r.item else None, "seller_id": r.item.seller_id if r.item else None,
            "customer_name": r.order.customer.display_name, "created_at": r.created_at.isoformat()}


@router.get("")
def list_refunds(user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    stmt = select(Refund).order_by(Refund.id.desc())
    if user.role == "CUSTOMER":
        stmt = stmt.where(Refund.order_id.in_(select(Order.id).where(Order.customer_id == user.id)))
    elif user.role == "SELLER":
        stmt = stmt.where(Refund.order_item_id.in_(select(OrderItem.id).where(OrderItem.seller_id == user.seller.id)))
    elif user.role not in ("ADMIN", "SUPPORT"):
        deny("Refund records are restricted")
    return [refund_dict(r) for r in db.scalars(stmt).all()]


@router.post("", status_code=201)
def request_refund(body: schemas.RefundIn, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    item = get_or_404(db, OrderItem, body.order_item_id, "Order item")
    order = get_or_404(db, Order, item.order_id, lock=True)
    if user.role != "ADMIN":
        require_order_owner(user, order)  # blocks other customers and every non-customer role
    if item.status != "DELIVERED":
        raise HTTPException(409, f"Item in state {item.status} is not refundable")
    if not within_days(item_delivered_at(item), config.REFUND_WINDOW_DAYS):
        raise HTTPException(409, f"Refund window of {config.REFUND_WINDOW_DAYS} days has passed")
    if active_refund_exists(db, item.id):
        raise HTTPException(409, "A refund already exists for this item")
    pay = next((p for p in order.payments if p.status in ("SUCCEEDED", "PARTIALLY_REFUNDED")), None)
    if pay is None:
        raise HTTPException(409, "No settled payment for this order")
    r = Refund(order_id=order.id, order_item_id=item.id, payment_id=pay.id, requested_by=user.id,
               amount=item.line_total, reason=body.reason)
    db.add(r)
    order.status = "REFUND_PENDING"
    log(db, user, "refund.request", "refund", order.id, f"item={item.id}")
    db.commit()
    return refund_dict(r)


def _load(db, refund_id):
    r = get_or_404(db, Refund, refund_id, lock=True)
    return r, r.item


@router.post("/{refund_id}/approve")
def approve(refund_id: int, body: schemas.DecisionIn, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    r, item = _load(db, refund_id)
    require_refund_permission(user, r, item, "decide")
    if not transition(db, Refund, r.id, "REQUESTED", "APPROVED", decided_by=user.id, decision_note=body.note):
        raise HTTPException(409, "Refund is not awaiting a decision")
    db.refresh(r)
    log(db, user, "refund.approve", "refund", r.id, body.note)
    db.commit()
    return refund_dict(r)


@router.post("/{refund_id}/reject")
def reject(refund_id: int, body: schemas.DecisionIn, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    r, item = _load(db, refund_id)
    require_refund_permission(user, r, item, "decide")
    if not transition(db, Refund, r.id, "REQUESTED", "REJECTED", decided_by=user.id, decision_note=body.note):
        raise HTTPException(409, "Refund is not awaiting a decision")
    db.refresh(r)
    restore_order_state(db, r.order)
    log(db, user, "refund.reject", "refund", r.id, body.note)
    db.commit()
    return refund_dict(r)


@router.post("/{refund_id}/complete")
def complete(refund_id: int, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    """Money movement. Admin, or support with the explicit can_issue_refunds permission. Never sellers."""
    r, item = _load(db, refund_id)
    require_refund_permission(user, r, item, "complete")
    try:
        complete_refund(db, r)
        log(db, user, "refund.complete", "refund", r.id, f"amount={r.amount}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(r)
    return refund_dict(r)
