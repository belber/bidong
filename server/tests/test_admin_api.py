import tempfile

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app import admin as admin_module
from app.admin_app import app as admin_app
from app.db import get_db
from app.models import (
    ActivationLog,
    AdminConfig,
    AtEvent,
    Binding,
    BiliCdnDomain,
    DownloadEvent,
    FollowEvent,
    ParseLog,
    User,
    VideoCard,
)
from app.time import utcnow_naive


@pytest.fixture()
def admin_client(db_engine, monkeypatch):
    testing_session = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )
    settings.robot_send_interval_seconds = 0
    settings.admin_password = "admin-dev-password"
    settings.dev_mode = False  # 避免 lifespan 去真实 DB 建表/播种
    monkeypatch.setattr("app.services.config_store.seed_defaults", lambda db: None)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    admin_app.dependency_overrides[get_db] = override_get_db
    admin_app.dependency_overrides.pop("admin", None)

    # 避免测试去真的请求 B站
    class FakeRobotClient:
        def __init__(self, *a, **k):
            self.sent = []

        def send_msg(self, uid, content):
            self.sent.append((uid, content))

        def close(self):
            pass

    monkeypatch.setattr(admin_module, "build_client", lambda *a, **k: FakeRobotClient())

    client = TestClient(admin_app)
    yield client
    client.close()
    admin_app.dependency_overrides.clear()


def _login(client, password="admin-dev-password"):
    return client.post("/api/admin/login", json={"password": password})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_admin_login_requires_password(admin_client):
    assert _login(admin_client, "wrong").status_code == 401
    resp = _login(admin_client)
    assert resp.status_code == 200
    assert resp.json()["token"]


def test_admin_routes_require_token(admin_client):
    assert admin_client.get("/api/admin/stats/overview").status_code == 401
    token = _login(admin_client).json()["token"]
    assert admin_client.get("/api/admin/stats/overview", headers=_auth(token)).status_code == 200


def test_overview_and_followers(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(FollowEvent(bili_uid="111", bili_name="A", mtime=1, sent_code=True, bound=False))
    db.add(FollowEvent(bili_uid="222", bili_name="B", mtime=2, sent_code=False, bound=False))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    resp = admin_client.get("/api/admin/stats/followers", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2

    detail = admin_client.get("/api/admin/stats/followers/detail", headers=_auth(token))
    assert detail.status_code == 200
    assert detail.json()["total"] == 2


def test_followers_trend_buckets_by_shanghai_date(admin_client, db_engine):
    from app.time import utcnow_naive

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    now = utcnow_naive()
    db.add(FollowEvent(bili_uid="111", bili_name="A", mtime=1, sent_code=True, bound=False, created_at=now))
    db.add(FollowEvent(bili_uid="222", bili_name="B", mtime=2, sent_code=False, bound=False, created_at=now))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/followers?days=7", headers=_auth(token)).json()
    # 今天应聚合到上海时区当天
    assert len(data["trend"]) == 7
    assert data["trend"][-1]["count"] == 2


def test_parse_summary_and_detail(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(ParseLog(source="local", input="BV1xx411c7mD", bvid="BV1xx411c7mD", ok=True))
    db.add(ParseLog(source="local", input="BV1yy411c7mD", ok=False, reason="network_timeout"))
    db.add(ParseLog(source="local", input="BV1yy411c7mD", ok=False, reason="network_timeout"))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/parse?source=local", headers=_auth(token)).json()
    assert data["total"] == 3
    assert data["ok"] == 1
    assert data["fail"] == 2
    assert {"reason": "network_timeout", "count": 2} in data["fail_by_reason"]

    detail = admin_client.get(
        "/api/admin/stats/parse/detail?source=local&result=fail", headers=_auth(token)
    ).json()
    assert detail["total"] == 2


def test_features_and_schedule_config(admin_client):
    token = _login(admin_client).json()["token"]
    resp = admin_client.put(
        "/api/admin/config/features",
        json={"watermarked": True, "clean": False, "audio": True},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"watermarked": True, "clean": False, "audio": True}

    sched = admin_client.put(
        "/api/admin/config/schedule",
        json={"at_poll_interval": 60, "follow_window": 900},
        headers=_auth(token),
    )
    assert sched.status_code == 200
    body = sched.json()
    assert body["at_poll_interval"] == 60
    assert body["follow_window"] == 900


def test_parse_features_config(admin_client):
    token = _login(admin_client).json()["token"]
    resp = admin_client.put(
        "/api/admin/config/parse-features",
        json={"comment": False, "danmaku": True},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"comment": False, "danmaku": True}

    got = admin_client.get("/api/admin/config/parse-features", headers=_auth(token))
    assert got.status_code == 200
    assert got.json() == {"comment": False, "danmaku": True}


def test_ui_config(admin_client):
    token = _login(admin_client).json()["token"]
    resp = admin_client.put(
        "/api/admin/config/ui",
        json={"robot_guide": False, "share": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"robot_guide": False, "share": False}


def test_cookie_status_and_update(admin_client):
    token = _login(admin_client).json()["token"]
    status = admin_client.get("/api/admin/cookie/status", headers=_auth(token))
    assert status.status_code == 200
    assert status.json()["cookie_valid"] is True

    upd = admin_client.post(
        "/api/admin/cookie/update",
        json={"cookie_text": "SESSDATA=sess1; bili_jct=jct1; DedeUserID=999; buvid3=b3; buvid4=b4"},
        headers=_auth(token),
    )
    assert upd.status_code == 200
    assert "SESSDATA" in upd.json()["saved_fields"]


def test_activation_send_reads_uids(admin_client, db_engine):
    token = _login(admin_client).json()["token"]
    resp = admin_client.post(
        "/api/admin/activation/send",
        json={"uids": ["111", "222"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["sent"] == 2
    assert resp.json()["failed"] == {}

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    assert db.query(ActivationLog).count() == 2
    db.close()


def test_activation_retry_failed(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(ActivationLog(bili_uid="111", code="ABC", sent_ok=False, send_reason="network"))
    db.add(Binding(bili_uid="111", activation_code="ABC", created_at=utcnow_naive()))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    resp = admin_client.post("/api/admin/activation/retry-failed", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["sent"] == 1


def test_help_config_admin_requires_auth_and_roundtrips(admin_client):
    assert admin_client.get("/api/admin/config/help").status_code == 401
    token = _login(admin_client).json()["token"]
    assert admin_client.get("/api/admin/config/help", headers=_auth(token)).json() == {"qq_group": ""}

    put = admin_client.put(
        "/api/admin/config/help",
        json={"qq_group": "987654321"},
        headers=_auth(token),
    )
    assert put.status_code == 200
    assert put.json() == {"qq_group": "987654321"}
    assert admin_client.get("/api/admin/config/help", headers=_auth(token)).json() == {"qq_group": "987654321"}


def test_download_stats_and_detail(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(
        DownloadEvent(
            bvid="BV1xx411c7mD",
            kind="watermarked",
            qn=16,
            host="upos-sz-mirrorcoso1.bilivideo.com",
            stage="download",
            status="fail",
            error_type="domain_not_configured",
            error_message="url not in domain list",
            wx_err_msg="downloadFile:fail url not in domain list",
            created_at=utcnow_naive(),
        )
    )
    db.add(
        DownloadEvent(
            bvid="BV1yy411c7mD",
            kind="audio",
            qn=30280,
            host="upos-sz-mirrorcos.bilivideo.com",
            stage="share",
            status="success",
            created_at=utcnow_naive(),
        )
    )
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/download", headers=_auth(token)).json()
    assert data["total"] == 2
    assert data["success"] == 1
    assert data["fail"] == 1
    assert data["success_rate"] == 50.0
    assert {"error_type": "domain_not_configured", "count": 1} in data["fail_by_error"]

    detail = admin_client.get(
        "/api/admin/stats/download/detail?status=fail", headers=_auth(token)
    ).json()
    assert detail["total"] == 1
    assert detail["items"][0]["bvid"] == "BV1xx411c7mD"


def test_download_domains_list_and_update(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(BiliCdnDomain(host="upos-sz-mirrorcoso1.bilivideo.com", is_configured=False))
    db.add(BiliCdnDomain(host="upos-sz-estgcos.bilivideo.com", is_configured=True))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/download/domains", headers=_auth(token)).json()
    assert data["total"] == 2
    hosts = {i["host"]: i for i in data["items"]}
    assert hosts["upos-sz-mirrorcoso1.bilivideo.com"]["suggestion"] == "需要配置"
    assert hosts["upos-sz-estgcos.bilivideo.com"]["is_configured"] is True

    put = admin_client.put(
        "/api/admin/download/domains/upos-sz-mirrorcoso1.bilivideo.com",
        json={"is_configured": True},
        headers=_auth(token),
    )
    assert put.status_code == 200
    assert put.json()["is_configured"] is True

    created = admin_client.put(
        "/api/admin/download/domains/upos-sz-mirrorhw.bilivideo.com",
        json={"is_configured": True},
        headers=_auth(token),
    )
    assert created.status_code == 200
    assert created.json()["host"] == "upos-sz-mirrorhw.bilivideo.com"
    assert created.json()["is_configured"] is True
    assert created.json()["seen_count"] == 0


@respx.mock
def test_operations_config_and_serverchan_test(admin_client):
    token = _login(admin_client).json()["token"]
    put = admin_client.put(
        "/api/admin/config/alert",
        json={
            "serverchan_sendkey": "SCTtestkey",
            "alert_cookie_enabled": False,
            "alert_domain_enabled": True,
            "report_enabled": True,
            "report_time": "08:30",
        },
        headers=_auth(token),
    )
    assert put.status_code == 200
    data = put.json()
    assert data["serverchan_sendkey"] == "SCTtestkey"
    assert data["alert_cookie_enabled"] is False
    assert data["report_enabled"] is True
    assert data["report_time"] == "08:30"

    route = respx.post("https://sctapi.ftqq.com/SCTtestkey.send").mock(
        return_value=httpx.Response(200, json={"code": 0})
    )
    resp = admin_client.post(
        "/api/admin/config/serverchan/test", headers=_auth(token)
    )
    assert resp.status_code == 200
    assert route.called


@respx.mock
def test_report_test_sends_serverchan(admin_client):
    token = _login(admin_client).json()["token"]
    admin_client.put(
        "/api/admin/config/alert",
        json={"serverchan_sendkey": "SCTtestkey"},
        headers=_auth(token),
    )
    route = respx.post("https://sctapi.ftqq.com/SCTtestkey.send").mock(
        return_value=httpx.Response(200, json={"code": 0})
    )
    resp = admin_client.post("/api/admin/config/report/test", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["channels"]["serverchan"] is True
    assert route.called


def test_at_summary_includes_parse_breakdown(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(AtEvent(feed_id="f1", bili_uid="111", bvid="BV1xx411c7mD", result="collected"))
    db.add(AtEvent(feed_id="f2", bili_uid="222", bvid="BV1yy411c7mD", result="parse_failed", reason="network_timeout"))
    db.add(AtEvent(feed_id="f3", bili_uid="333", bvid="BV1zz411c7mD", result="unbound"))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/at", headers=_auth(token)).json()
    assert data["total"] == 3
    assert data["collected"] == 1
    assert data["failed"] == 1
    assert {"reason": "network_timeout", "count": 1} in data["fail_by_reason"]


def test_at_detail_includes_comment_and_video_title(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(AtEvent(feed_id="f1", bili_uid="111", bili_name="小明", bvid="BV1xx411c7mD",
                   comment="@壁咚咚私藏 帮我收藏这个", result="collected"))
    db.add(VideoCard(user_id=1, bvid="BV1xx411c7mD", title="测试视频标题", cover_url="", up_name="UP",
                     partition="", desc="", source_url="", source="robot",
                     collected_at=utcnow_naive(), month="2026-09"))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/at/detail", headers=_auth(token)).json()
    item = data["items"][0]
    assert item["comment"] == "@壁咚咚私藏 帮我收藏这个"
    assert item["bili_name"] == "小明"
    assert item["video_title"] == "测试视频标题"
    assert item["bvid"] == "BV1xx411c7mD"


def test_activation_detail_lists_all_codes_and_status(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    sent_at = utcnow_naive()
    db.add(Binding(bili_uid="111", bili_name="小明", activation_code="ABC111", code_sent_at=sent_at))
    db.add(Binding(bili_uid="222", bili_name="小红", activation_code="DEF222"))
    db.add(ActivationLog(bili_uid="222", code="DEF222", sent_ok=False, send_reason="risk_control"))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/activation/detail", headers=_auth(token)).json()
    assert data["total"] == 2
    by_uid = {i["bili_uid"]: i for i in data["items"]}
    assert by_uid["111"]["sent_ok"] is True
    assert by_uid["222"]["sent_ok"] is False
    assert by_uid["222"]["send_reason"] == "risk_control"
    assert by_uid["222"]["bound"] is False


def test_parse_detail_local_origin_uses_nickname_then_openid(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    u1 = User(openid="openid-a", nickname="张三")
    db.add(u1); db.commit(); db.refresh(u1)
    db.add(ParseLog(source="local", user_id=u1.id, input="https://www.bilibili.com/video/BV1xx411c7mD",
                    bvid="BV1xx411c7mD", ok=True, video_title="链接视频标题"))
    u2 = User(openid="openid-b-no-nick")
    db.add(u2); db.commit(); db.refresh(u2)
    db.add(ParseLog(source="local", user_id=u2.id, input="BV1yy411c7mD", bvid="BV1yy411c7mD", ok=False, reason="network_timeout"))
    db.add(VideoCard(user_id=1, bvid="BV1yy411c7mD", title="回填视频标题", cover_url="", up_name="UP",
                     partition="", desc="", source_url="", source="local",
                     collected_at=utcnow_naive(), month="2026-09"))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/parse/detail?source=local", headers=_auth(token)).json()
    by_bvid = {i["bvid"]: i for i in data["items"]}
    assert by_bvid["BV1xx411c7mD"]["origin"] == "张三"
    assert by_bvid["BV1xx411c7mD"]["video_title"] == "链接视频标题"
    assert by_bvid["BV1yy411c7mD"]["origin"] == "openid-b-no-nick"
    assert by_bvid["BV1yy411c7mD"]["video_title"] == "回填视频标题"


def test_follow_monitor_detail_joins_code_send_and_bind(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    mtime = int(utcnow_naive().timestamp())
    db.add(FollowEvent(bili_uid="111", bili_name="小明", mtime=mtime - 60, sent_code=True, bound=False))
    db.add(Binding(bili_uid="111", bili_name="小明", activation_code="ABC111", code_sent_at=utcnow_naive()))
    db.add(FollowEvent(bili_uid="222", bili_name="小红", mtime=mtime - 120, sent_code=True, bound=False))
    db.add(Binding(bili_uid="222", bili_name="小红", activation_code="DEF222", bound_at=utcnow_naive()))
    db.add(FollowEvent(bili_uid="333", bili_name="阿强", mtime=mtime - 180, sent_code=False, bound=False))
    db.add(ActivationLog(bili_uid="333", code="", sent_ok=False, send_reason="network"))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/follow-monitor/detail", headers=_auth(token)).json()
    by_uid = {i["bili_uid"]: i for i in data["items"]}
    assert by_uid["111"]["code"] == "ABC111"
    assert by_uid["111"]["sent_ok"] is True
    assert by_uid["111"]["bound"] is False
    assert by_uid["222"]["bound"] is True
    assert by_uid["222"]["bound_at"]
    assert by_uid["333"]["sent_ok"] is False
    assert by_uid["333"]["send_reason"] == "network"
    assert by_uid["333"]["follow_time"]


def test_follow_monitor_summary(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    mtime = int(utcnow_naive().timestamp())
    db.add(FollowEvent(bili_uid="111", mtime=mtime - 60))
    db.add(FollowEvent(bili_uid="222", mtime=mtime - 120))
    db.add(Binding(bili_uid="111", activation_code="A", code_sent_at=utcnow_naive()))
    db.add(Binding(bili_uid="222", activation_code="B", bound_at=utcnow_naive()))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/follow-monitor?days=7", headers=_auth(token)).json()
    assert data["total"] == 2
    assert data["sent_ok"] == 2
    assert data["bound"] == 1
    assert data["today"] == 2


def test_activation_resend_sends_for_given_uids(admin_client):
    token = _login(admin_client).json()["token"]
    resp = admin_client.post(
        "/api/admin/activation/resend",
        json={"uids": ["111", "222"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["sent"] == 2
