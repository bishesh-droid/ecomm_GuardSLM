from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import create_token, hash_password, verify_password
from ..database import get_db
from ..models import Address, Cart, Seller, SellerApplication, User, Wishlist
from ..permissions import deny, require_authenticated_user, require_customer
from ..services import get_or_404, log

router = APIRouter(prefix="/auth", tags=["auth"])


def user_dict(u: User) -> dict:
    d = {"id": u.id, "username": u.username, "display_name": u.display_name, "email": u.email, "phone": u.phone,
         "role": u.role, "is_active": u.is_active, "can_issue_refunds": u.can_issue_refunds}
    if u.seller:
        d["seller"] = {"id": u.seller.id, "store_name": u.seller.store_name, "status": u.seller.status}
    return d


@router.post("/login")
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        log(db, None, "auth.login_failed", "user", body.username[:40], decision="BLOCK")
        db.commit()
        raise HTTPException(401, "Invalid username or password")
    log(db, user, "auth.login", "user", user.id)
    db.commit()
    return {"access_token": create_token(user), "token_type": "bearer", "user": user_dict(user)}


@router.post("/register", status_code=201)
def register(body: schemas.RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where((User.username == body.username) | (User.email == body.email))):
        raise HTTPException(409, "Username or email already registered")
    user = User(username=body.username, display_name=body.display_name, email=body.email,
                password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.flush()
    if body.role == "CUSTOMER":
        db.add_all([Cart(user_id=user.id), Wishlist(user_id=user.id)])
    else:
        seller = Seller(user_id=user.id, store_name=body.store_name or body.display_name, status="PENDING")
        db.add(seller)
        db.flush()
        db.add(SellerApplication(seller_id=seller.id, message="Self-registration"))
    log(db, user, "auth.register", "user", user.id)
    db.commit()
    return {"user": user_dict(user), "access_token": create_token(user)}


@router.get("/me")
def me(user: User = Depends(require_authenticated_user)):
    return user_dict(user)


@router.patch("/me")
def update_me(body: schemas.ProfileUpdate, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user, k, v)
    log(db, user, "profile.update", "user", user.id)
    db.commit()
    return user_dict(user)


def addr_dict(a: Address) -> dict:
    return {c: getattr(a, c) for c in ("id", "label", "full_name", "line1", "city", "state", "postal_code", "country")}


@router.get("/addresses")
def list_addresses(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    return [addr_dict(a) for a in db.scalars(select(Address).where(Address.user_id == user.id).order_by(Address.id))]


@router.post("/addresses", status_code=201)
def add_address(body: schemas.AddressIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    a = Address(user_id=user.id, **body.model_dump())
    db.add(a)
    db.commit()
    return addr_dict(a)


@router.put("/addresses/{address_id}")
def update_address(address_id: int, body: schemas.AddressIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    a = get_or_404(db, Address, address_id)
    if a.user_id != user.id:
        deny("This address belongs to another customer")
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    return addr_dict(a)


@router.delete("/addresses/{address_id}", status_code=204)
def delete_address(address_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    a = get_or_404(db, Address, address_id)
    if a.user_id != user.id:
        deny("This address belongs to another customer")
    db.delete(a)
    db.commit()
