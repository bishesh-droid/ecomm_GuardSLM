# Playwright guide

## Setup

```bash
docker compose up --build -d          # from the project root; wait until all services are healthy
cd tests/playwright
npm install
npx playwright install chromium
npx playwright test                   # all specs
npx playwright test smoke.spec.js     # smoke only
```

`BASE_URL` (default `http://localhost:5173`) and `API_URL` (default `http://localhost:8000`) can be overridden.
Specs run with a single worker; each test calls `POST /admin/dev/reset` first (needs `ENABLE_DEV_RESET=true`, the default
in `.env.example`) so every test starts from the same seed.

## Conventions an agent can rely on

* **Stable URLs** - `/products?q=&category=&min_price=&max_price=&sort=`, `/products/:id`, `/cart`, `/checkout`, `/orders`,
  `/orders/:id`, `/wishlist`, `/profile`, `/help`, `/seller[/products|/inventory|/orders|/returns|/reports/:sellerId]`,
  `/seller/products/new`, `/seller/products/:id/edit`, `/warehouse`, `/support[/orders|/refunds|/returns]`,
  `/admin[/users|/sellers|/products|/orders|/refunds|/reviews|/audit-logs]`.
* **Test IDs** - every actionable control has `data-testid`. Patterns: `product-card-{id}`, `add-to-cart-{id}`, `cart-item-{itemId}`,
  `cart-qty-{itemId}`, `cart-remove-{itemId}`, `payment-method-{CARD|UPI|COD}`, `payment-token`, `place-order`, `order-link-{id}`,
  `order-status[-{id}]`, `cancel-order-{id}`, `refund-item-{itemId}`, `return-item-{itemId}`, `wh-{pick|pack|dispatch|deliver}-{shipmentId}`,
  `product-{approve|reject|suspend|unsuspend}-{id}`, `seller-{approve|reject}-{id}`, `refund-{approve|reject|complete}-{id}`,
  `return-override-{approve|reject}-{id}`, `review-{hide|restore|delete}-{id}`.
* **Labels** - every form field has a `<label for>`; use `getByLabel(...)` as an alternative to test ids.
* **Feedback** - success: `flash-ok`; error/denied: `flash-error` (text starts with `BLOCK:` or `ASK:` for authorization decisions).
* **Denied pages** - navigating to a resource you may not see renders `access-denied` with `decision-badge` = `BLOCK`.
* **Roles** - `current-user`, `current-role` in the header expose who is signed in.

## Spec files

| File | Contents |
|---|---|
| `smoke.spec.js` | Home, search, category + price filters (URL driven), login for every role, bad credentials, anonymous redirect |
| `customer-flow.spec.js` | Cart edits, card checkout, payment failure + retry, COD, wishlist, address, review, ticket |
| `authorization.spec.js` | The 16 research scenarios (ALLOW and BLOCK) + audit-log check |
| `workflows.spec.js` | Seller product lifecycle, inventory, fulfilment, return -> refund, support refund permission, moderation, admin pages |

## Sandbox payment inputs

`tok_sim_ok` succeeds, `tok_sim_fail` declines, `name@sim` / `name@fail` for UPI. Real card numbers are rejected.
