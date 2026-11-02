# Authorization matrix

All decisions live in `backend/app/permissions.py`. Role guards are FastAPI dependencies; resource guards are
functions called with the **database row**, so ownership is never taken from client input. Every non-ALLOW
decision raises `AuthzDenied` and is written to `activity_logs` (visible at `GET /audit-logs`, admin only).

Denial payload: HTTP `403` `{"detail": {"decision": "BLOCK", "message": "..."}}`.
With `CANCEL_SHIPPED_POLICY=ASK` a post-dispatch cancel returns HTTP `409` with `decision: "ASK"` instead.

## Role x operation

| Operation | Admin | Seller | Customer | Warehouse | Support | Guard / endpoint |
|---|---|---|---|---|---|---|
| Browse active products | Allow | Allow | Allow | Allow | Allow | `GET /products` (public) |
| Manage own products | Allow | Own only | Block | Block | Block | `require_product_owner` - `PUT /seller/products/{id}` |
| Manage other seller's products | Allow | Block | Block | Block | Block | `require_product_owner` |
| View own orders | Allow | Own items | Own only | Assigned fulfilment | Authorized lookup | `can_view_order`, `order_dict` role projection |
| View all orders | Allow | Block | Block | Block | Limited (no unpaid, 100 max, no full address) | `GET /admin/orders`, `GET /support/orders` |
| Update fulfilment | Allow | Own items | Block | Assigned orders | Block | `require_shipment_access` |
| Edit cart | Block | Block | Own only | Block | Block | `require_customer` + cart looked up from the JWT user |
| Request return | Allow | Block | Own order | Block | Block | `require_order_owner` (admin bypass) |
| Approve refunds | Allow | Limited seller workflow | Block | Block | Explicit permission only | `require_refund_permission` |
| Manage inventory | Allow | Own products | Block | Assigned warehouse stock | Block | `require_inventory_access` |
| Moderate products | Allow | Block | Block | Block | Block | `require_admin` - `/admin/products/{id}/{action}` |
| Approve sellers | Allow | Block | Block | Block | Block | `require_admin` - `/admin/sellers/{id}/approve` |
| Moderate reviews | Allow | Block | Block | Block | Limited (hide only) | `/reviews/{id}/hide`, `/restore` (admin only) |
| Manage users | Allow | Block | Block | Block | Block | `require_admin` - `/admin/users` |

### Interpretation of the "limited" cells

* **Seller refunds** - a seller may *approve or reject* a refund only when the refunded order item is theirs. They can never
  *complete* a refund (money movement) or touch payment records.
* **Support refunds** - allowed only when `users.can_issue_refunds = true`, granted by an admin (`PATCH /admin/users/{id}`).
  `support1` is seeded **without** it.
* **Support orders** - lookup by order id or customer name; projection omits street address and always omits payment tokens.
  `GET /support/customers/{id}/payment-credentials` always returns `BLOCK` (no role may read complete credentials; none are stored).
* **Support reviews** - may hide a review; only admins may restore or delete.
* **Warehouse** - sees only orders where `assigned_warehouse_id` is theirs; shipping name/address are shown (needed to ship) but never
  email, phone, payment data or customer profile.

## Role guards and resource guards

| Name | Kind | Behaviour |
|---|---|---|
| `require_authenticated_user` | dependency | Valid JWT, user exists and `is_active` |
| `require_admin` / `require_seller` / `require_customer` / `require_warehouse` / `require_support` | dependency | Role must match |
| `require_approved_seller` | dependency | Seller role *and* `sellers.status = APPROVED` |
| `require_product_owner(user, product)` | function | Admin, or seller whose `seller_id` owns it |
| `require_order_owner(user, order)` | function | Customer whose id equals `order.customer_id` |
| `can_view_order(user, order)` | function | Read rules per role (table above) |
| `require_order_item_seller(user, item)` | function | Admin, or the seller on that line item |
| `require_shipment_access(user, shipment, order)` | function | Admin, owning seller, or assigned warehouse operator |
| `require_inventory_access(user, inv, product)` | function | Admin, owning seller, or the warehouse the stock is assigned to |
| `require_refund_permission(user, refund, item, action)` | function | See interpretation above |
| `require_review_owner(user, review)` | function | Only the author edits/deletes (sellers cannot edit reviews) |
| `require_sales_report_access(user, seller_id)` | function | Admin or the same seller |
| `require_cancel_policy(order)` | function | Order-state rule + `BLOCK`/`ASK` policy after dispatch |

## Additional state and transaction checks (beyond role/ownership)

| Area | Rule |
|---|---|
| Order cancel | Only `PENDING_PAYMENT, CONFIRMED, PROCESSING, PACKED`; `SHIPPED` -> BLOCK/ASK; others 409 |
| Fulfilment | Strictly forward one step: `CONFIRMED -> PROCESSING -> PACKED -> SHIPPED -> DELIVERED` |
| Payment | Compare-and-set `PENDING -> SUCCEEDED/FAILED`; terminal afterwards; duplicates return 409; customers cannot confirm |
| Return | Item `DELIVERED`, within `RETURN_WINDOW_DAYS` (14), no active refund |
| Refund | Item `DELIVERED`, within `REFUND_WINDOW_DAYS` (30), one active refund per item, `APPROVED -> COMPLETED` CAS, cannot exceed paid amount |
| Reviews | Qualifying delivered purchase, one review per product, hidden reviews cannot be edited by the author |
| Products | `DRAFT -> PENDING_REVIEW -> ACTIVE/REJECTED`, `SUSPENDED` by admin only; sellers may only `pause`/`activate` approved listings |
| Sellers | `PENDING -> APPROVED/REJECTED` by an admin who is not the applicant; pending sellers cannot create listings |
| Stock | `UPDATE inventory SET quantity = quantity - :n WHERE quantity >= :n`; DB `CHECK (quantity >= 0)` |

## Research scenarios -> verification

| # | Scenario | Expected | Backend test | Playwright |
|---|---|---|---|---|
| 1 | customer1 views own order | ALLOW | `test_01_*` | `01 ALLOW` |
| 2 | customer1 views customer2's order | BLOCK | `test_02_*` | `02 BLOCK` |
| 3 | seller1 edits own product | ALLOW | `test_03_*` | `03 ALLOW` |
| 4 | seller1 edits seller2's product | BLOCK | `test_04_*` | `04 BLOCK` |
| 5 | seller1 views own sales report | ALLOW | `test_05_*` | `05 ALLOW` |
| 6 | seller1 views seller2's sales report | BLOCK | `test_06_*` | `06 BLOCK` |
| 7 | cancel eligible unshipped order | ALLOW | `test_07_*` | `07 ALLOW` |
| 8 | cancel dispatched order | BLOCK (or ASK) | `test_08_*`, `test_08b_*` | `08 BLOCK` |
| 9 | refund own eligible purchase | ALLOW | `test_09_*` | `09 ALLOW` |
| 10 | refund someone else's purchase | BLOCK | `test_10_*` | `10 BLOCK` |
| 11 | warehouse updates assigned shipment | ALLOW | `test_11_*` | `11 ALLOW` |
| 12 | warehouse changes product price | BLOCK | `test_12_*` | `12 BLOCK` |
| 13 | support views permitted order info | ALLOW | `test_13_*` | `13 ALLOW` |
| 14 | support reads full payment credentials | BLOCK | `test_14_*` | `14 BLOCK` |
| 15 | admin suspends fraudulent listing | ALLOW | `test_15_*` | `15 ALLOW` |
| 16 | seller approves own registration | BLOCK | `test_16_*` | `16 BLOCK` |
