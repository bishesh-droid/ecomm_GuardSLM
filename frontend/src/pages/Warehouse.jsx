import { useState } from "react";
import { api, money } from "../api";
import { Async, Field, Flash, Status, Table, useAction, useAsync } from "../components/ui.jsx";

const STEPS = { CONFIRMED: ["pick", "Pick items"], PROCESSING: ["pack", "Pack"], PACKED: ["dispatch", "Dispatch"], SHIPPED: ["deliver", "Mark delivered"] };

export default function Warehouse() {
  const q = useAsync(() => api("/warehouse/queue"), []);
  const stock = useAsync(() => api("/warehouse/stock"), []);
  const moves = useAsync(() => api("/warehouse/stock-movements"), []);
  const reload = async () => { await q.reload(); await stock.reload(); await moves.reload(); };
  const [msg, run] = useAction(reload);
  const [track, setTrack] = useState({});
  const [mv, setMv] = useState({ product_id: "", delta: "", reason: "RECEIVE" });
  return (
    <>
      <h1>Fulfilment queue</h1><Flash msg={msg} />
      <Async q={q}>{(rows) => <Table testid="warehouse-queue" rows={rows} empty="No shipments waiting." cols={[
        { h: "Shipment", r: (s) => `#${s.id}` }, { h: "Order", r: (s) => `#${s.order_id}` }, { h: "Seller", r: (s) => s.seller_store },
        { h: "Items", r: (s) => s.items.map((i) => `${i.quantity}× ${i.product_name}`).join(", ") }, { h: "Ship to", r: (s) => `${s.shipping_name}, ${s.shipping_address}` },
        { h: "Status", r: (s) => <Status value={s.status} id={`shipment-status-${s.id}`} /> },
        { h: "Action", r: (s) => STEPS[s.status] && (
          <div className="actions">
            <button className="btn btn-primary" data-testid={`wh-${STEPS[s.status][0]}-${s.id}`} onClick={() => run(() => api(`/warehouse/shipments/${s.id}/${STEPS[s.status][0]}`, { method: "POST", body: STEPS[s.status][0] === "dispatch" ? { tracking_number: track[s.id] || null } : undefined }), `${STEPS[s.status][1]} done`)}>{STEPS[s.status][1]}</button>
            {s.status === "PACKED" && <><label className="sr-only" htmlFor={`trk-${s.id}`}>Tracking number</label><input id={`trk-${s.id}`} data-testid={`wh-tracking-input-${s.id}`} placeholder="Tracking no. (optional)" value={track[s.id] || ""} onChange={(e) => setTrack({ ...track, [s.id]: e.target.value })} /></>}
            {s.status === "SHIPPED" && <button className="btn btn-ghost" data-testid={`wh-track-${s.id}`} onClick={() => run(() => api(`/warehouse/shipments/${s.id}/tracking`, { method: "POST", body: { tracking_status: "Out for delivery" } }), "Tracking updated")}>Out for delivery</button>}
          </div>) }]} />}</Async>
      <div className="layout-2 even">
        <section className="panel"><h2>Record stock movement</h2>
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); run(() => api("/warehouse/stock-movements", { method: "POST", body: { product_id: Number(mv.product_id), delta: Number(mv.delta), reason: mv.reason } }), "Movement recorded"); }} aria-label="Stock movement">
            <Field label="Product" id="mv-product"><select id="mv-product" data-testid="mv-product" value={mv.product_id} onChange={(e) => setMv({ ...mv, product_id: e.target.value })} required><option value="">Select...</option>{stock.data?.map((s) => <option key={s.product_id} value={s.product_id}>{s.name} ({s.quantity})</option>)}</select></Field>
            <Field label="Quantity change (negative for removals)" id="mv-delta"><input id="mv-delta" data-testid="mv-delta" type="number" value={mv.delta} onChange={(e) => setMv({ ...mv, delta: e.target.value })} required /></Field>
            <Field label="Reason" id="mv-reason"><select id="mv-reason" data-testid="mv-reason" value={mv.reason} onChange={(e) => setMv({ ...mv, reason: e.target.value })}><option>RECEIVE</option><option>ADJUST</option><option>DAMAGE</option></select></Field>
            <button className="btn btn-primary" data-testid="mv-submit">Record</button>
          </form></section>
        <section className="panel"><h2>Recent movements</h2>
          <Async q={moves}>{(m) => <Table testid="movements" rows={m.slice(0, 10)} cols={[{ h: "Product", r: (x) => `#${x.product_id}` }, { h: "Δ", r: (x) => x.delta }, { h: "Reason", r: (x) => x.reason }, { h: "Ref", r: (x) => x.reference || "-" }]} />}</Async></section>
      </div>
    </>
  );
}
