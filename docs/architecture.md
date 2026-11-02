# Architecture

```
Browser (React + Vite, :5173)  --JWT bearer-->  FastAPI (:8000)  --SQLAlchemy-->  PostgreSQL (:5432)
                                                  |- routes/*      HTTP only, thin
                                                  |- permissions.py  every access decision
                                                  |- services.py     transactional business rules
                                                  '- models.py       schema + CHECK/UNIQUE constraints
```

* **Backend** `backend/app` - FastAPI, SQLAlchemy 2, Pydantic v2, PyJWT (HS256), bcrypt.
  Tables are created at startup (`create_all`) and the database is seeded once if empty (`seed.py`).
* **Frontend** `frontend/src` - React 18, React Router 6, plain CSS. The UI hides actions a role should not have, but
  it never relies on that: every call is authorized again by the backend and 403s render an `access-denied` panel.
* **Images** - generated at start-up as local SVG files under `backend/app/static/products/` and served from `/static/products/`.
  No external image or API dependency exists.

## Transaction design

| Flow | Technique |
|---|---|
| Checkout | One DB transaction: validate address ownership and cart -> for each product (sorted by id to avoid deadlocks) atomic `UPDATE ... WHERE quantity >= n` -> order, one shipment per seller, order items, payment -> clear cart. Any failure rolls everything back, including stock already reserved. |
| Overselling | Conditional UPDATE + `CHECK (quantity >= 0)`; losing concurrent checkouts get 409. Verified by `test_concurrent_checkout_never_oversells`. |
| Payment | `transition()` = `UPDATE payments SET status=:new WHERE id=:id AND status='PENDING'`; `rowcount == 0` -> 409. Parent order row is locked with `SELECT ... FOR UPDATE`. |
| Refund | Same compare-and-set `APPROVED -> COMPLETED`, payment row locked, `refunded_amount <= amount`. One active refund per item. |
| Cancel | Locks the order, releases stock, cancels shipments/items, settles a prepaid payment as refunded - single commit. |
| Return received | CAS `APPROVED -> RETURNED`, restock, auto-open refund request. |

## Order / shipment state model

```
PENDING_PAYMENT -> CONFIRMED -> PROCESSING -> PACKED -> SHIPPED -> DELIVERED
        \-> CANCELLED (until SHIPPED)           DELIVERED -> RETURN_REQUESTED -> RETURN_APPROVED -> RETURNED -> REFUND_PENDING -> REFUNDED
```

A multi-seller order has one `Shipment` per seller. The order status is the *least advanced* non-cancelled
shipment (e.g. one seller PACKED, another SHIPPED => order PACKED) until return/refund states take over.
Order items mirror their shipment status.

## Simulated payments

`POST /payments/{id}/pay {token}` is a deterministic sandbox gateway:

| Method | Success | Decline |
|---|---|---|
| CARD | `tok_sim_ok` | `tok_sim_fail` (anything else is "unrecognized token" -> FAILED) |
| UPI | `name@sim` | `name@fail` (other handles FAILED) |
| COD | confirmed at checkout; payment becomes SUCCEEDED when delivered | - |

Strings that look like card numbers (12+ digits) are rejected with 422 and never stored. Only `last4` of the token is kept.

## Data model

See `backend/app/models.py`. Core tables: `users, sellers, seller_applications, categories, products, inventory,
stock_movements, carts, cart_items, wishlists, wishlist_items, addresses, payment_methods (fake tokens), orders, order_items,
shipments, payments, refunds, returns, reviews, review_reports, support_tickets, activity_logs`.

Notable constraints: `inventory.quantity >= 0`, `products.price > 0`, `cart_items.quantity > 0`, `reviews.rating BETWEEN 1 AND 5`,
unique `(cart_id, product_id)`, unique `(product_id, user_id)` on reviews, `CHECK` on role / seller / product / order / payment status.

## Deterministic seed

`python -m app.seed --reset` (or `POST /admin/dev/reset` when `ENABLE_DEV_RESET=true`) rebuilds: 10 users (the 9 required plus
`seller4`, a PENDING seller for approval scenarios), 8 categories, 41 products (38 active, 1 draft, 1 pending-review,
1 intentionally fraudulent listing), 10 orders in assorted states, an open return, an open refund, a reported review and 2 tickets.
IDs are stable between resets; timestamps are relative to "now" so return/refund windows behave the same on every run.
