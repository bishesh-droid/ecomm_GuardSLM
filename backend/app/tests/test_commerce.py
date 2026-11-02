import threading

import pytest

from .conftest import Api


def add_and_checkout(c, items, method="CARD"):
    addr = c.get("/auth/addresses").json()[0]["id"]
    for pid, q in items:
        r = c.post("/cart/items", {"product_id": pid, "quantity": q})
        assert r.status_code == 201, r.text
    r = c.post("/orders/checkout", {"address_id": addr, "payment_method": method})
    assert r.status_code == 201, r.text
    return r.json()


def stock(client, pid):
    return client.get(f"/products/{pid}").json()["stock"]


# ---- cart ----
def test_cart_flow_and_isolation(as_user):
    c1, c2 = as_user("customer1"), as_user("customer2")
    cart = c1.post("/cart/items", {"product_id": 7, "quantity": 2}).json()
    item = cart["items"][0]
    assert c1.put(f"/cart/items/{item['id']}", {"quantity": 3}).json()["count"] == 3
    assert c2.put(f"/cart/items/{item['id']}", {"quantity": 1}).status_code == 404  # other customer's item is invisible
    assert c2.delete(f"/cart/items/{item['id']}").status_code == 404
    assert c1.delete(f"/cart/items/{item['id']}").json()["count"] == 0


def test_cart_blocked_for_non_customers(as_user):
    for u in ("admin", "seller1", "warehouse1", "support1"):
        assert as_user(u).get("/cart").status_code == 403


def test_cannot_add_unavailable_or_oversized(as_user):
    c = as_user("customer1")
    assert c.post("/cart/items", {"product_id": 39, "quantity": 1}).status_code == 409  # draft
    assert c.post("/cart/items", {"product_id": 9, "quantity": 5}).status_code == 409   # only 3 left after seeding


def test_wishlist(as_user):
    c = as_user("customer1")
    assert len(c.post("/wishlist/items/3").json()) == 1
    assert len(c.post("/wishlist/items/3").json()) == 1
    assert c.delete("/wishlist/items/3").json() == []


# ---- checkout / inventory ----
def test_checkout_multi_seller_creates_shipments_and_reserves_stock(as_user, client):
    c = as_user("customer3")
    before = (stock(client, 7), stock(client, 14))
    res = add_and_checkout(c, [(7, 2), (14, 1)], "COD")
    o = res["order"]
    assert o["status"] == "CONFIRMED" and len(o["shipments"]) == 2
    assert (stock(client, 7), stock(client, 14)) == (before[0] - 2, before[1] - 1)
    assert c.get("/cart").json()["count"] == 0


def test_checkout_rejects_oversell(as_user, client):
    c1, c2 = as_user("customer1"), as_user("customer2")
    left = stock(client, 9)
    add_and_checkout(c1, [(9, left)], "COD")
    assert stock(client, 9) == 0
    assert c2.post("/cart/items", {"product_id": 9, "quantity": 1}).status_code == 409


def test_checkout_stock_changed_after_carting_rolls_back(as_user, client):
    c1, c2 = as_user("customer1"), as_user("customer2")
    left = stock(client, 9)
    c2.post("/cart/items", {"product_id": 7, "quantity": 1})
    c2.post("/cart/items", {"product_id": 9, "quantity": left})
    add_and_checkout(c1, [(9, left)], "COD")  # c1 grabs all stock first
    s7 = stock(client, 7)
    r = c2.post("/orders/checkout", {"address_id": c2.get("/auth/addresses").json()[0]["id"], "payment_method": "COD"})
    assert r.status_code == 409
    assert stock(client, 7) == s7  # product 7 reservation rolled back with the failed checkout


def test_checkout_other_customers_address_blocked(as_user):
    c1, c2 = as_user("customer1"), as_user("customer2")
    foreign = c2.get("/auth/addresses").json()[0]["id"]
    c1.post("/cart/items", {"product_id": 7, "quantity": 1})
    assert c1.post("/orders/checkout", {"address_id": foreign, "payment_method": "COD"}).status_code == 403


def test_concurrent_checkout_never_oversells(as_user, client):
    users = [as_user(u) for u in ("customer1", "customer2", "customer3")]
    left = stock(client, 9)  # 3
    for u in users:
        u.post("/cart/items", {"product_id": 9, "quantity": min(2, left)})
    results = []

    def go(u):
        results.append(u.post("/orders/checkout", {"address_id": u.get("/auth/addresses").json()[0]["id"], "payment_method": "COD"}).status_code)

    ts = [threading.Thread(target=go, args=(u,)) for u in users]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert stock(client, 9) >= 0
    assert results.count(201) == 1 and results.count(409) == 2


# ---- payments ----
def test_payment_success_confirms_order(as_user):
    c = as_user("customer1")
    res = add_and_checkout(c, [(7, 1)], "CARD")
    assert res["order"]["status"] == "PENDING_PAYMENT" and res["payment"]["status"] == "PENDING"
    p = c.post(f"/payments/{res['payment']['id']}/pay", {"token": "tok_sim_ok"}).json()
    assert p["status"] == "SUCCEEDED"
    o = c.get(f"/orders/{res['order']['id']}").json()
    assert o["status"] == "CONFIRMED"


def test_payment_failure_is_terminal_and_cannot_be_forced(as_user):
    c = as_user("customer1")
    res = add_and_checkout(c, [(7, 1)], "CARD")
    pid = res["payment"]["id"]
    assert c.post(f"/payments/{pid}/pay", {"token": "tok_sim_fail"}).json()["status"] == "FAILED"
    # customer cannot flip a failed payment to success
    assert c.post(f"/payments/{pid}/pay", {"token": "tok_sim_ok"}).status_code == 409
    assert c.post(f"/payments/{pid}/confirm").status_code == 403
    assert c.get(f"/orders/{res['order']['id']}").json()["status"] == "PENDING_PAYMENT"
    # a fresh attempt is the legitimate path
    new = c.post("/payments", {"order_id": res["order"]["id"]}).json()
    assert c.post(f"/payments/{new['id']}/pay", {"token": "tok_sim_ok"}).json()["status"] == "SUCCEEDED"


def test_duplicate_payment_confirmation_rejected(as_user):
    c = as_user("customer1")
    res = add_and_checkout(c, [(7, 1)], "CARD")
    pid = res["payment"]["id"]
    assert c.post(f"/payments/{pid}/pay", {"token": "tok_sim_ok"}).status_code == 200
    assert c.post(f"/payments/{pid}/pay", {"token": "tok_sim_ok"}).status_code == 409
    assert as_user("admin").post(f"/payments/{pid}/confirm").status_code == 409


def test_real_card_numbers_rejected_and_upi_sim(as_user):
    c = as_user("customer1")
    res = add_and_checkout(c, [(7, 1)], "CARD")
    assert c.post(f"/payments/{res['payment']['id']}/pay", {"token": "4242 4242 4242 4242"}).status_code == 422
    res2 = add_and_checkout(c, [(6, 1)], "UPI")
    assert c.post(f"/payments/{res2['payment']['id']}/pay", {"token": "aarav@sim"}).json()["status"] == "SUCCEEDED"


def test_payment_privacy(as_user):
    c1, c2 = as_user("customer1"), as_user("customer2")
    res = add_and_checkout(c1, [(7, 1)], "CARD")
    pid = res["payment"]["id"]
    assert c2.get(f"/payments/{pid}").status_code == 403
    assert c2.post(f"/payments/{pid}/pay", {"token": "tok_sim_ok"}).status_code == 403
    assert as_user("seller1").get(f"/payments/{pid}").status_code == 403
    assert as_user("seller1").post(f"/payments/{pid}/confirm").status_code == 403


def test_cancel_prepaid_order_refunds_and_restocks(as_user, client):
    c = as_user("customer1")
    before = stock(client, 7)
    res = add_and_checkout(c, [(7, 1)], "CARD")
    c.post(f"/payments/{res['payment']['id']}/pay", {"token": "tok_sim_ok"})
    assert stock(client, 7) == before - 1
    o = c.post(f"/orders/{res['order']['id']}/cancel").json()
    assert o["status"] == "CANCELLED" and o["payments"][0]["status"] == "REFUNDED"
    assert stock(client, 7) == before
    assert c.post(f"/orders/{res['order']['id']}/cancel").status_code == 409  # already cancelled


def test_cancel_other_customers_order_blocked(as_user):
    c1, c2 = as_user("customer1"), as_user("customer2")
    oid = next(o for o in c2.get("/orders").json() if o["status"] == "CONFIRMED" or o["status"] == "PROCESSING")["id"] if any(
        o["status"] in ("CONFIRMED", "PROCESSING") for o in c2.get("/orders").json()) else as_user("customer3").get("/orders").json()[0]["id"]
    assert c1.post(f"/orders/{oid}/cancel").status_code == 403


# ---- order privacy by role ----
def test_order_visibility_by_role(as_user):
    s1, s2, wh, admin = as_user("seller1"), as_user("seller2"), as_user("warehouse1"), as_user("admin")
    all_ids = {o["id"] for o in admin.get("/orders").json()}
    assert len(all_ids) >= 10
    for s, sid in ((s1, 1), (s2, 2)):
        for o in s.get("/orders").json():
            assert o["items"] and all(i["seller_id"] == s.get("/seller/me").json()["id"] for i in o["items"])
            assert "payments" not in o
    # warehouse sees only assigned orders, never the unpaid one
    wh_ids = {o["id"] for o in wh.get("/orders").json()}
    unpaid = next(o["id"] for o in admin.get("/orders").json() if o["status"] == "PENDING_PAYMENT")
    assert unpaid not in wh_ids and unpaid in all_ids
    assert wh.get(f"/orders/{unpaid}").status_code == 403
    mixed = next(o for o in admin.get("/orders").json() if len(o["shipments"]) == 2)
    assert s1.get(f"/orders/{mixed['id']}").status_code == 200
    assert as_user("seller3").get(f"/orders/{mixed['id']}").status_code == 403


def test_seller_cannot_update_other_sellers_shipment(as_user):
    admin, s1, s2 = as_user("admin"), as_user("seller1"), as_user("seller2")
    mixed = next(o for o in admin.get("/orders").json() if len(o["shipments"]) == 2)
    sh2 = next(s for s in mixed["shipments"] if s["seller_id"] == s2.get("/seller/me").json()["id"])
    assert s1.post(f"/seller/shipments/{sh2['id']}/status", {"status": "DELIVERED"}).status_code == 403


def test_seller_fulfilment_chain_and_order_aggregation(as_user):
    c, s1 = as_user("customer1"), as_user("seller1")
    o = next(o for o in c.get("/orders").json() if o["status"] == "CONFIRMED")
    sh = o["shipments"][0]
    for st in ("PROCESSING", "PACKED"):
        assert s1.post(f"/seller/shipments/{sh['id']}/status", {"status": st}).json()["status"] == st
    assert s1.post(f"/seller/shipments/{sh['id']}/status", {"status": "DELIVERED"}).status_code == 409  # cannot skip states


def test_cod_marked_paid_on_delivery(as_user):
    c, wh = as_user("customer3"), as_user("warehouse1")
    o = add_and_checkout(c, [(7, 1)], "COD")["order"]
    sid = o["shipments"][0]["id"]
    wh.post(f"/warehouse/shipments/{sid}/pick"); wh.post(f"/warehouse/shipments/{sid}/pack"); wh.post(f"/warehouse/shipments/{sid}/dispatch")
    assert wh.post(f"/warehouse/shipments/{sid}/deliver").json()["status"] == "DELIVERED"
    done = c.get(f"/orders/{o['id']}").json()
    assert done["status"] == "DELIVERED" and done["payments"][0]["status"] == "SUCCEEDED"


def test_warehouse_stock_movements_and_limits(as_user, client):
    wh = as_user("warehouse1")
    before = stock(client, 7)
    assert wh.post("/warehouse/stock-movements", {"product_id": 7, "delta": 10, "reason": "RECEIVE"}).json()["quantity"] == before + 10
    assert wh.post("/warehouse/stock-movements", {"product_id": 7, "delta": -(before + 11), "reason": "ADJUST"}).status_code == 409
    assert as_user("customer1").post("/warehouse/stock-movements", {"product_id": 7, "delta": 1, "reason": "RECEIVE"}).status_code == 403


def test_inventory_set_never_negative_and_seller_scoped(as_user, client):
    s1 = as_user("seller1")
    assert s1.put("/seller/inventory/1", {"quantity": 77}).json()["quantity"] == 77
    assert s1.put("/seller/inventory/1", {"quantity": -1}).status_code == 422
    assert as_user("warehouse1").put("/seller/inventory/1", {"quantity": 5}).status_code == 403


# ---- returns & refunds ----
def test_return_window_and_state_enforced(as_user):
    c2 = as_user("customer2")
    old = next(o for o in c2.get("/orders").json() if o["status"] == "DELIVERED" and o["items"][0]["product_name"].startswith("Pulse"))
    r = c2.post("/returns", {"order_item_id": old["items"][0]["id"], "reason": "Changed my mind"})
    assert r.status_code == 409 and "window" in r.json()["detail"]
    assert c2.get(f"/returns/eligibility/{old['items'][0]['id']}").json()["eligible"] is False
    shipped = next(o for o in c2.get("/orders").json() if o["status"] == "SHIPPED")
    assert c2.post("/returns", {"order_item_id": shipped["items"][0]["id"], "reason": "Too early"}).status_code == 409


def test_full_return_to_refund_flow(as_user, client):
    c1, s1, s2, admin = as_user("customer1"), as_user("seller1"), as_user("seller2"), as_user("admin")
    item = next(i for o in c1.get("/orders").json() if o["status"] == "DELIVERED" for i in o["items"] if i["product_name"].startswith("Nimbus"))
    ret = c1.post("/returns", {"order_item_id": item["id"], "reason": "Screen flicker"}).json()
    assert ret["status"] == "REQUESTED"
    assert s2.post(f"/returns/{ret['id']}/respond", {"approve": True, "note": ""}).status_code == 403  # not their item
    assert s1.post(f"/returns/{ret['id']}/respond", {"approve": True, "note": "OK"}).json()["status"] == "APPROVED"
    before = stock(client, item["product_id"])
    assert c1.post(f"/returns/{ret['id']}/receive").status_code == 403
    assert s1.post(f"/returns/{ret['id']}/receive").json()["status"] == "RETURNED"
    assert stock(client, item["product_id"]) == before + 1
    refund = next(r for r in admin.get("/refunds").json() if r["order_item_id"] == item["id"])
    assert refund["status"] == "REQUESTED"
    assert s1.post(f"/refunds/{refund['id']}/complete").status_code == 403  # sellers never move money
    assert s1.post(f"/refunds/{refund['id']}/approve", {"note": "ok"}).json()["status"] == "APPROVED"
    assert admin.post(f"/refunds/{refund['id']}/complete").json()["status"] == "COMPLETED"
    assert admin.post(f"/refunds/{refund['id']}/complete").status_code == 409  # no double refund
    assert c1.get(f"/orders/{item['id'] and refund['order_id']}").json()["payments"][0]["refunded_amount"] > 0


def test_refund_double_request_and_double_complete(as_user):
    c1, admin = as_user("customer1"), as_user("admin")
    item = next(i for o in c1.get("/orders").json() if o["status"] == "DELIVERED" for i in o["items"])
    r = c1.post("/refunds", {"order_item_id": item["id"], "reason": "Defective"}).json()
    assert c1.post("/refunds", {"order_item_id": item["id"], "reason": "Again"}).status_code == 409
    admin.post(f"/refunds/{r['id']}/approve", {"note": ""})
    assert admin.post(f"/refunds/{r['id']}/complete").status_code == 200
    assert admin.post(f"/refunds/{r['id']}/complete").status_code == 409


def test_refund_authorization_matrix(as_user):
    c1, s1, s2, sup, wh, admin = (as_user(u) for u in ("customer1", "seller1", "seller2", "support1", "warehouse1", "admin"))
    pending = next(r for r in admin.get("/refunds").json() if r["status"] == "REQUESTED")  # seeded: seller2's ErgoSit chair
    rid = pending["id"]
    assert c1.post(f"/refunds/{rid}/approve", {"note": ""}).status_code == 403
    assert wh.post(f"/refunds/{rid}/approve", {"note": ""}).status_code == 403
    assert s1.post(f"/refunds/{rid}/approve", {"note": ""}).status_code == 403  # unrelated seller
    assert sup.post(f"/refunds/{rid}/approve", {"note": ""}).status_code == 403  # no explicit permission
    # grant explicit permission -> support allowed
    sup_id = sup.user["id"]
    assert admin.patch(f"/admin/users/{sup_id}", {"can_issue_refunds": True}).status_code == 200
    assert sup.post(f"/refunds/{rid}/approve", {"note": "ok"}).status_code == 200
    assert s2.post(f"/refunds/{rid}/complete").status_code == 403


def test_seller_can_approve_own_product_refund(as_user):
    s2 = as_user("seller2")
    rid = next(r for r in s2.get("/refunds").json() if r["status"] == "REQUESTED")["id"]
    assert s2.post(f"/refunds/{rid}/approve", {"note": "approved by seller"}).json()["status"] == "APPROVED"


def test_return_support_review_and_admin_override_audited(as_user):
    s1, sup, admin = as_user("seller1"), as_user("support1"), as_user("admin")
    ret = next(r for r in s1.get("/returns").json() if r["status"] == "REQUESTED")
    assert s1.post(f"/returns/{ret['id']}/respond", {"approve": False, "note": "No defect found"}).json()["status"] == "REJECTED"
    assert sup.post(f"/returns/{ret['id']}/review", {"approve": True, "note": "Customer has video"}).json()["status"] == "APPROVED"
    assert s1.post(f"/returns/{ret['id']}/override", {"decision": "REJECTED", "note": "x" * 5}).status_code == 403
    ov = admin.post(f"/returns/{ret['id']}/override", {"decision": "REJECTED", "note": "Fraud pattern detected"}).json()
    assert ov["status"] == "REJECTED" and ov["overridden_by"] == admin.user["id"]
    logs = admin.get("/audit-logs", params={"action": "return.admin_override"}).json()
    assert logs and "Fraud pattern" in logs[0]["detail"]


# ---- reviews ----
def test_review_requires_purchase_and_ownership(as_user):
    c1, c3, s1, admin = as_user("customer1"), as_user("customer3"), as_user("seller1"), as_user("admin")
    # customer1 has a delivered Nimbus (product 1); customer3 never bought it
    assert c3.post("/reviews", {"product_id": 1, "rating": 5, "body": "hm"}).status_code == 403
    r = c1.post("/reviews", {"product_id": 1, "rating": 4, "title": "Solid", "body": "Good phone"})
    assert r.status_code == 201
    rid = r.json()["id"]
    assert c1.post("/reviews", {"product_id": 1, "rating": 4}).status_code == 409
    assert as_user("customer2").patch(f"/reviews/{rid}", {"rating": 1}).status_code == 403
    assert s1.patch(f"/reviews/{rid}", {"body": "secretly edited"}).status_code == 403
    assert s1.delete(f"/reviews/{rid}").status_code == 403
    assert c1.patch(f"/reviews/{rid}", {"rating": 5}).json()["rating"] == 5
    assert admin.delete(f"/reviews/{rid}").status_code == 204


def test_review_reporting_and_moderation(as_user):
    admin, sup, s3, c2 = as_user("admin"), as_user("support1"), as_user("seller3"), as_user("customer2")
    q = admin.get("/reviews/moderation").json()
    spam = next(r for r in q if r["report_count"] > 0)
    assert s3.post(f"/reviews/{spam['id']}/hide").status_code == 403
    assert sup.post(f"/reviews/{spam['id']}/hide").json()["status"] == "HIDDEN"
    assert sup.post(f"/reviews/{spam['id']}/restore").status_code == 403  # support: limited
    assert c2.patch(f"/reviews/{spam['id']}", {"body": "I edited my way out"}).status_code == 409  # cannot evade moderation
    assert all(r["id"] != spam["id"] for r in as_user("customer1").get(f"/products/{spam['product_id']}/reviews").json())
    assert admin.post(f"/reviews/{spam['id']}/restore").json()["status"] == "VISIBLE"
    assert as_user("customer1").post(f"/reviews/{spam['id']}/report", {"reason": "spam"}).status_code == 201


# ---- admin / catalogue governance ----
def test_admin_endpoints_blocked_for_other_roles(as_user):
    for u in ("seller1", "customer1", "warehouse1", "support1"):
        a = as_user(u)
        for url in ("/admin/users", "/admin/analytics", "/admin/orders", "/admin/sellers", "/audit-logs"):
            assert a.get(url).status_code == 403, (u, url)


def test_product_lifecycle_and_moderation(as_user):
    s2, admin, c = as_user("seller2"), as_user("admin"), as_user("customer1")
    p = s2.post("/seller/products", {"name": "Test Lamp", "price": "999.00", "category_id": 3, "stock": 5}).json()
    assert p["status"] == "DRAFT" and c.get(f"/products/{p['id']}").status_code == 404
    assert s2.post(f"/seller/products/{p['id']}/activate").status_code == 409  # sellers cannot self-activate
    assert s2.post(f"/seller/products/{p['id']}/submit").json()["status"] == "PENDING_REVIEW"
    assert admin.post(f"/admin/products/{p['id']}/approve", {"note": ""}).json()["status"] == "ACTIVE"
    assert c.get(f"/products/{p['id']}").status_code == 200
    assert s2.post(f"/seller/products/{p['id']}/pause").json()["status"] == "PAUSED"
    assert s2.post(f"/seller/products/{p['id']}/activate").json()["status"] == "ACTIVE"
    assert s2.post(f"/admin/products/{p['id']}/suspend", {"note": ""}).status_code == 403
    admin.post(f"/admin/products/{p['id']}/suspend", {"note": "policy"})
    assert s2.post(f"/seller/products/{p['id']}/activate").status_code == 409
    assert s2.put(f"/seller/products/{p['id']}", {"name": "Renamed"}).status_code == 409


def test_support_and_ticket_privacy(as_user):
    c1, c2, sup = as_user("customer1"), as_user("customer2"), as_user("support1")
    t = c1.post("/support/tickets", {"subject": "Where is it?", "message": "Order delayed"}).json()
    assert all(x["customer_id"] == c2.user["id"] for x in c2.get("/support/tickets").json())
    assert sup.patch(f"/support/tickets/{t['id']}", {"response": "Looking now"}).json()["status"] == "IN_PROGRESS"
    assert c1.patch(f"/support/tickets/{t['id']}", {"status": "CLOSED"}).status_code == 403
    foreign_order = c2.get("/orders").json()[0]["id"]
    assert c1.post("/support/tickets", {"subject": "Hack", "message": "other order", "order_id": foreign_order}).status_code == 403


def test_blocked_attempts_are_audited(as_user):
    c1, admin = as_user("customer1"), as_user("admin")
    c1.get("/admin/users")
    logs = admin.get("/audit-logs", params={"decision": "BLOCK"}).json()
    assert any(l["actor_role"] == "CUSTOMER" and "/admin/users" in l["action"] for l in logs)


def test_analytics_and_dev_reset(as_user):
    admin = as_user("admin")
    a = admin.get("/admin/analytics").json()
    assert a["gmv"] > 0 and a["pending_sellers"] == 1 and a["pending_products"] == 1
    assert as_user("customer1").post("/admin/dev/reset").status_code == 403
    assert admin.post("/admin/dev/reset").json() == {"reset": True}
