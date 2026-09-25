"""概览页的五个口径：访问 / 机器人 / 解析 / 下载 / 域名。"""

from datetime import timedelta

from sqlalchemy.orm import sessionmaker

from app.models import BiliCdnDomain, DownloadEvent, FollowEvent, ParseLog, User
from app.services import overview_stats
from app.time import utcnow_naive


def _db(db_engine):
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    return Session()


def _parse_log(db, source, *, user_id=None, bili_uid=None, ok=True, count=1):
    for _ in range(count):
        db.add(
            ParseLog(
                source=source,
                user_id=user_id,
                bili_uid=bili_uid,
                ok=ok,
                reason="" if ok else "network",
            )
        )
    db.commit()


def test_parse_users_counts_distinct_users(db_engine):
    db = _db(db_engine)
    # 同一个用户解析 3 次只算 1 个人
    _parse_log(db, "local", user_id=1, count=3)
    _parse_log(db, "local", user_id=2, count=1)
    # 机器人链路没有小程序用户，按 B站 UID 去重
    _parse_log(db, "robot", bili_uid="111", count=2)
    _parse_log(db, "robot", bili_uid="222", count=1)
    _parse_log(db, "robot", bili_uid="", count=1)  # 空 UID 不算人
    _parse_log(db, "local", user_id=1, ok=False, count=1)

    result = overview_stats.parse_users(db)
    assert result["local_users"] == 2
    assert result["robot_users"] == 2
    assert result["local_ok"] == 4
    assert result["local_fail"] == 1
    assert result["robot_ok"] == 4
    db.close()


def _event(db, *, session_id, stage, status, bvid="BV1", kind="watermarked", user_id=1,
           error_type="", host="h.example", days_ago=0):
    db.add(
        DownloadEvent(
            user_id=user_id,
            bvid=bvid,
            session_id=session_id,
            kind=kind,
            stage=stage,
            status=status,
            error_type=error_type,
            host=host,
            created_at=utcnow_naive() - timedelta(days=days_ago),
        )
    )


def test_download_outcomes_counts_copied_link_as_success(db_engine):
    db = _db(db_engine)
    db.add(User(id=1, openid="u1"))
    db.add(User(id=2, openid="u2"))
    db.commit()

    # A：正常保存成功
    _event(db, session_id="a", stage="resolve", status="success")
    _event(db, session_id="a", stage="download", status="success")
    _event(db, session_id="a", stage="save", status="success")
    # B：下载失败，用户改用复制链接兜底 —— 按成功算
    _event(db, session_id="b", stage="resolve", status="success")
    _event(db, session_id="b", stage="download", status="fail", error_type="domain_not_registered")
    _event(db, session_id="b", stage="fallback", status="copy_link")
    # C：彻底失败
    _event(db, session_id="c", stage="resolve", status="success")
    _event(db, session_id="c", stage="download", status="fail", error_type="expired")
    db.commit()

    result = overview_stats.download_outcomes(db)
    assert result["total"] == 3
    assert result["saved"] == 1
    assert result["copied"] == 1
    assert result["fail"] == 1
    assert result["success"] == 2
    assert result["success_rate"] == 66.7
    # 成功原因不该出现在失败原因里
    assert result["fail_by_error"] == [{"error_type": "expired", "count": 1}]
    db.close()


def test_domain_summary(db_engine):
    db = _db(db_engine)
    db.add(BiliCdnDomain(host="a.example", is_configured=True, seen_count=10))
    db.add(BiliCdnDomain(host="b.example", is_configured=False, seen_count=3))
    db.add(BiliCdnDomain(host="c.example", is_configured=False, seen_count=2))
    db.commit()

    result = overview_stats.domain_summary(db)
    assert result["total"] == 3
    assert result["configured"] == 1
    assert result["unconfigured"] == 2
    assert result["hits"] == 15
    assert {h["host"] for h in result["recent_unconfigured"]} == {"b.example", "c.example"}
    db.close()


def test_download_outcomes_splits_today(db_engine):
    """今日下载单独看一份，不然当天有没有人在下载只能靠眼力从累计里抠。"""
    db = _db(db_engine)
    db.add(User(id=1, openid="u1"))
    db.commit()

    # 今天：一次保存成功
    _event(db, session_id="a", stage="resolve", status="success")
    _event(db, session_id="a", stage="save", status="success")
    # 今天：一次彻底失败
    _event(db, session_id="b", stage="resolve", status="success")
    _event(db, session_id="b", stage="download", status="fail", error_type="wx_error")
    # 3 天前：成功，但不该算进"今日"
    _event(db, session_id="c", stage="resolve", status="success", days_ago=3)
    _event(db, session_id="c", stage="save", status="success", days_ago=3)
    db.commit()

    result = overview_stats.download_outcomes(db)
    assert result["total"] == 3
    assert result["saved"] == 2
    assert result["fail"] == 1
    assert result["today_total"] == 2
    assert result["today_saved"] == 1
    assert result["today_copied"] == 0
    assert result["today_fail"] == 1
    db.close()


def test_domain_summary_counts_new_unconfigured_today(db_engine):
    db = _db(db_engine)
    db.add(
        BiliCdnDomain(
            host="old.example",
            is_configured=False,
            seen_count=1,
            first_seen_at=utcnow_naive() - timedelta(days=5),
        )
    )
    db.add(
        BiliCdnDomain(
            host="new.example", is_configured=False, seen_count=1,
            first_seen_at=utcnow_naive(),
        )
    )
    db.add(
        BiliCdnDomain(
            host="ok.example", is_configured=True, seen_count=2,
            first_seen_at=utcnow_naive(),
        )
    )
    db.commit()

    result = overview_stats.domain_summary(db)
    # 已配置的新域名不算"需要处理的新增"
    assert result["new_unconfigured_today"] == 1
    assert [h["host"] for h in result["new_unconfigured_today_hosts"]] == ["new.example"]
    assert result["unconfigured"] == 2
    db.close()


def test_bot_section_has_followers_and_bound(db_engine):
    db = _db(db_engine)
    db.add(FollowEvent(bili_uid="111", bili_name="A", mtime=1, sent_code=True))
    db.add(FollowEvent(bili_uid="222", bili_name="B", mtime=2, sent_code=True))
    db.commit()

    from app.models import Binding
    from app.time import utcnow_naive

    db.add(Binding(bili_uid="111", activation_code="CODE1", bound_at=utcnow_naive()))
    db.commit()

    section = overview_stats.bot_section(db)
    assert section["followers_total"] == 2
    assert section["bound"] == 1
    assert section["conversion"] == 50.0
    db.close()


def test_overview_api_exposes_five_sections(admin_client):
    login = admin_client.post("/api/admin/login", json={"password": "admin-dev-password"})
    token = login.json()["token"]
    resp = admin_client.get(
        "/api/admin/stats/overview?days=30",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for key in ("visit", "bot", "parse", "download", "domains", "cookie"):
        assert key in data, f"缺少 {key}"
    # 旧字段保留，避免既有页面/测试被这次改动带崩
    for key in ("followers", "at", "activation", "local_parse", "robot_parse"):
        assert key in data
    assert "today_uv" in data["visit"]
    assert "total_uv" in data["visit"]
    assert data["visit"]["target"] == 500
    assert "local_users" in data["parse"]
    assert "copied" in data["download"]
    assert "today_total" in data["download"]
    assert "unconfigured" in data["domains"]
    assert "new_unconfigured_today" in data["domains"]
    # 访问趋势给底部图表用
    assert data["visit"]["trend"]
    assert "uv" in data["visit"]["trend"][0]
