"""Centralized authorization. Every route delegates its access decision to this module.

Role guards are FastAPI dependencies; resource guards are plain functions called with the
loaded row, so the *ownership* check always runs against database state, never client input.
Every denial raises AuthzDenied, which main.py records in the activity log as BLOCK.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from . import config
from .auth import get_current_user
from .database import get_db
from .models import (
    Inventory, Order, OrderItem, Product, Refund, Review, Seller, Shipment, User,
)


class AuthzDenied(HTTPException):
    def __init__(self, detail: str = "Forbidden", decision: str = "BLOCK"):
        super().__init__(status_code=403 if decision == "BLOCK" else 409, detail={"decision": decision, "message": detail})


def deny(msg: str = "You are not allowed to perform this action") -> None:
    raise AuthzDenied(msg)


# ---------------- role guards ----------------
require_authenticated_user = get_current_user


def _role(*roles: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            deny(f"Requires role: {'/'.join(roles)}")
        return user
    return dep


require_admin = _role("ADMIN")
require_seller = _role("SELLER")
require_customer = _role("CUSTOMER")
require_warehouse = _role("WAREHOUSE")
require_support = _role("SUPPORT")
require_admin_or_support = _role("ADMIN", "SUPPORT")
require_staff = _role("ADMIN", "SUPPORT", "WAREHOUSE")


def seller_profile(user: User) -> Seller:
    if user.seller is None:
        deny("No seller profile")
    return user.seller


def require_approved_seller(user: User = Depends(require_seller)) -> User:
    if seller_profile(user).status != "APPROVED":
        deny("Seller account is not approved")
    return user


# ---------------- resource guards ----------------
def require_product_owner(user: User, product: Product) -> None:
    if user.role == "ADMIN":
        return
    if user.role == "SELLER" and user.seller and product.seller_id == user.seller.id:
        return
    deny("You do not own this product")


def require_order_owner(user: User, order: Order) -> None:
    if user.role != "CUSTOMER" or order.customer_id != user.id:
        deny("This order belongs to another customer")


def can_view_order(user: User, order: Order) -> None:
    """Read access. Customers: own; sellers: only if they have items; warehouse: assigned; support: authorized lookup; admin: all."""
    if user.role == "ADMIN" or user.role == "SUPPORT":
        return
    if user.role == "CUSTOMER" and order.customer_id == user.id:
        return
    if user.role == "SELLER" and user.seller and any(i.seller_id == user.seller.id for i in order.items):
        return
    if user.role == "WAREHOUSE" and order.assigned_warehouse_id == user.id:
        return
    deny("You cannot view this order")


def require_order_item_seller(user: User, item: OrderItem) -> None:
    if user.role == "ADMIN":
        return
    if user.role == "SELLER" and user.seller and item.seller_id == user.seller.id:
        return
    deny("This order item belongs to a different seller")


def require_shipment_access(user: User, shipment: Shipment, order: Order) -> None:
    if user.role == "ADMIN":
        return
    if user.role == "SELLER" and user.seller and shipment.seller_id == user.seller.id:
        return
    if user.role == "WAREHOUSE" and order.assigned_warehouse_id == user.id:
        return
    deny("You cannot update this shipment")


def require_inventory_access(user: User, inv: Inventory, product: Product) -> None:
    if user.role == "ADMIN":
        return
    if user.role == "SELLER" and user.seller and product.seller_id == user.seller.id:
        return
    if user.role == "WAREHOUSE" and inv.warehouse_id == user.id:
        return
    deny("You cannot manage this inventory")


def require_refund_permission(user: User, refund: Refund, item: OrderItem | None, action: str) -> None:
    """action: 'decide' (approve/reject) or 'complete' (money movement)."""
    if user.role == "ADMIN":
        return
    if user.role == "SELLER" and action == "decide":
        # limited seller workflow: only refunds on items the seller sold
        if item is not None and user.seller and item.seller_id == user.seller.id:
            return
        deny("Refund concerns another seller's product")
    if user.role == "SUPPORT" and user.can_issue_refunds:
        return
    deny("You do not have refund permission")


def require_review_owner(user: User, review: Review) -> None:
    if review.user_id != user.id:
        deny("You can only change your own reviews")


def require_sales_report_access(user: User, seller_id: int) -> None:
    if user.role == "ADMIN":
        return
    if user.role == "SELLER" and user.seller and user.seller.id == seller_id:
        return
    deny("Sales analytics are private to the owning seller")


def require_cancel_policy(order: Order) -> None:
    """Order-state rule for cancellation, with the configurable post-dispatch policy."""
    if order.status in ("PENDING_PAYMENT", "CONFIRMED", "PROCESSING", "PACKED"):
        return
    if order.status in ("SHIPPED",):
        raise AuthzDenied("Order already dispatched; cancel not allowed. Request a return after delivery.",
                          decision="ASK" if config.CANCEL_SHIPPED_POLICY == "ASK" else "BLOCK")
    raise HTTPException(409, f"Order in state {order.status} cannot be cancelled")
