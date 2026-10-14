"""管理端：抖音会话、能力开关、以及统计的平台维度。"""

import httpx
import respx
from sqlalchemy.orm import sessionmaker

from app.models import DownloadEvent, ParseLog
from app.services import config_store
from app.services.douyin_provider import DETAIL_API


def _auth(admin_client):
    token = admin_client.post(
        "/api/admin/login", json={"password": "admin-dev-password"}
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_douyin_session_requires_admin(admin_client):
    assert admin_client.get("/api/admin/douyin/session").status_code == 401


def test_session_reports_unconfigured(admin_client):
    headers = _auth(admin_client)
    data = admin_client.get("/api/admin/douyin/session", headers=headers).json()
    assert data["configured"] is False
    assert data["parse_node"] == "tencent"
    assert data["switches"] == {"parse": True, "video": True, "audio": True, "images": True}
    assert "probe" not in data  # 不带 probe=1 不打真接口


@respx.mock
def test_session_probe_reports_body_size(admin_client, db_engine):
    respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=b"x" * 4096))
    headers = _auth(admin_client)

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_douyin_cookie(db, "sessionid=a; sid_tt=a; uid_tt=a")
    db.commit()
    db.close()

    data = admin_client.get(
        "/api/admin/douyin/session", params={"probe": 1}, headers=headers
    ).json()
    assert data["configured"] is True
    assert data["probe"]["ok"] is True
    assert data["probe"]["bytes"] == 4096


@respx.mock
def test_empty_body_counts_as_dead(admin_client, db_engine):
    respx.get(DETAIL_API).mock(return_value=httpx.Response(200, content=b""))
    headers = _auth(admin_client)

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    config_store.set_douyin_cookie(db, "sessionid=a; sid_tt=a; uid_tt=a")
    db.commit()
    db.close()

    data = admin_client.post("/api/admin/douyin/probe", headers=headers).json()
    assert data["ok"] is False
    assert data["bytes"] == 0
    assert data["error"] == "空包"


def test_cookie_update_normalizes_and_reports(admin_client, db_engine):
    headers = _auth(admin_client)
    raw = "sessionid=abc; douyin.com; sid_tt=abc\nuid_tt=abc;"
    resp = admin_client.post(
        "/api/admin/douyin/cookie", json={"cookie": raw}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["configured"] is True

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    assert config_store.douyin_cookie(db) == "sessionid=abc; sid_tt=abc; uid_tt=abc"
    db.close()


def test_switches_roundtrip(admin_client):
    headers = _auth(admin_client)
    resp = admin_client.put(
        "/api/admin/douyin/switches", json={"images": False}, headers=headers
    )
    assert resp.json()["images"] is False
    assert resp.json()["video"] is True  # 没传的保持不变


def test_node_switch(admin_client):
    headers = _auth(admin_client)
    assert admin_client.put(
        "/api/admin/douyin/node", json={"node": "home"}, headers=headers
    ).json() == {"node": "home"}
    assert admin_client.put(
        "/api/admin/douyin/node", json={"node": "bogus"}, headers=headers
    ).status_code == 422


def test_parse_monitor_filters_by_platform(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(ParseLog(platform="bilibili", source="local", input="b1", ok=True))
    db.add(ParseLog(platform="douyin", source="local", input="d1", ok=False, reason="douyin_session_invalid"))
    db.add(ParseLog(platform="douyin", source="local", input="d2", ok=True))
    db.commit()
    db.close()

    headers = _auth(admin_client)
    all_rows = admin_client.get(
        "/api/admin/stats/parse", params={"source": "local"}, headers=headers
    ).json()
    assert all_rows["total"] == 3

    dy = admin_client.get(
        "/api/admin/stats/parse", params={"source": "local", "platform": "douyin"}, headers=headers
    ).json()
    assert dy["total"] == 2
    assert dy["ok"] == 1
    assert dy["fail"] == 1
    assert {"reason": "douyin_session_invalid", "count": 1} in dy["fail_by_reason"]

    detail = admin_client.get(
        "/api/admin/stats/parse/detail",
        params={"source": "local", "platform": "bilibili"},
        headers=headers,
    ).json()
    assert detail["total"] == 1


def test_download_monitor_filters_by_platform(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(DownloadEvent(platform="bilibili", bvid="BV1", kind="watermarked", stage="resolve", status="success"))
    db.add(DownloadEvent(platform="douyin", bvid="768", kind="video", stage="resolve", status="fail", error_type="domain_not_configured"))
    db.commit()
    db.close()

    headers = _auth(admin_client)
    dy = admin_client.get(
        "/api/admin/stats/download", params={"platform": "douyin"}, headers=headers
    ).json()
    assert dy["total"] == 1
    assert dy["fail"] == 1

    detail = admin_client.get(
        "/api/admin/stats/download/detail", params={"platform": "douyin"}, headers=headers
    ).json()
    assert detail["total"] == 1
    assert detail["items"][0]["bvid"] == "768"
