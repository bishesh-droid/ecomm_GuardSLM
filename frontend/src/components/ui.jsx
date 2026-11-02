import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { imageUrl, money } from "../api";

export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const run = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try { setState({ data: await fn(), error: null, loading: false }); }
    catch (e) { setState({ data: null, error: e, loading: false }); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); }, [run]);
  return { ...state, reload: run };
}

export function AccessDenied({ error }) {
  return (
    <div className="panel denied" data-testid="access-denied" role="alert">
      <h2>Access denied</h2>
      <p data-testid="denied-message">{error?.message || "You are not allowed to view this page."}</p>
      <span className="badge badge-red" data-testid="decision-badge">{error?.decision || "BLOCK"}</span>
      <p><Link to="/">Back to marketplace</Link></p>
    </div>
  );
}

/** Renders loading / error (403 -> AccessDenied) / content. */
export function Async({ q, children }) {
  if (q.loading && !q.data) return <p className="muted" data-testid="loading">Loading...</p>;
  if (q.error) {
    if (q.error.status === 403) return <AccessDenied error={q.error} />;
    if (q.error.status === 404) return <div className="panel" data-testid="not-found"><h2>Not found</h2><p>{q.error.message}</p></div>;
    return <p className="alert alert-error" role="alert" data-testid="error">{q.error.message}</p>;
  }
  return children(q.data);
}

const TONE = {
  DELIVERED: "green", SUCCEEDED: "green", ACTIVE: "green", APPROVED: "green", COMPLETED: "green", REFUNDED: "green", VISIBLE: "green", RESOLVED: "green", ALLOW: "green", RETURNED: "green",
  SHIPPED: "blue", PACKED: "blue", PROCESSING: "blue", CONFIRMED: "blue", IN_PROGRESS: "blue", RETURN_APPROVED: "blue", PARTIALLY_REFUNDED: "blue",
  PENDING: "amber", PENDING_PAYMENT: "amber", COD_PENDING: "amber", PENDING_REVIEW: "amber", REQUESTED: "amber", REFUND_PENDING: "amber", RETURN_REQUESTED: "amber", OPEN: "amber", DRAFT: "gray", PAUSED: "gray", CLOSED: "gray",
  CANCELLED: "red", FAILED: "red", REJECTED: "red", SUSPENDED: "red", HIDDEN: "red", BLOCK: "red", ASK: "amber",
};
export function Status({ value, id }) {
  return <span className={`badge badge-${TONE[value] || "gray"}`} data-testid={id}>{(value || "").replaceAll("_", " ")}</span>;
}

export function Stars({ value }) {
  const full = Math.round(value || 0);
  return <span className="stars" aria-label={`${value} out of 5`}>{"★".repeat(full)}{"☆".repeat(5 - full)}</span>;
}

export function ProductCard({ p, onWish }) {
  return (
    <article className="card product-card" data-testid={`product-card-${p.id}`}>
      <Link to={`/products/${p.id}`} className="card-img"><img src={imageUrl(p.image)} alt={p.name} loading="lazy" /></Link>
      <div className="card-body">
        <Link to={`/products/${p.id}`} className="card-title" data-testid={`product-link-${p.id}`}>{p.name}</Link>
        <div className="muted small">{p.brand} · {p.category}</div>
        <div><Stars value={p.rating} /> <span className="muted small">({p.review_count})</span></div>
        <div className="price" data-testid={`product-price-${p.id}`}>{money(p.price)}</div>
        <div className="small">{p.stock > 0 ? (p.stock <= 5 ? <span className="warn">Only {p.stock} left</span> : <span className="ok">In stock</span>) : <span className="err">Out of stock</span>}</div>
        {onWish && <button className="btn btn-ghost small" onClick={() => onWish(p)} data-testid={`wishlist-add-${p.id}`}>♡ Wishlist</button>}
      </div>
    </article>
  );
}

export function Field({ label, id, children }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
    </div>
  );
}

export function Table({ cols, rows, empty = "Nothing here yet.", testid }) {
  if (!rows?.length) return <p className="muted" data-testid={testid ? `${testid}-empty` : undefined}>{empty}</p>;
  return (
    <div className="table-wrap">
      <table className="table" data-testid={testid}>
        <thead><tr>{cols.map((c) => <th key={c.h}>{c.h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={r.id ?? i} data-testid={testid ? `${testid}-row-${r.id ?? i}` : undefined}>{cols.map((c) => <td key={c.h}>{c.r(r)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

export function Flash({ msg }) {
  if (!msg) return null;
  return <p className={`alert ${msg.type === "error" ? "alert-error" : "alert-ok"}`} role="status" data-testid={msg.type === "error" ? "flash-error" : "flash-ok"}>{msg.text}</p>;
}

/** Run an action, surface success/error in a Flash, and reload data. */
export function useAction(reload) {
  const [msg, setMsg] = useState(null);
  const run = async (fn, okText = "Done") => {
    try { await fn(); setMsg({ type: "ok", text: okText }); reload && (await reload()); return true; }
    catch (e) { setMsg({ type: "error", text: e.decision ? `${e.decision}: ${e.message}` : e.message }); return false; }
  };
  return [msg, run, setMsg];
}

export function Tabs({ items, base }) {
  return (
    <nav className="subnav" aria-label="Section navigation">
      {items.map(([to, label, tid]) => <Link key={to} to={base + to} data-testid={tid}>{label}</Link>)}
    </nav>
  );
}
