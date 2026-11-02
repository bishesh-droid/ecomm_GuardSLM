from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Order, OrderItem, Product, Review, ReviewReport, User
from ..permissions import (
    deny, require_admin_or_support, require_authenticated_user, require_customer, require_review_owner,
)
from ..services import get_or_404, log, recompute_rating

router = APIRouter(prefix="/reviews", tags=["reviews"])


def review_dict(r: Review, with_reports: bool = False) -> dict:
    d = {"id": r.id, "product_id": r.product_id, "product_name": r.product.name, "rating": r.rating, "title": r.title,
         "body": r.body, "status": r.status, "author": r.user.display_name, "user_id": r.user_id,
         "created_at": r.created_at.isoformat()}
    if with_reports:
        d["report_count"] = len(r.reports)
        d["report_reasons"] = [x.reason for x in r.reports]
    return d


def has_qualifying_purchase(db: Session, user: User, product_id: int) -> bool:
    return db.scalar(
        select(func.count(OrderItem.id)).join(Order, Order.id == OrderItem.order_id).where(
            Order.customer_id == user.id, OrderItem.product_id == product_id,
            OrderItem.status.in_(["DELIVERED", "RETURN_REQUESTED", "RETURN_APPROVED", "RETURNED", "REFUNDED"]))
    ) > 0


@router.get("/mine")
def my_reviews(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return [review_dict(r) for r in db.scalars(select(Review).where(Review.user_id == user.id).order_by(Review.id.desc()))]


@router.get("/moderation")
def moderation_queue(user: User = Depends(require_admin_or_support), db: Session = Depends(get_db)):
    rows = db.scalars(select(Review).order_by(Review.id.desc())).all()
    rows.sort(key=lambda r: (-len(r.reports), -r.id))
    return [review_dict(r, True) for r in rows]


@router.post("", status_code=201)
def create_review(body: schemas.ReviewIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    product = get_or_404(db, Product, body.product_id, "Product")
    if not has_qualifying_purchase(db, user, product.id):
        deny("Only customers with a delivered purchase can review this product")
    if db.scalar(select(func.count(Review.id)).where(Review.product_id == product.id, Review.user_id == user.id)):
        raise HTTPException(409, "You have already reviewed this product")
    r = Review(product_id=product.id, user_id=user.id, rating=body.rating, title=body.title, body=body.body)
    db.add(r)
    db.flush()
    recompute_rating(db, product)
    log(db, user, "review.create", "review", r.id)
    db.commit()
    return review_dict(r)


@router.patch("/{review_id}")
def edit_review(review_id: int, body: schemas.ReviewUpdate, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    r = get_or_404(db, Review, review_id)
    require_review_owner(user, r)
    if r.status == "HIDDEN":
        raise HTTPException(409, "Moderated reviews cannot be edited")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    db.flush()
    recompute_rating(db, r.product)
    log(db, user, "review.edit", "review", r.id)
    db.commit()
    return review_dict(r)


@router.delete("/{review_id}", status_code=204)
def delete_review(review_id: int, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    r = get_or_404(db, Review, review_id)
    if user.role != "ADMIN":
        require_review_owner(user, r)
        if r.status == "HIDDEN":
            raise HTTPException(409, "Moderated reviews cannot be deleted by the author")
    product = r.product
    db.delete(r)
    db.flush()
    recompute_rating(db, product)
    log(db, user, "review.delete", "review", review_id)
    db.commit()


@router.post("/{review_id}/report", status_code=201)
def report_review(review_id: int, body: schemas.ReportIn, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    r = get_or_404(db, Review, review_id)
    if r.user_id == user.id:
        raise HTTPException(409, "You cannot report your own review")
    if db.scalar(select(func.count(ReviewReport.id)).where(ReviewReport.review_id == r.id, ReviewReport.reporter_id == user.id)):
        raise HTTPException(409, "You already reported this review")
    db.add(ReviewReport(review_id=r.id, reporter_id=user.id, reason=body.reason))
    log(db, user, "review.report", "review", r.id, body.reason)
    db.commit()
    return {"reported": True}


@router.post("/{review_id}/hide")
def hide_review(review_id: int, user: User = Depends(require_admin_or_support), db: Session = Depends(get_db)):
    r = get_or_404(db, Review, review_id)
    r.status = "HIDDEN"
    db.flush()
    recompute_rating(db, r.product)
    log(db, user, "review.hide", "review", r.id)
    db.commit()
    return review_dict(r, True)


@router.post("/{review_id}/restore")
def restore_review(review_id: int, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN":
        deny("Only administrators can restore moderated reviews")
    r = get_or_404(db, Review, review_id)
    r.status = "VISIBLE"
    db.flush()
    recompute_rating(db, r.product)
    log(db, user, "review.restore", "review", r.id)
    db.commit()
    return review_dict(r, True)
