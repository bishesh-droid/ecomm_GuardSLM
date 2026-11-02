from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, schemas
from ..database import get_db
from ..models import Order, OrderItem, Payment, Refund, ReturnRequest, User
from ..permissions import (
    deny, require_admin, require_authenticated_user, require_order_item_seller, require_order_owner,
    require_admin_or_support,
)
from ..services import (
    active_refund_exists, get_or_404, item_delivered_at, log, release_stock, restore_order_state, transition, within_days,
)

router = APIRouter(prefix="/returns", tags=["returns"])


def return_dict(r: ReturnRequest) -> dict:
    return {"id": r.id, "order_id": r.order_id, "order_item_id": r.order_item_id, "reason": r.reason, "status": r.status,
            "seller_response": r.seller_response, "support_note": r.support_note, "overridden_by": r.overridden_by,
            "product_name": r.item.product_name, "seller_id": r.item.seller_id, "customer_id": r.customer_id,
            "created_at": r.created_at.isoformat()}


@router.get("")
def list_returns(user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    stmt = select(ReturnRequest).order_by(ReturnRequest.id.desc())
    if user.role == "CUSTOMER":
        stmt = stmt.where(ReturnRequest.customer_id == user.id)
    elif user.role == "SELLER":
        stmt = stmt.where(ReturnRequest.order_item_id.in_(select(OrderItem.id).where(OrderItem.seller_id == user.seller.id)))
    elif user.role == "WAREHOUSE":
        stmt = stmt.where(ReturnRequest.order_id.in_(select(Order.id).where(Order.assigned_warehouse_id == user.id)))
    return [return_dict(r) for r in db.scalars(stmt).all()]


@router.get("/eligibility/{order_item_id}")
def eligibility(order_item_id: int, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    item = get_or_404(db, OrderItem, order_item_id, "Order item")
    if user.role != "ADMIN":
        require_order_owner(user, item.order)
    reasons = []
    if item.status != "DELIVERED":
        reasons.append(f"Item is {item.status}")
    elif not within_days(item_delivered_at(item), config.RETURN_WINDOW_DAYS):
        reasons.append(f"Return window of {config.RETURN_WINDOW_DAYS} days has passed")
    return {"eligible": not reasons, "reasons": reasons, "window_days": config.RETURN_WINDOW_DAYS}


@router.post("", status_code=201)
def request_return(body: schemas.ReturnIn, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    item = get_or_404(db, OrderItem, body.order_item_id, "Order item")
    order = get_or_404(db, Order, item.order_id, lock=True)
    if user.role != "ADMIN":
        require_order_owner(user, order)
    if item.status != "DELIVERED":
        raise HTTPException(409, f"Item in state {item.status} cannot be returned")
    if not within_days(item_delivered_at(item), config.RETURN_WINDOW_DAYS):
        raise HTTPException(409, f"Return window of {config.RETURN_WINDOW_DAYS} days has passed")
    if active_refund_exists(db, item.id):
        raise HTTPException(409, "A refund already exists for this item")
    r = ReturnRequest(order_id=order.id, order_item_id=item.id, customer_id=order.customer_id, reason=body.reason)
    db.add(r)
    item.status = "RETURN_REQUESTED"
    order.status = "RETURN_REQUESTED"
    log(db, user, "return.request", "order_item", item.id)
    db.commit()
    return return_dict(r)


def _set(db, r: ReturnRequest, from_states, to, item_status, **extra):
    if not transition(db, ReturnRequest, r.id, from_states, to, **extra):
        raise HTTPException(409, f"Return is {r.status}; expected one of {from_states}")
    db.refresh(r)
    r.item.status = item_status
    if to == "APPROVED":
        r.order.status = "RETURN_APPROVED"
    elif to == "REJECTED":
        restore_order_state(db, r.order)


@router.post("/{return_id}/respond")
def seller_respond(return_id: int, body: schemas.ReturnDecisionIn, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    r = get_or_404(db, ReturnRequest, return_id, lock=True)
    require_order_item_seller(user, r.item)
    if body.approve:
        _set(db, r, ["REQUESTED"], "APPROVED", "RETURN_APPROVED", seller_response=body.note)
    else:
        _set(db, r, ["REQUESTED"], "REJECTED", "DELIVERED", seller_response=body.note)
        db.refresh(r.order)
        restore_order_state(db, r.order)
    log(db, user, "return.seller_respond", "return", r.id, f"approve={body.approve}")
    db.commit()
    return return_dict(r)


@router.post("/{return_id}/review")
def support_review(return_id: int, body: schemas.ReturnDecisionIn, user: User = Depends(require_admin_or_support), db: Session = Depends(get_db)):
    r = get_or_404(db, ReturnRequest, return_id, lock=True)
    if body.approve:
        _set(db, r, ["REQUESTED", "REJECTED"], "APPROVED", "RETURN_APPROVED", support_note=body.note)
    else:
        _set(db, r, ["REQUESTED"], "REJECTED", "DELIVERED", support_note=body.note)
        db.refresh(r.order)
        restore_order_state(db, r.order)
    log(db, user, "return.support_review", "return", r.id, f"approve={body.approve}")
    db.commit()
    return return_dict(r)


@router.post("/{return_id}/override")
def admin_override(return_id: int, body: schemas.ReturnOverrideIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    r = get_or_404(db, ReturnRequest, return_id, lock=True)
    if r.status == "RETURNED":
        raise HTTPException(409, "Return already completed")
    prev = r.status
    if body.decision == "APPROVED":
        _set(db, r, ["REQUESTED", "REJECTED", "APPROVED"], "APPROVED", "RETURN_APPROVED", overridden_by=user.id, support_note=f"[admin override] {body.note}")
    else:
        _set(db, r, ["REQUESTED", "REJECTED", "APPROVED"], "REJECTED", "DELIVERED", overridden_by=user.id, support_note=f"[admin override] {body.note}")
        db.refresh(r.order)
        restore_order_state(db, r.order)
    log(db, user, "return.admin_override", "return", r.id, f"{prev}->{body.decision}: {body.note}")
    db.commit()
    return return_dict(r)


@router.post("/{return_id}/receive")
def receive(return_id: int, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    """Goods back at the warehouse/seller: restock and open the refund for approval."""
    r = get_or_404(db, ReturnRequest, return_id, lock=True)
    item, order = r.item, r.order
    if user.role == "WAREHOUSE":
        if order.assigned_warehouse_id != user.id:
            deny("Order is not assigned to your warehouse")
    else:
        require_order_item_seller(user, item)
    _set(db, r, ["APPROVED"], "RETURNED", "RETURNED")
    release_stock(db, item.product_id, item.quantity, "RETURN", f"return:{r.id}", user)
    pay = next((p for p in order.payments if p.status in ("SUCCEEDED", "PARTIALLY_REFUNDED")), None)
    if pay is not None and not active_refund_exists(db, item.id):
        db.add(Refund(order_id=order.id, order_item_id=item.id, payment_id=pay.id, requested_by=r.customer_id,
                      amount=item.line_total, reason=f"Return #{r.id} received"))
        order.status = "REFUND_PENDING"
    else:
        order.status = "RETURNED"
    log(db, user, "return.receive", "return", r.id)
    db.commit()
    return return_dict(r)
