import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="guardslm-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ENABLE_DEV_RESET"] = "true"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import reset_and_seed  # noqa: E402

PASSWORD = "GuardSLM2026!"


@pytest.fixture(scope="session")
def _client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client(_client):
    reset_and_seed()
    return _client


class Api:
    """Tiny helper: api('customer1').get('/orders')."""
    def __init__(self, client, username):
        r = client.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.client, self.headers, self.user = client, {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]

    def get(self, url, **kw): return self.client.get(url, headers=self.headers, **kw)
    def post(self, url, json=None, **kw): return self.client.post(url, json=json, headers=self.headers, **kw)
    def put(self, url, json=None, **kw): return self.client.put(url, json=json, headers=self.headers, **kw)
    def patch(self, url, json=None, **kw): return self.client.patch(url, json=json, headers=self.headers, **kw)
    def delete(self, url, **kw): return self.client.delete(url, headers=self.headers, **kw)


@pytest.fixture()
def as_user(client):
    return lambda username: Api(client, username)
