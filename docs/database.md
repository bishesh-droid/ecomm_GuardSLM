# Database reference

PostgreSQL 16 (SQLite is used only by the pytest suite). Schema = `backend/app/models.py`; created by `Base.metadata.create_all` at start-up.

| Table | Purpose | Key constraints |
|---|---|---|
| users | accounts for all roles; `can_issue_refunds` for support | unique username/email; role CHECK |
| sellers | store profile + onboarding status | 1:1 with user; status CHECK |
| seller_applications | onboarding audit trail | FK seller, reviewer |
| categories | 8 categories | unique name/slug |
| products | listings owned by one seller | price > 0; status CHECK; FK seller, category |
| inventory | on-hand quantity per product, assigned warehouse | unique product; quantity >= 0 |
| stock_movements | ledger of every quantity change (RESERVE/RELEASE/RECEIVE/ADJUST/DAMAGE/RETURN) | FK product, actor |
| carts / cart_items | one cart per customer | unique (cart, product); quantity > 0 |
| wishlists / wishlist_items | one wishlist per customer | unique (wishlist, product) |
| addresses | customer addresses | FK user |
| payment_methods | fake saved sandbox tokens (never real data) | FK user |
| orders | order header, address snapshot, assigned warehouse | status CHECK |
| order_items | line items snapshotting name/price, tied to a seller and shipment | quantity > 0 |
| shipments | one per seller per order: status, carrier, tracking | FK order, seller |
| payments | one or more attempts per order; status, refunded_amount | status CHECK |
| refunds | per order item; REQUESTED/APPROVED/REJECTED/COMPLETED | FK order, item, payment |
| returns | per order item; REQUESTED/APPROVED/REJECTED/RETURNED, seller + support + admin override fields | FK order, item |
| reviews / review_reports | one review per user per product; reports by other users | rating 1..5; unique (product, user) |
| support_tickets | customer queries | FK customer, order |
| activity_logs | audit trail incl. BLOCK/ASK decisions | indexed by actor, action, time |

Inspect with: `docker compose exec db psql -U guardslm -d guardslm -c '\dt'`.
