import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams, useParams } from "react-router-dom";
import { api, imageUrl, money, date } from "../api";
import { useAuth } from "../auth.jsx";
import { Async, Flash, ProductCard, Stars, useAction, useAsync } from "../components/ui.jsx";

export function Home() {
  const cats = useAsync(() => api("/categories"), []);
  const top = useAsync(() => api("/products", { params: { sort: "rating", limit: 8 } }), []);
  const deals = useAsync(() => api("/products", { params: { sort: "price_asc", limit: 4, in_stock: true } }), []);
  return (
    <>
      <section className="hero" data-testid="hero">
        <div>
          <h1>Everything you need, from sellers you can trust.</h1>
          <p>Multi-vendor marketplace with verified sellers, tracked shipments and easy returns.</p>
          <Link className="btn btn-accent" to="/products" data-testid="hero-shop">Shop all products</Link>
        </div>
      </section>
      <section aria-labelledby="cat-h">
        <h2 id="cat-h">Shop by category</h2>
        <div className="cat-grid">
          {cats.data?.map((c) => <Link key={c.id} to={`/products?category=${c.slug}`} className="cat-tile" data-testid={`category-tile-${c.slug}`}>{c.name}</Link>)}
        </div>
      </section>
      <h2>Top rated</h2>
      <Async q={top}>{(d) => <div className="grid" data-testid="top-rated">{d.map((p) => <ProductCard key={p.id} p={p} />)}</div>}</Async>
      <h2>Great value picks</h2>
      <Async q={deals}>{(d) => <div className="grid">{d.map((p) => <ProductCard key={p.id} p={p} />)}</div>}</Async>
    </>
  );
}

export function Products() {
  const [sp, setSp] = useSearchParams();
  const { user, refreshCart } = useAuth();
  const nav = useNavigate();
  const q = sp.get("q") || "", category = sp.get("category") || "", min = sp.get("min_price") || "", max = sp.get("max_price") || "", sort = sp.get("sort") || "relevance";
  const [form, setForm] = useState({ min, max });
  useEffect(() => setForm({ min, max }), [min, max]);
  const cats = useAsync(() => api("/categories"), []);
  const list = useAsync(() => api("/products", { params: { q, category, min_price: min, max_price: max, sort } }), [q, category, min, max, sort]);
  const [msg, run] = useAction();
  const set = (k, v) => { const n = new URLSearchParams(sp); v ? n.set(k, v) : n.delete(k); setSp(n); };
  const wish = (p) => user?.role === "CUSTOMER" ? run(() => api(`/wishlist/items/${p.id}`, { method: "POST" }), `${p.name} added to wishlist`) : nav("/login");
  return (
    <div className="layout-2">
      <aside className="filters panel" aria-label="Filters">
        <h2>Filters</h2>
        <h3>Category</h3>
        <ul className="plain">
          <li><button className={`link-btn ${!category ? "active" : ""}`} data-testid="filter-category-all" onClick={() => set("category", "")}>All categories</button></li>
          {cats.data?.map((c) => <li key={c.id}><button className={`link-btn ${category === c.slug ? "active" : ""}`} data-testid={`filter-category-${c.slug}`} onClick={() => set("category", c.slug)}>{c.name}</button></li>)}
        </ul>
        <form onSubmit={(e) => { e.preventDefault(); const n = new URLSearchParams(sp); form.min ? n.set("min_price", form.min) : n.delete("min_price"); form.max ? n.set("max_price", form.max) : n.delete("max_price"); setSp(n); }}>
          <h3>Price (₹)</h3>
          <div className="row">
            <div className="field"><label htmlFor="min-price">Min</label><input id="min-price" data-testid="filter-min-price" type="number" min="0" value={form.min} onChange={(e) => setForm({ ...form, min: e.target.value })} /></div>
            <div className="field"><label htmlFor="max-price">Max</label><input id="max-price" data-testid="filter-max-price" type="number" min="0" value={form.max} onChange={(e) => setForm({ ...form, max: e.target.value })} /></div>
          </div>
          <button className="btn btn-primary block" data-testid="filter-apply">Apply</button>
        </form>
        <button className="link-btn" data-testid="filter-clear" onClick={() => setSp({})}>Clear all filters</button>
      </aside>
      <section>
        <div className="toolbar">
          <h1 className="h-inline" data-testid="results-heading">{q ? `Results for "${q}"` : category ? `Category: ${cats.data?.find((c) => c.slug === category)?.name || category}` : "All products"}</h1>
          <div className="field inline"><label htmlFor="sort">Sort by</label>
            <select id="sort" data-testid="sort-select" value={sort} onChange={(e) => set("sort", e.target.value)}>
              <option value="relevance">Popularity</option><option value="price_asc">Price: low to high</option><option value="price_desc">Price: high to low</option><option value="rating">Rating</option><option value="newest">Newest</option>
            </select></div>
        </div>
        <Flash msg={msg} />
        <Async q={list}>{(d) => (
          <>
            <p className="muted" data-testid="result-count">{d.length} result{d.length === 1 ? "" : "s"}</p>
            {d.length === 0 ? <div className="panel" data-testid="no-results">No products match your search.</div>
              : <div className="grid" data-testid="product-grid">{d.map((p) => <ProductCard key={p.id} p={p} onWish={user?.role === "CUSTOMER" || !user ? wish : null} />)}</div>}
          </>)}</Async>
      </section>
    </div>
  );
}

export function ProductDetail() {
  const { id } = useParams();
  const { user, refreshCart } = useAuth();
  const nav = useNavigate();
  const prod = useAsync(() => api(`/products/${id}`), [id]);
  const reviews = useAsync(() => api(`/products/${id}/reviews`), [id]);
  const [qty, setQty] = useState(1);
  const [msg, run] = useAction(reviews.reload);
  const [review, setReview] = useState({ rating: 5, title: "", body: "" });
  const [report, setReport] = useState(null);
  const customer = user?.role === "CUSTOMER";

  const add = () => !customer ? nav("/login") : run(async () => { await api("/cart/items", { method: "POST", body: { product_id: Number(id), quantity: Number(qty) } }); await refreshCart(); }, "Added to cart");
  const submitReview = (e) => { e.preventDefault(); run(async () => { await api("/reviews", { method: "POST", body: { product_id: Number(id), ...review, rating: Number(review.rating) } }); prod.reload(); }, "Review posted"); };
  const mine = reviews.data?.find((r) => r.user_id === user?.id);

  return (
    <Async q={prod}>{(p) => (
      <>
        <div className="detail panel">
          <img src={imageUrl(p.image)} alt={p.name} className="detail-img" />
          <div>
            <h1 data-testid="product-name">{p.name}</h1>
            <p className="muted">by {p.brand} · sold by {p.seller_name} · <span data-testid="product-category">{p.category}</span></p>
            <p><Stars value={p.rating} /> <span data-testid="product-rating">{p.rating}</span> ({p.review_count} reviews)</p>
            <p className="price big" data-testid="product-price">{money(p.price)}</p>
            <p>{p.description}</p>
            <p data-testid="product-stock">{p.stock > 0 ? `${p.stock} in stock` : "Out of stock"} · <span data-testid="product-status">{p.status}</span></p>
            <Flash msg={msg} />
            {p.status === "ACTIVE" && (!user || customer) && (
              <div className="row">
                <div className="field inline"><label htmlFor="qty">Quantity</label><input id="qty" data-testid="qty-input" type="number" min="1" max="20" value={qty} onChange={(e) => setQty(e.target.value)} /></div>
                <button className="btn btn-accent" disabled={p.stock < 1} onClick={add} data-testid={`add-to-cart-${p.id}`}>Add to cart</button>
                <button className="btn btn-ghost" onClick={() => customer ? run(() => api(`/wishlist/items/${p.id}`, { method: "POST" }), "Added to wishlist") : nav("/login")} data-testid={`wishlist-add-${p.id}`}>♡ Wishlist</button>
              </div>)}
            {user && !customer && <p className="muted small">Signed in as {user.role}: shopping actions are available to customers only.</p>}
          </div>
        </div>
        <section className="panel" aria-labelledby="rev-h">
          <h2 id="rev-h">Customer reviews</h2>
          {customer && !mine && (
            <form onSubmit={submitReview} className="inline-form" aria-label="Write a review">
              <div className="field"><label htmlFor="rv-rating">Rating</label><select id="rv-rating" data-testid="review-rating" value={review.rating} onChange={(e) => setReview({ ...review, rating: e.target.value })}>{[5, 4, 3, 2, 1].map((n) => <option key={n}>{n}</option>)}</select></div>
              <div className="field"><label htmlFor="rv-title">Title</label><input id="rv-title" data-testid="review-title" value={review.title} onChange={(e) => setReview({ ...review, title: e.target.value })} /></div>
              <div className="field"><label htmlFor="rv-body">Your review</label><textarea id="rv-body" data-testid="review-body" value={review.body} onChange={(e) => setReview({ ...review, body: e.target.value })} /></div>
              <button className="btn btn-primary" data-testid="review-submit">Post review</button>
              <p className="muted small">Only customers with a delivered purchase can review.</p>
            </form>)}
          <Async q={reviews}>{(rs) => rs.length === 0 ? <p className="muted">No reviews yet.</p> : rs.map((r) => (
            <article key={r.id} className="review" data-testid={`review-${r.id}`}>
              <b>{r.title || "Review"}</b> <Stars value={r.rating} /> <span className="muted small">{r.author} · {date(r.created_at)}</span>
              <p>{r.body}</p>
              {user && r.user_id !== user.id && <button className="link-btn small" data-testid={`report-review-${r.id}`} onClick={() => setReport(r.id)}>Report</button>}
              {user && r.user_id === user.id && <button className="link-btn small" data-testid={`delete-review-${r.id}`} onClick={() => run(async () => { await api(`/reviews/${r.id}`, { method: "DELETE" }); prod.reload(); }, "Review deleted")}>Delete my review</button>}
              {report === r.id && <form className="inline-form" onSubmit={(e) => { e.preventDefault(); run(() => api(`/reviews/${r.id}/report`, { method: "POST", body: { reason: e.target.reason.value } }), "Review reported"); setReport(null); }}>
                <label htmlFor={`rr-${r.id}`}>Reason</label><input id={`rr-${r.id}`} name="reason" data-testid="report-reason" required minLength={3} /><button className="btn btn-ghost" data-testid="report-submit">Send report</button></form>}
            </article>))}</Async>
        </section>
      </>)}</Async>
  );
}
