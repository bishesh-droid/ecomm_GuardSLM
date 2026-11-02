from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, schemas
from ..database import get_db
from ..models import Order, OrderItem, Product, Refund, Seller, SellerApplication, User, utcnow
from ..permissions import require_admin
from ..services import get_or_404, log, money, order_dict, product_dict, transition
from .auth import user_dict

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def users(role: str | None = None, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.id)
    if role:
        stmt = stmt.where(User.role == role)
    return [user_dict(u) | {"created_at": u.created_at.isoformat()} for u in db.scalars(stmt)]


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: schemas.UserAdminUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = get_or_404(db, User, user_id)
    if u.id == admin.id and body.is_active is False:
        raise HTTPException(409, "You cannot deactivate your own account")
    if body.can_issue_refunds is not None and u.role != "SUPPORT":
        raise HTTPException(422, "Refund permission applies to support agents only")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(u, k, v)
    log(db, admin, "admin.user_update", "user", u.id, str(body.model_dump(exclude_none=True)))
    db.commit()
    return user_dict(u)


# ---------- seller onboarding ----------
def seller_dict(s: Seller, db: Session) -> dict:
    app = db.scalar(select(SellerApplication).where(SellerApplication.seller_id == s.id).order_by(SellerApplication.id.desc()))
    return {"id": s.id, "store_name": s.store_name, "status": s.status, "username": s.user.username,
            "display_name": s.user.display_name, "created_at": s.created_at.isoformat(),
            "application_message": app.message if app else None, "review_note": app.review_note if app else None}


@router.get("/sellers")
def sellers(status: str | None = None, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(Seller).order_by(Seller.id)
    if status:
        stmt = stmt.where(Seller.status == status)
    return [seller_dict(s, db) for s in db.scalars(stmt)]


def _decide_seller(db, admin, seller_id, to, body):
    s = get_or_404(db, Seller, seller_id, "Seller")
    if s.user_id == admin.id:
        raise HTTPException(409, "Cannot decide your own application")
    if not transition(db, Seller, s.id, ["PENDING", "REJECTED"] if to == "APPROVED" else ["PENDING", "APPROVED"], to,
                      **({"approved_at": utcnow()} if to == "APPROVED" else {})):
        raise HTTPException(409, f"Seller cannot move from {s.status} to {to}")
    db.refresh(s)
    app = db.scalar(select(SellerApplication).where(SellerApplication.seller_id == s.id).order_by(SellerApplication.id.desc()))
    if app:
        app.status, app.reviewed_by, app.review_note, app.reviewed_at = to, admin.id, body.note, utcnow()
    log(db, admin, f"admin.seller_{to.lower()}", "seller", s.id, body.note)
    db.commit()
    return seller_dict(s, db)


@router.post("/sellers/{seller_id}/approve")
def approve_seller(seller_id: int, body: schemas.SellerDecisionIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _decide_seller(db, admin, seller_id, "APPROVED", body)


@router.post("/sellers/{seller_id}/reject")
def reject_seller(seller_id: int, body: schemas.SellerDecisionIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _decide_seller(db, admin, seller_id, "REJECTED", body)


# ---------- product moderation ----------
@router.get("/products")
def all_products(status: str | None = None, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(Product).order_by(Product.id)
    if status:
        stmt = stmt.where(Product.status == status)
    return [product_dict(p) for p in db.scalars(stmt)]


_MOD = {
    "approve": ({"PENDING_REVIEW"}, "ACTIVE"),
    "reject": ({"PENDING_REVIEW"}, "REJECTED"),
    "suspend": ({"ACTIVE", "PAUSED", "PENDING_REVIEW"}, "SUSPENDED"),
    "unsuspend": ({"SUSPENDED"}, "ACTIVE"),
}


@router.post("/products/{product_id}/{action}")
def moderate_product(product_id: int, action: str, body: schemas.ModerationIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if action not in _MOD:
        raise HTTPException(404, "Unknown moderation action")
    p = get_or_404(db, Product, product_id)
    allowed, to = _MOD[action]
    if not transition(db, Product, p.id, list(allowed), to):
        raise HTTPException(409, f"Cannot {action} a listing in state {p.status}")
    db.refresh(p)
    log(db, admin, f"admin.product_{action}", "product", p.id, body.note)
    db.commit()
    return product_dict(p)


@router.get("/orders")
def all_orders(status: str | None = None, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(Order).order_by(Order.id.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    return [order_dict(o, admin) for o in db.scalars(stmt)]


@router.get("/analytics")
def analytics(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    paid = select(Order).where(Order.status.notin_(["PENDING_PAYMENT", "CANCELLED"]))
    orders = db.scalars(paid).all()
    by_status = dict(db.execute(select(Order.status, func.count(Order.id)).group_by(Order.status)).all())
    by_role = dict(db.execute(select(User.role, func.count(User.id)).group_by(User.role)).all())
    top = defaultdict(float)
    for it in db.scalars(select(OrderItem).join(Order).where(Order.status.notin_(["PENDING_PAYMENT", "CANCELLED"]))):
        top[it.seller_id] += float(it.line_total)
    names = {s.id: s.store_name for s in db.scalars(select(Seller))}
    return {
        "gmv": money(sum(o.total for o in orders)), "order_count": len(orders), "orders_by_status": by_status,
        "users_by_role": by_role,
        "pending_sellers": db.scalar(select(func.count(Seller.id)).where(Seller.status == "PENDING")),
        "pending_products": db.scalar(select(func.count(Product.id)).where(Product.status == "PENDING_REVIEW")),
        "pending_refunds": db.scalar(select(func.count(Refund.id)).where(Refund.status == "REQUESTED")),
        "refunded_total": money(db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.status == "COMPLETED"))),
        "top_sellers": sorted([{"seller": names[k], "revenue": round(v, 2)} for k, v in top.items()], key=lambda x: -x["revenue"]),
    }


@router.post("/dev/reset")
def dev_reset(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Re-seeds the database to its deterministic baseline. Disabled unless ENABLE_DEV_RESET=true."""
    if not config.ENABLE_DEV_RESET:
        raise HTTPException(404, "Not found")
    from ..seed import reset_and_seed
    db.rollback()  # release this request's open transaction, otherwise DROP TABLE waits on it forever
    db.close()
    reset_and_seed()
    return {"reset": True}
