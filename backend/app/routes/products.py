from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from ..auth import bearer, get_current_user
from ..database import get_db
from ..models import Category, Product, Review, User
from ..services import product_dict

router = APIRouter(prefix="/products", tags=["products"])
categories_router = APIRouter(prefix="/categories", tags=["categories"])


def optional_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if creds is None:
        return None
    try:
        return get_current_user(request, creds, db)
    except HTTPException:
        return None


@categories_router.get("")
def list_categories(db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name, "slug": c.slug} for c in db.scalars(select(Category).order_by(Category.name))]


@router.get("")
def list_products(
    q: str | None = None, category: str | None = Query(None, description="category slug"),
    min_price: float | None = Query(None, ge=0), max_price: float | None = Query(None, ge=0),
    sort: str = Query("relevance", pattern="^(relevance|price_asc|price_desc|rating|newest)$"),
    in_stock: bool = False, limit: int = Query(60, le=200), offset: int = 0, db: Session = Depends(get_db),
):
    stmt = select(Product).options(joinedload(Product.category), joinedload(Product.seller), joinedload(Product.inventory)).where(Product.status == "ACTIVE")
    if q:
        like = f"%{q.lower()}%"
        from sqlalchemy import func
        stmt = stmt.where(or_(func.lower(Product.name).like(like), func.lower(Product.brand).like(like), func.lower(Product.description).like(like)))
    if category:
        stmt = stmt.join(Category).where(Category.slug == category)
    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
    if in_stock:
        from ..models import Inventory
        stmt = stmt.join(Inventory, Inventory.product_id == Product.id).where(Inventory.quantity > 0)
    order = {"price_asc": Product.price.asc(), "price_desc": Product.price.desc(), "rating": Product.rating.desc(),
             "newest": Product.created_at.desc(), "relevance": Product.review_count.desc()}[sort]
    rows = db.scalars(stmt.order_by(order, Product.id).limit(limit).offset(offset)).unique().all()
    return [product_dict(p) for p in rows]


@router.get("/{product_id}")
def get_product(product_id: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None:
        raise HTTPException(404, "Product not found")
    if p.status != "ACTIVE":
        owner = user and (user.role == "ADMIN" or (user.seller and user.seller.id == p.seller_id))
        if not owner:
            raise HTTPException(404, "Product not found")
    return product_dict(p)


@router.get("/{product_id}/reviews")
def product_reviews(product_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(Review).where(Review.product_id == product_id, Review.status == "VISIBLE").order_by(Review.created_at.desc())).all()
    return [{"id": r.id, "rating": r.rating, "title": r.title, "body": r.body, "author": r.user.display_name,
             "user_id": r.user_id, "created_at": r.created_at.isoformat()} for r in rows]
