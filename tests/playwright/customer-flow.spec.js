import { test, expect } from "@playwright/test";
import { login, resetDb } from "./helpers.js";

test.beforeEach(async ({ request }) => resetDb(request));

async function addToCart(page, id, qty = 1) {
  await page.goto(`/products/${id}`);
  await page.getByTestId("qty-input").fill(String(qty));
  await page.getByTestId(`add-to-cart-${id}`).click();
  await expect(page.getByTestId("flash-ok")).toContainText("Added to cart");
}

test("cart: add, change quantity, remove", async ({ page }) => {
  await login(page, "customer3");
  await addToCart(page, 7);
  await expect(page.getByTestId("cart-count")).toHaveText("1");
  await page.getByTestId("nav-cart").click();
  await expect(page).toHaveURL(/\/cart$/);
  const row = page.locator("[data-testid^=cart-item-]").first();
  await expect(row).toBeVisible();
  const qty = page.locator("[data-testid^=cart-qty-]").first();
  await qty.fill("3");
  await qty.blur();
  await expect(page.getByTestId("cart-items-count")).toHaveText("3");
  await page.locator("[data-testid^=cart-remove-]").first().click();
  await expect(page.getByTestId("cart-empty")).toBeVisible();
});

test("checkout with sandbox card succeeds and confirms the order", async ({ page }) => {
  await login(page, "customer3");
  await addToCart(page, 7, 2);
  await page.goto("/cart");
  await page.getByTestId("proceed-checkout").click();
  await expect(page).toHaveURL(/\/checkout$/);
  await page.getByTestId("payment-method-CARD").check();
  await page.getByTestId("payment-token").fill("tok_sim_ok");
  await page.getByTestId("place-order").click();
  await expect(page.getByTestId("order-placed")).toBeVisible();
  await expect(page.getByTestId("order-status")).toHaveText("CONFIRMED");
  await expect(page.getByTestId("payment-status")).toHaveText("SUCCEEDED");
});

test("payment failure leaves order unpaid; retry with a good token succeeds", async ({ page }) => {
  await login(page, "customer3");
  await addToCart(page, 6);
  await page.goto("/checkout");
  await page.getByTestId("payment-token").fill("tok_sim_fail");
  await page.getByTestId("place-order").click();
  await expect(page).toHaveURL(/payment=failed/);
  await expect(page.getByTestId("order-status")).toHaveText("PENDING PAYMENT");
  await expect(page.getByTestId("payment-failure")).toContainText("declined");
  await page.getByTestId("retry-token").fill("tok_sim_ok");
  await page.getByTestId("pay-now").click();
  await expect(page.getByTestId("order-status")).toHaveText("CONFIRMED");
});

test("cash on delivery confirms immediately", async ({ page }) => {
  await login(page, "customer1");
  await addToCart(page, 12);
  await page.goto("/checkout");
  await page.getByTestId("payment-method-COD").check();
  await page.getByTestId("place-order").click();
  await expect(page.getByTestId("order-status")).toHaveText("CONFIRMED");
  await expect(page.getByTestId("payment-status")).toHaveText("COD PENDING");
});

test("wishlist add / move to cart / remove", async ({ page }) => {
  await login(page, "customer1");
  await page.goto("/products/3");
  await page.getByTestId("wishlist-add-3").click();
  await page.goto("/wishlist");
  await expect(page.getByTestId("wishlist-item-3")).toBeVisible();
  await page.getByTestId("wishlist-to-cart-3").click();
  await expect(page.getByTestId("cart-count")).toHaveText("1");
  await page.getByTestId("wishlist-remove-3").click();
  await expect(page.getByTestId("wishlist-empty")).toBeVisible();
});

test("customer adds an address in the profile", async ({ page }) => {
  await login(page, "customer2");
  await page.goto("/profile");
  for (const [k, v] of Object.entries({ label: "Work", full_name: "Meera Iyer", line1: "1 Tech Park", city: "Bengaluru", state: "Karnataka", postal_code: "560001" }))
    await page.getByTestId(`addr-${k}`).fill(v);
  await page.getByTestId("address-add").click();
  await expect(page.getByTestId("address-list")).toContainText("Bengaluru");
});

test("customer can review a product they received, and report is available to others", async ({ page }) => {
  await login(page, "customer1");
  await page.goto("/products/1");            // Nimbus X5 delivered in seeded order #1
  await page.getByLabel("Title").fill("Great phone");
  await page.getByLabel("Your review").fill("Battery easily lasts two days.");
  await page.getByTestId("review-submit").click();
  await expect(page.getByTestId("flash-ok")).toContainText("Review posted");
  await expect(page.locator("[data-testid^=review-]").filter({ hasText: "Great phone" })).toBeVisible();
});

test("customer opens a support ticket", async ({ page }) => {
  await login(page, "customer1");
  await page.goto("/help");
  await page.getByTestId("ticket-subject").fill("Delivery question");
  await page.getByTestId("ticket-message").fill("When will my order arrive?");
  await page.getByTestId("ticket-submit").click();
  await expect(page.getByTestId("tickets-table")).toContainText("Delivery question");
});
