import { useState } from "react";
import { Link } from "react-router-dom";
import { api, date, money } from "../api";
import { useAuth } from "../auth.jsx";
import { Async, Field, Flash, Status, Table, useAction, useAsync } from "../components/ui.jsx";

export function SupportHome() {
  const [status, setStatus] = useState("");
  const q = useAsync(() => api("/support/tickets", { params: { status } }), [status]);
  const [msg, run] = useAction(q.reload);
  const [resp, setResp] = useState({});
  return (
    <>
      <h1>Customer queries</h1><Flash msg={msg} />
      <div className="field inline"><label htmlFor="t-filter">Status</label>
        <select id="t-filter" data-testid="ticket-filter" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"].map((s) => <option key={s}>{s}</option>)}</select></div>
      <Async q={q}>{(ts) => <Table testid="support-tickets" rows={ts} cols={[
        { h: "#", r: (t) => t.id }, { h: "Customer", r: (t) => t.customer_name }, { h: "Order", r: (t) => t.order_id ? <Link to={`/support/orders?q=${t.order_id}`}>#{t.order_id}</Link> : "-" },
        { h: "Subject", r: (t) => <><b>{t.subject}</b><div className="small">{t.message}</div></> }, { h: "Status", r: (t) => <Status value={t.status} id={`ticket-status-${t.id}`} /> },
        { h: "Respond", r: (t) => <div className="row"><label className="sr-only" htmlFor={`tr-${t.id}`}>Response to ticket {t.id}</label>
          <input id={`tr-${t.id}`} data-testid={`ticket-response-${t.id}`} defaultValue={t.response || ""} onChange={(e) => setResp({ ...resp, [t.id]: e.target.value })} />
          <button className="btn btn-ghost" data-testid={`ticket-reply-${t.id}`} onClick={() => run(() => api(`/support/tickets/${t.id}`, { method: "PATCH", body: { response: resp[t.id] ?? t.response } }), "Response saved")}>Reply</button>
          <button className="btn btn-ghost" data-testid={`ticket-resolve-${t.id}`} onClick={() => run(() => api(`/support/tickets/${t.id}`, { method: "PATCH", body: { status: "RESOLVED" } }), "Ticket resolved")}>Resolve</button></div> }]} />}</Async>
    </>
  );
}

export function SupportOrders() {
  const initial = new URLSearchParams(location.search).get("q") || "";
  const [q, setQ] = useState(initial);
  const [term, setTerm] = useState(initial);
  const res = useAsync(() => api("/support/orders", { params: { q: term } }), [term]);
  const [sel, setSel] = useState(null);
  const detail = useAsync(() => (sel ? api(`/support/orders/${sel}`) : Promise.resolve(null)), [sel]);
  const [creds, setCreds] = useState(null);
  const { user } = useAuth();
  return (
    <>
      <h1>Order lookup</h1>
      <form className="row" role="search" onSubmit={(e) => { e.preventDefault(); setTerm(q); }}>
        <div className="field inline"><label htmlFor="lookup-q">Order number or customer name</label><input id="lookup-q" data-testid="lookup-input" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <button className="btn btn-primary" data-testid="lookup-submit">Search</button>
      </form>
      <Async q={res}>{(os) => <Table testid="lookup-results" rows={os} cols={[
        { h: "Order", r: (o) => <button className="link-btn" data-testid={`lookup-open-${o.id}`} onClick={() => setSel(o.id)}>#{o.id}</button> }, { h: "Customer", r: (o) => o.customer_name },
        { h: "Total", r: (o) => money(o.total) }, { h: "Status", r: (o) => <Status value={o.status} /> }, { h: "Placed", r: (o) => date(o.created_at) }]} />}</Async>
      {sel && detail.data && <section className="panel" data-testid="lookup-detail"><h2>Order #{detail.data.id}</h2>
        <p>Customer: {detail.data.customer_name} · Status <Status value={detail.data.status} /> · Ship-to city: {detail.data.shipping_city}</p>
        <ul className="plain">{detail.data.items.map((i) => <li key={i.id}>{i.quantity}× {i.product_name} <Status value={i.status} /></li>)}</ul>
        {detail.data.payments?.map((p) => <p key={p.id} className="small">Payment {p.method}: <Status value={p.status} /> {money(p.amount)} (ref ····{p.token_last4 || "n/a"})</p>)}
        <button className="btn btn-ghost" data-testid="view-credentials" onClick={async () => { try { await api(`/support/customers/${detail.data.customer_id}/payment-credentials`); } catch (e) { setCreds(e); } }}>View customer payment credentials</button>
        {creds && <p className="alert alert-error" role="alert" data-testid="credentials-denied">{creds.decision}: {creds.message}</p>}
      </section>}
    </>
  );
}

export function RefundsTable({ canComplete = true }) {
  const q = useAsync(() => api("/refunds"), []);
  const [msg, run] = useAction(q.reload);
  const [note, setNote] = useState("");
  return (
    <>
      <Flash msg={msg} />
      <div className="field"><label htmlFor="refund-note">Decision note</label><input id="refund-note" data-testid="refund-note" value={note} onChange={(e) => setNote(e.target.value)} /></div>
      <Async q={q}>{(rs) => <Table testid="refunds-table" rows={rs} cols={[
        { h: "#", r: (r) => r.id }, { h: "Order", r: (r) => `#${r.order_id}` }, { h: "Customer", r: (r) => r.customer_name }, { h: "Product", r: (r) => r.product_name },
        { h: "Amount", r: (r) => money(r.amount) }, { h: "Reason", r: (r) => r.reason }, { h: "Status", r: (r) => <Status value={r.status} id={`refund-status-${r.id}`} /> },
        { h: "Actions", r: (r) => <div className="actions">
          {r.status === "REQUESTED" && <>
            <button className="btn btn-primary" data-testid={`refund-approve-${r.id}`} onClick={() => run(() => api(`/refunds/${r.id}/approve`, { method: "POST", body: { note } }), "Refund approved")}>Approve</button>
            <button className="btn btn-ghost" data-testid={`refund-reject-${r.id}`} onClick={() => run(() => api(`/refunds/${r.id}/reject`, { method: "POST", body: { note } }), "Refund rejected")}>Reject</button></>}
          {r.status === "APPROVED" && <button className="btn btn-accent" data-testid={`refund-complete-${r.id}`} onClick={() => run(() => api(`/refunds/${r.id}/complete`, { method: "POST" }), "Refund completed")}>Complete payout</button>}
        </div> }]} />}</Async>
    </>
  );
}

export function ReturnsTable({ admin = false }) {
  const q = useAsync(() => api("/returns"), []);
  const [msg, run] = useAction(q.reload);
  const [note, setNote] = useState("");
  return (
    <>
      <Flash msg={msg} />
      <div className="field"><label htmlFor="return-note">Review note</label><input id="return-note" data-testid="return-note" value={note} onChange={(e) => setNote(e.target.value)} /></div>
      <Async q={q}>{(rs) => <Table testid="returns-table" rows={rs} cols={[
        { h: "#", r: (r) => r.id }, { h: "Order", r: (r) => `#${r.order_id}` }, { h: "Product", r: (r) => r.product_name }, { h: "Reason", r: (r) => r.reason },
        { h: "Seller response", r: (r) => r.seller_response || "-" }, { h: "Status", r: (r) => <Status value={r.status} id={`return-status-${r.id}`} /> },
        { h: "Actions", r: (r) => <div className="actions">
          {["REQUESTED", "REJECTED"].includes(r.status) && <button className="btn btn-primary" data-testid={`return-review-approve-${r.id}`} onClick={() => run(() => api(`/returns/${r.id}/review`, { method: "POST", body: { approve: true, note } }), "Return approved")}>Approve</button>}
          {r.status === "REQUESTED" && <button className="btn btn-ghost" data-testid={`return-review-reject-${r.id}`} onClick={() => run(() => api(`/returns/${r.id}/review`, { method: "POST", body: { approve: false, note } }), "Return rejected")}>Reject</button>}
          {admin && r.status !== "RETURNED" && <>
            <button className="btn btn-danger" data-testid={`return-override-approve-${r.id}`} onClick={() => run(() => api(`/returns/${r.id}/override`, { method: "POST", body: { decision: "APPROVED", note: note || "Admin override" } }), "Override recorded in audit log")}>Override: approve</button>
            <button className="btn btn-danger" data-testid={`return-override-reject-${r.id}`} onClick={() => run(() => api(`/returns/${r.id}/override`, { method: "POST", body: { decision: "REJECTED", note: note || "Admin override" } }), "Override recorded in audit log")}>Override: reject</button></>}
        </div> }]} />}</Async>
    </>
  );
}

export const SupportRefunds = () => <><h1>Refund requests</h1><p className="muted">Support can only approve or pay out refunds when an administrator has granted the explicit refund permission.</p><RefundsTable /></>;
export const SupportReturns = () => <><h1>Return requests</h1><ReturnsTable /></>;
