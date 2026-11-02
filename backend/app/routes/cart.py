from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Cart, CartItem, Product, Wishlist, WishlistItem, User
from ..permissions import require_customer
from ..services import get_or_404, money, product_dict

router = APIRouter(prefix="/cart", tags=["cart"])
wishlist_router = APIRouter(prefix="/wishlist", tags=["wishlist"])


def get_cart(db: Session, user: User) -> Cart:
    cart = db.scalar(select(Cart).where(Cart.user_id == user.id))
    if cart is None:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.flush()
    return cart


def cart_dict(cart: Cart) -> dict:
    items = [{"id": i.id, "quantity": i.quantity, "product": product_dict(i.product),
              "line_total": money(i.product.price * i.quantity)} for i in cart.items]
    return {"id": cart.id, "items": items, "total": money(sum(i["line_total"] for i in items)),
            "count": sum(i["quantity"] for i in items)}


@router.get("")
def view_cart(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    cart = get_cart(db, user)
    db.commit()
    return cart_dict(cart)


@router.post("/items", status_code=201)
def add_item(body: schemas.CartAdd, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, body.product_id, "Product")
    if p.status != "ACTIVE" or p.seller.status != "APPROVED":
        raise HTTPException(409, "Product is not available")
    cart = get_cart(db, user)
    existing = next((i for i in cart.items if i.product_id == p.id), None)
    qty = (existing.quantity if existing else 0) + body.quantity
    if qty > p.inventory.quantity:
        raise HTTPException(409, f"Only {p.inventory.quantity} in stock")
    if existing:
        existing.quantity = qty
    else:
        cart.items.append(CartItem(product_id=p.id, quantity=qty))
    db.commit()
    return cart_dict(cart)


@router.put("/items/{item_id}")
def set_quantity(item_id: int, body: schemas.CartUpdate, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    cart = get_cart(db, user)
    item = next((i for i in cart.items if i.id == item_id), None)
    if item is None:  # also covers other customers' items: never reveal them
        raise HTTPException(404, "Cart item not found")
    if body.quantity > item.product.inventory.quantity:
        raise HTTPException(409, f"Only {item.product.inventory.quantity} in stock")
    item.quantity = body.quantity
    db.commit()
    return cart_dict(cart)


@router.delete("/items/{item_id}")
def remove_item(item_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    cart = get_cart(db, user)
    item = next((i for i in cart.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(404, "Cart item not found")
    cart.items.remove(item)
    db.commit()
    return cart_dict(cart)


def get_wishlist(db: Session, user: User) -> Wishlist:
    w = db.scalar(select(Wishlist).where(Wishlist.user_id == user.id))
    if w is None:
        w = Wishlist(user_id=user.id)
        db.add(w)
        db.flush()
    return w


def wishlist_dict(w: Wishlist) -> list:
    return [{"id": i.id, "product": product_dict(i.product)} for i in w.items]


@wishlist_router.get("")
def view_wishlist(user: User = Depends(require_customer), db: Session = Depends(get_db)):
    w = get_wishlist(db, user)
    db.commit()
    return wishlist_dict(w)


@wishlist_router.post("/items/{product_id}", status_code=201)
def add_wish(product_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    p = get_or_404(db, Product, product_id, "Product")
    if p.status != "ACTIVE":
        raise HTTPException(409, "Product is not available")
    w = get_wishlist(db, user)
    if not any(i.product_id == p.id for i in w.items):
        w.items.append(WishlistItem(product_id=p.id))
    db.commit()
    return wishlist_dict(w)


@wishlist_router.delete("/items/{product_id}")
def remove_wish(product_id: int, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    w = get_wishlist(db, user)
    for i in list(w.items):
        if i.product_id == product_id:
            w.items.remove(i)
    db.commit()
    return wishlist_dict(w)
