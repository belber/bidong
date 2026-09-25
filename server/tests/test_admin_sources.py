import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.admin_app import app as admin_app
from app.db import get_db
from app.models import VideoSource

CSV_TEXT = """bvid,title,platform,author_name,author_id,author_url,source_url,source_video_id,bili_published_at,note
BV15Pbj6yEKg,【小视频】126-减脂只是为了多吃,douyin,小山坡,MS4wA,https://www.douyin.com/user/MS4wA,https://v.douyin.com/Ou/,7681665,2026-09-05,
BV1Yubj6GELK,【小视频】123-重情重义的兄弟变恋人,douyin,,,,https://v.douyin.com/HQtGtlUmIQc/,,2026-09-05,parse失败 404
not-a-bvid,坏行,douyin,某某,,,,,,
"""


@pytest.fixture()
def admin_client(db_engine, monkeypatch):
    testing_session = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )
    settings.admin_password = "admin-dev-password"
    settings.dev_mode = False
    monkeypatch.setattr("app.services.config_store.seed_defaults", lambda db: None)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    admin_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(admin_app)
    yield client
    client.close()
    admin_app.dependency_overrides.clear()


def _login(client):
    return client.post("/api/admin/login", json={"password": "admin-dev-password"})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_admin_sources_require_token(admin_client):
    assert admin_client.get("/api/admin/sources/stats").status_code == 401
    assert (
        admin_client.post("/api/admin/sources/import", json={"csv": CSV_TEXT}).status_code
        == 401
    )


def test_admin_sources_import_and_stats(admin_client, db_engine):
    token = _login(admin_client).json()["token"]
    resp = admin_client.post(
        "/api/admin/sources/import", json={"csv": CSV_TEXT}, headers=_auth(token)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 2
    assert data["updated"] == 0
    assert len(data["rejected"]) == 1
    assert data["rejected"][0]["reason"] == "invalid bvid"

    db = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()
    assert db.query(VideoSource).count() == 2
    db.close()

    stats = admin_client.get("/api/admin/sources/stats", headers=_auth(token))
    assert stats.status_code == 200
    body = stats.json()
    assert body["total"] == 2
    assert body["with_author"] == 1
    assert body["without_author"] == 1
    assert body["last_updated_at"]


def test_admin_sources_import_is_idempotent(admin_client):
    token = _login(admin_client).json()["token"]
    admin_client.post(
        "/api/admin/sources/import", json={"csv": CSV_TEXT}, headers=_auth(token)
    )
    again = admin_client.post(
        "/api/admin/sources/import", json={"csv": CSV_TEXT}, headers=_auth(token)
    )
    assert again.json()["created"] == 0
    assert again.json()["updated"] == 2


def test_admin_sources_import_requires_bvid_column(admin_client):
    token = _login(admin_client).json()["token"]
    resp = admin_client.post(
        "/api/admin/sources/import",
        json={"csv": "title,platform\n标题,douyin\n"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


def test_admin_repost_config_roundtrip(admin_client):
    token = _login(admin_client).json()["token"]
    initial = admin_client.get("/api/admin/config/repost", headers=_auth(token))
    assert initial.status_code == 200
    assert initial.json()["up_mid"] == settings.repost_up_mid
    assert initial.json()["account_name"] == "帅哥录屏"

    resp = admin_client.put(
        "/api/admin/config/repost",
        json={
            "up_mid": "111,222",
            "account_name": "帅哥录屏",
            "account_avatar_url": "https://cos.example/avatar.jpg",
            "source_ingest_token": "secret-token",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["up_mid"] == "111,222"
    assert body["account_avatar_url"] == "https://cos.example/avatar.jpg"
    assert body["source_ingest_token"] == "secret-token"

    again = admin_client.get("/api/admin/config/repost", headers=_auth(token)).json()
    assert again["up_mid"] == "111,222"
    assert again["source_ingest_token"] == "secret-token"


def test_admin_page_exposes_sources_view(admin_client):
    html = admin_client.get("/admin/index.html").text
    assert 'data-view="sources"' in html
    assert 'id="view-sources"' in html
    assert "视频出处" in html
