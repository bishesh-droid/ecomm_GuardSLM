export const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const KEY = "guardslm_token";

export const getToken = () => localStorage.getItem(KEY);
export const setToken = (t) => (t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY));
export const imageUrl = (p) => (p ? (p.startsWith("http") ? p : API + p) : "");

export class ApiError extends Error {
  constructor(status, detail) {
    const msg = typeof detail === "string" ? detail : detail?.message || JSON.stringify(detail);
    super(msg);
    this.status = status;
    this.decision = detail?.decision || null; // BLOCK | ASK for authorization denials
  }
}

export async function api(path, { method = "GET", body, params } = {}) {
  const url = new URL(API + path);
  Object.entries(params || {}).forEach(([k, v]) => v !== "" && v != null && url.searchParams.set(k, v));
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let detail = data.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ");
    throw new ApiError(res.status, detail || res.statusText);
  }
  return data;
}

export const money = (v) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(v ?? 0);
export const date = (s) => (s ? new Date(s).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "-");
