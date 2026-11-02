import { useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate, useLocation } from "react-router-dom";
import { homeFor, useAuth } from "./auth.jsx";
import { AccessDenied } from "./components/ui.jsx";
import { Home, Products, ProductDetail } from "./pages/Browse.jsx";
import { Cart, Checkout, Orders, OrderDetail, Wishlist, Profile, Help } from "./pages/Customer.jsx";
import Login from "./pages/Login.jsx";
import { SellerDashboard, SellerProducts, SellerProductForm, SellerInventory, SellerOrders, SellerReturns, SellerReport } from "./pages/Seller.jsx";
import Warehouse from "./pages/Warehouse.jsx";
import { SupportHome, SupportOrders, SupportRefunds, SupportReturns } from "./pages/Support.jsx";
import { AdminDashboard, AdminUsers, AdminSellers, AdminProducts, AdminOrders, AdminRefunds, AdminReviews, AdminAudit } from "./pages/Admin.jsx";

const NAV = {
  CUSTOMER: [["/", "Shop", "nav-home"], ["/orders", "Orders", "nav-orders"], ["/wishlist", "Wishlist", "nav-wishlist"], ["/profile", "Profile", "nav-profile"], ["/help", "Help", "nav-help"]],
  SELLER: [["/seller", "Dashboard", "nav-seller-dashboard"], ["/seller/products", "Products", "nav-seller-products"], ["/seller/inventory", "Inventory", "nav-seller-inventory"], ["/seller/orders", "Orders", "nav-seller-orders"], ["/seller/returns", "Returns & refunds", "nav-seller-returns"]],
  WAREHOUSE: [["/warehouse", "Fulfilment queue", "nav-warehouse"]],
  SUPPORT: [["/support", "Tickets", "nav-support-tickets"], ["/support/orders", "Order lookup", "nav-support-orders"], ["/support/refunds", "Refunds", "nav-support-refunds"], ["/support/returns", "Returns", "nav-support-returns"], ["/admin/reviews", "Review moderation", "nav-support-reviews"]],
  ADMIN: [["/admin", "Analytics", "nav-admin-dashboard"], ["/admin/users", "Users", "nav-admin-users"], ["/admin/sellers", "Sellers", "nav-admin-sellers"], ["/admin/products", "Moderation", "nav-admin-products"], ["/admin/orders", "Orders", "nav-admin-orders"], ["/admin/refunds", "Refunds & returns", "nav-admin-refunds"], ["/admin/reviews", "Reviews", "nav-admin-reviews"], ["/admin/audit-logs", "Audit logs", "nav-admin-audit"]],
};

function Header() {
  const { user, logout, cartCount } = useAuth();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const submit = (e) => { e.preventDefault(); nav(`/products?q=${encodeURIComponent(q)}`); };
  return (
    <header className="topbar">
      <div className="topbar-main">
        <Link to={user ? homeFor(user.role) : "/"} className="logo" data-testid="logo">Guard<span>Mart</span></Link>
        <form className="search" role="search" onSubmit={submit}>
          <label htmlFor="search-input" className="sr-only">Search products</label>
          <input id="search-input" data-testid="search-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search products, brands and more" />
          <button type="submit" data-testid="search-submit" aria-label="Search">Search</button>
        </form>
        <div className="topbar-right">
          {user ? (
            <>
              <span className="who" data-testid="current-user">{user.display_name} <small data-testid="current-role">{user.role}</small></span>
              {user.role === "CUSTOMER" && <Link to="/cart" className="cart-link" data-testid="nav-cart">Cart <b data-testid="cart-count">{cartCount}</b></Link>}
              <button className="link-btn" onClick={() => { logout(); nav("/login"); }} data-testid="logout">Sign out</button>
            </>
          ) : <Link to="/login" data-testid="nav-login">Sign in</Link>}
        </div>
      </div>
      <nav className="topbar-nav" aria-label="Main navigation">
        {(user ? NAV[user.role] : [["/products", "All products", "nav-products"]]).map(([to, label, tid]) => (
          <NavLink key={to} to={to} end={to === "/" || to === "/admin" || to === "/seller" || to === "/support"} data-testid={tid}>{label}</NavLink>
        ))}
        {(!user || user.role === "CUSTOMER") && <NavLink to="/products" data-testid="nav-products">All products</NavLink>}
      </nav>
    </header>
  );
}

function Guard({ roles, children }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <p className="muted">Loading...</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  if (roles && !roles.includes(user.role)) return <AccessDenied error={{ message: `This area is for ${roles.join("/")} accounts.`, decision: "BLOCK" }} />;
  return children;
}

export default function App() {
  const g = (roles, el) => <Guard roles={roles}>{el}</Guard>;
  const C = ["CUSTOMER"], S = ["SELLER"], A = ["ADMIN"], AS = ["ADMIN", "SUPPORT"];
  return (
    <>
      <Header />
      <main className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/products" element={<Products />} />
          <Route path="/products/:id" element={<ProductDetail />} />
          <Route path="/login" element={<Login />} />
          <Route path="/cart" element={g(C, <Cart />)} />
          <Route path="/checkout" element={g(C, <Checkout />)} />
          <Route path="/orders" element={g(C, <Orders />)} />
          <Route path="/orders/:id" element={g(null, <OrderDetail />)} />
          <Route path="/wishlist" element={g(C, <Wishlist />)} />
          <Route path="/profile" element={g(null, <Profile />)} />
          <Route path="/help" element={g(C, <Help />)} />
          <Route path="/seller" element={g(S, <SellerDashboard />)} />
          <Route path="/seller/products" element={g(S, <SellerProducts />)} />
          <Route path="/seller/products/new" element={g(S, <SellerProductForm />)} />
          <Route path="/seller/products/:id/edit" element={g(["SELLER", "ADMIN"], <SellerProductForm />)} />
          <Route path="/seller/inventory" element={g(S, <SellerInventory />)} />
          <Route path="/seller/orders" element={g(S, <SellerOrders />)} />
          <Route path="/seller/returns" element={g(S, <SellerReturns />)} />
          <Route path="/seller/reports/:sellerId" element={g(["SELLER", "ADMIN"], <SellerReport />)} />
          <Route path="/warehouse" element={g(["WAREHOUSE"], <Warehouse />)} />
          <Route path="/support" element={g(AS, <SupportHome />)} />
          <Route path="/support/orders" element={g(AS, <SupportOrders />)} />
          <Route path="/support/refunds" element={g(AS, <SupportRefunds />)} />
          <Route path="/support/returns" element={g(AS, <SupportReturns />)} />
          <Route path="/admin" element={g(A, <AdminDashboard />)} />
          <Route path="/admin/users" element={g(A, <AdminUsers />)} />
          <Route path="/admin/sellers" element={g(A, <AdminSellers />)} />
          <Route path="/admin/products" element={g(A, <AdminProducts />)} />
          <Route path="/admin/orders" element={g(A, <AdminOrders />)} />
          <Route path="/admin/refunds" element={g(A, <AdminRefunds />)} />
          <Route path="/admin/reviews" element={g(AS, <AdminReviews />)} />
          <Route path="/admin/audit-logs" element={g(A, <AdminAudit />)} />
          <Route path="*" element={<div className="panel" data-testid="not-found"><h2>Page not found</h2><Link to="/">Go home</Link></div>} />
        </Routes>
      </main>
      <footer className="footer">GuardMart · GuardSLM research sandbox · simulated payments only</footer>
    </>
  );
}
