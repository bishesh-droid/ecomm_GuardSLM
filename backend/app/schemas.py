from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=160)
    role: Literal["CUSTOMER", "SELLER"] = "CUSTOMER"
    store_name: str | None = None


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=160)


class AddressIn(BaseModel):
    label: str = "Home"
    full_name: str = Field(min_length=1, max_length=120)
    line1: str = Field(min_length=1, max_length=200)
    city: str
    state: str
    postal_code: str = Field(min_length=3, max_length=16)
    country: str = "India"


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    brand: str = ""
    description: str = ""
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    category_id: int
    stock: int = Field(default=0, ge=0)
    submit_for_review: bool = False


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    brand: str | None = None
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    category_id: int | None = None


class InventoryUpdate(BaseModel):
    quantity: int = Field(ge=0)


class StockMovementIn(BaseModel):
    product_id: int
    delta: int
    reason: Literal["RECEIVE", "ADJUST", "DAMAGE"] = "RECEIVE"


class CartAdd(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=20)


class CartUpdate(BaseModel):
    quantity: int = Field(ge=1, le=20)


class CheckoutIn(BaseModel):
    address_id: int
    payment_method: Literal["CARD", "UPI", "COD"]


class PayIn(BaseModel):
    """Simulated gateway token. tok_sim_ok / any upi ending @sim succeed; tok_sim_fail / @fail fail.
    Never send real card numbers, CVV or UPI PINs."""
    token: str = Field(default="tok_sim_ok", max_length=64)


class PaymentCreateIn(BaseModel):
    order_id: int
    method: Literal["CARD", "UPI", "COD"] | None = None


class RefundIn(BaseModel):
    order_item_id: int
    reason: str = Field(min_length=3, max_length=500)


class DecisionIn(BaseModel):
    note: str = Field(default="", max_length=500)


class ReturnIn(BaseModel):
    order_item_id: int
    reason: str = Field(min_length=3, max_length=500)


class ReturnDecisionIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)


class ReturnOverrideIn(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    note: str = Field(min_length=3, max_length=500)


class ReviewIn(BaseModel):
    product_id: int
    rating: int = Field(ge=1, le=5)
    title: str = Field(default="", max_length=120)
    body: str = Field(default="", max_length=2000)


class ReviewUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    title: str | None = Field(default=None, max_length=120)
    body: str | None = Field(default=None, max_length=2000)


class ReportIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=3, max_length=2000)
    order_id: int | None = None


class TicketUpdate(BaseModel):
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"] | None = None
    response: str | None = Field(default=None, max_length=2000)


class ShipmentStatusIn(BaseModel):
    status: Literal["PROCESSING", "PACKED", "SHIPPED", "DELIVERED"]
    tracking_number: str | None = Field(default=None, max_length=64)
    carrier: str | None = Field(default=None, max_length=64)


class TrackingIn(BaseModel):
    tracking_status: str = Field(min_length=2, max_length=200)


class UserAdminUpdate(BaseModel):
    is_active: bool | None = None
    can_issue_refunds: bool | None = None


class SellerDecisionIn(BaseModel):
    note: str = Field(default="", max_length=500)


class ModerationIn(BaseModel):
    note: str = Field(default="", max_length=500)


class DispatchIn(BaseModel):
    tracking_number: str | None = Field(default=None, max_length=64)
    carrier: str | None = Field(default=None, max_length=64)
