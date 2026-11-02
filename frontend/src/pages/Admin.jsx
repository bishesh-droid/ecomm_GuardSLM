import { useState } from "react";
import { Link } from "react-router-dom";
import { api, date, money } from "../api";
import { useAuth } from "../auth.jsx";
import { Async, Flash, Status, Table, useAction, useAsync } from "../components/ui.jsx";
import { RefundsTable, ReturnsTable } from "./Support.jsx";

export function AdminDashboard() {
  const q = useAsync(() => api("/admin/analytics"), []);
  return (
    <>
      <h1>Platform analytics</h1>
      <Async q={q}>{(a) => (
        <>
          <div className="stats">
            <div className="stat"><span>GMV</span><b data-testid="stat-gmv">{money(a.gmv)}</b></div>
            <div className="stat"><span>Orders</span><b data-testid="stat-orders">{a.order_count}</b></div>
            <div className="stat"><span>Refunded</span><b data-testid="stat-refunded">{money(a.refunded_total)}</b></div>
            <div className="stat"><span>Pending sellers</span><b data-testid="stat-pending-sellers">{a.pending_sellers}</b></div>
            <div className="stat"><span>Products to review</span><b data-testid="stat-pending-products">{a.pending_products}</b></div>
            <div className="stat"><span>Refunds awaiting</span><b data-testid="stat-pending-refunds">{a.pending_refunds}</b></div>
          </div>
          <div className="layout-2 even">
            <section className="panel"><h2>Orders by status</h2><ul className="plain">{Object.entries(a.orders_by_status).map(([k, v]) => <li key={k}><Status value={k} /> {v}</li>)}</ul></section>
            <section className="panel"><h2>Top sellers</h2><Table testid="top-sellers" rows={a.top_sellers.map((s, i) => ({ ...s, id: i }))} cols={[{ h: "Seller", r: (s) => s.seller }, { h: "Revenue", r: (s) => money(s.revenue) }]} /></section>
          </div>
        </>)}</Async>
    </>
  );
}

export function AdminUsers() {
  const q = useAsync(() => api("/admin/users"), []);
  const [msg, run] = useAction(q.reload);
  return (
    <>
      <h1>User management</h1><Flash msg={msg} />
      <Async q={q}>{(us) => <Table testid="users-table" rows={us} cols={[
        { h: "ID", r: (u) => u.id }, { h: "Username", r: (u) => u.username }, { h: "Name", r: (u) => u.display_name }, { h: "Role", r: (u) => u.role },
        { h: "Active", r: (u) => <Status value={u.is_active ? "ACTIVE" : "SUSPENDED"} id={`user-active-${u.id}`} /> },
        { h: "Refund permission", r: (u) => u.role === "SUPPORT" ? <button className="btn btn-ghost" data-testid={`toggle-refund-perm-${u.id}`} onClick={() => run(() => api(`/admin/users/${u.id}`, { method: "PATCH", body: { can_issue_refunds: !u.can_issue_refunds } }), "Permission updated")}>{u.can_issue_refunds ? "Granted · revoke" : "Not granted · grant"}</button> : "-" },
        { h: "Account", r: (u) => <button className="btn btn-ghost" data-testid={`toggle-active-${u.id}`} onClick={() => run(() => api(`/admin/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } }), "User updated")}>{u.is_active ? "Deactivate" : "Activate"}</button> }]} />}</Async>
    </>
  );
}

export function AdminSellers() {
  const q = useAsync(() => api("/admin/sellers"), []);
  const [msg, run] = useAction(q.reload);
  return (
    <>
      <h1>Seller approvals</h1><Flash msg={msg} />
      <Async q={q}>{(ss) => <Table testid="sellers-table" rows={ss} cols={[
        { h: "ID", r: (s) => s.id }, { h: "Store", r: (s) => s.store_name }, { h: "User", r: (s) => s.username }, { h: "Applied", r: (s) => date(s.created_at) },
        { h: "Status", r: (s) => <Status value={s.status} id={`seller-status-${s.id}`} /> },
        { h: "Decision", r: (s) => <div className="actions">
          {s.status !== "APPROVED" && <button className="btn btn-primary" data-testid={`seller-approve-${s.id}`} onClick={() => run(() => api(`/admin/sellers/${s.id}/approve`, { method: "POST", body: { note: "Approved" } }), "Seller approved")}>Approve</button>}
          {s.status !== "REJECTED" && <button className="btn btn-ghost" data-testid={`seller-reject-${s.id}`} onClick={() => run(() => api(`/admin/sellers/${s.id}/reject`, { method: "POST", body: { note: "Rejected" } }), "Seller rejected")}>Reject</button>}</div> }]} />}</Async>
    </>
  );
}

export function AdminProducts() {
  const [status, setStatus] = useState("");
  const q = useAsync(() => api("/admin/products", { params: { status } }), [status]);
  const [msg, run] = useAction(q.reload);
  const act = (p, a, label) => run(() => api(`/admin/products/${p.id}/${a}`, { method: "POST", body: { note: `${a} by admin` } }), label);
  return (
    <>
      <h1>Product moderation</h1><Flash msg={msg} />
      <div className="field inline"><label htmlFor="pm-status">Status</label>
        <select id="pm-status" data-testid="product-status-filter" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{["PENDING_REVIEW", "ACTIVE", "DRAFT", "PAUSED", "REJECTED", "SUSPENDED"].map((s) => <option key={s}>{s}</option>)}</select></div>
      <Async q={q}>{(ps) => <Table testid="admin-products" rows={ps} cols={[
        { h: "ID", r: (p) => p.id }, { h: "Product", r: (p) => <Link to={`/products/${p.id}`}>{p.name}</Link> }, { h: "Seller", r: (p) => p.seller_name }, { h: "Price", r: (p) => money(p.price) },
        { h: "Status", r: (p) => <Status value={p.status} id={`product-status-${p.id}`} /> },
        { h: "Moderate", r: (p) => <div className="actions">
          {p.status === "PENDING_REVIEW" && <><button className="btn btn-primary" data-testid={`product-approve-${p.id}`} onClick={() => act(p, "approve", "Listing approved")}>Approve</button><button className="btn btn-ghost" data-testid={`product-reject-${p.id}`} onClick={() => act(p, "reject", "Listing rejected")}>Reject</button></>}
          {["ACTIVE", "PAUSED", "PENDING_REVIEW"].includes(p.status) && <button className="btn btn-danger" data-testid={`product-suspend-${p.id}`} onClick={() => act(p, "suspend", "Listing suspended")}>Suspend</button>}
          {p.status === "SUSPENDED" && <button className="btn btn-ghost" data-testid={`product-unsuspend-${p.id}`} onClick={() => act(p, "unsuspend", "Listing restored")}>Unsuspend</button>}</div> }]} />}</Async>
    </>
  );
}

export function AdminOrders() {
  const [status, setStatus] = useState("");
  const q = useAsync(() => api("/admin/orders", { params: { status } }), [status]);
  return (
    <>
      <h1>All orders</h1>
      <div className="field inline"><label htmlFor="ao-status">Status</label>
        <select id="ao-status" data-testid="order-status-filter" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{["PENDING_PAYMENT", "CONFIRMED", "PROCESSING", "PACKED", "SHIPPED", "DELIVERED", "CANCELLED", "RETURN_REQUESTED", "REFUND_PENDING", "REFUNDED"].map((s) => <option key={s}>{s}</option>)}</select></div>
      <Async q={q}>{(os) => <Table testid="admin-orders" rows={os} cols={[
        { h: "Order", r: (o) => <Link to={`/orders/${o.id}`} data-testid={`order-link-${o.id}`}>#{o.id}</Link> }, { h: "Customer", r: (o) => o.customer_name }, { h: "Placed", r: (o) => date(o.created_at) },
        { h: "Total", r: (o) => money(o.total) }, { h: "Sellers", r: (o) => o.shipments.length }, { h: "Payment", r: (o) => <Status value={o.payments?.at(-1)?.status} /> }, { h: "Status", r: (o) => <Status value={o.status} id={`order-status-${o.id}`} /> }]} />}</Async>
    </>
  );
}

export function AdminRefunds() {
  return <><h1>Refund management</h1><RefundsTable /><h2>Returns</h2><ReturnsTable admin /></>;
}

export function AdminReviews() {
  const { user } = useAuth();
  const q = useAsync(() => api("/reviews/moderation"), []);
  const [msg, run] = useAction(q.reload);
  return (
    <>
      <h1>Review moderation</h1><Flash msg={msg} />
      <Async q={q}>{(rs) => <Table testid="review-moderation" rows={rs} cols={[
        { h: "#", r: (r) => r.id }, { h: "Product", r: (r) => r.product_name }, { h: "Author", r: (r) => r.author }, { h: "Review", r: (r) => <><b>{r.title}</b> ({r.rating}★)<div className="small">{r.body}</div></> },
        { h: "Reports", r: (r) => r.report_count ? <span className="warn" data-testid={`report-count-${r.id}`}>{r.report_count}: {r.report_reasons.join("; ")}</span> : 0 },
        { h: "Status", r: (r) => <Status value={r.status} id={`review-status-${r.id}`} /> },
        { h: "Moderate", r: (r) => <div className="actions">
          {r.status === "VISIBLE" && <button className="btn btn-danger" data-testid={`review-hide-${r.id}`} onClick={() => run(() => api(`/reviews/${r.id}/hide`, { method: "POST" }), "Review hidden")}>Hide</button>}
          {r.status === "HIDDEN" && <button className="btn btn-ghost" data-testid={`review-restore-${r.id}`} onClick={() => run(() => api(`/reviews/${r.id}/restore`, { method: "POST" }), "Review restored")}>Restore</button>}
          {user.role === "ADMIN" && <button className="btn btn-ghost" data-testid={`review-delete-${r.id}`} onClick={() => run(() => api(`/reviews/${r.id}`, { method: "DELETE" }), "Review deleted")}>Delete</button>}</div> }]} />}</Async>
    </>
  );
}

export function AdminAudit() {
  const [decision, setDecision] = useState("");
  const q = useAsync(() => api("/audit-logs", { params: { decision, limit: 200 } }), [decision]);
  return (
    <>
      <h1>Audit logs</h1>
      <div className="field inline"><label htmlFor="al-decision">Decision</label>
        <select id="al-decision" data-testid="audit-decision-filter" value={decision} onChange={(e) => setDecision(e.target.value)}><option value="">All</option><option>ALLOW</option><option>BLOCK</option><option>ASK</option></select>
        <button className="btn btn-ghost" onClick={q.reload} data-testid="audit-refresh">Refresh</button></div>
      <Async q={q}>{(ls) => <Table testid="audit-table" rows={ls} cols={[
        { h: "When", r: (l) => new Date(l.created_at).toLocaleString("en-IN") }, { h: "Actor", r: (l) => l.actor_role ? `${l.actor_role} #${l.actor_id}` : "anonymous" },
        { h: "Action", r: (l) => l.action }, { h: "Entity", r: (l) => l.entity_type ? `${l.entity_type} ${l.entity_id ?? ""}` : "-" }, { h: "Decision", r: (l) => <Status value={l.decision} /> }, { h: "Detail", r: (l) => l.detail || "-" }]} />}</Async>
    </>
  );
}
