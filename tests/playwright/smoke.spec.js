import { test, expect } from "@playwright/test";
import { login, resetDb } from "./helpers.js";

test.beforeEach(async ({ request }) => resetDb(request));

test("home page, categories and search", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("hero")).toBeVisible();
  await page.getByTestId("search-input").fill("vertex");
  await page.getByTestId("search-submit").click();
  await expect(page).toHaveURL(/\/products\?q=vertex/);
  await expect(page.getByTestId("product-card-6")).toBeVisible();
  await expect(page.getByTestId("result-count")).toContainText("1 result");
});

test("category and price filters narrow results via URL", async ({ page }) => {
  await page.goto("/products");
  const all = await page.locator("[data-testid^=product-card-]").count();
  await page.getByTestId("filter-category-books").click();
  await expect(page).toHaveURL(/category=books/);
  await expect(page.getByTestId("product-card-23")).toBeVisible();
  await page.getByTestId("filter-max-price").fill("450");
  await page.getByTestId("filter-apply").click();
  await expect(page).toHaveURL(/max_price=450/);
  await expect(page.getByTestId("product-card-23")).toBeVisible();   // Midnight Algorithm, 399
  await expect(page.getByTestId("product-card-25")).toHaveCount(0);  // 899 filtered out
  expect(await page.locator("[data-testid^=product-card-]").count()).toBeLessThan(all);
  await page.getByTestId("filter-clear").click();
  await expect(page.getByTestId("search-input")).toBeVisible();
});

test("search with no hits shows empty state", async ({ page }) => {
  await page.goto("/products?q=zzzzqqq");
  await expect(page.getByTestId("no-results")).toBeVisible();
});

for (const [user, landing, nav] of [
  ["admin", "/admin", "nav-admin-dashboard"], ["seller1", "/seller", "nav-seller-dashboard"], ["customer1", "/", "nav-orders"],
  ["warehouse1", "/warehouse", "nav-warehouse"], ["support1", "/support", "nav-support-tickets"],
]) {
  test(`${user} can sign in and lands on ${landing}`, async ({ page }) => {
    await login(page, user);
    await expect(page).toHaveURL(new RegExp(`${landing === "/" ? "/$" : landing}$`));
    await expect(page.getByTestId(nav)).toBeVisible();
    await page.getByTestId("logout").click();
    await expect(page.getByTestId("nav-login")).toBeVisible();
  });
}

test("bad credentials are rejected", async ({ page }) => {
  await page.goto("/login");
  await page.getByTestId("login-username").fill("customer1");
  await page.getByTestId("login-password").fill("wrong");
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("login-error")).toBeVisible();
});

test("anonymous users are redirected to login for protected pages", async ({ page }) => {
  await page.goto("/orders");
  await expect(page).toHaveURL(/\/login/);
});
