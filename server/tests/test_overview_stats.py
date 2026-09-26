"""概览页 / 运营日报共用的按天口径。"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import sessionmaker

from app.models import (
    BiliCdnDomain,
    Binding,
    DownloadEvent,
    FollowEvent,
    ParseLog,
    User,
    VideoCard,
    VisitEvent,
)
from app.services import overview_stats

DAY = date(2026, 9, 18)
AT = datetime(2026, 9, 18, 1, 0)  # 上海时间 09:00
SH = timedelta(hours=8)


def _db(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()


def _seed(db):
    user = User(openid="openid-1", created_at=AT)
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(VisitEvent(user_id=user.id, path="home", created_at=AT))
    db.add(VisitEvent(user_id=user.id, path="home", created_at=AT))
    # 前一天的数据不该进这一天的快照
    db.add(VisitEvent(user_id=user.id, path="home", created_at=AT - timedelta(days=1)))

    db.add(FollowEvent(bili_uid="111", bili_name="A", mtime=1, sent_code=True, created_at=AT))
    db.add(FollowEvent(bili_uid="111", bili_name="A", mtime=2, created_at=AT))
    db.add(FollowEvent(bili_uid="222", bili_name="B", mtime=3, created_at=AT - timedelta(days=3)))
    db.add(Binding(bili_uid="111", activation_code="C1", bound_at=AT, created_at=AT))

    db.add(ParseLog(source="local", user_id=user.id, ok=True, created_at=AT))
    db.add(
        ParseLog(
            source="local", user_id=user.id, ok=False, reason="network", created_at=AT
        )
    )
    db.add(ParseLog(source="robot", bili_uid="111", ok=True, created_at=AT))
    db.add(ParseLog(source="local", user_id=user.id, ok=True, created_at=AT - timedelta(days=1)))

    db.add(
        VideoCard(
            user_id=user.id, bvid="BV1xx411c7mD", title="t", cover_url="", up_name="u",
            partition="", desc="", source_url="", source="local",
            collected_at=AT, month="2026-09",
        )
    )
    db.commit()
    return user


def _event(db, *, user_id, kind, session_id, stage, status, error_type="", host="h.example",
           at=None):
    db.add(
        DownloadEvent(
            user_id=user_id, bvid="BV1xx411c7mD", kind=kind, session_id=session_id,
            stage=stage, status=status, error_type=error_type, host=host,
            created_at=at or AT,
        )
    )


def _seed_downloads(db, user_id):
    # 视频：一次保存成功
    _event(db, user_id=user_id, kind="watermarked", session_id="v1", stage="resolve", status="success")
    _event(db, user_id=user_id, kind="watermarked", session_id="v1", stage="save", status="success")
    # 视频：下载失败后改用复制链接 → 算成功
    _event(db, user_id=user_id, kind="watermarked", session_id="v2", stage="resolve", status="success")
    _event(db, user_id=user_id, kind="watermarked", session_id="v2", stage="download", status="fail",
           error_type="domain_not_registered")
    _event(db, user_id=user_id, kind="watermarked", session_id="v2", stage="fallback", status="copy_link")
    # 视频：彻底失败
    _event(db, user_id=user_id, kind="watermarked", session_id="v3", stage="resolve", status="success")
    _event(db, user_id=user_id, kind="watermarked", session_id="v3", stage="download", status="fail",
           error_type="expired")
    # 音频：成功一次
    _event(db, user_id=user_id, kind="audio", session_id="a1", stage="download", status="success")
    # 字幕：失败一次
    _event(db, user_id=user_id, kind="subtitle", session_id="s1", stage="download", status="fail",
           error_type="wx_error")
    # 前一天：不该算进来
    _event(db, user_id=user_id, kind="watermarked", session_id="old", stage="save", status="success",
           at=AT - timedelta(days=1))
    db.commit()


def test_visit_section(db_engine):
    db = _db(db_engine)
    _seed(db)
    snapshot = overview_stats.day_snapshot(db, DAY)
    visit = snapshot["visit"]
    assert visit["uv"] == 1
    assert visit["pv"] == 2
    assert visit["new_users"] == 1
    assert visit["total_uv"] == 1
    assert visit["target"] == 500
    assert visit["remaining"] == 499
    db.close()


def test_bot_section_counts_distinct_followers(db_engine):
    db = _db(db_engine)
    _seed(db)
    bot = overview_stats.day_snapshot(db, DAY)["bot"]
    assert bot["new_follows"] == 1          # 同一个人两条关注事件只算一次
    assert bot["followers_total"] == 2      # 累计含 3 天前那个
    assert bot["bound"] == 1
    assert bot["conversion"] == 50.0
    assert bot["sent_ok"] == 1
    db.close()


def test_parse_section(db_engine):
    db = _db(db_engine)
    _seed(db)
    parse = overview_stats.day_snapshot(db, DAY)["parse"]
    assert parse["total"] == 3
    assert parse["ok"] == 2
    assert parse["fail"] == 1
    assert parse["fail_by_reason"] == [{"reason": "network", "count": 1}]
    assert parse["local_total"] == 2
    assert parse["robot_total"] == 1
    assert parse["local_users"] == 1
    assert parse["robot_users"] == 1
    assert parse["new_cards"] == 1
    db.close()


def test_download_section_separates_video_from_exports(db_engine):
    db = _db(db_engine)
    user = _seed(db)
    _seed_downloads(db, user.id)
    snapshot = overview_stats.day_snapshot(db, DAY)

    download = snapshot["download"]
    assert download["total"] == 3           # 只算视频，音频/字幕另有归属
    assert download["saved"] == 1
    assert download["copied"] == 1
    assert download["success"] == 2
    assert download["fail"] == 1
    assert download["success_rate"] == 66.7
    assert download["fail_by_error"] == [{"error_type": "expired", "count": 1}]

    exports = snapshot["exports"]
    assert exports["audio"] == {"total": 1, "users": 1, "success": 1, "fail": 0}
    assert exports["subtitle"] == {"total": 1, "users": 1, "success": 0, "fail": 1}
    # 没人用的项也要在，前端才能显示 0
    assert exports["comment"] == {"total": 0, "users": 0, "success": 0, "fail": 0}
    assert exports["danmaku"] == {"total": 0, "users": 0, "success": 0, "fail": 0}
    db.close()


def test_domains_section(db_engine):
    db = _db(db_engine)
    db.add(BiliCdnDomain(host="ok.example", is_configured=True, seen_count=10,
                         first_seen_at=AT, last_seen_at=AT))
    db.add(BiliCdnDomain(host="new.example", is_configured=False, seen_count=3,
                         first_seen_at=AT, last_seen_at=AT))
    db.add(BiliCdnDomain(host="old.example", is_configured=False, seen_count=2,
                         first_seen_at=AT - timedelta(days=5),
                         last_seen_at=AT - timedelta(days=5)))
    db.commit()

    domains = overview_stats.day_snapshot(db, DAY)["domains"]
    assert domains["total"] == 3
    assert domains["configured"] == 1
    assert domains["unconfigured"] == 2
    assert domains["hits"] == 15
    assert domains["seen"] == 2            # 这一天命中过 2 个
    assert [d["host"] for d in domains["new_unconfigured"]] == ["new.example"]
    db.close()


def test_snapshot_is_scoped_to_the_given_day(db_engine):
    """昨天的数据不该出现在今天的快照里（日报统计的是已收口的那一天）。"""
    db = _db(db_engine)
    user = _seed(db)
    _seed_downloads(db, user.id)
    yesterday = overview_stats.day_snapshot(db, DAY - timedelta(days=1))
    assert yesterday["visit"]["pv"] == 1
    assert yesterday["parse"]["total"] == 1
    assert yesterday["download"]["total"] == 1
    assert yesterday["exports"]["audio"]["total"] == 0
    db.close()


def test_overview_api_exposes_all_sections(admin_client):
    login = admin_client.post("/api/admin/login", json={"password": "admin-dev-password"})
    resp = admin_client.get(
        "/api/admin/stats/overview?days=30",
        headers={"Authorization": f"Bearer {login.json()['token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for key in ("visit", "bot", "parse", "download", "exports", "domains", "cookie"):
        assert key in data, key
    # 旧字段保留，避免既有页面被这次改动带崩
    for key in ("followers", "at", "activation", "local_parse", "robot_parse"):
        assert key in data
    assert data["visit"]["trend"]
    assert set(data["exports"]) == {"audio", "comment", "danmaku", "subtitle"}
