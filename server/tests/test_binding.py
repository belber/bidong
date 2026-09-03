from app.models import Binding
from app.services.activation import issue_activation


def test_bind_and_get_binding(client, auth_headers, db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    issued = issue_activation(db, "999")
    code = issued.activation_code
    db.close()

    resp = client.get("/api/binding", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"bound": False, "bili_uid": None, "bili_name": None}

    resp = client.post("/api/binding", json={"code": code}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["bound"] is True
    assert resp.json()["bili_uid"] == "999"

    resp = client.get("/api/binding", headers=auth_headers)
    assert resp.json()["bound"] is True


def test_bind_invalid_code(client, auth_headers):
    resp = client.post("/api/binding", json={"code": "NOPE"}, headers=auth_headers)
    assert resp.status_code == 400


def test_bind_reused_code_fails(client, auth_headers, db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    issued = issue_activation(db, "888")
    code = issued.activation_code
    db.close()

    assert client.post("/api/binding", json={"code": code}, headers=auth_headers).status_code == 200
    resp = client.post("/api/binding", json={"code": code}, headers=auth_headers)
    assert resp.status_code == 400


def test_unbind_and_rebind_with_same_code(client, auth_headers, db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    issued = issue_activation(db, "777")
    code = issued.activation_code
    db.close()

    assert client.post("/api/binding", json={"code": code}, headers=auth_headers).status_code == 200
    assert client.get("/api/binding", headers=auth_headers).json()["bound"] is True

    resp = client.delete("/api/binding", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get("/api/binding", headers=auth_headers).json()["bound"] is False

    # 解绑后仍可用同一个激活码重新绑定
    assert client.post("/api/binding", json={"code": code}, headers=auth_headers).status_code == 200
