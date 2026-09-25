from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import VideoSource
from app.services import config_store

TOKEN = "test-ingest-token"
ENDPOINT = "/api/sources/ingest"


def _db(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    return Session()


def _item(**over):
    data = {
        "bvid": "BV15Pbj6yEKg",
        "title": "【小视频】126-减脂只是为了多吃",
        "platform": "douyin",
        "author_name": "小山坡",
        "author_id": "MS4wLjABAAAAfake",
        "author_url": "https://www.douyin.com/user/MS4wLjABAAAAfake",
        "source_url": "https://v.douyin.com/Ou--3FzQeWs/",
        "source_video_id": "7681665368289533561",
        "bili_published_at": "2026-09-05",
        "note": "",
    }
    data.update(over)
    return data


def _configure_token(db_engine, token=TOKEN):
    db = _db(db_engine)
    config_store.set_raw(db, "source_ingest_token", token)
    db.close()


def _headers(token=TOKEN):
    return {"X-Ingest-Token": token}


def test_ingest_without_configured_token_returns_503(client, db_engine, monkeypatch):
    monkeypatch.setattr(settings, "source_ingest_token", "")
    resp = client.post(ENDPOINT, json={"items": [_item()]}, headers=_headers())
    assert resp.status_code == 503


def test_ingest_with_wrong_token_returns_401(client, db_engine):
    _configure_token(db_engine)
    resp = client.post(ENDPOINT, json={"items": [_item()]}, headers=_headers("nope"))
    assert resp.status_code == 401


def test_ingest_with_missing_token_returns_401(client, db_engine):
    _configure_token(db_engine)
    resp = client.post(ENDPOINT, json={"items": [_item()]})
    assert resp.status_code == 401


def test_ingest_creates_row(client, db_engine):
    _configure_token(db_engine)
    resp = client.post(ENDPOINT, json={"items": [_item()]}, headers=_headers())
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "created": 1, "updated": 0, "rejected": []}

    db = _db(db_engine)
    row = db.query(VideoSource).filter(VideoSource.bvid == "BV15Pbj6yEKg").one()
    assert row.platform == "douyin"
    assert row.author_name == "小山坡"
    assert row.author_url.endswith("MS4wLjABAAAAfake")
    assert row.bili_published_at == "2026-09-05"
    db.close()


def test_ingest_is_idempotent_and_updates(client, db_engine):
    _configure_token(db_engine)
    client.post(ENDPOINT, json={"items": [_item()]}, headers=_headers())
    resp = client.post(
        ENDPOINT,
        json={"items": [_item(author_name="小山坡改名了", author_url="https://new")]},
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == 0
    assert resp.json()["updated"] == 1

    db = _db(db_engine)
    rows = db.query(VideoSource).filter(VideoSource.bvid == "BV15Pbj6yEKg").all()
    assert len(rows) == 1
    assert rows[0].author_name == "小山坡改名了"
    assert rows[0].author_url == "https://new"
    db.close()


def test_ingest_empty_fields_do_not_wipe_existing_values(client, db_engine):
    _configure_token(db_engine)
    client.post(ENDPOINT, json={"items": [_item()]}, headers=_headers())
    # 重发时不带作者信息（例如历史行只有平台），不应把已补好的信息冲掉
    client.post(
        ENDPOINT,
        json={"items": [_item(author_name="", author_id="", author_url="", note="")]},
        headers=_headers(),
    )

    db = _db(db_engine)
    row = db.query(VideoSource).filter(VideoSource.bvid == "BV15Pbj6yEKg").one()
    assert row.author_name == "小山坡"
    assert row.author_id == "MS4wLjABAAAAfake"
    db.close()


def test_ingest_rejects_invalid_bvid(client, db_engine):
    _configure_token(db_engine)
    resp = client.post(
        ENDPOINT,
        json={"items": [_item(bvid="BV1"), _item(bvid="")]},
        headers=_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 0
    assert len(data["rejected"]) == 2
    assert data["rejected"][0]["reason"] == "invalid bvid"

    db = _db(db_engine)
    assert db.query(VideoSource).count() == 0
    db.close()


def test_ingest_accepts_single_object_and_array(client, db_engine):
    _configure_token(db_engine)
    single = client.post(ENDPOINT, json=_item(), headers=_headers())
    assert single.status_code == 200
    assert single.json()["created"] == 1

    arr = client.post(
        ENDPOINT,
        json=[_item(bvid="BV1txaT6nEz3", platform="x")],
        headers=_headers(),
    )
    assert arr.status_code == 200
    assert arr.json()["created"] == 1

    db = _db(db_engine)
    assert db.query(VideoSource).count() == 2
    db.close()


def test_ingest_partial_batch_keeps_valid_items(client, db_engine):
    _configure_token(db_engine)
    resp = client.post(
        ENDPOINT,
        json={"items": [_item(), _item(bvid="bad", author_name="无效")]},
        headers=_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 1
    assert len(data["rejected"]) == 1

    db = _db(db_engine)
    assert db.query(VideoSource).count() == 1
    db.close()


def test_ingest_rejects_more_than_500_items(client, db_engine):
    _configure_token(db_engine)
    items = [_item(bvid=f"BV{i:010d}") for i in range(501)]
    resp = client.post(ENDPOINT, json={"items": items}, headers=_headers())
    assert resp.status_code == 400


def test_ingest_rejects_bad_body(client, db_engine):
    _configure_token(db_engine)
    resp = client.post(ENDPOINT, json={"hello": "world"}, headers=_headers())
    assert resp.status_code == 400


def test_ingest_truncates_overlong_fields(client, db_engine):
    _configure_token(db_engine)
    resp = client.post(
        ENDPOINT,
        json={"items": [_item(title="x" * 5000, platform="y" * 100)]},
        headers=_headers(),
    )
    assert resp.status_code == 200

    db = _db(db_engine)
    row = db.query(VideoSource).filter(VideoSource.bvid == "BV15Pbj6yEKg").one()
    assert len(row.title) <= 500
    assert len(row.platform) <= 32
    db.close()
