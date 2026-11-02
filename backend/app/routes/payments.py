import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Order, Payment, SavedPaymentMethod, User, utcnow
from ..permissions import (
    deny, require_admin, require_authenticated_user, require_customer, require_order_owner,
)
from ..services import confirm_order, get_or_404, log, payment_dict, transition

router = APIRouter(prefix="/payments", tags=["payments"])


def simulate_outcome(method: str, token: str) -> tuple[bool, str | None]:
    """Deterministic sandbox gateway. No real instruments are ever processed."""
    if re.fullmatch(r"[\d \-]{12,23}", token):
        raise HTTPException(422, "Real card numbers are not accepted; use a sandbox token (tok_sim_ok / tok_sim_fail)")
    t = token.strip().lower()
    if method == "UPI":
        if t.endswith("@sim"):
            return True, None
        if t.endswith("@fail"):
            return False, "UPI collect request declined (simulated)"
        return False, "Unknown UPI handle (use name@sim to succeed)"
    if t == "tok_sim_ok":
        return True, None
    if t == "tok_sim_fail":
        return False, "Card declined (simulated)"
    return False, "Unrecognized sandbox token"


@router.get("/methods")
def my_payment_methods(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """Masked saved tokens, own only."""
    rows = db.scalars(select(SavedPaymentMethod).where(SavedPaymentMethod.user_id == user.id)).all()
    return [{"id": m.id, "kind": m.kind, "label": m.label, "last4": m.last4, "token": m.token} for m in rows]


@router.post("", status_code=201)
def create_payment(body: schemas.PaymentCreateIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """Create a fresh attempt for an unpaid order (e.g. after a failed attempt)."""
    order = get_or_404(db, Order, body.order_id, lock=True)
    require_order_owner(user, order)
    if order.status != "PENDING_PAYMENT":
        raise HTTPException(409, "Order is not awaiting payment")
    if any(p.status in ("PENDING", "SUCCEEDED") for p in order.payments):
        raise HTTPException(409, "A payment is already in progress or completed")
    method = body.method or order.payment_method
    if method == "COD":
        raise HTTPException(409, "COD orders are confirmed at checkout")
    pay = Payment(order_id=order.id, method=method, amount=order.total, status="PENDING")
    db.add(pay)
    log(db, user, "payment.create", "order", order.id)
    db.commit()
    return payment_dict(pay)


@router.get("/{payment_id}")
def get_payment(payment_id: int, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    pay = get_or_404(db, Payment, payment_id)
    if user.role == "CUSTOMER":
        require_order_owner(user, pay.order)
    elif user.role not in ("ADMIN", "SUPPORT"):
        deny("Payment records are restricted")
    return payment_dict(pay)


@router.post("/{payment_id}/pay")
def pay(payment_id: int, body: schemas.PayIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """Submit a sandbox token. A payment is decided exactly once; FAILED/SUCCEEDED are terminal."""
    pay_row = get_or_404(db, Payment, payment_id)
    order = get_or_404(db, Order, pay_row.order_id, lock=True)
    require_order_owner(user, order)
    ok, reason = simulate_outcome(pay_row.method, body.token)
    new = "SUCCEEDED" if ok else "FAILED"
    extra = {"confirmed_at": utcnow(), "provider_ref": f"sim_{pay_row.id:06d}", "token_last4": re.sub(r"\W", "", body.token)[-4:]}
    if not ok:
        extra["failure_reason"] = reason
    if not transition(db, Payment, pay_row.id, "PENDING", new, **extra):
        db.rollback()
        raise HTTPException(409, "Payment already processed; duplicate confirmation rejected")
    db.refresh(pay_row)
    if ok:
        if order.status != "PENDING_PAYMENT":
            db.rollback()
            raise HTTPException(409, "Order is not awaiting payment")
        confirm_order(db, order)
    log(db, user, f"payment.{new.lower()}", "payment", pay_row.id)
    db.commit()
    return payment_dict(pay_row)


@router.post("/{payment_id}/confirm")
def admin_confirm(payment_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Manual reconciliation by an administrator. Customers/sellers/support are blocked."""
    pay_row = get_or_404(db, Payment, payment_id)
    order = get_or_404(db, Order, pay_row.order_id, lock=True)
    if order.status != "PENDING_PAYMENT":
        raise HTTPException(409, "Order is not awaiting payment")
    if not transition(db, Payment, pay_row.id, "PENDING", "SUCCEEDED", confirmed_at=utcnow(), provider_ref=f"manual_{pay_row.id:06d}"):
        raise HTTPException(409, "Only a PENDING payment can be confirmed")
    db.refresh(pay_row)
    confirm_order(db, order)
    log(db, user, "payment.admin_confirm", "payment", pay_row.id)
    db.commit()
    return payment_dict(pay_row)


@router.post("/{payment_id}/fail")
def admin_fail(payment_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    pay_row = get_or_404(db, Payment, payment_id)
    if not transition(db, Payment, pay_row.id, "PENDING", "FAILED", failure_reason="Marked failed by administrator"):
        raise HTTPException(409, "Only a PENDING payment can be failed")
    db.refresh(pay_row)
    log(db, user, "payment.admin_fail", "payment", pay_row.id)
    db.commit()
    return payment_dict(pay_row)
