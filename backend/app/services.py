"""Transactional business logic shared by routes. Callers own the commit."""
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import (
    FLOW, ActivityLog, Inventory, Order, OrderItem, Payment, Product, Refund, Review, Shipment,
    StockMovement, User, aware, utcnow,
)

NEXT_STATE = {"CONFIRMED": "PROCESSING", "PROCESSING": "PACKED", "PACKED": "SHIPPED", "SHIPPED": "DELIVERED"}
SPECIAL_ORDER_STATES = {"CANCELLED", "RETURN_REQUESTED", "RETURN_APPROVED", "RETURNED", "REFUND_PENDING", "REFUNDED", "PENDING_PAYMENT"}


def money(v) -> float:
    return float(Decimal(v or 0).quantize(Decimal("0.01")))


def log(db: Session, user: User | None, action: str, entity_type: str | None = None, entity_id=None,
        detail: str | None = None, decision: str = "ALLOW") -> None:
    db.add(ActivityLog(
        actor_id=user.id if user else None, actor_role=user.role if user else None, action=action,
        entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail, decision=decision,
    ))


def get_or_404(db: Session, model, ident, what: str | None = None, lock: bool = False):
    obj = db.get(model, ident, with_for_update=lock) if lock else db.get(model, ident)
    if obj is None:
        raise HTTPException(404, f"{what or model.__name__} not found")
    return obj


def transition(db: Session, model, ident: int, from_states, to_state: str, **extra) -> bool:
    """Atomic compare-and-set on a status column. Returns False if the row was not in from_states.
    This is what blocks duplicate payment confirmations and double refunds even under concurrency."""
    if isinstance(from_states, str):
        from_states = [from_states]
    res = db.execute(
        update(model).where(model.id == ident, model.status.in_(from_states)).values(status=to_state, **extra)
    )
    return res.rowcount == 1


# ---------------- inventory ----------------
def reserve_stock(db: Session, product_id: int, qty: int, reference: str, actor: User | None) -> None:
    res = db.execute(
        update(Inventory).where(Inventory.product_id == product_id, Inventory.quantity >= qty)
        .values(quantity=Inventory.quantity - qty)
    )
    if res.rowcount != 1:
        raise HTTPException(409, f"Insufficient stock for product {product_id}")
    db.add(StockMovement(product_id=product_id, delta=-qty, reason="RESERVE", reference=reference, actor_id=actor.id if actor else None))


def release_stock(db: Session, product_id: int, qty: int, reason: str, reference: str, actor: User | None) -> None:
    db.execute(update(Inventory).where(Inventory.product_id == product_id).values(quantity=Inventory.quantity + qty))
    db.add(StockMovement(product_id=product_id, delta=qty, reason=reason, reference=reference, actor_id=actor.id if actor else None))


def adjust_stock(db: Session, product_id: int, delta: int, reason: str, actor: User) -> int:
    """Atomic stock change that can never drive quantity below zero."""
    cond = [Inventory.product_id == product_id]
    if delta < 0:
        cond.append(Inventory.quantity >= -delta)
    res = db.execute(update(Inventory).where(*cond).values(quantity=Inventory.quantity + delta))
    if res.rowcount != 1:
        raise HTTPException(409, "Stock cannot go below zero")
    db.add(StockMovement(product_id=product_id, delta=delta, reason=reason, actor_id=actor.id))
    return db.scalar(select(Inventory.quantity).where(Inventory.product_id == product_id))


# ---------------- order state ----------------
def recompute_order_status(order: Order) -> None:
    if order.status in SPECIAL_ORDER_STATES:
        return
    active = [s for s in order.shipments if s.status != "CANCELLED"]
    if not active:
        return
    order.status = min((s.status for s in active), key=FLOW.index)
    if order.status == "DELIVERED" and order.delivered_at is None:
        order.delivered_at = utcnow()


def advance_shipment(db: Session, shipment: Shipment, order: Order, target: str, tracking: str | None = None,
                     carrier: str | None = None) -> None:
    if order.status in SPECIAL_ORDER_STATES:
        raise HTTPException(409, f"Order in state {order.status} cannot be fulfilled")
    if NEXT_STATE.get(shipment.status) != target:
        raise HTTPException(409, f"Shipment cannot move from {shipment.status} to {target}")
    extra = {}
    if target == "SHIPPED":
        extra["tracking_number"] = tracking or shipment.tracking_number or f"GSLM{order.id:05d}{shipment.id:03d}"
        extra["carrier"] = carrier or shipment.carrier or "GuardExpress"
        extra["tracking_status"] = "Dispatched from warehouse"
    if target == "DELIVERED":
        extra["tracking_status"] = "Delivered"
    if not transition(db, Shipment, shipment.id, shipment.status, target, **extra):
        raise HTTPException(409, "Shipment was updated concurrently")
    db.refresh(shipment)
    for it in shipment.items:
        if it.status not in ("CANCELLED", "RETURNED", "REFUNDED"):
            it.status = target
    db.flush()
    db.refresh(order)
    recompute_order_status(order)
    if order.status == "DELIVERED":
        # cash on delivery is collected on delivery
        for p in order.payments:
            if p.status == "COD_PENDING":
                transition(db, Payment, p.id, "COD_PENDING", "SUCCEEDED", confirmed_at=utcnow())


def confirm_order(db: Session, order: Order) -> None:
    """Called exactly once after payment success/COD: confirms, assigns warehouse and shipment records."""
    warehouse = db.scalar(select(User).where(User.role == "WAREHOUSE", User.is_active.is_(True)).order_by(User.id))
    order.status = "CONFIRMED"
    order.assigned_warehouse_id = warehouse.id if warehouse else None
    for s in order.shipments:
        s.status = "CONFIRMED"
    for it in order.items:
        it.status = "CONFIRMED"


def release_order_stock(db: Session, order: Order, actor: User | None, reason: str = "RELEASE") -> None:
    for it in sorted(order.items, key=lambda i: i.product_id):
        if it.status not in ("CANCELLED", "RETURNED", "REFUNDED"):
            release_stock(db, it.product_id, it.quantity, reason, f"order:{order.id}", actor)


# ---------------- refunds ----------------
def active_refund_exists(db: Session, order_item_id: int) -> bool:
    return db.scalar(select(func.count(Refund.id)).where(
        Refund.order_item_id == order_item_id, Refund.status.in_(["REQUESTED", "APPROVED", "COMPLETED"]))) > 0


def complete_refund(db: Session, refund: Refund) -> None:
    """APPROVED -> COMPLETED exactly once; updates payment totals and order state atomically."""
    if not transition(db, Refund, refund.id, "APPROVED", "COMPLETED"):
        raise HTTPException(409, "Refund is not in an approvable state (already completed or not approved)")
    pay = db.get(Payment, refund.payment_id, with_for_update=True) if refund.payment_id else None
    if pay is None or pay.status not in ("SUCCEEDED", "PARTIALLY_REFUNDED"):
        raise HTTPException(409, "No settled payment to refund")
    new_total = Decimal(pay.refunded_amount) + Decimal(refund.amount)
    if new_total > Decimal(pay.amount):
        raise HTTPException(409, "Refund exceeds paid amount")
    pay.refunded_amount = new_total
    pay.status = "REFUNDED" if new_total == Decimal(pay.amount) else "PARTIALLY_REFUNDED"
    order = db.get(Order, refund.order_id)
    if refund.order_item_id:
        item = db.get(OrderItem, refund.order_item_id)
        item.status = "REFUNDED"
    pending = db.scalar(select(func.count(Refund.id)).where(
        Refund.order_id == order.id, Refund.status.in_(["REQUESTED", "APPROVED"])))
    if pay.status == "REFUNDED" or all(i.status in ("REFUNDED", "CANCELLED") for i in order.items):
        order.status = "REFUNDED"
    elif pending:
        order.status = "REFUND_PENDING"
    else:
        restore_order_state(db, order)


def restore_order_state(db: Session, order: Order) -> None:
    """After a return/refund is resolved without refunding everything, fall back to the fulfilment state."""
    if order.status not in ("RETURN_REQUESTED", "RETURN_APPROVED", "RETURNED", "REFUND_PENDING"):
        return
    busy = any(i.status in ("RETURN_REQUESTED", "RETURN_APPROVED", "RETURNED") for i in order.items) or db.scalar(
        select(func.count(Refund.id)).where(Refund.order_id == order.id, Refund.status.in_(["REQUESTED", "APPROVED"]))) > 0
    if not busy:
        order.status = "DELIVERED"


def item_delivered_at(item: OrderItem):
    return aware(item.order.delivered_at) or aware(next((s.updated_at for s in item.order.shipments if s.id == item.shipment_id), None))


def within_days(dt, days: int) -> bool:
    dt = aware(dt)
    return dt is not None and utcnow() - dt <= timedelta(days=days)


# ---------------- ratings ----------------
def recompute_rating(db: Session, product: Product) -> None:
    rows = db.execute(select(func.count(Review.id), func.coalesce(func.sum(Review.rating), 0))
                      .where(Review.product_id == product.id, Review.status == "VISIBLE")).one()
    n = product.seed_review_count + rows[0]
    total = Decimal(product.seed_rating) * product.seed_review_count + Decimal(rows[1])
    product.review_count = n
    product.rating = (total / n).quantize(Decimal("0.01")) if n else Decimal(0)


# ---------------- serializers ----------------
def product_dict(p: Product, include_stock: bool = True, include_seller: bool = True) -> dict:
    d = {
        "id": p.id, "name": p.name, "brand": p.brand, "description": p.description, "price": money(p.price),
        "category": p.category.name, "category_id": p.category_id, "category_slug": p.category.slug,
        "image": p.image, "rating": float(p.rating), "review_count": p.review_count, "status": p.status,
        "seller_id": p.seller_id, "created_at": p.created_at.isoformat(),
    }
    if include_seller:
        d["seller_name"] = p.seller.store_name
    if include_stock and p.inventory is not None:
        d["stock"] = p.inventory.quantity
    return d


def item_dict(i: OrderItem) -> dict:
    return {"id": i.id, "product_id": i.product_id, "seller_id": i.seller_id, "product_name": i.product_name,
            "unit_price": money(i.unit_price), "quantity": i.quantity, "line_total": money(i.line_total),
            "status": i.status, "shipment_id": i.shipment_id, "image": i.product.image if i.product else ""}


def payment_dict(p: Payment) -> dict:
    return {"id": p.id, "order_id": p.order_id, "method": p.method, "status": p.status, "amount": money(p.amount),
            "refunded_amount": money(p.refunded_amount), "token_last4": p.token_last4,
            "failure_reason": p.failure_reason, "created_at": p.created_at.isoformat()}


def shipment_dict(s: Shipment) -> dict:
    return {"id": s.id, "order_id": s.order_id, "seller_id": s.seller_id, "status": s.status, "carrier": s.carrier,
            "tracking_number": s.tracking_number, "tracking_status": s.tracking_status,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None, "item_ids": [i.id for i in s.items]}


def order_dict(o: Order, viewer: User) -> dict:
    """Role-scoped projection of an order. The scoping lives here so no route can forget it."""
    items, shipments = list(o.items), list(o.shipments)
    if viewer.role == "SELLER":
        sid = viewer.seller.id
        items = [i for i in items if i.seller_id == sid]
        shipments = [s for s in shipments if s.seller_id == sid]
    d = {
        "id": o.id, "status": o.status, "created_at": o.created_at.isoformat(), "payment_method": o.payment_method,
        "items": [item_dict(i) for i in items], "shipments": [shipment_dict(s) for s in shipments],
        "total": money(o.total) if viewer.role != "SELLER" else money(sum(i.line_total for i in items)),
        "shipping_city": o.shipping_city, "shipping_postal_code": o.shipping_postal_code,
        "customer_id": o.customer_id if viewer.role in ("ADMIN", "CUSTOMER", "SUPPORT") else None,
    }
    if viewer.role in ("ADMIN", "CUSTOMER", "WAREHOUSE", "SELLER", "SUPPORT"):
        d["shipping_name"] = o.shipping_name
    if viewer.role in ("ADMIN", "CUSTOMER", "WAREHOUSE", "SELLER"):
        d["shipping_address"] = o.shipping_address
    if viewer.role in ("ADMIN", "SUPPORT", "CUSTOMER"):
        d["payments"] = [payment_dict(p) for p in o.payments]
        d["customer_name"] = o.customer.display_name
    return d
