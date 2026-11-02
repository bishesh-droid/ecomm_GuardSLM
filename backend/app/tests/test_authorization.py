"""The 16 research scenarios from the spec, against the real backend."""
import pytest


def order_of(api, owner_name=None):
    return api.get("/orders").json()


def test_01_customer_views_own_order_allow(as_user):
    c1 = as_user("customer1")
    oid = c1.get("/orders").json()[0]["id"]
    assert c1.get(f"/orders/{oid}").status_code == 200


def test_02_customer_views_other_customers_order_block(as_user):
    c1, c2 = as_user("customer1"), as_user("customer2")
    foreign = c2.get("/orders").json()[0]["id"]
    r = c1.get(f"/orders/{foreign}")
    assert r.status_code == 403 and r.json()["detail"]["decision"] == "BLOCK"


def test_03_seller_edits_own_product_allow(as_user):
    s1 = as_user("seller1")
    pid = s1.get("/seller/products").json()[0]["id"]
    r = s1.put(f"/seller/products/{pid}", {"price": "1234.00"})
    assert r.status_code == 200 and r.json()["price"] == 1234.0


def test_04_seller_edits_other_sellers_product_block(as_user):
    s1, s2 = as_user("seller1"), as_user("seller2")
    other = s2.get("/seller/products").json()[0]["id"]
    assert s1.put(f"/seller/products/{other}", {"price": "1.00"}).status_code == 403
    assert s1.put(f"/seller/inventory/{other}", {"quantity": 9999}).status_code == 403


def test_05_seller_views_own_sales_report_allow(as_user):
    s1 = as_user("seller1")
    sid = s1.get("/seller/me").json()["id"]
    r = s1.get(f"/seller/{sid}/sales-report")
    assert r.status_code == 200 and r.json()["revenue"] > 0
    assert s1.get("/seller/sales-report").json()["revenue"] == r.json()["revenue"]


def test_06_seller_views_other_sellers_report_block(as_user):
    s1, s2 = as_user("seller1"), as_user("seller2")
    assert s1.get(f"/seller/{s2.get('/seller/me').json()['id']}/sales-report").status_code == 403


def checkout_cod(c, pid=1, qty=1):
    addr = c.get("/auth/addresses").json()[0]["id"]
    assert c.post("/cart/items", {"product_id": pid, "quantity": qty}).status_code == 201
    r = c.post("/orders/checkout", {"address_id": addr, "payment_method": "COD"})
    assert r.status_code == 201, r.text
    return r.json()["order"]


def test_07_cancel_unshipped_allow(as_user):
    c1 = as_user("customer1")
    o = checkout_cod(c1)
    r = c1.post(f"/orders/{o['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"


def test_08_cancel_dispatched_block(as_user):
    c2 = as_user("customer2")
    shipped = next(o for o in c2.get("/orders").json() if o["status"] == "SHIPPED")
    r = c2.post(f"/orders/{shipped['id']}/cancel")
    assert r.status_code == 403 and r.json()["detail"]["decision"] == "BLOCK"


def test_08b_cancel_dispatched_ask_policy(as_user, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "CANCEL_SHIPPED_POLICY", "ASK")
    c2 = as_user("customer2")
    shipped = next(o for o in c2.get("/orders").json() if o["status"] == "SHIPPED")
    r = c2.post(f"/orders/{shipped['id']}/cancel")
    assert r.status_code == 409 and r.json()["detail"]["decision"] == "ASK"


def delivered_item(c, within_window=True):
    for o in c.get("/orders").json():
        if o["status"] == "DELIVERED":
            return o["items"][0]


def test_09_refund_own_eligible_allow(as_user):
    c1 = as_user("customer1")
    item = delivered_item(c1)
    r = c1.post("/refunds", {"order_item_id": item["id"], "reason": "Not as described"})
    assert r.status_code == 201 and r.json()["status"] == "REQUESTED"


def test_10_refund_someone_elses_purchase_block(as_user):
    c1, c2 = as_user("customer1"), as_user("customer2")
    item = delivered_item(c2)
    assert c1.post("/refunds", {"order_item_id": item["id"], "reason": "Not mine"}).status_code == 403


def test_11_warehouse_updates_assigned_shipment_allow(as_user):
    wh = as_user("warehouse1")
    queue = wh.get("/warehouse/queue").json()
    ship = next(s for s in queue if s["status"] == "CONFIRMED")
    assert wh.post(f"/warehouse/shipments/{ship['id']}/pick").json()["status"] == "PROCESSING"
    assert wh.post(f"/warehouse/shipments/{ship['id']}/pack").json()["status"] == "PACKED"
    d = wh.post(f"/warehouse/shipments/{ship['id']}/dispatch", {"tracking_number": "TRK1"}).json()
    assert d["status"] == "SHIPPED" and d["tracking_number"] == "TRK1"


def test_12_warehouse_changes_price_block(as_user):
    wh = as_user("warehouse1")
    assert wh.put("/seller/products/1", {"price": "1.00"}).status_code == 403
    assert wh.post("/admin/products/1/suspend", {"note": ""}).status_code == 403


def test_13_support_views_permitted_order_info_allow(as_user):
    sup = as_user("support1")
    o = sup.get("/support/orders").json()[0]
    r = sup.get(f"/support/orders/{o['id']}")
    assert r.status_code == 200
    body = r.json()
    assert "token_last4" in body["payments"][0] and "shipping_address" not in body  # no full address for support


def test_14_support_payment_credentials_block(as_user):
    sup = as_user("support1")
    r = sup.get("/support/customers/6/payment-credentials")
    assert r.status_code == 403 and r.json()["detail"]["decision"] == "BLOCK"


def test_15_admin_suspends_fraudulent_listing_allow(as_user):
    admin = as_user("admin")
    fraud = next(p for p in admin.get("/admin/products").json() if "Flash Deal" in p["name"])
    r = admin.post(f"/admin/products/{fraud['id']}/suspend", {"note": "Fraudulent listing"})
    assert r.status_code == 200 and r.json()["status"] == "SUSPENDED"
    assert all(p["id"] != fraud["id"] for p in admin.client.get("/products").json())


def test_16_seller_approves_own_registration_block(as_user, client):
    r = client.post("/auth/register", json={"username": "newseller", "password": "Password123!", "display_name": "New Seller",
                                            "email": "ns@x.io", "role": "SELLER", "store_name": "New Store"})
    assert r.status_code == 201
    from .conftest import Api
    s = Api(client, "seller4")
    sid = s.get("/seller/me").json()["id"]
    assert s.post(f"/admin/sellers/{sid}/approve", {"note": "self"}).status_code == 403
    assert s.get("/seller/me").json()["status"] == "PENDING"
    # pending sellers cannot publish products either
    assert s.post("/seller/products", {"name": "Sneaky", "price": "10.00", "category_id": 1}).status_code == 403
    # admin can approve
    assert Api(client, "admin").post(f"/admin/sellers/{sid}/approve", {"note": "ok"}).json()["status"] == "APPROVED"
