def test_login_dev_creates_user_and_is_idempotent(client):
    resp = client.post("/api/login", json={"code": "dev_abc"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["user"]["id"] > 0

    again = client.post("/api/login", json={"code": "dev_abc"}).json()
    assert again["user"]["id"] == data["user"]["id"]


def test_login_real_wx_code_maps_to_stable_dev_user(client):
    first = client.post("/api/login", json={"code": "wx-real-code-1"}).json()
    second = client.post("/api/login", json={"code": "wx-real-code-2"}).json()
    assert first["user"]["id"] == second["user"]["id"]


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/cards")
    assert resp.status_code == 401


def test_invalid_token_rejected(client):
    resp = client.get("/api/cards", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401
