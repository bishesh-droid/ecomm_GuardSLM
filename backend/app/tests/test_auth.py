import pytest

from .conftest import PASSWORD

ROLES = {"admin": "ADMIN", "seller1": "SELLER", "seller2": "SELLER", "seller3": "SELLER", "customer1": "CUSTOMER",
         "customer2": "CUSTOMER", "customer3": "CUSTOMER", "warehouse1": "WAREHOUSE", "support1": "SUPPORT"}


@pytest.mark.parametrize("username,role", ROLES.items())
def test_login_every_role(client, username, role):
    r = client.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == role
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["username"] == username


def test_bad_password_and_missing_token(client):
    assert client.post("/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_register_cannot_create_admin(client):
    r = client.post("/auth/register", json={"username": "evil", "password": "Password123!", "display_name": "E", "email": "e@x.io", "role": "ADMIN"})
    assert r.status_code == 422


def test_password_not_stored_plaintext(client):
    from app.database import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        assert all(u.password_hash.startswith("$2") and PASSWORD not in u.password_hash for u in db.query(User))


def test_public_browse_and_filters(client):
    assert len(client.get("/products").json()) >= 30
    assert all(p["status"] == "ACTIVE" for p in client.get("/products").json())
    hits = client.get("/products", params={"q": "laptop"}).json()
    assert hits and all("laptop" in (p["name"] + p["description"]).lower() for p in hits)
    cheap = client.get("/products", params={"category": "books", "max_price": 500}).json()
    assert cheap and all(p["category_slug"] == "books" and p["price"] <= 500 for p in cheap)
    assert len(client.get("/categories").json()) == 8
