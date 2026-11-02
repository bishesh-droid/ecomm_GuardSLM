import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, date, imageUrl, money } from "../api";
import { useAuth } from "../auth.jsx";
import { Async, Field, Flash, ProductCard, Status, Table, useAction, useAsync } from "../components/ui.jsx";

export function Cart() {
  const { refreshCart } = useAuth();
  const q = useAsync(() => api("/cart"), []);
  const [msg, run] = useAction(async () => { await q.reload(); await refreshCart(); });
  return (
    <>
      <h1>Shopping cart</h1>
      <Flash msg={msg} />
      <Async q={q}>{(c) => c.items.length === 0 ? (
        <div className="panel" data-testid="cart-empty">Your cart is empty. <Link to="/products">Continue shopping</Link></div>
      ) : (
        <div className="layout-2 right">
          <div>
            {c.items.map((i) => (
              <div className="panel cart-row" key={i.id} data-testid={`cart-item-${i.id}`}>
                <img src={imageUrl(i.product.image)} alt={i.product.name} />
                <div className="grow">
                  <Link to={`/products/${i.product.id}`}><b>{i.product.name}</b></Link>
                  <div className="muted small">Sold by {i.product.seller_name}</div>
                  <div className="price">{money(i.product.price)}</div>
                </div>
                <div className="field inline"><label htmlFor={`qty-${i.id}`}>Qty</label>
                  <input id={`qty-${i.id}`} data-testid={`cart-qty-${i.id}`} type="number" min="1" max="20" defaultValue={i.quantity}
                    onBlur={(e) => Number(e.target.value) !== i.quantity && run(() => api(`/cart/items/${i.id}`, { method: "PUT", body: { quantity: Number(e.target.value) } }), "Quantity updated")} /></div>
                <div data-testid={`cart-line-${i.id}`}><b>{money(i.line_total)}</b></div>
                <button className="btn btn-ghost" data-testid={`cart-remove-${i.id}`} onClick={() => run(() => api(`/cart/items/${i.id}`, { method: "DELETE" }), "Item removed")}>Remove</button>
              </div>))}
          </div>
          <aside className="panel summary">
            <h2>Order summary</h2>
            <p>Items: <b data-testid="cart-items-count">{c.count}</b></p>
            <p className="big">Total <b data-testid="cart-total">{money(c.total)}</b></p>
            <Link className="btn btn-accent block" to="/checkout" data-testid="proceed-checkout">Proceed to checkout</Link>
          </aside>
        </div>)}</Async>
    </>
  );
}

export function Checkout() {
  const nav = useNavigate();
  const { refreshCart } = useAuth();
  const cart = useAsync(() => api("/cart"), []);
  const addrs = useAsync(() => api("/auth/addresses"), []);
  const [addr, setAddr] = useState("");
  const [method, setMethod] = useState("CARD");
  const [token, setToken] = useState("tok_sim_ok");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pick = (m) => { setMethod(m); setToken(m === "CARD" ? "tok_sim_ok" : m === "UPI" ? "aarav@sim" : ""); };

  const place = async (e) => {
    e.preventDefault(); setError(""); setBusy(true);
    try {
      const res = await api("/orders/checkout", { method: "POST", body: { address_id: Number(addr || addrs.data[0]?.id), payment_method: method } });
      await refreshCart();
      if (method !== "COD") {
        const pay = await api(`/payments/${res.payment.id}/pay`, { method: "POST", body: { token } });
        if (pay.status === "FAILED") { nav(`/orders/${res.order.id}?payment=failed`); return; }
      }
      nav(`/orders/${res.order.id}?placed=1`);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  return (
    <>
      <h1>Checkout</h1>
      {error && <p className="alert alert-error" role="alert" data-testid="checkout-error">{error}</p>}
      <Async q={cart}>{(c) => c.items.length === 0 ? <div className="panel" data-testid="cart-empty">Your cart is empty.</div> : (
        <form className="layout-2 right" onSubmit={place} aria-label="Checkout form">
          <div>
            <section className="panel"><h2>1. Delivery address</h2>
              <Async q={addrs}>{(as) => as.length === 0 ? <p>Add an address in <Link to="/profile">your profile</Link> first.</p> : (
                <fieldset className="radio-group"><legend className="sr-only">Delivery address</legend>
                  {as.map((a, i) => (
                    <label key={a.id} className="radio" data-testid={`address-option-${a.id}`}>
                      <input type="radio" name="address" value={a.id} checked={(addr || as[0].id) == a.id} onChange={() => setAddr(a.id)} data-testid={`checkout-address-${a.id}`} />
                      <span><b>{a.label}</b> {a.full_name}, {a.line1}, {a.city} {a.postal_code}</span>
                    </label>))}
                </fieldset>)}</Async></section>
            <section className="panel"><h2>2. Payment (sandbox)</h2>
              <fieldset className="radio-group"><legend className="sr-only">Payment method</legend>
                {[["CARD", "Simulated card"], ["UPI", "Simulated UPI"], ["COD", "Cash on delivery"]].map(([m, label]) => (
                  <label key={m} className="radio"><input type="radio" name="method" checked={method === m} onChange={() => pick(m)} data-testid={`payment-method-${m}`} /><span>{label}</span></label>))}
              </fieldset>
              {method !== "COD" && (
                <Field label={method === "CARD" ? "Sandbox card token (tok_sim_ok succeeds, tok_sim_fail declines)" : "Sandbox UPI handle (name@sim succeeds, name@fail declines)"} id="pay-token">
                  <input id="pay-token" data-testid="payment-token" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" required />
                </Field>)}
              <p className="muted small">No real card numbers, bank credentials or UPI PINs are collected.</p>
            </section>
          </div>
          <aside className="panel summary"><h2>Summary</h2>
            {c.items.map((i) => <p key={i.id} className="small">{i.quantity} × {i.product.name}</p>)}
            <p className="big">Total <b data-testid="checkout-total">{money(c.total)}</b></p>
            <button className="btn btn-accent block" disabled={busy || !addrs.data?.length} data-testid="place-order">{busy ? "Placing..." : "Place order"}</button>
          </aside>
        </form>)}</Async>
    </>
  );
}

export function Orders() {
  const q = useAsync(() => api("/orders"), []);
  return (
    <>
      <h1>Your orders</h1>
      <Async q={q}>{(os) => os.length === 0 ? <div className="panel" data-testid="orders-empty">No orders yet.</div> : (
        <Table testid="orders-table" rows={os} cols={[
          { h: "Order", r: (o) => <Link to={`/orders/${o.id}`} data-testid={`order-link-${o.id}`}>#{o.id}</Link> },
          { h: "Placed", r: (o) => date(o.created_at) },
          { h: "Items", r: (o) => o.items.map((i) => `${i.quantity}× ${i.product_name}`).join(", ") },
          { h: "Total", r: (o) => money(o.total) },
          { h: "Status", r: (o) => <Status value={o.status} id={`order-status-${o.id}`} /> },
        ]} />)}</Async>
    </>
  );
}

const CANCELLABLE = ["PENDING_PAYMENT", "CONFIRMED", "PROCESSING", "PACKED", "SHIPPED"];

export function OrderDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const q = useAsync(() => api(`/orders/${id}`), [id]);
  const rets = useAsync(() => user.role === "CUSTOMER" ? api("/returns") : Promise.resolve([]), [id]);
  const [msg, run] = useAction(async () => { await q.reload(); await rets.reload(); });
  const [form, setForm] = useState(null); // {type,itemId}
  const [reason, setReason] = useState("");
  const [token, setToken] = useState("tok_sim_ok");
  const customer = user.role === "CUSTOMER";

  return (
    <Async q={q}>{(o) => {
      const payment = o.payments?.[o.payments.length - 1];
      const retPay = o.status === "PENDING_PAYMENT" && customer && o.payment_method !== "COD";
      const submitForm = (e) => {
        e.preventDefault();
        const path = form.type === "return" ? "/returns" : "/refunds";
        run(() => api(path, { method: "POST", body: { order_item_id: form.itemId, reason } }), form.type === "return" ? "Return requested" : "Refund requested").then(() => { setForm(null); setReason(""); });
      };
      const pay = () => run(async () => {
        let pid = payment?.id;
        if (!payment || payment.status !== "PENDING") pid = (await api("/payments", { method: "POST", body: { order_id: o.id } })).id;
        const r = await api(`/payments/${pid}/pay`, { method: "POST", body: { token } });
        if (r.status === "FAILED") throw new Error(r.failure_reason || "Payment failed");
      }, "Payment successful");
      return (
        <>
          <h1>Order #{o.id} <Status value={o.status} id="order-status" /></h1>
          <Flash msg={msg} />
          {new URLSearchParams(location.search).get("placed") && <p className="alert alert-ok" data-testid="order-placed">Thank you! Your order has been placed.</p>}
          <div className="layout-2 right">
            <div>
              <section className="panel"><h2>Items</h2>
                {o.items.map((i) => (
                  <div className="order-item" key={i.id} data-testid={`order-item-${i.id}`}>
                    <img src={imageUrl(i.image)} alt="" />
                    <div className="grow"><Link to={`/products/${i.product_id}`}>{i.product_name}</Link>
                      <div className="muted small">{i.quantity} × {money(i.unit_price)}</div></div>
                    <Status value={i.status} id={`item-status-${i.id}`} />
                    {customer && (
                      <div className="actions">
                        {i.status === "DELIVERED" && <>
                          <button className="btn btn-ghost" data-testid={`return-item-${i.id}`} onClick={() => setForm({ type: "return", itemId: i.id })}>Return</button>
                          <button className="btn btn-ghost" data-testid={`refund-item-${i.id}`} onClick={() => setForm({ type: "refund", itemId: i.id })}>Request refund</button>
                          <Link className="btn btn-ghost" to={`/products/${i.product_id}`} data-testid={`review-item-${i.id}`}>Review</Link></>}
                      </div>)}
                  </div>))}
                {form && (
                  <form className="inline-form" onSubmit={submitForm} aria-label={`${form.type} request`}>
                    <Field label={`Reason for ${form.type}`} id="reason"><input id="reason" data-testid="reason-input" value={reason} onChange={(e) => setReason(e.target.value)} required minLength={3} /></Field>
                    <button className="btn btn-primary" data-testid="reason-submit">Submit {form.type}</button>
                    <button type="button" className="btn btn-ghost" onClick={() => setForm(null)}>Cancel</button>
                  </form>)}
              </section>
              <section className="panel"><h2>Shipments</h2>
                {o.shipments.map((s) => (
                  <div key={s.id} className="shipment" data-testid={`shipment-${s.id}`}>
                    <Status value={s.status} id={`shipment-status-${s.id}`} />
                    <span className="muted small"> {s.carrier ? `${s.carrier} · ` : ""}{s.tracking_number ? <span data-testid={`tracking-${s.id}`}>{s.tracking_number}</span> : "Tracking not available yet"} {s.tracking_status && `· ${s.tracking_status}`}</span>
                  </div>))}
              </section>
              {rets.data?.filter((r) => r.order_id === o.id).length > 0 && <section className="panel"><h2>Returns</h2>
                <Table testid="order-returns" rows={rets.data.filter((r) => r.order_id === o.id)} cols={[
                  { h: "Return", r: (r) => `#${r.id}` }, { h: "Item", r: (r) => r.product_name }, { h: "Reason", r: (r) => r.reason },
                  { h: "Status", r: (r) => <Status value={r.status} id={`return-status-${r.id}`} /> }]} /></section>}
            </div>
            <aside className="panel summary">
              <h2>Summary</h2>
              <p>Total: <b data-testid="order-total">{money(o.total)}</b></p>
              {o.shipping_address && <p className="small" data-testid="order-address"><b>Ship to</b><br />{o.shipping_name}<br />{o.shipping_address}</p>}
              {payment && <p className="small">Payment: {payment.method} · <Status value={payment.status} id="payment-status" />{payment.failure_reason && <><br /><span className="err" data-testid="payment-failure">{payment.failure_reason}</span></>}</p>}
              {retPay && (
                <div className="inline-form">
                  <Field label="Sandbox payment token" id="retry-token"><input id="retry-token" data-testid="retry-token" value={token} onChange={(e) => setToken(e.target.value)} /></Field>
                  <button className="btn btn-accent block" data-testid="pay-now" onClick={pay}>Pay now</button>
                </div>)}
              {customer && CANCELLABLE.includes(o.status) && (
                <button className="btn btn-danger block" data-testid={`cancel-order-${o.id}`} onClick={() => run(() => api(`/orders/${o.id}/cancel`, { method: "POST" }), "Order cancelled")}>Cancel order</button>)}
            </aside>
          </div>
        </>);
    }}</Async>
  );
}

export function Wishlist() {
  const { refreshCart } = useAuth();
  const q = useAsync(() => api("/wishlist"), []);
  const [msg, run] = useAction(q.reload);
  return (
    <>
      <h1>Your wishlist</h1><Flash msg={msg} />
      <Async q={q}>{(items) => items.length === 0 ? <div className="panel" data-testid="wishlist-empty">Nothing saved yet.</div> : (
        <div className="grid" data-testid="wishlist-grid">{items.map((w) => (
          <div key={w.id} data-testid={`wishlist-item-${w.product.id}`}>
            <ProductCard p={w.product} />
            <div className="row pad">
              <button className="btn btn-accent" data-testid={`wishlist-to-cart-${w.product.id}`} onClick={() => run(async () => { await api("/cart/items", { method: "POST", body: { product_id: w.product.id } }); await refreshCart(); }, "Moved to cart")}>Add to cart</button>
              <button className="btn btn-ghost" data-testid={`wishlist-remove-${w.product.id}`} onClick={() => run(() => api(`/wishlist/items/${w.product.id}`, { method: "DELETE" }), "Removed")}>Remove</button>
            </div></div>))}</div>)}</Async>
    </>
  );
}

const EMPTY = { label: "Home", full_name: "", line1: "", city: "", state: "", postal_code: "" };

export function Profile() {
  const { user } = useAuth();
  const [name, setName] = useState(user.display_name);
  const [phone, setPhone] = useState(user.phone || "");
  const addrs = useAsync(() => user.role === "CUSTOMER" ? api("/auth/addresses") : Promise.resolve([]), []);
  const methods = useAsync(() => user.role === "CUSTOMER" ? api("/payments/methods") : Promise.resolve([]), []);
  const [msg, run] = useAction(addrs.reload);
  const [a, setA] = useState(EMPTY);
  return (
    <>
      <h1>My profile</h1><Flash msg={msg} />
      <section className="panel"><h2>Account</h2>
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); run(() => api("/auth/me", { method: "PATCH", body: { display_name: name, phone } }), "Profile saved"); }}>
          <p>Username: <b data-testid="profile-username">{user.username}</b> · Role: {user.role}</p>
          <Field label="Display name" id="p-name"><input id="p-name" data-testid="profile-name" value={name} onChange={(e) => setName(e.target.value)} required /></Field>
          <Field label="Phone" id="p-phone"><input id="p-phone" data-testid="profile-phone" value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
          <button className="btn btn-primary" data-testid="profile-save">Save</button>
        </form></section>
      {user.role === "CUSTOMER" && <>
        <section className="panel"><h2>Addresses</h2>
          <Async q={addrs}>{(as) => <ul className="plain" data-testid="address-list">{as.map((x) => (
            <li key={x.id} data-testid={`address-${x.id}`}><b>{x.label}</b>: {x.full_name}, {x.line1}, {x.city}, {x.state} {x.postal_code}
              <button className="link-btn" data-testid={`address-delete-${x.id}`} onClick={() => run(() => api(`/auth/addresses/${x.id}`, { method: "DELETE" }), "Address removed")}>Delete</button></li>))}</ul>}</Async>
          <form className="form-grid" onSubmit={(e) => { e.preventDefault(); run(() => api("/auth/addresses", { method: "POST", body: a }), "Address added").then(() => setA(EMPTY)); }} aria-label="Add address">
            {[["label", "Label"], ["full_name", "Full name"], ["line1", "Address line"], ["city", "City"], ["state", "State"], ["postal_code", "Postal code"]].map(([k, l]) => (
              <Field key={k} label={l} id={`addr-${k}`}><input id={`addr-${k}`} data-testid={`addr-${k}`} value={a[k]} onChange={(e) => setA({ ...a, [k]: e.target.value })} required /></Field>))}
            <button className="btn btn-primary" data-testid="address-add">Add address</button>
          </form></section>
        <section className="panel"><h2>Saved sandbox payment tokens</h2>
          <Async q={methods}>{(ms) => <ul className="plain">{ms.map((m) => <li key={m.id}>{m.kind} · {m.label} · <code>{m.token}</code></li>)}</ul>}</Async></section></>}
    </>
  );
}

export function Help() {
  const q = useAsync(() => api("/support/tickets"), []);
  const orders = useAsync(() => api("/orders"), []);
  const [msg, run] = useAction(q.reload);
  const [t, setT] = useState({ subject: "", message: "", order_id: "" });
  return (
    <>
      <h1>Help & support</h1><Flash msg={msg} />
      <section className="panel"><h2>Contact support</h2>
        <form className="inline-form" onSubmit={(e) => { e.preventDefault(); run(() => api("/support/tickets", { method: "POST", body: { ...t, order_id: t.order_id ? Number(t.order_id) : null } }), "Ticket created").then(() => setT({ subject: "", message: "", order_id: "" })); }} aria-label="New ticket">
          <Field label="Subject" id="t-subject"><input id="t-subject" data-testid="ticket-subject" value={t.subject} onChange={(e) => setT({ ...t, subject: e.target.value })} required minLength={3} /></Field>
          <Field label="Related order (optional)" id="t-order"><select id="t-order" data-testid="ticket-order" value={t.order_id} onChange={(e) => setT({ ...t, order_id: e.target.value })}><option value="">None</option>{orders.data?.map((o) => <option key={o.id} value={o.id}>Order #{o.id}</option>)}</select></Field>
          <Field label="Message" id="t-message"><textarea id="t-message" data-testid="ticket-message" value={t.message} onChange={(e) => setT({ ...t, message: e.target.value })} required minLength={3} /></Field>
          <button className="btn btn-primary" data-testid="ticket-submit">Submit ticket</button>
        </form></section>
      <section className="panel"><h2>Your tickets</h2>
        <Async q={q}>{(ts) => <Table testid="tickets-table" rows={ts} cols={[
          { h: "#", r: (x) => x.id }, { h: "Subject", r: (x) => x.subject }, { h: "Status", r: (x) => <Status value={x.status} /> }, { h: "Response", r: (x) => x.response || "-" }]} />}</Async></section>
    </>
  );
}
