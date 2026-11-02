from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import (
    Category, Inventory, Order, OrderItem, Product, Seller, Shipment, StockMovement, User, utcnow,
)
from ..permissions import (
    deny, require_approved_seller, require_authenticated_user, require_inventory_access, require_product_owner,
    require_sales_report_access, require_seller, require_shipment_access, seller_profile,
)
from ..services import (
    adjust_stock, advance_shipment, get_or_404, log, money, order_dict, product_dict, shipment_dict,
)

router = APIRouter(prefix="/seller", tags=["seller"])


@router.get("/me")
def seller_me(user: User = Depends(require_seller)):
    s = seller_profile(user)
    return {"id": s.id, "store_name": s.store_name, "status": s.status, "description": s.description}


# ---------- products ----------
@router.get("/products")
def my_products(user: User = Depends(require_seller), db: Session = Depends(get_db)):
    sid = seller_profile(user).id
    return [product_dict(p) for p in db.scalars(select(Product).where(Product.seller_id == sid).order_by(Product.id.desc()))]


@router.post("/products", status_code=201)
def create_product(body: schemas.ProductIn, user: User = Depends(require_approved_seller), db: Session = Depends(get_db)):
    get_or_404(db, Category, body.category_id, "Category")
    p = Product(seller_id=user.seller.id, category_id=body.category_id, name=body.name, brand=body.brand or user.seller.store_name,
                description=body.description, price=body.price,
                status="PENDING_REVIEW" if body.submit_for_review else "DRAFT", image="/static/products/default.svg")
    db.add(p)
    db.flush()
    db.add(Inventory(product_id=p.id, quantity=body.stock))
    if body.stock:
        db.add(StockMovement(product_id=p.id, delta=body.stock, reason="RECEIVE", reference="initial", actor_id=user.id))
    log(db, user, "product.create", "product", p.id)
    db.commit()
    return product_dict(p)


@router.get("/products/{product_id}")
def my_product(product_id: int, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, product_id)
    require_product_owner(user, p)
    return product_dict(p)


@router.put("/products/{product_id}")
def edit_product(product_id: int, body: schemas.ProductUpdate, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, product_id)
    require_product_owner(user, p)
    if p.status == "SUSPENDED" and user.role != "ADMIN":
        raise HTTPException(409, "Suspended listings cannot be edited")
    data = body.model_dump(exclude_none=True)
    if "category_id" in data:
        get_or_404(db, Category, data["category_id"], "Category")
    for k, v in data.items():
        setattr(p, k, v)
    log(db, user, "product.edit", "product", p.id, ",".join(data))
    db.commit()
    return product_dict(p)


_ACTIONS = {
    "submit": ({"DRAFT", "REJECTED"}, "PENDING_REVIEW"),
    "pause": ({"ACTIVE"}, "PAUSED"),
    "activate": ({"PAUSED"}, "ACTIVE"),  # only listings admins already approved can be re-activated
}


@router.post("/products/{product_id}/{action}")
def product_action(product_id: int, action: str, user: User = Depends(require_approved_seller), db: Session = Depends(get_db)):
    if action not in _ACTIONS:
        raise HTTPException(404, "Unknown action")
    p = get_or_404(db, Product, product_id)
    require_product_owner(user, p)
    allowed_from, to = _ACTIONS[action]
    if p.status not in allowed_from:
        raise HTTPException(409, f"Cannot {action} a listing in state {p.status}")
    p.status = to
    log(db, user, f"product.{action}", "product", p.id)
    db.commit()
    return product_dict(p)


# ---------- inventory ----------
@router.get("/inventory")
def my_inventory(user: User = Depends(require_seller), db: Session = Depends(get_db)):
    sid = seller_profile(user).id
    rows = db.scalars(select(Product).where(Product.seller_id == sid).order_by(Product.id)).all()
    return [{"product_id": p.id, "name": p.name, "status": p.status, "quantity": p.inventory.quantity if p.inventory else 0} for p in rows]


@router.put("/inventory/{product_id}")
def set_inventory(product_id: int, body: schemas.InventoryUpdate, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, product_id)
    inv = db.scalar(select(Inventory).where(Inventory.product_id == p.id).with_for_update())
    require_inventory_access(user, inv, p)
    if user.role == "WAREHOUSE":
        deny("Warehouse staff record stock movements instead")
    delta = body.quantity - inv.quantity
    qty = adjust_stock(db, p.id, delta, "ADJUST", user) if delta else inv.quantity
    log(db, user, "inventory.set", "product", p.id, f"qty={qty}")
    db.commit()
    return {"product_id": p.id, "quantity": qty}


# ---------- orders / fulfilment ----------
@router.get("/orders")
def my_orders(user: User = Depends(require_seller), db: Session = Depends(get_db)):
    sid = seller_profile(user).id
    ids = select(OrderItem.order_id).where(OrderItem.seller_id == sid)
    orders = db.scalars(select(Order).where(Order.id.in_(ids), Order.status != "PENDING_PAYMENT").order_by(Order.id.desc())).all()
    return [order_dict(o, user) for o in orders]


@router.post("/shipments/{shipment_id}/status")
def update_shipment(shipment_id: int, body: schemas.ShipmentStatusIn, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    ship = get_or_404(db, Shipment, shipment_id, lock=True)
    order = get_or_404(db, Order, ship.order_id, lock=True)
    if user.role not in ("SELLER", "ADMIN"):
        deny("Use the warehouse endpoints for fulfilment")
    require_shipment_access(user, ship, order)
    advance_shipment(db, ship, order, body.status, body.tracking_number, body.carrier)
    log(db, user, f"shipment.{body.status.lower()}", "shipment", ship.id)
    db.commit()
    return shipment_dict(ship)


# ---------- analytics ----------
def sales_report(db: Session, seller_id: int) -> dict:
    rows = db.execute(
        select(OrderItem, Order.created_at, Order.status).join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.seller_id == seller_id, Order.status.notin_(["PENDING_PAYMENT", "CANCELLED"]),
               OrderItem.status != "CANCELLED")
    ).all()
    revenue = units = 0
    by_product, by_status, by_day, order_ids = defaultdict(lambda: [0, 0.0]), defaultdict(int), defaultdict(float), set()
    for it, created, _ in rows:
        if it.status in ("REFUNDED",):
            continue
        line = float(it.line_total)
        revenue += line
        units += it.quantity
        order_ids.add(it.order_id)
        by_product[it.product_name][0] += it.quantity
        by_product[it.product_name][1] += line
        by_status[it.status] += 1
        by_day[created.date().isoformat()] += line
    return {
        "seller_id": seller_id, "revenue": round(revenue, 2), "units_sold": units, "orders": len(order_ids),
        "top_products": sorted([{"name": k, "units": v[0], "revenue": round(v[1], 2)} for k, v in by_product.items()],
                               key=lambda x: -x["revenue"])[:10],
        "items_by_status": dict(by_status),
        "daily_revenue": [{"date": d, "revenue": round(v, 2)} for d, v in sorted(by_day.items())],
        "active_listings": db.scalar(select(func.count(Product.id)).where(Product.seller_id == seller_id, Product.status == "ACTIVE")),
        "low_stock": [{"product_id": p.id, "name": p.name, "quantity": p.inventory.quantity} for p in db.scalars(
            select(Product).where(Product.seller_id == seller_id)) if p.inventory and p.inventory.quantity <= 5],
    }


@router.get("/sales-report")
def my_sales_report(user: User = Depends(require_seller), db: Session = Depends(get_db)):
    return sales_report(db, seller_profile(user).id)


@router.get("/{seller_id}/sales-report")
def sales_report_for(seller_id: int, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    get_or_404(db, Seller, seller_id, "Seller")
    require_sales_report_access(user, seller_id)
    return sales_report(db, seller_id)
