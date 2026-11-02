// The 16 research scenarios, driven through the real UI where one exists and through the API otherwise.
import { test, expect } from "@playwright/test";
import { apiAs, expectDenied, login, resetDb } from "./helpers.js";

test.beforeEach(async ({ request }) => resetDb(request));

// Seed facts (deterministic): order 1 customer1 DELIVERED; order 2 customer2 DELIVERED (old); order 3 customer1 CONFIRMED;
// order 4 customer2 SHIPPED; products 1..12 seller1, 13..27 seller2, 28..38 seller3; product 38 = suspicious listing.

test("01 ALLOW customer1 views own order", async ({ page }) => {
  await login(page, "customer1");
  await page.goto("/orders");
  await page.getByTestId("order-link-1").click();
  await expect(page).toHaveURL(/\/orders\/1$/);
  await expect(page.getByTestId("order-status")).toHaveText("DELIVERED");
});

test("02 BLOCK customer1 views customer2's order", async ({ page }) => {
  await login(page, "customer1");
  await page.goto("/orders/2");
  await expectDenied(page);
});

test("03 ALLOW seller1 edits own product", async ({ page }) => {
  await login(page, "seller1");
  await page.goto("/seller/products/1/edit");
  await page.getByTestId("pf-price").fill("23999");
  await page.getByTestId("pf-save").click();
  await expect(page.getByTestId("flash-ok")).toContainText("Product updated");
});

test("04 BLOCK seller1 edits seller2's product", async ({ page, request }) => {
  await login(page, "seller1");
  await page.goto("/seller/products/13/edit");
  await expectDenied(page);
  expect((await apiAs(request, "seller1", "PUT", "/seller/products/13", { price: "1.00" })).status()).toBe(403);
  expect((await apiAs(request, "seller1", "PUT", "/seller/inventory/13", { quantity: 999 })).status()).toBe(403);
});

test("05 ALLOW seller1 views own sales report", async ({ page }) => {
  await login(page, "seller1");
  await expect(page.getByTestId("stat-revenue")).toBeVisible();
  await page.getByTestId("own-report-link").click();
  await expect(page).toHaveURL(/\/seller\/reports\/1$/);
  await expect(page.getByTestId("stat-revenue")).toBeVisible();
});

test("06 BLOCK seller1 views another seller's sales report", async ({ page }) => {
  await login(page, "seller1");
  await page.goto("/seller/reports/2");
  await expectDenied(page);
});

test("07 ALLOW customer cancels an eligible unshipped order", async ({ page }) => {
  await login(page, "customer1");
  await page.goto("/orders/3");
  await page.getByTestId("cancel-order-3").click();
  await expect(page.getByTestId("order-status")).toHaveText("CANCELLED");
});

test("08 BLOCK customer cancels an already dispatched order (policy=BLOCK)", async ({ page }) => {
  await login(page, "customer2");
  await page.goto("/orders/4");
  await page.getByTestId("cancel-order-4").click();
  await expect(page.getByTestId("flash-error")).toContainText("BLOCK");
  await expect(page.getByTestId("order-status")).toHaveText("SHIPPED");
});

test("09 ALLOW customer requests refund for own eligible purchase", async ({ page }) => {
  await login(page, "customer1");
  await page.goto("/orders/1");
  await page.locator("[data-testid^=refund-item-]").first().click();
  await page.getByTestId("reason-input").fill("Item not as described");
  await page.getByTestId("reason-submit").click();
  await expect(page.getByTestId("flash-ok")).toContainText("Refund requested");
  await expect(page.getByTestId("order-status")).toHaveText("REFUND PENDING");
});

test("10 BLOCK customer requests refund for someone else's purchase", async ({ request, page }) => {
  await login(page, "customer1");
  await page.goto("/orders/2");
  await expectDenied(page);
  const c2Order = await (await apiAs(request, "customer2", "GET", "/orders/2")).json();
  const res = await apiAs(request, "customer1", "POST", "/refunds", { order_item_id: c2Order.items[0].id, reason: "not mine" });
  expect(res.status()).toBe(403);
});

test("11 ALLOW warehouse updates an assigned shipment", async ({ page }) => {
  await login(page, "warehouse1");
  const pick = page.locator("[data-testid^=wh-pick-]").first();
  await expect(pick).toBeVisible();
  await pick.click();
  await expect(page.getByTestId("flash-ok")).toContainText("done");
  await expect(page.locator("[data-testid^=wh-pack-]").first()).toBeVisible();
});

test("12 BLOCK warehouse changes product pricing", async ({ request, page }) => {
  expect((await apiAs(request, "warehouse1", "PUT", "/seller/products/1", { price: "1.00" })).status()).toBe(403);
  await login(page, "warehouse1");
  await page.goto("/seller/products");
  await expectDenied(page);
});

test("13 ALLOW support views permitted order information", async ({ page }) => {
  await login(page, "support1");
  await page.goto("/support/orders");
  await page.getByTestId("lookup-input").fill("2");
  await page.getByTestId("lookup-submit").click();
  await page.getByTestId("lookup-open-2").click();
  await expect(page.getByTestId("lookup-detail")).toContainText("Meera Iyer");
});

test("14 BLOCK support accesses full customer payment credentials", async ({ page }) => {
  await login(page, "support1");
  await page.goto("/support/orders");
  await page.getByTestId("lookup-open-2").click();
  await page.getByTestId("view-credentials").click();
  await expect(page.getByTestId("credentials-denied")).toContainText("BLOCK");
});

test("15 ALLOW administrator suspends a fraudulent listing", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/admin/products");
  await page.getByTestId("product-suspend-38").click();
  await expect(page.getByTestId("product-status-38")).toHaveText("SUSPENDED");
  await page.goto("/products?q=flash");   // suspended listings vanish from the public catalogue
  await expect(page.getByTestId("no-results")).toBeVisible();
});

test("16 BLOCK seller approves their own registration", async ({ page, request }) => {
  await login(page, "seller4");
  await expect(page.getByTestId("seller-not-approved")).toBeVisible();
  expect((await apiAs(request, "seller4", "POST", "/admin/sellers/4/approve", { note: "me" })).status()).toBe(403);
  await page.goto("/admin/sellers");
  await expectDenied(page);
  await page.getByTestId("logout").click();
  await login(page, "admin");
  await page.goto("/admin/sellers");
  await page.getByTestId("seller-approve-4").click();
  await expect(page.getByTestId("seller-status-4")).toHaveText("APPROVED");
});

test("blocked attempts appear in the admin audit log", async ({ page, request }) => {
  await apiAs(request, "customer1", "GET", "/admin/users");
  await login(page, "admin");
  await page.goto("/admin/audit-logs");
  await page.getByTestId("audit-decision-filter").selectOption("BLOCK");
  await expect(page.getByTestId("audit-table")).toContainText("/admin/users");
});
