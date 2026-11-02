from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Order, SupportTicket, User
from ..permissions import (
    deny, require_admin_or_support, require_authenticated_user, require_customer, require_support,
)
from ..services import get_or_404, log, order_dict

router = APIRouter(prefix="/support", tags=["support"])


def ticket_dict(t: SupportTicket) -> dict:
    return {"id": t.id, "customer_id": t.customer_id, "customer_name": t.customer.display_name, "order_id": t.order_id,
            "subject": t.subject, "message": t.message, "status": t.status, "response": t.response,
            "created_at": t.created_at.isoformat(), "updated_at": t.updated_at.isoformat()}


@router.get("/orders")
def lookup_orders(q: str | None = None, user: User = Depends(require_admin_or_support), db: Session = Depends(get_db)):
    """Authorized lookup: by order id or customer name. Payment tokens/credentials are never in the projection."""
    stmt = select(Order).join(User, User.id == Order.customer_id).order_by(Order.id.desc()).limit(50)
    if q:
        conds = [User.display_name.ilike(f"%{q}%")]
        if q.strip().isdigit():
            conds.append(Order.id == int(q))
        stmt = stmt.where(or_(*conds))
    log(db, user, "support.order_lookup", "order", None, q)
    db.commit()
    return [order_dict(o, user) for o in db.scalars(stmt).all()]


@router.get("/orders/{order_id}")
def support_order(order_id: int, user: User = Depends(require_admin_or_support), db: Session = Depends(get_db)):
    o = get_or_404(db, Order, order_id)
    log(db, user, "support.order_view", "order", order_id)
    db.commit()
    return order_dict(o, user)


@router.get("/customers/{customer_id}/payment-credentials")
def payment_credentials(customer_id: int, user: User = Depends(require_support)):
    deny("Payment credentials are never exposed to support staff")


@router.post("/tickets", status_code=201)
def create_ticket(body: schemas.TicketIn, user: User = Depends(require_customer), db: Session = Depends(get_db)):
    if body.order_id is not None:
        o = get_or_404(db, Order, body.order_id)
        if o.customer_id != user.id:
            deny("This order belongs to another customer")
    t = SupportTicket(customer_id=user.id, order_id=body.order_id, subject=body.subject, message=body.message)
    db.add(t)
    log(db, user, "ticket.create", "ticket", None)
    db.commit()
    return ticket_dict(t)


@router.get("/tickets")
def list_tickets(status: str | None = None, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    stmt = select(SupportTicket).order_by(SupportTicket.id.desc())
    if user.role == "CUSTOMER":
        stmt = stmt.where(SupportTicket.customer_id == user.id)
    elif user.role not in ("SUPPORT", "ADMIN"):
        deny("Tickets are restricted")
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    return [ticket_dict(t) for t in db.scalars(stmt).all()]


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: int, body: schemas.TicketUpdate, user: User = Depends(require_admin_or_support), db: Session = Depends(get_db)):
    t = get_or_404(db, SupportTicket, ticket_id)
    if body.response is not None:
        t.response = body.response
    if body.status:
        t.status = body.status
    elif body.response:
        t.status = "IN_PROGRESS"
    t.assigned_to = user.id
    log(db, user, "ticket.update", "ticket", t.id, body.status)
    db.commit()
    return ticket_dict(t)
