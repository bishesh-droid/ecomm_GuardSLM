import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, date, money } from "../api";
import { useAuth } from "../auth.jsx";
import { Async, Field, Flash, Status, Table, Tabs, useAction, useAsync } from "../components/ui.jsx";

function Bars({ data }) {
  const max = Math.max(1, ...data.map((d) => d.revenue));
  if (!data.length) return <p className="muted">No sales yet.</p>;
  return <div className="bars" role="img" aria-label="Daily revenue">{data.map((d) => <div key={d.date} className="bar" title={`${d.date}: ${money(d.revenue)}`} style={{ height: `${(d.revenue / max) * 100}%` }}><span>{d.date.slice(5)}</span></div>)}</div>;
}

export function ReportView({ r }) {
  return (
    <>
      <div className="stats">
        <div className="stat"><span>Revenue</span><b data-testid="stat-revenue">{money(r.revenue)}</b></div>
        <div className="stat"><span>Units sold</span><b data-testid="stat-units">{r.units_sold}</b></div>
        <div className="stat"><span>Orders</span><b data-testid="stat-orders">{r.orders}</b></div>
        <div className="stat"><span>Active listings</span><b data-testid="stat-listings">{r.active_listings}</b></div>
      </div>
      <div className="layout-2 even">
        <section className="panel"><h2>Revenue by day</h2><Bars data={r.daily_revenue} /></section>
        <section className="panel"><h2>Top products</h2>
          <Table testid="top-products" rows={r.top_products.map((p, i) => ({ ...p, id: i }))} cols={[{ h: "Product", r: (p) => p.name }, { h: "Units", r: (p) => p.units }, { h: "Revenue", r: (p) => money(p.revenue) }]} /></section>
      </div>
      {r.low_stock.length > 0 && <section className="panel"><h2>Low stock</h2><ul className="plain">{r.low_stock.map((l) => <li key={l.product_id}>{l.name}: <b className="warn">{l.quantity}</b> left</li>)}</ul></section>}
    </>
  );
}

export function SellerDashboard() {
  const me = useAsync(() => api("/seller/me"), []);
  const rep = useAsync(() => api("/seller/sales-report"), []);
  return (
    <>
      <h1>Seller dashboard</h1>
      <Async q={me}>{(s) => (
        <p>{s.store_name} · status <Status value={s.status} id="seller-status" /> · <Link to={`/seller/reports/${s.id}`} data-testid="own-report-link">Full sales report</Link></p>)}</Async>
      {me.data?.status !== "APPROVED" && me.data && <p className="alert alert-error" data-testid="seller-not-approved">Your store is awaiting administrator approval. You can browse but not publish listings.</p>}
      <Async q={rep}>{(r) => <ReportView r={r} />}</Async>
    </>
  );
}

export function SellerReport() {
  const { sellerId } = useParams();
  const q = useAsync(() => api(`/seller/${sellerId}/sales-report`), [sellerId]);
  return <><h1>Sales report · seller #{sellerId}</h1><Async q={q}>{(r) => <ReportView r={r} />}</Async></>;
}

export function SellerProducts() {
  const q = useAsync(() => api("/seller/products"), []);
  const [msg, run] = useAction(q.reload);
  const act = (p, a) => run(() => api(`/seller/products/${p.id}/${a}`, { method: "POST" }), `Listing ${a}d`);
  return (
    <>
      <div className="toolbar"><h1 className="h-inline">My products</h1><Link className="btn btn-primary" to="/seller/products/new" data-testid="new-product">+ New product</Link></div>
      <Flash msg={msg} />
      <Async q={q}>{(ps) => <Table testid="seller-products" rows={ps} cols={[
        { h: "ID", r: (p) => p.id }, { h: "Name", r: (p) => <Link to={`/products/${p.id}`}>{p.name}</Link> }, { h: "Category", r: (p) => p.category },
        { h: "Price", r: (p) => money(p.price) }, { h: "Stock", r: (p) => p.stock }, { h: "Status", r: (p) => <Status value={p.status} id={`product-status-${p.id}`} /> },
        { h: "Actions", r: (p) => <div className="actions">
          <Link className="btn btn-ghost" to={`/seller/products/${p.id}/edit`} data-testid={`edit-product-${p.id}`}>Edit</Link>
          {["DRAFT", "REJECTED"].includes(p.status) && <button className="btn btn-ghost" data-testid={`submit-product-${p.id}`} onClick={() => act(p, "submit")}>Submit for review</button>}
          {p.status === "ACTIVE" && <button className="btn btn-ghost" data-testid={`pause-product-${p.id}`} onClick={() => act(p, "pause")}>Pause</button>}
          {p.status === "PAUSED" && <button className="btn btn-ghost" data-testid={`activate-product-${p.id}`} onClick={() => act(p, "activate")}>Activate</button>}
        </div> }]} />}</Async>
    </>
  );
}

export function SellerProductForm() {
  const { id } = useParams();
  const nav = useNavigate();
  const cats = useAsync(() => api("/categories"), []);
  const existing = useAsync(() => (id ? api(`/seller/products/${id}`) : Promise.resolve(null)), [id]);
  const [f, setF] = useState(null);
  const [msg, run] = useAction();
  const form = f || (existing.data ? { name: existing.data.name, brand: existing.data.brand, description: existing.data.description, price: existing.data.price, category_id: existing.data.category_id, stock: 0, submit_for_review: false }
    : { name: "", brand: "", description: "", price: "", category_id: "", stock: 0, submit_for_review: false });
  const set = (k, v) => setF({ ...form, [k]: v });
  const submit = async (e) => {
    e.preventDefault();
    const body = { name: form.name, brand: form.brand, description: form.description, price: String(form.price), category_id: Number(form.category_id || cats.data[0].id) };
    const ok = await run(() => id ? api(`/seller/products/${id}`, { method: "PUT", body }) : api("/seller/products", { method: "POST", body: { ...body, stock: Number(form.stock), submit_for_review: form.submit_for_review } }), id ? "Product updated" : "Product created");
    if (ok && !id) nav("/seller/products");
  };
  return (
    <Async q={existing}>{() => (
      <>
        <h1 data-testid="product-form-title">{id ? `Edit product #${id}` : "New product"}</h1>
        <Flash msg={msg} />
        <form className="panel form-grid" onSubmit={submit} aria-label="Product form">
          <Field label="Name" id="pf-name"><input id="pf-name" data-testid="pf-name" value={form.name} onChange={(e) => set("name", e.target.value)} required minLength={2} /></Field>
          <Field label="Brand" id="pf-brand"><input id="pf-brand" data-testid="pf-brand" value={form.brand} onChange={(e) => set("brand", e.target.value)} /></Field>
          <Field label="Price (₹)" id="pf-price"><input id="pf-price" data-testid="pf-price" type="number" step="0.01" min="0.01" value={form.price} onChange={(e) => set("price", e.target.value)} required /></Field>
          <Field label="Category" id="pf-category"><select id="pf-category" data-testid="pf-category" value={form.category_id} onChange={(e) => set("category_id", e.target.value)}>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
          {!id && <Field label="Initial stock" id="pf-stock"><input id="pf-stock" data-testid="pf-stock" type="number" min="0" value={form.stock} onChange={(e) => set("stock", e.target.value)} /></Field>}
          <Field label="Description" id="pf-desc"><textarea id="pf-desc" data-testid="pf-description" value={form.description} onChange={(e) => set("description", e.target.value)} /></Field>
          {!id && <label className="radio"><input type="checkbox" data-testid="pf-submit-review" checked={form.submit_for_review} onChange={(e) => set("submit_for_review", e.target.checked)} /> Submit for review immediately</label>}
          <button className="btn btn-primary" data-testid="pf-save">{id ? "Save changes" : "Create product"}</button>
        </form>
      </>)}</Async>
  );
}

export function SellerInventory() {
  const q = useAsync(() => api("/seller/inventory"), []);
  const [msg, run] = useAction(q.reload);
  const [edit, setEdit] = useState({});
  return (
    <>
      <h1>Inventory</h1><Flash msg={msg} />
      <Async q={q}>{(rows) => <Table testid="inventory-table" rows={rows.map((r) => ({ ...r, id: r.product_id }))} cols={[
        { h: "Product", r: (r) => r.name }, { h: "Status", r: (r) => <Status value={r.status} /> }, { h: "On hand", r: (r) => <span data-testid={`stock-${r.product_id}`}>{r.quantity}</span> },
        { h: "Set quantity", r: (r) => <div className="row"><label className="sr-only" htmlFor={`inv-${r.product_id}`}>New quantity for {r.name}</label>
          <input id={`inv-${r.product_id}`} data-testid={`inventory-input-${r.product_id}`} type="number" min="0" value={edit[r.product_id] ?? r.quantity} onChange={(e) => setEdit({ ...edit, [r.product_id]: e.target.value })} />
          <button className="btn btn-ghost" data-testid={`inventory-save-${r.product_id}`} onClick={() => run(() => api(`/seller/inventory/${r.product_id}`, { method: "PUT", body: { quantity: Number(edit[r.product_id] ?? r.quantity) } }), "Inventory updated")}>Update</button></div> }]} />}</Async>
    </>
  );
}

const NEXT = { CONFIRMED: "PROCESSING", PROCESSING: "PACKED", PACKED: "SHIPPED", SHIPPED: "DELIVERED" };

export function SellerOrders() {
  const q = useAsync(() => api("/seller/orders"), []);
  const [msg, run] = useAction(q.reload);
  return (
    <>
      <h1>Orders & shipments</h1><Flash msg={msg} />
      <Async q={q}>{(os) => os.length === 0 ? <p className="muted">No orders yet.</p> : os.map((o) => (
        <section className="panel" key={o.id} data-testid={`seller-order-${o.id}`}>
          <h3>Order #{o.id} <Status value={o.status} id={`seller-order-status-${o.id}`} /> <span className="muted small">{date(o.created_at)} · ship to {o.shipping_name}, {o.shipping_city}</span></h3>
          {o.shipments.map((s) => (
            <div key={s.id} className="shipment">
              <Status value={s.status} id={`shipment-status-${s.id}`} />{" "}
              {o.items.filter((i) => i.shipment_id === s.id).map((i) => `${i.quantity}× ${i.product_name}`).join(", ")}
              {s.tracking_number && <span className="muted small"> · {s.tracking_number}</span>}
              {NEXT[s.status] && !["RETURN_REQUESTED", "CANCELLED"].includes(o.status) && (
                <button className="btn btn-ghost" data-testid={`ship-next-${s.id}`} onClick={() => run(() => api(`/seller/shipments/${s.id}/status`, { method: "POST", body: { status: NEXT[s.status] } }), `Shipment ${NEXT[s.status]}`)}>Mark {NEXT[s.status].toLowerCase()}</button>)}
            </div>))}
        </section>))}</Async>
    </>
  );
}

export function SellerReturns() {
  const rets = useAsync(() => api("/returns"), []);
  const refs = useAsync(() => api("/refunds"), []);
  const reload = async () => { await rets.reload(); await refs.reload(); };
  const [msg, run] = useAction(reload);
  const [note, setNote] = useState("");
  return (
    <>
      <h1>Returns & refunds</h1><Flash msg={msg} />
      <div className="field"><label htmlFor="resp-note">Response note (optional)</label><input id="resp-note" data-testid="response-note" value={note} onChange={(e) => setNote(e.target.value)} /></div>
      <section className="panel"><h2>Return requests</h2>
        <Async q={rets}>{(rs) => <Table testid="seller-returns" rows={rs} cols={[
          { h: "#", r: (r) => r.id }, { h: "Order", r: (r) => `#${r.order_id}` }, { h: "Product", r: (r) => r.product_name }, { h: "Reason", r: (r) => r.reason },
          { h: "Status", r: (r) => <Status value={r.status} id={`return-status-${r.id}`} /> },
          { h: "Actions", r: (r) => <div className="actions">
            {r.status === "REQUESTED" && <>
              <button className="btn btn-primary" data-testid={`return-approve-${r.id}`} onClick={() => run(() => api(`/returns/${r.id}/respond`, { method: "POST", body: { approve: true, note } }), "Return approved")}>Approve</button>
              <button className="btn btn-ghost" data-testid={`return-reject-${r.id}`} onClick={() => run(() => api(`/returns/${r.id}/respond`, { method: "POST", body: { approve: false, note } }), "Return rejected")}>Reject</button></>}
            {r.status === "APPROVED" && <button className="btn btn-primary" data-testid={`return-receive-${r.id}`} onClick={() => run(() => api(`/returns/${r.id}/receive`, { method: "POST" }), "Return received, stock restored")}>Mark received</button>}
          </div> }]} />}</Async></section>
      <section className="panel"><h2>Refund requests on your products</h2>
        <Async q={refs}>{(rs) => <Table testid="seller-refunds" rows={rs} cols={[
          { h: "#", r: (r) => r.id }, { h: "Product", r: (r) => r.product_name }, { h: "Amount", r: (r) => money(r.amount) }, { h: "Reason", r: (r) => r.reason },
          { h: "Status", r: (r) => <Status value={r.status} id={`refund-status-${r.id}`} /> },
          { h: "Actions", r: (r) => r.status === "REQUESTED" && <div className="actions">
            <button className="btn btn-primary" data-testid={`refund-approve-${r.id}`} onClick={() => run(() => api(`/refunds/${r.id}/approve`, { method: "POST", body: { note } }), "Refund approved")}>Approve</button>
            <button className="btn btn-ghost" data-testid={`refund-reject-${r.id}`} onClick={() => run(() => api(`/refunds/${r.id}/reject`, { method: "POST", body: { note } }), "Refund rejected")}>Reject</button></div> }]} />}</Async>
        <p className="muted small">Approved refunds are settled by an administrator; sellers cannot move money.</p></section>
    </>
  );
}
