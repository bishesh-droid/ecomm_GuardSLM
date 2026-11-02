from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Inventory, Order, Product, Shipment, StockMovement, User
from ..permissions import deny, require_inventory_access, require_shipment_access, require_warehouse
from ..services import adjust_stock, advance_shipment, get_or_404, log, shipment_dict

router = APIRouter(prefix="/warehouse", tags=["warehouse"])


def _row(s: Shipment) -> dict:
    o = s.order
    d = shipment_dict(s)
    d.update({"order_status": o.status, "shipping_name": o.shipping_name, "shipping_address": o.shipping_address,
              "items": [{"id": i.id, "product_name": i.product_name, "quantity": i.quantity, "status": i.status} for i in s.items],
              "seller_store": s.items[0].product.seller.store_name if s.items else None})
    return d


@router.get("/queue")
def queue(user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    """Only shipments of orders assigned to this operator that still need fulfilment work."""
    rows = db.scalars(
        select(Shipment).join(Order, Order.id == Shipment.order_id)
        .where(Order.assigned_warehouse_id == user.id, Shipment.status.in_(["CONFIRMED", "PROCESSING", "PACKED", "SHIPPED"]))
        .order_by(Shipment.id)
    ).all()
    return [_row(s) for s in rows]


@router.get("/orders")
def assigned_orders(user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    rows = db.scalars(select(Shipment).join(Order, Order.id == Shipment.order_id)
                      .where(Order.assigned_warehouse_id == user.id).order_by(Shipment.id.desc())).all()
    return [_row(s) for s in rows]


def _step(db: Session, user: User, shipment_id: int, target: str, tracking: str | None = None, carrier: str | None = None):
    ship = get_or_404(db, Shipment, shipment_id, lock=True)
    order = get_or_404(db, Order, ship.order_id, lock=True)
    require_shipment_access(user, ship, order)
    advance_shipment(db, ship, order, target, tracking, carrier)
    log(db, user, f"warehouse.{target.lower()}", "shipment", ship.id)
    db.commit()
    return _row(ship)


@router.post("/shipments/{shipment_id}/pick")
def pick(shipment_id: int, user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    return _step(db, user, shipment_id, "PROCESSING")


@router.post("/shipments/{shipment_id}/pack")
def pack(shipment_id: int, user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    return _step(db, user, shipment_id, "PACKED")


@router.post("/shipments/{shipment_id}/dispatch")
def dispatch(shipment_id: int, body: schemas.DispatchIn | None = None, user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    return _step(db, user, shipment_id, "SHIPPED", body.tracking_number if body else None, body.carrier if body else None)


@router.post("/shipments/{shipment_id}/deliver")
def deliver(shipment_id: int, user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    return _step(db, user, shipment_id, "DELIVERED")


@router.post("/shipments/{shipment_id}/tracking")
def tracking(shipment_id: int, body: schemas.TrackingIn, user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    ship = get_or_404(db, Shipment, shipment_id, lock=True)
    require_shipment_access(user, ship, ship.order)
    if ship.status not in ("SHIPPED",):
        raise HTTPException(409, "Tracking can only be updated for dispatched shipments")
    ship.tracking_status = body.tracking_status
    log(db, user, "warehouse.tracking", "shipment", ship.id, body.tracking_status)
    db.commit()
    return _row(ship)


@router.get("/stock")
def stock(user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    rows = db.scalars(select(Inventory).where(Inventory.warehouse_id == user.id).order_by(Inventory.product_id)).all()
    return [{"product_id": i.product_id, "name": i.product.name, "quantity": i.quantity} for i in rows]


@router.get("/stock-movements")
def movements(user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    pids = select(Inventory.product_id).where(Inventory.warehouse_id == user.id)
    rows = db.scalars(select(StockMovement).where(StockMovement.product_id.in_(pids)).order_by(StockMovement.id.desc()).limit(50)).all()
    return [{"id": m.id, "product_id": m.product_id, "delta": m.delta, "reason": m.reason, "reference": m.reference,
             "created_at": m.created_at.isoformat()} for m in rows]


@router.post("/stock-movements", status_code=201)
def record_movement(body: schemas.StockMovementIn, user: User = Depends(require_warehouse), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, body.product_id)
    inv = db.scalar(select(Inventory).where(Inventory.product_id == p.id))
    require_inventory_access(user, inv, p)
    if body.delta == 0:
        raise HTTPException(422, "delta must be non-zero")
    if body.reason == "RECEIVE" and body.delta < 0 or body.reason == "DAMAGE" and body.delta > 0:
        raise HTTPException(422, "delta sign does not match reason")
    qty = adjust_stock(db, p.id, body.delta, body.reason, user)
    log(db, user, "warehouse.stock_movement", "product", p.id, f"{body.reason} {body.delta}")
    db.commit()
    return {"product_id": p.id, "quantity": qty}
