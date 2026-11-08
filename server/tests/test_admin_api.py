import tempfile
from datetime import timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import event
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
    VideoSource,
    VisitEvent,
)
from app.services import admin_stats
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


def test_parse_monitor_breaks_down_reporter(admin_client, db_engine):
    """B站链接解析按出处台账的 reporter 汇总/筛选，明细带上报方。"""
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add_all([
        VideoSource(bvid="BV1xx411c7mD", reporter="hol"),
        VideoSource(bvid="BV1yy411c7mD", reporter="belber"),
    ])
    db.add_all([
        ParseLog(source="local", platform="bilibili", input="a", bvid="BV1xx411c7mD", ok=True),
        ParseLog(source="local", platform="bilibili", input="a2", bvid="BV1xx411c7mD", ok=False, reason="x"),
        ParseLog(source="local", platform="bilibili", input="b", bvid="BV1yy411c7mD", ok=True),
        ParseLog(source="local", platform="bilibili", input="c", bvid="BV1zz411c7mD", ok=True),
    ])
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get(
        "/api/admin/stats/parse?source=local&platform=bilibili", headers=_auth(token)
    ).json()
    counts = {r["reporter"]: r["count"] for r in data["by_reporter"]}
    assert counts == {"hol": 2, "belber": 1, "未知": 1}

    detail = admin_client.get(
        "/api/admin/stats/parse/detail?source=local&platform=bilibili",
        headers=_auth(token),
    ).json()
    by_input = {i["input"]: i["reporter"] for i in detail["items"]}
    assert by_input["a"] == "hol"
    assert by_input["b"] == "belber"
    assert by_input["c"] == ""

    filtered = admin_client.get(
        "/api/admin/stats/parse/detail?source=local&platform=bilibili&reporter=hol",
        headers=_auth(token),
    ).json()
    assert filtered["total"] == 2
    assert {i["reporter"] for i in filtered["items"]} == {"hol"}


def test_parse_summary_groups_reporters_by_joined_column(db_engine):
    """上报方聚合要按裸列分组，避免 PostgreSQL 拒绝 coalesce 聚合表达式。"""
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", capture)
    try:
        admin_stats.parse_summary(db, "local", platform="bilibili")
    finally:
        event.remove(db_engine, "before_cursor_execute", capture)
        db.close()

    assert any("GROUP BY video_source.reporter" in sql for sql in statements)


def test_parse_trend_buckets_by_shanghai_date(admin_client, db_engine):
    """解析趋势按上海时区日期分桶，和关注 / 下载 / 访问几个页面同一口径。"""
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(ParseLog(source="local", input="BV1xx411c7mD", bvid="BV1xx411c7mD", ok=True))
    db.add(ParseLog(source="local", input="BV1yy411c7mD", ok=False, reason="network_timeout"))
    db.add(ParseLog(source="local", input="BV1zz411c7mD", ok=False, reason="network_timeout"))
    # 今天之外的记录不该被算进「今天」，但要在范围内
    db.add(
        ParseLog(
            source="local",
            input="BV1aa411c7mD",
            ok=True,
            created_at=utcnow_naive() - timedelta(days=1),
        )
    )
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/parse?source=local&days=7", headers=_auth(token)).json()

    assert len(data["trend"]) == 7
    assert data["trend"][-1]["ok"] == 1
    assert data["trend"][-1]["fail"] == 2
    assert data["trend"][-2]["ok"] == 1
    assert data["trend"][-2]["fail"] == 0
    assert data["trend"][0] == {"date": data["trend"][0]["date"], "ok": 0, "fail": 0}


def test_parse_trend_all_history_only_lists_days_with_data(admin_client, db_engine):
    """days=0 是「全部历史」：只给有数据的日期，不铺一堆空柱子。"""
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(
        ParseLog(
            source="local",
            input="BV1aa411c7mD",
            ok=True,
            created_at=utcnow_naive() - timedelta(days=9),
        )
    )
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get("/api/admin/stats/parse?source=local&days=0", headers=_auth(token)).json()

    assert len(data["trend"]) == 1
    assert data["trend"][0]["ok"] == 1


def test_admin_parse_view_has_trend_chart(admin_client):
    html = admin_client.get("/admin/index.html").text
    assert 'id="chart-parse"' in html
    assert 'drawChart("chart-parse"' in html
    # 平台切换要同时作用于卡片与趋势，别只筛明细
    assert '"/stats/parse?source=local&days=" + days + "&platform=" + platform' in html
    # 解析监控按上报方汇总/筛选，明细也有这一列
    assert "上报方分布" in html
    assert "parseReporter" in html
    assert "<th>上报方</th>" in html


def test_admin_charts_load_echarts_from_local_static(admin_client):
    """管理端图表不能依赖外部 CDN，否则 CDN 不可达时所有趋势图都不显示。"""
    html = admin_client.get("/admin/").text
    assert '<script src="/admin/vendor/echarts.min.js"></script>' in html

    script = admin_client.get("/admin/vendor/echarts.min.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert "echarts" in script.text.lower()


def test_admin_crawler_page_distinguishes_api_paths(admin_client):
    """爬虫表里来源=请求头 记的是 API 路径，别把列名写成「页面」误导人。"""
    html = admin_client.get("/admin/index.html").text
    assert "爬虫访问路径" in html
    assert "路径（API / 页面）" in html
    assert "记的是 API 请求路径" in html


def test_parse_detail_supports_history_pagination(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    now = utcnow_naive()
    for i in range(25):
        db.add(
            ParseLog(
                source="local",
                input=f"BV1xx411c{i:02d}",
                bvid=f"BV1xx411c{i:02d}",
                ok=i % 2 == 0,
                reason="" if i % 2 == 0 else "network_timeout",
                created_at=now - timedelta(minutes=i),
            )
        )
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get(
        "/api/admin/stats/parse/detail?source=local&days=0&page=2&size=20",
        headers=_auth(token),
    ).json()

    assert data["total"] == 25
    assert data["page"] == 2
    assert data["size"] == 20
    assert data["pages"] == 2
    assert len(data["items"]) == 5


def test_at_detail_supports_all_history_and_pagination(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    old = utcnow_naive() - timedelta(days=120)
    for i in range(22):
        db.add(
            AtEvent(
                feed_id=f"old-{i}",
                bili_uid=str(1000 + i),
                bvid=f"BV1yy411c{i:02d}",
                result="collected",
                created_at=old + timedelta(minutes=i),
            )
        )
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get(
        "/api/admin/stats/at/detail?days=0&page=2&size=20",
        headers=_auth(token),
    ).json()

    assert data["total"] == 22
    assert data["page"] == 2
    assert data["size"] == 20
    assert data["pages"] == 2
    assert len(data["items"]) == 2


def test_admin_parse_view_has_history_pagination_controls(admin_client):
    html = admin_client.get("/admin/index.html").text
    assert "全部历史" in html
    assert "parsePage(-1)" in html
    assert "parsePage(1)" in html
    assert "parseSize(this.value)" in html
    assert "S.parse.page" in html
    assert "S.parse.size" in html
    assert '"/stats/parse/detail?source=local" + rangeSuffix' in html


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
        json={"robot_guide": False, "share": False, "at_reply": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"robot_guide": False, "share": False, "at_reply": False}


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


def test_cookie_update_supports_netscape_format(admin_client):
    token = _login(admin_client).json()["token"]
    cookie_text = """# Netscape HTTP Cookie File
# https://curl.haxx.se/rfc/cookie_spec.html
# This is a generated file! Do not edit.
.bilibili.com\tTRUE\t/\tTRUE\t1806592776\tSESSDATA\tnetscape-sess
.bilibili.com\tTRUE\t/\tTRUE\t1806592776\tbili_jct\tnetscape-jct
.bilibili.com\tTRUE\t/\tTRUE\t1806592776\tDedeUserID\t999
.bilibili.com\tTRUE\t/\tFALSE\t1806846006\tbuvid3\tnetscape-b3
.bilibili.com\tTRUE\t/\tFALSE\t1825601195\tbuvid4\tnetscape-b4
"""
    resp = admin_client.post(
        "/api/admin/cookie/update",
        json={"cookie_text": cookie_text},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["saved_fields"] == [
        "SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"
    ]


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
    assert detail["items"][0]["created_at"].endswith("Z")


def test_download_detail_shows_openid_video_title_and_link(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = User(openid="openid-dl-a", nickname="下载用户")
    db.add(user)
    db.commit()
    db.refresh(user)
    card = VideoCard(
        user_id=user.id,
        bvid="BV1xx411c7mD",
        title="帅哥合集 01",
        cover_url="",
        up_name="UP",
        partition="",
        desc="",
        source_url="https://www.bilibili.com/video/BV1xx411c7mD",
        source="local",
        collected_at=utcnow_naive(),
        month="2026-09",
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    db.add(
        DownloadEvent(
            user_id=user.id,
            card_id=card.id,
            bvid=card.bvid,
            video_title=card.title,
            source_url=card.source_url,
            kind="watermarked",
            qn=16,
            host="upos-sz-mirrorcoso1.bilivideo.com",
            stage="download",
            status="success",
            created_at=utcnow_naive(),
        )
    )
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    detail = admin_client.get(
        "/api/admin/stats/download/detail", headers=_auth(token)
    ).json()
    item = detail["items"][0]
    assert item["openid"] == "openid-dl-a"
    assert item["video_title"] == "帅哥合集 01"
    assert item["source_url"] == "https://www.bilibili.com/video/BV1xx411c7mD"

    by_user = admin_client.get(
        "/api/admin/stats/download/detail",
        params={"q": "openid-dl-a"},
        headers=_auth(token),
    ).json()
    assert by_user["total"] == 1

    by_title = admin_client.get(
        "/api/admin/stats/download/detail",
        params={"q": "帅哥合集"},
        headers=_auth(token),
    ).json()
    assert by_title["total"] == 1


def test_visit_monitor_lists_openid_and_counts(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    u1 = User(openid="openid-v1", nickname="小明")
    u2 = User(openid="openid-v2")
    db.add_all([u1, u2])
    db.commit()
    db.refresh(u1)
    db.refresh(u2)
    now = utcnow_naive()
    db.add_all(
        [
            VisitEvent(
                user_id=u1.id,
                path="pages/home/home",
                env_version="trial",
                api_base="https://api.beastnotes.cn",
                created_at=now,
            ),
            VisitEvent(
                user_id=u1.id,
                path="pages/home/home",
                env_version="trial",
                api_base="https://api.beastnotes.cn",
                created_at=now,
            ),
            VisitEvent(user_id=u2.id, path="pages/home/home", created_at=now),
        ]
    )
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    summary = admin_client.get(
        "/api/admin/stats/visit?days=30", headers=_auth(token)
    ).json()
    assert summary["pv"] == 3
    assert summary["uv"] == 2
    assert summary["today_pv"] == 3
    assert summary["today_uv"] == 2
    assert summary["total_uv"] == 2
    assert sum(point["pv"] for point in summary["trend"]) == 3
    assert sum(point["uv"] for point in summary["trend"]) == 2

    detail = admin_client.get(
        "/api/admin/stats/visit/detail?days=30", headers=_auth(token)
    ).json()
    assert detail["total"] == 3
    by_openid = {i["openid"]: i for i in detail["items"]}
    assert set(by_openid) == {"openid-v1", "openid-v2"}
    assert by_openid["openid-v1"]["nickname"] == "小明"
    assert by_openid["openid-v1"]["path"] == "pages/home/home"
    assert by_openid["openid-v1"]["env_version"] == "trial"
    assert by_openid["openid-v1"]["api_base"] == "https://api.beastnotes.cn"
    assert by_openid["openid-v2"]["nickname"] == ""
    assert detail["items"][0]["created_at"]

    only_v2 = admin_client.get(
        "/api/admin/stats/visit/detail",
        params={"q": "openid-v2"},
        headers=_auth(token),
    ).json()
    assert only_v2["total"] == 1

    by_nickname = admin_client.get(
        "/api/admin/stats/visit/detail",
        params={"q": "小明"},
        headers=_auth(token),
    ).json()
    assert by_nickname["total"] == 2


def _add_download_events(db, user_id, bvid, rows):
    """rows: [(距现在多少秒前, stage, status, session_id, error_type, error_message)]"""
    from datetime import timedelta

    now = utcnow_naive()
    for seconds_ago, stage, status, session_id, error_type, message in rows:
        db.add(
            DownloadEvent(
                user_id=user_id,
                bvid=bvid,
                video_title="测试视频",
                source_url=f"https://www.bilibili.com/video/{bvid}",
                kind="watermarked",
                host="upos-sz-estgoss.bilivideo.com",
                stage=stage,
                status=status,
                session_id=session_id,
                error_type=error_type,
                error_message=message,
                created_at=now - timedelta(seconds=seconds_ago),
            )
        )
    db.commit()


def test_download_sessions_split_legacy_events_on_resolve(admin_client, db_engine):
    """没有 session_id 的历史事件：同一 bvid 内遇到 resolve 就开新会话。"""
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = User(openid="openid-dl-session")
    db.add(user)
    db.commit()
    db.refresh(user)
    _add_download_events(
        db,
        user.id,
        "BV1xx411c7mD",
        [
            (150, "resolve", "success", "", "", ""),
            (149, "download", "success", "", "", ""),
            (60, "save", "fail", "", "permission", "saveVideoToPhotosAlbum:fail:auth denied"),
            (20, "resolve", "success", "", "", ""),
            (19, "download", "success", "", "", ""),
            (18, "save", "fail", "", "permission", "saveVideoToPhotosAlbum:fail auth deny"),
            (10, "fallback", "copy_link", "", "", ""),
            (5, "fallback", "copy_link", "", "", ""),
        ],
    )
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get(
        "/api/admin/stats/download/sessions", headers=_auth(token)
    ).json()
    assert data["total"] == 2
    newest, oldest = data["items"][0], data["items"][1]
    assert newest["openid"] == "openid-dl-session"
    assert newest["bvid"] == "BV1xx411c7mD"
    assert newest["result"] == "fail"
    assert newest["fail_stage"] == "save"
    assert newest["fail_error_type"] == "permission"
    assert "auth deny" in newest["fail_message"]
    assert newest["copied_link"] is True
    assert newest["event_count"] == 5

    assert oldest["result"] == "fail"
    assert oldest["fail_stage"] == "save"
    assert oldest["copied_link"] is False
    assert oldest["event_count"] == 3

    summary = admin_client.get(
        "/api/admin/stats/download?days=30", headers=_auth(token)
    ).json()
    assert summary["total"] == 2
    assert summary["success"] == 0
    assert summary["fail"] == 2
    assert {"error_type": "permission", "count": 2} in summary["fail_by_error"]
    assert {"error_type": "unknown", "count": 2} not in summary["fail_by_error"]


def test_download_sessions_prefer_session_id_and_ignore_copy_link(admin_client, db_engine):
    """有 session_id 时按 id 切分；copy_link 不算失败。"""
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    user = User(openid="openid-dl-sid")
    db.add(user)
    db.commit()
    db.refresh(user)
    _add_download_events(
        db,
        user.id,
        "BV1yy411c7mD",
        [
            (200, "resolve", "success", "s1", "", ""),
            (198, "download", "success", "s1", "", ""),
            (190, "save", "success", "s1", "", ""),
            (100, "resolve", "success", "s2", "", ""),
            (99, "download", "success", "s2", "", ""),
            (98, "save", "fail", "s2", "permission", "auth deny"),
            (95, "fallback", "copy_link", "s2", "", ""),
            (50, "resolve", "fail", "s3", "domain_not_registered", "暂无已配置的下载域名"),
        ],
    )
    db.close()

    token = _login(admin_client).json()["token"]
    data = admin_client.get(
        "/api/admin/stats/download/sessions", headers=_auth(token)
    ).json()
    assert data["total"] == 3
    by_result = {(i["result"], i["fail_stage"]) for i in data["items"]}
    assert by_result == {("success", ""), ("fail", "save"), ("fail", "resolve")}

    summary = admin_client.get(
        "/api/admin/stats/download?days=30", headers=_auth(token)
    ).json()
    assert summary["total"] == 3
    assert summary["success"] == 1
    assert summary["fail"] == 2
    assert summary["success_rate"] == 33.3


def test_download_monitor_pagination_supports_all_history(admin_client, db_engine):
    """days=0 查全部历史；两种明细都按 page/size 分页。"""
    from datetime import timedelta

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    now = utcnow_naive()
    db.add(
        DownloadEvent(
            bvid="BV1old000000",
            kind="watermarked",
            stage="save",
            status="success",
            created_at=now - timedelta(days=400),
        )
    )
    db.add(
        DownloadEvent(
            bvid="BV1new000000",
            kind="watermarked",
            stage="save",
            status="success",
            created_at=now - timedelta(hours=1),
        )
    )
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    detail_30 = admin_client.get(
        "/api/admin/stats/download/detail",
        params={"days": 30, "page": 1, "size": 1},
        headers=_auth(token),
    ).json()
    assert detail_30["total"] == 1
    assert detail_30["items"][0]["bvid"] == "BV1new000000"

    detail_all_page2 = admin_client.get(
        "/api/admin/stats/download/detail",
        params={"days": 0, "page": 2, "size": 1},
        headers=_auth(token),
    ).json()
    assert detail_all_page2["total"] == 2
    assert detail_all_page2["items"][0]["bvid"] == "BV1old000000"

    sessions_30 = admin_client.get(
        "/api/admin/stats/download/sessions",
        params={"days": 30, "page": 1, "size": 1},
        headers=_auth(token),
    ).json()
    assert sessions_30["total"] == 1
    assert sessions_30["items"][0]["bvid"] == "BV1new000000"

    sessions_all_page2 = admin_client.get(
        "/api/admin/stats/download/sessions",
        params={"days": 0, "page": 2, "size": 1},
        headers=_auth(token),
    ).json()
    assert sessions_all_page2["total"] == 2
    assert sessions_all_page2["items"][0]["bvid"] == "BV1old000000"

    summary_all = admin_client.get(
        "/api/admin/stats/download",
        params={"days": 0},
        headers=_auth(token),
    ).json()
    assert summary_all["total"] == 2
    assert sum(x["count"] for x in summary_all["trend"]) == 2


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


def test_bulk_import_domains(admin_client, db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    db.add(BiliCdnDomain(host="upos-sz-mirrorcoso1.bilivideo.com", is_configured=False))
    db.add(BiliCdnDomain(host="upos-sz-estgcos.bilivideo.com", is_configured=True))
    db.commit()
    db.close()

    token = _login(admin_client).json()["token"]
    text = "[https://upos-sz-mirrorcoso1.bilivideo.com;https://upos-sz-estgcos.bilivideo.com;https://cn-jstz-cu-01-02.bilivideo.com;https://cn-jstz-cu-01-02.bilivideo.com](https://upos-sz-mirrorcoso1.bilivideo.com)"
    resp = admin_client.post(
        "/api/admin/download/domains/bulk",
        json={"text": text},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inserted"] == ["cn-jstz-cu-01-02.bilivideo.com"]
    assert data["updated"] == ["upos-sz-mirrorcoso1.bilivideo.com"]
    assert data["already_configured"] == ["upos-sz-estgcos.bilivideo.com"]
    assert data["invalid"] == []

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    db = Session()
    rows = {r.host: r.is_configured for r in db.query(BiliCdnDomain).all()}
    db.close()
    assert rows["upos-sz-mirrorcoso1.bilivideo.com"] is True
    assert rows["upos-sz-estgcos.bilivideo.com"] is True
    assert rows["cn-jstz-cu-01-02.bilivideo.com"] is True


@respx.mock
def test_operations_config_and_serverchan_test(admin_client):
    token = _login(admin_client).json()["token"]
    put = admin_client.put(
        "/api/admin/config/alert",
        json={
            "serverchan_sendkey": "SCTtestkey",
            "alert_cookie_enabled": False,
            "alert_domain_enabled": True,
            "alert_fault_enabled": False,
            "report_enabled": True,
            "report_time": "08:30",
        },
        headers=_auth(token),
    )
    assert put.status_code == 200
    data = put.json()
    assert data["serverchan_sendkey"] == "SCTtestkey"
    assert data["alert_cookie_enabled"] is False
    assert data["alert_fault_enabled"] is False
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
