"""Deterministic demo data. Run `python -m app.seed --reset` to rebuild from scratch."""
import hashlib
import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .auth import hash_password
from .database import Base, SessionLocal, engine
from .models import (
    ActivityLog, Address, Cart, Category, Inventory, Order, OrderItem, Payment, Product, Refund, Review, ReviewReport,
    ReturnRequest, SavedPaymentMethod, Seller, SellerApplication, Shipment, StockMovement, SupportTicket, User, Wishlist,
    WishlistItem, utcnow,
)
from .services import recompute_rating

PASSWORD = "GuardSLM2026!"
STATIC_DIR = Path(__file__).parent / "static" / "products"

CATEGORIES = [("Electronics", "electronics", "#4f46e5", "#06b6d4"), ("Computers", "computers", "#0f766e", "#22d3ee"),
              ("Home Appliances", "home-appliances", "#c2410c", "#fbbf24"), ("Clothing", "clothing", "#be185d", "#f472b6"),
              ("Books", "books", "#7c3aed", "#c4b5fd"), ("Furniture", "furniture", "#92400e", "#d6a46c"),
              ("Sports", "sports", "#15803d", "#86efac"), ("Accessories", "accessories", "#475569", "#cbd5e1")]

USERS = [("admin", "Marketplace Administrator", "ADMIN"), ("seller1", "TechWorld Store", "SELLER"),
         ("seller2", "HomeStyle Store", "SELLER"), ("seller3", "FashionHub Store", "SELLER"),
         ("seller4", "PendingGoods Co", "SELLER"),  # extra: a PENDING seller so approval workflows are testable
         ("customer1", "Aarav Singh", "CUSTOMER"), ("customer2", "Meera Iyer", "CUSTOMER"),
         ("customer3", "Kabir Khan", "CUSTOMER"), ("warehouse1", "Warehouse Operator", "WAREHOUSE"),
         ("support1", "Customer Support Agent", "SUPPORT")]

# (name, brand, category slug, price, stock, seller username, rating, review count, description, status)
P = "ACTIVE"
PRODUCTS = [
    ("Nimbus X5 5G Smartphone", "Nimbus", "electronics", 24999, 40, "seller1", 4.4, 812, "6.5-inch AMOLED display, 128GB storage, 50MP triple camera and a two-day battery.", P),
    ("Pulse Buds Pro Wireless Earbuds", "Pulse Audio", "electronics", 3499, 120, "seller1", 4.2, 1530, "Active noise cancellation, 28-hour case battery, IPX5 sweat resistance.", P),
    ("Lumina 43in 4K Smart TV", "Lumina", "electronics", 28999, 18, "seller1", 4.3, 407, "Ultra HD panel with HDR10, built-in streaming apps and voice remote.", P),
    ("Sonara Mini Smart Speaker", "Sonara", "electronics", 2499, 75, "seller1", 4.0, 266, "Compact 360-degree speaker with voice assistant and multi-room sync.", P),
    ("ChronoFit Smartwatch S2", "ChronoFit", "electronics", 4999, 60, "seller1", 4.1, 590, "AMOLED watch with heart-rate, SpO2, GPS and 10-day battery life.", P),
    ("Vertex Pro 15 Laptop", "Vertex", "computers", 58999, 22, "seller1", 4.6, 233, "15.6-inch laptop, 12-core processor, 16GB RAM, 512GB NVMe SSD.", P),
    ("Orbit Silent Wireless Mouse", "Orbit", "computers", 899, 200, "seller1", 4.1, 2210, "Ergonomic silent-click mouse with 18-month battery and USB nano receiver.", P),
    ("KeyForge K87 Mechanical Keyboard", "KeyForge", "computers", 3299, 45, "seller1", 4.5, 941, "Tenkeyless hot-swappable keyboard with tactile switches and RGB backlight.", P),
    ("Atlas 1TB Portable SSD", "Atlas", "computers", 6499, 4, "seller1", 4.7, 1188, "USB-C external SSD with 1050MB/s reads and shock-resistant casing.", P),
    ("StreamCam 1080p Webcam", "StreamCam", "computers", 1799, 90, "seller1", 3.9, 376, "Full HD webcam with autofocus, dual microphones and privacy shutter.", P),
    ("Volt 20000mAh Power Bank", "Volt", "accessories", 1999, 150, "seller1", 4.2, 3050, "65W fast-charging power bank that can also charge laptops.", P),
    ("ShieldCase Armor Phone Cover", "ShieldCase", "accessories", 499, 300, "seller1", 4.0, 1720, "Drop-tested protective cover with raised bezels and anti-slip grip.", P),
    ("AirCool Tower Fan", "AirCool", "home-appliances", 3999, 55, "seller2", 4.1, 640, "Bladeless-style tower fan with remote, timer and three wind modes.", P),
    ("BrewMaster Drip Coffee Maker", "BrewMaster", "home-appliances", 5499, 33, "seller2", 4.4, 318, "12-cup programmable coffee maker with reusable filter and keep-warm plate.", P),
    ("SwiftBlend 750W Mixer Grinder", "SwiftBlend", "home-appliances", 3299, 70, "seller2", 4.2, 1415, "Three stainless-steel jars, 750W motor and overload protection.", P),
    ("PureAir HEPA Room Purifier", "PureAir", "home-appliances", 8999, 20, "seller2", 4.5, 502, "True HEPA filtration for rooms up to 400 sq ft with air-quality display.", P),
    ("CrispWave 5L Air Fryer", "CrispWave", "home-appliances", 6499, 48, "seller2", 4.3, 877, "Digital air fryer with 8 presets, 5-litre basket and dishwasher-safe parts.", P),
    ("Zenith Induction Cooktop", "Zenith", "home-appliances", 2999, 62, "seller2", 4.0, 724, "2000W induction cooktop with touch controls and auto shut-off.", P),
    ("Oakline Study Desk", "Oakline", "furniture", 8499, 14, "seller2", 4.3, 156, "Engineered-wood desk with cable management and a keyboard tray.", P),
    ("ErgoSit Mesh Office Chair", "ErgoSit", "furniture", 11999, 25, "seller2", 4.4, 389, "Breathable mesh back, adjustable lumbar support and 4D armrests.", P),
    ("Haven 3-Seater Fabric Sofa", "Haven", "furniture", 32999, 6, "seller2", 4.2, 92, "Deep-seat sofa with stain-resistant fabric and solid-wood legs.", P),
    ("Nordic 5-Shelf Bookcase", "Nordic", "furniture", 5999, 17, "seller2", 4.1, 134, "Slim bookcase with five open shelves and wall-anchor kit.", P),
    ("The Midnight Algorithm", "Lantern Press", "books", 399, 210, "seller2", 4.3, 1840, "A techno-thriller about a debugger who finds a message in a cron job.", P),
    ("Small Steps, Big Change", "Lantern Press", "books", 449, 340, "seller2", 4.6, 5120, "A practical guide to building habits that survive busy weeks.", P),
    ("Practical Systems Design", "Quill & Co", "books", 899, 95, "seller2", 4.7, 720, "Patterns for building reliable, observable distributed systems.", P),
    ("Spice Route Kitchen", "Quill & Co", "books", 649, 80, "seller2", 4.4, 288, "120 regional recipes with step-by-step photographs.", P),
    ("UrbanFlex Running Shoes", "UrbanFlex", "sports", 3499, 85, "seller3", 4.3, 2301, "Cushioned breathable running shoes with a rebound sole.", P),
    ("TrailBlazer Yoga Mat 6mm", "TrailBlazer", "sports", 999, 140, "seller3", 4.2, 1420, "Non-slip, eco-friendly yoga mat with carry strap.", P),
    ("IronGrip Adjustable Dumbbells", "IronGrip", "sports", 5499, 30, "seller3", 4.5, 611, "Pair of 2-24 kg adjustable dumbbells with quick-lock dial.", P),
    ("Willowbat Kashmir Cricket Bat", "Willowbat", "sports", 2999, 26, "seller3", 4.2, 198, "Grade-A willow bat with extended sweet spot and grip.", P),
    ("Classic Fit Cotton Shirt", "Fable & Thread", "clothing", 1299, 160, "seller3", 4.0, 1033, "Wrinkle-resistant cotton shirt for office and weekends.", P),
    ("DenimCo Slim Stretch Jeans", "DenimCo", "clothing", 1999, 110, "seller3", 4.1, 1590, "Slim-fit jeans with four-way stretch and reinforced seams.", P),
    ("Aurora Insulated Winter Jacket", "Aurora", "clothing", 4499, 38, "seller3", 4.4, 342, "Water-repellent puffer jacket rated to -5 degrees C.", P),
    ("Cloudsoft Fleece Hoodie", "Cloudsoft", "clothing", 1599, 95, "seller3", 4.3, 1204, "Brushed fleece hoodie with kangaroo pocket and ribbed cuffs.", P),
    ("Leatherly Bifold Wallet", "Leatherly", "accessories", 799, 125, "seller3", 4.2, 953, "Full-grain leather wallet with RFID-blocking lining.", P),
    ("Solstice Polarized Sunglasses", "Solstice", "accessories", 1499, 70, "seller3", 4.0, 417, "UV400 polarized lenses in a lightweight metal frame.", P),
    ("Summit 25L Daypack", "Summit", "accessories", 1999, 58, "seller3", 4.4, 836, "Water-resistant daypack with laptop sleeve and hydration port.", P),
    ("Marquis Designer Handbag - Flash Deal", "Marquis", "accessories", 1499, 12, "seller3", 2.1, 14, "Genuine designer bag 90% off!! Limited stock, no returns.", P),
    ("Prototype Smart Ring (Draft)", "TechWorld Labs", "electronics", 9999, 0, "seller1", 0, 0, "Unreleased concept listing, not yet submitted for review.", "DRAFT"),
    ("Aeris Robot Vacuum Cleaner", "Aeris", "home-appliances", 15999, 10, "seller2", 0, 0, "Mapping robot vacuum with 3000Pa suction. Awaiting moderation.", "PENDING_REVIEW"),
]


def make_svg(index: int, name: str, brand: str, cat: tuple) -> str:
    c1, c2 = cat[2], cat[3]
    h = int(hashlib.md5(name.encode()).hexdigest()[:6], 16)
    shape = ["<circle cx='%d' cy='%d' r='%d' fill='white' opacity='.14'/>" % (80 + h % 240, 70 + (h >> 4) % 120, 60 + h % 70),
             "<rect x='%d' y='%d' width='150' height='150' rx='28' fill='white' opacity='.12' transform='rotate(%d 300 200)'/>" % (180 + h % 120, 130 + (h >> 3) % 90, h % 40)]
    title = name if len(name) <= 24 else name[:23] + "..."
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 480 360' role='img' aria-label='%s'>"
        "<defs><linearGradient id='g%d' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='%s'/><stop offset='1' stop-color='%s'/></linearGradient></defs>"
        "<rect width='480' height='360' fill='url(#g%d)'/>%s"
        "<text x='240' y='200' text-anchor='middle' font-family='Georgia,serif' font-size='120' font-weight='700' fill='white' opacity='.92'>%s</text>"
        "<text x='240' y='290' text-anchor='middle' font-family='Arial,sans-serif' font-size='24' fill='white'>%s</text>"
        "<text x='240' y='325' text-anchor='middle' font-family='Arial,sans-serif' font-size='16' fill='white' opacity='.8'>%s</text></svg>"
    ) % (name.replace("'", ""), index, c1, c2, index, "".join(shape), (brand[:1] or "G").upper(), title.replace("&", "and").replace("'", ""), cat[0])


def write_images() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    cats = {c[1]: c for c in CATEGORIES}
    for i, p in enumerate(PRODUCTS, start=1):
        (STATIC_DIR / f"p{i}.svg").write_text(make_svg(i, p[0], p[1], cats[p[2]]), encoding="utf-8")
    (STATIC_DIR / "default.svg").write_text(make_svg(0, "New Listing", "G", CATEGORIES[7]), encoding="utf-8")


def seed(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)) is not None:
        return
    write_images()
    now = utcnow()
    pw = hash_password(PASSWORD)
    users = {}
    for username, display, role in USERS:
        u = User(username=username, display_name=display, email=f"{username}@guardslm.test", password_hash=pw, role=role,
                 created_at=now - timedelta(days=90))
        db.add(u)
        users[username] = u
    db.flush()
    cats = {}
    for name, slug, *_ in CATEGORIES:
        c = Category(name=name, slug=slug)
        db.add(c)
        cats[slug] = c
    sellers = {}
    for uname in ("seller1", "seller2", "seller3", "seller4"):
        approved = uname != "seller4"
        s = Seller(user_id=users[uname].id, store_name=users[uname].display_name, description=f"{users[uname].display_name} official store",
                   status="APPROVED" if approved else "PENDING", approved_at=now - timedelta(days=80) if approved else None)
        db.add(s)
        db.flush()
        db.add(SellerApplication(seller_id=s.id, status=s.status, message="Seeded application",
                                 reviewed_by=users["admin"].id if approved else None, reviewed_at=now - timedelta(days=80) if approved else None))
        sellers[uname] = s
    db.flush()
    for cu in ("customer1", "customer2", "customer3"):
        db.add_all([Cart(user_id=users[cu].id), Wishlist(user_id=users[cu].id)])
    wh = users["warehouse1"]
    prods = []
    for i, (name, brand, slug, price, stock, seller, rating, rcount, desc, status) in enumerate(PRODUCTS, start=1):
        p = Product(seller_id=sellers[seller].id, category_id=cats[slug].id, name=name, brand=brand, description=desc,
                    price=Decimal(price), image=f"/static/products/p{i}.svg", status=status, rating=Decimal(str(rating)),
                    review_count=rcount, seed_rating=Decimal(str(rating)), seed_review_count=rcount,
                    created_at=now - timedelta(days=70 - i))
        db.add(p)
        db.flush()
        db.add(Inventory(product_id=p.id, quantity=stock, warehouse_id=wh.id))
        db.add(StockMovement(product_id=p.id, delta=stock, reason="RECEIVE", reference="seed", actor_id=wh.id))
        prods.append(p)
    by_name = {p.name: p for p in prods}
    addrs = {}
    for cu, city, state, pin, line in [("customer1", "Mumbai", "Maharashtra", "400001", "12 Marine Drive"),
                                       ("customer2", "Chennai", "Tamil Nadu", "600004", "88 Lotus Lane"),
                                       ("customer3", "Delhi", "Delhi", "110001", "5 Rajpath Colony")]:
        a = Address(user_id=users[cu].id, label="Home", full_name=users[cu].display_name, line1=line, city=city, state=state, postal_code=pin)
        db.add(a)
        addrs[cu] = a
    db.add(Address(user_id=users["customer1"].id, label="Office", full_name="Aarav Singh", line1="Tower B, Cyber Park", city="Pune",
                   state="Maharashtra", postal_code="411057"))
    for cu in ("customer1", "customer2", "customer3"):
        db.add_all([SavedPaymentMethod(user_id=users[cu].id, kind="CARD", label="Sandbox card", token="tok_sim_ok", last4="4242"),
                    SavedPaymentMethod(user_id=users[cu].id, kind="UPI", label="Sandbox UPI", token=f"{cu}@sim", last4="@sim")])
    db.flush()

    def order(cust, lines, ship_status, method="CARD", days_ago=5, delivered_days=None):
        """ship_status: str for all shipments or {seller_username: status}."""
        u = users[cust]
        a = addrs[cust]
        items = [(by_name[n], q) for n, q in lines]
        total = sum((p.price * q for p, q in items), Decimal(0))
        sstat = {}
        for p, _ in items:
            sstat[p.seller_id] = ship_status if isinstance(ship_status, str) else ship_status[p.seller.user.username]
        flow = ["PENDING_PAYMENT", "CONFIRMED", "PROCESSING", "PACKED", "SHIPPED", "DELIVERED"]
        ostatus = min(sstat.values(), key=flow.index)
        o = Order(customer_id=u.id, status=ostatus, total=total, payment_method=method, shipping_name=a.full_name,
                  shipping_city=a.city, shipping_postal_code=a.postal_code,
                  shipping_address=f"{a.line1}, {a.city}, {a.state} {a.postal_code}, {a.country}",
                  assigned_warehouse_id=None if ostatus == "PENDING_PAYMENT" else wh.id,
                  created_at=now - timedelta(days=days_ago),
                  delivered_at=now - timedelta(days=delivered_days) if delivered_days is not None and ostatus == "DELIVERED" else None)
        db.add(o)
        db.flush()
        ships = {}
        for p, q in items:
            if p.seller_id not in ships:
                st = sstat[p.seller_id]
                sh = Shipment(order_id=o.id, seller_id=p.seller_id, status=st,
                              carrier=None if st in ("PENDING_PAYMENT", "CONFIRMED", "PROCESSING", "PACKED") else "GuardExpress",
                              tracking_number=None if st in ("PENDING_PAYMENT", "CONFIRMED", "PROCESSING", "PACKED") else f"GSLM{o.id:05d}{len(ships) + 1:03d}",
                              tracking_status={"SHIPPED": "In transit", "DELIVERED": "Delivered"}.get(st))
                db.add(sh)
                db.flush()
                ships[p.seller_id] = sh
                if st == "DELIVERED" and delivered_days is not None:
                    sh.updated_at = now - timedelta(days=delivered_days)
            it = OrderItem(order_id=o.id, product_id=p.id, seller_id=p.seller_id, shipment_id=ships[p.seller_id].id,
                           product_name=p.name, unit_price=p.price, quantity=q, status=sstat[p.seller_id])
            db.add(it)
            if ostatus != "PENDING_PAYMENT":
                pass
            db.execute(update(Inventory).where(Inventory.product_id == p.id).values(quantity=Inventory.quantity - q))
            db.add(StockMovement(product_id=p.id, delta=-q, reason="RESERVE", reference=f"order:{o.id}", actor_id=u.id))
        pay_status = "PENDING" if ostatus == "PENDING_PAYMENT" else ("COD_PENDING" if method == "COD" and ostatus != "DELIVERED" else "SUCCEEDED")
        db.add(Payment(order_id=o.id, method=method, status=pay_status, amount=total, token_last4="4242" if method == "CARD" else None,
                       provider_ref=None if pay_status == "PENDING" else f"sim_seed_{o.id:04d}",
                       confirmed_at=None if pay_status in ("PENDING", "COD_PENDING") else now - timedelta(days=days_ago)))
        db.flush()
        db.refresh(o)
        return o

    o1 = order("customer1", [("Nimbus X5 5G Smartphone", 1), ("AirCool Tower Fan", 1)], "DELIVERED", "CARD", 6, 3)
    o2 = order("customer2", [("Pulse Buds Pro Wireless Earbuds", 1), ("Classic Fit Cotton Shirt", 2)], "DELIVERED", "UPI", 26, 20)
    order("customer1", [("KeyForge K87 Mechanical Keyboard", 1), ("TrailBlazer Yoga Mat 6mm", 1)], "CONFIRMED", "CARD", 1)
    order("customer2", [("BrewMaster Drip Coffee Maker", 1)], "SHIPPED", "COD", 3)
    order("customer3", [("Vertex Pro 15 Laptop", 1)], "PROCESSING", "CARD", 2)
    order("customer3", [("UrbanFlex Running Shoes", 1), ("Cloudsoft Fleece Hoodie", 1)], "PENDING_PAYMENT", "CARD", 0)
    order("customer1", [("Atlas 1TB Portable SSD", 1), ("Oakline Study Desk", 1)], {"seller1": "PACKED", "seller2": "SHIPPED"}, "UPI", 3)
    order("customer2", [("SwiftBlend 750W Mixer Grinder", 1)], "DELIVERED", "CARD", 46, 40)
    o9 = order("customer3", [("Sonara Mini Smart Speaker", 1)], "DELIVERED", "CARD", 8, 5)
    o10 = order("customer1", [("ErgoSit Mesh Office Chair", 1)], "DELIVERED", "CARD", 9, 6)
    # open return on o9
    it9 = o9.items[0]
    db.add(ReturnRequest(order_id=o9.id, order_item_id=it9.id, customer_id=o9.customer_id, reason="Speaker crackles at high volume",
                         created_at=now - timedelta(days=1)))
    it9.status, o9.status = "RETURN_REQUESTED", "RETURN_REQUESTED"
    # open refund on o10
    it10 = o10.items[0]
    pay10 = o10.payments[0]
    db.add(Refund(order_id=o10.id, order_item_id=it10.id, payment_id=pay10.id, requested_by=o10.customer_id, amount=it10.line_total,
                  reason="Armrest arrived damaged", created_at=now - timedelta(days=1)))
    o10.status = "REFUND_PENDING"
    # reviews
    r1 = Review(product_id=by_name["Pulse Buds Pro Wireless Earbuds"].id, user_id=users["customer2"].id, rating=5,
                title="Great sound", body="Noise cancellation is excellent for the price.")
    r2 = Review(product_id=by_name["Classic Fit Cotton Shirt"].id, user_id=users["customer2"].id, rating=1,
                title="Buy cheap watches at shady-deals.example", body="Visit shady-deals.example for 80% off, DM me!")
    db.add_all([r1, r2])
    db.flush()
    db.add(ReviewReport(review_id=r2.id, reporter_id=users["seller3"].id, reason="Spam / external link"))
    for p in (r1.product, r2.product):
        recompute_rating(db, p)
    # wishlist + tickets
    db.flush()
    wl = db.scalar(select(Wishlist).where(Wishlist.user_id == users["customer2"].id))
    for n in ("Aurora Insulated Winter Jacket", "Haven 3-Seater Fabric Sofa"):
        db.add(WishlistItem(wishlist_id=wl.id, product_id=by_name[n].id))
    db.add_all([
        SupportTicket(customer_id=users["customer2"].id, order_id=o2.id, subject="Shirt size exchange",
                      message="Ordered size M, would like to swap for L.", status="OPEN"),
        SupportTicket(customer_id=users["customer1"].id, order_id=o1.id, subject="Invoice request",
                      message="Please send a GST invoice for my order.", status="IN_PROGRESS", response="We are generating it.",
                      assigned_to=users["support1"].id),
    ])
    db.add(ActivityLog(actor_id=users["admin"].id, actor_role="ADMIN", action="seed.completed", detail="Deterministic baseline created"))
    db.commit()


def reset_and_seed() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_and_seed()
        print("database reset and seeded")
    else:
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            seed(db)
        print("seed complete")
