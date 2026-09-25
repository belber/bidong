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


def test_admin_uploads_repost_avatar(admin_client):
    token = _login(admin_client).json()["token"]
    resp = admin_client.post(
        "/api/admin/sources/avatar",
        content=b"fake-jpeg-bytes",
        headers={**_auth(token), "Content-Type": "image/jpeg"},
    )
    assert resp.status_code == 200
    url = resp.json()["account_avatar_url"]
    assert "repost-avatar" in url
    assert url.endswith(".jpg")

    cfg = admin_client.get("/api/admin/config/repost", headers=_auth(token)).json()
    assert cfg["account_avatar_url"] == url


def test_admin_avatar_upload_rejects_non_image(admin_client):
    token = _login(admin_client).json()["token"]
    resp = admin_client.post(
        "/api/admin/sources/avatar",
        content=b"not-an-image",
        headers={**_auth(token), "Content-Type": "text/plain"},
    )
    assert resp.status_code == 400


LIST_CSV = """bvid,title,platform,author_name,author_id,author_url,source_url,bili_published_at,note
BV15Pbj6yEKg,【小视频】126-减脂只是为了多吃,douyin,小山坡,MS4wA,https://www.douyin.com/user/MS4wA,https://v.douyin.com/Ou/,2026-09-05,
BV1vcbj6mEfk,【小视频】125-遇到事情先拍抖音,douyin,JACKSON_13,MS4wB,https://www.douyin.com/user/MS4wB,https://v.douyin.com/30/,2026-09-04,
BV1txaT6nEz3,【小视频】188-夜里的肌肉身材,youtube,Hot Athletes,UCT085,https://www.youtube.com/@HotChineseAthletes,https://youtube.com/shorts/D3S,2026-09-24,
BV1Yubj6GELK,【小视频】123-重情重义的兄弟变恋人,douyin,,,,https://v.douyin.com/HQtGtlUmIQc/,2026-09-05,parse失败 404
"""


def _import(client, token, csv_text=LIST_CSV):
    resp = client.post(
        "/api/admin/sources/import", json={"csv": csv_text}, headers=_auth(token)
    )
    assert resp.status_code == 200
    return resp.json()


def test_admin_sources_list_is_paginated(admin_client):
    token = _login(admin_client).json()["token"]
    _import(admin_client, token)

    resp = admin_client.get(
        "/api/admin/sources/list", params={"page": 1, "size": 2}, headers=_auth(token)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert data["page"] == 1
    assert data["size"] == 2
    assert data["pages"] == 2
    assert len(data["items"]) == 2
    # 按 B站发布日期倒序
    assert data["items"][0]["bili_published_at"] == "2026-09-24"
    assert data["items"][0]["platform_label"] == "YouTube"

    page2 = admin_client.get(
        "/api/admin/sources/list", params={"page": 2, "size": 2}, headers=_auth(token)
    ).json()
    assert len(page2["items"]) == 2
    ids = {i["bvid"] for i in data["items"]} | {i["bvid"] for i in page2["items"]}
    assert len(ids) == 4


def test_admin_sources_list_search(admin_client):
    token = _login(admin_client).json()["token"]
    _import(admin_client, token)

    by_author = admin_client.get(
        "/api/admin/sources/list", params={"q": "JACKSON"}, headers=_auth(token)
    ).json()
    assert by_author["total"] == 1
    assert by_author["items"][0]["bvid"] == "BV1vcbj6mEfk"

    by_bvid = admin_client.get(
        "/api/admin/sources/list", params={"q": "BV15Pbj"}, headers=_auth(token)
    ).json()
    assert by_bvid["total"] == 1

    by_title = admin_client.get(
        "/api/admin/sources/list", params={"q": "肌肉身材"}, headers=_auth(token)
    ).json()
    assert by_title["total"] == 1

    none = admin_client.get(
        "/api/admin/sources/list", params={"q": "不存在的东西"}, headers=_auth(token)
    ).json()
    assert none["total"] == 0


def test_admin_sources_list_filters_by_platform_and_status(admin_client):
    token = _login(admin_client).json()["token"]
    _import(admin_client, token)

    youtube = admin_client.get(
        "/api/admin/sources/list", params={"platform": "youtube"}, headers=_auth(token)
    ).json()
    assert youtube["total"] == 1

    missing = admin_client.get(
        "/api/admin/sources/list",
        params={"status": "without_author"},
        headers=_auth(token),
    ).json()
    assert missing["total"] == 1
    assert missing["items"][0]["bvid"] == "BV1Yubj6GELK"
    assert missing["items"][0]["note"] == "parse失败 404"

    with_author = admin_client.get(
        "/api/admin/sources/list",
        params={"status": "with_author"},
        headers=_auth(token),
    ).json()
    assert with_author["total"] == 3


def test_admin_sources_list_caps_page_size(admin_client):
    token = _login(admin_client).json()["token"]
    _import(admin_client, token)
    data = admin_client.get(
        "/api/admin/sources/list", params={"size": 9999}, headers=_auth(token)
    ).json()
    assert data["size"] == 100


def test_admin_sources_stats_breaks_down_by_platform(admin_client):
    token = _login(admin_client).json()["token"]
    _import(admin_client, token)
    stats = admin_client.get("/api/admin/sources/stats", headers=_auth(token)).json()
    by_platform = {row["platform"]: row for row in stats["by_platform"]}
    assert by_platform["douyin"]["count"] == 3
    assert by_platform["douyin"]["label"] == "抖音"
    assert by_platform["youtube"]["count"] == 1
    assert stats["total"] == 4
