from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Address, Cart, Order, OrderItem, Payment, Product, Refund, Shipment, User, utcnow
from ..permissions import (
    can_view_order, deny, require_authenticated_user, require_cancel_policy, require_customer, require_order_owner,
)
from ..services import (
    confirm_order, get_or_404, log, order_dict, payment_dict, release_order_stock, reserve_stock, transition,
)

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/checkout", status_code=201)
def checkout(body: schemas.CheckoutIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    """One transaction: validate cart -> reserve stock atomically -> create order, shipments, payment."""
    address = get_or_404(db, Address, body.address_id, "Address")
    if address.user_id != user.id:
        deny("This address belongs to another customer")
    cart = db.scalar(select(Cart).where(Cart.user_id == user.id))
    if cart is None or not cart.items:
        raise HTTPException(409, "Cart is empty")
    try:
        lines = []
        for ci in sorted(cart.items, key=lambda c: c.product_id):  # stable lock order avoids deadlocks
            p = db.get(Product, ci.product_id)
            if p.status != "ACTIVE" or p.seller.status != "APPROVED":
                raise HTTPException(409, f"'{p.name}' is no longer available")
            reserve_stock(db, p.id, ci.quantity, "checkout", user)
            lines.append((p, ci.quantity))
        total = sum((p.price * q for p, q in lines), Decimal(0))
        order = Order(
            customer_id=user.id, status="PENDING_PAYMENT", total=total, payment_method=body.payment_method,
            shipping_name=address.full_name, shipping_city=address.city, shipping_postal_code=address.postal_code,
            shipping_address=f"{address.line1}, {address.city}, {address.state} {address.postal_code}, {address.country}",
        )
        db.add(order)
        db.flush()
        by_seller: dict[int, Shipment] = {}
        for p, q in lines:
            ship = by_seller.get(p.seller_id)
            if ship is None:
                ship = Shipment(order_id=order.id, seller_id=p.seller_id, status="PENDING_PAYMENT")
                db.add(ship)
                db.flush()
                by_seller[p.seller_id] = ship
            db.add(OrderItem(order_id=order.id, product_id=p.id, seller_id=p.seller_id, shipment_id=ship.id,
                             product_name=p.name, unit_price=p.price, quantity=q, status="PENDING_PAYMENT"))
        payment = Payment(order_id=order.id, method=body.payment_method, amount=total,
                          status="COD_PENDING" if body.payment_method == "COD" else "PENDING")
        db.add(payment)
        db.flush()
        db.refresh(order)
        if body.payment_method == "COD":
            confirm_order(db, order)
        for ci in list(cart.items):
            cart.items.remove(ci)
        log(db, user, "order.checkout", "order", order.id, f"total={total} method={body.payment_method}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"order": order_dict(order, user), "payment": payment_dict(payment)}


@router.get("")
def list_orders(status: str | None = None, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    stmt = select(Order).order_by(Order.id.desc())
    if user.role == "CUSTOMER":
        stmt = stmt.where(Order.customer_id == user.id)
    elif user.role == "SELLER":
        stmt = stmt.where(Order.id.in_(select(OrderItem.order_id).where(OrderItem.seller_id == user.seller.id)))
    elif user.role == "WAREHOUSE":
        stmt = stmt.where(Order.assigned_warehouse_id == user.id)
    elif user.role == "SUPPORT":
        stmt = stmt.where(Order.status != "PENDING_PAYMENT").limit(100)  # limited lookup
    if status:
        stmt = stmt.where(Order.status == status)
    return [order_dict(o, user) for o in db.scalars(stmt).all()]


@router.get("/{order_id}")
def get_order(order_id: int, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    order = get_or_404(db, Order, order_id)
    can_view_order(user, order)
    log(db, user, "order.view", "order", order_id)
    db.commit()
    return order_dict(order, user)


@router.post("/{order_id}/cancel")
def cancel_order(order_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    order = get_or_404(db, Order, order_id, lock=True)
    require_order_owner(user, order)
    require_cancel_policy(order)  # BLOCK/ASK after dispatch, 409 for terminal states
    try:
        release_order_stock(db, order, user, "RELEASE")
        for s in order.shipments:
            s.status = "CANCELLED"
        for it in order.items:
            it.status = "CANCELLED"
        order.status = "CANCELLED"
        for pay in order.payments:
            if pay.status in ("PENDING", "FAILED", "COD_PENDING"):
                pay.status = "CANCELLED"
            elif pay.status == "SUCCEEDED":
                # prepaid and unshipped: simulated refund is system-approved and settled in the same transaction
                if not transition(db, Payment, pay.id, "SUCCEEDED", "REFUNDED", refunded_amount=pay.amount):
                    raise HTTPException(409, "Payment changed concurrently")
                db.add(Refund(order_id=order.id, payment_id=pay.id, requested_by=user.id, amount=pay.amount,
                              reason="Order cancelled before dispatch", status="COMPLETED", decision_note="auto-approved"))
        log(db, user, "order.cancel", "order", order.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return order_dict(order, user)
