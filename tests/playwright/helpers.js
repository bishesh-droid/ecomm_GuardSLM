import { expect } from "@playwright/test";

export const API = process.env.API_URL || "http://localhost:8000";
export const PASSWORD = "GuardSLM2026!";

/** Re-seed the database to its deterministic baseline (requires ENABLE_DEV_RESET=true on the backend). */
export async function resetDb(request) {
  const token = await apiToken(request, "admin");
  const res = await request.post(`${API}/admin/dev/reset`, { headers: { Authorization: `Bearer ${token}` } });
  expect(res.ok(), "dev reset must be enabled").toBeTruthy();
}

export async function apiToken(request, username) {
  const res = await request.post(`${API}/auth/login`, { data: { username, password: PASSWORD } });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).access_token;
}

/** Direct backend call as a given user: returns the raw response so tests can assert on 403s. */
export async function apiAs(request, username, method, path, data) {
  const token = await apiToken(request, username);
  return request.fetch(`${API}${path}`, { method, data, headers: { Authorization: `Bearer ${token}` } });
}

export async function login(page, username) {
  await page.goto("/login");
  await page.getByTestId("login-username").fill(username);
  await page.getByTestId("login-password").fill(PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("current-user")).toBeVisible();
}

export const expectDenied = async (page) => {
  await expect(page.getByTestId("access-denied")).toBeVisible();
  await expect(page.getByTestId("decision-badge")).toHaveText("BLOCK");
};
