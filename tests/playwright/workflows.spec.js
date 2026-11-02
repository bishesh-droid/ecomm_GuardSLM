import { test, expect } from "@playwright/test";
import { login, resetDb } from "./helpers.js";

test.beforeEach(async ({ request }) => resetDb(request));

test("seller creates a product, admin approves it, it becomes searchable", async ({ page }) => {
  await login(page, "seller2");
  await page.goto("/seller/products/new");
  await page.getByTestId("pf-name").fill("Aurelia Desk Lamp");
  await page.getByTestId("pf-price").fill("1299");
  await page.getByTestId("pf-stock").fill("15");
  await page.getByTestId("pf-description").fill("Warm dimmable LED lamp");
  await page.getByTestId("pf-submit-review").check();
  await page.getByTestId("pf-save").click();
  await expect(page).toHaveURL(/\/seller\/products$/);
  await expect(page.getByTestId("seller-products")).toContainText("Aurelia Desk Lamp");
  await page.getByTestId("logout").click();

  await login(page, "admin");
  await page.goto("/admin/products");
  await page.getByTestId("product-status-filter").selectOption("PENDING_REVIEW");
  const row = page.getByTestId("admin-products").locator("tr", { hasText: "Aurelia Desk Lamp" });
  await row.locator("[data-testid^=product-approve-]").click();
  await expect(page.getByTestId("flash-ok")).toContainText("approved");
  await page.goto("/products?q=aurelia");
  await expect(page.getByTestId("result-count")).toContainText("1 result");
});

test("seller pauses and re-activates a listing, updates inventory", async ({ page }) => {
  await login(page, "seller1");
  await page.goto("/seller/products");
  await page.getByTestId("pause-product-2").click();
  await expect(page.getByTestId("product-status-2")).toHaveText("PAUSED");
  await page.getByTestId("activate-product-2").click();
  await expect(page.getByTestId("product-status-2")).toHaveText("ACTIVE");
  await page.goto("/seller/inventory");
  await page.getByTestId("inventory-input-2").fill("77");
  await page.getByTestId("inventory-save-2").click();
  await expect(page.getByTestId("stock-2")).toHaveText("77");
});

test("fulfilment: seller and warehouse move a shipment to delivery", async ({ page }) => {
  await login(page, "customer1");
  await page.goto("/orders/3");
  await expect(page.getByTestId("order-status")).toHaveText("CONFIRMED");
  await page.getByTestId("logout").click();

  await login(page, "warehouse1");
  for (const step of ["pick", "pack", "dispatch", "deliver"]) {
    const btn = page.locator(`[data-testid^=wh-${step}-]`).first();
    await expect(btn).toBeVisible();
    const id = (await btn.getAttribute("data-testid")).split("-").pop();
    await btn.click();
    await expect(page.getByTestId("flash-ok")).toBeVisible();
    if (step === "deliver") expect(id).toBeTruthy();
  }
});

test("return flow: customer requests, seller approves and receives, admin completes refund", async ({ page }) => {
  await login(page, "customer1");
  await page.goto("/orders/1");
  await page.locator("[data-testid^=return-item-]").first().click();
  await page.getByTestId("reason-input").fill("Screen flicker");
  await page.getByTestId("reason-submit").click();
  await expect(page.getByTestId("flash-ok")).toContainText("Return requested");
  await page.getByTestId("logout").click();

  await login(page, "seller1");
  await page.goto("/seller/returns");
  const approve = page.getByTestId("seller-returns").locator("tr", { hasText: "Nimbus" }).locator("[data-testid^=return-approve-]");
  await approve.click();
  await page.getByTestId("seller-returns").locator("tr", { hasText: "Nimbus" }).locator("[data-testid^=return-receive-]").click();
  await expect(page.getByTestId("flash-ok")).toContainText("stock restored");
  await page.getByTestId("logout").click();

  await login(page, "admin");
  await page.goto("/admin/refunds");
  const refund = page.getByTestId("refunds-table").locator("tr", { hasText: "Nimbus" });
  await refund.locator("[data-testid^=refund-approve-]").click();
  await refund.locator("[data-testid^=refund-complete-]").click();
  await expect(refund.locator("[data-testid^=refund-status-]")).toHaveText("COMPLETED");
});

test("support cannot approve refunds until an admin grants the permission", async ({ page }) => {
  await login(page, "support1");
  await page.goto("/support/refunds");
  await page.locator("[data-testid^=refund-approve-]").first().click();
  await expect(page.getByTestId("flash-error")).toContainText("BLOCK");
  await page.getByTestId("logout").click();

  await login(page, "admin");
  await page.goto("/admin/users");
  await page.locator("[data-testid^=toggle-refund-perm-]").first().click();
  await expect(page.getByTestId("flash-ok")).toContainText("Permission updated");
  await page.getByTestId("logout").click();

  await login(page, "support1");
  await page.goto("/support/refunds");
  await page.locator("[data-testid^=refund-approve-]").first().click();
  await expect(page.getByTestId("flash-ok")).toContainText("Refund approved");
});

test("admin moderates a reported review and overrides a return decision", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/admin/reviews");
  await expect(page.locator("[data-testid^=report-count-]").first()).toBeVisible();
  await page.locator("[data-testid^=review-hide-]").first().click();
  await expect(page.getByTestId("flash-ok")).toContainText("hidden");
  await page.goto("/admin/refunds");
  await page.locator("[data-testid^=return-override-reject-]").first().click();
  await expect(page.getByTestId("flash-ok")).toContainText("audit log");
  await page.goto("/admin/audit-logs");
  await expect(page.getByTestId("audit-table")).toContainText("return.admin_override");
});

test("admin dashboard, users and orders pages render", async ({ page }) => {
  await login(page, "admin");
  await expect(page.getByTestId("stat-gmv")).toBeVisible();
  await page.getByTestId("nav-admin-users").click();
  await expect(page.getByTestId("users-table")).toContainText("customer1");
  await page.getByTestId("nav-admin-orders").click();
  await page.getByTestId("order-status-filter").selectOption("SHIPPED");
  await expect(page.getByTestId("admin-orders")).toContainText("SHIPPED");
});
