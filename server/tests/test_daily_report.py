from datetime import date, datetime, timedelta

from sqlalchemy.orm import sessionmaker

from app.models import (
    ActivationLog,
    BiliCdnDomain,
    Binding,
    DownloadEvent,
    FollowEvent,
    ParseLog,
    User,
    VideoCard,
    VisitEvent,
)
from app.services import config_store, daily_report


def _db(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)()


def _seed(db):
    at = datetime(2026, 9, 18, 1, 0)  # 上海时间 09:00
    user = User(openid="openid-1", created_at=at)
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(VisitEvent(user_id=user.id, path="home", created_at=at))
    db.add(VisitEvent(user_id=user.id, path="result", created_at=at))
    db.add(VisitEvent(user_id=user.id, path="home", created_at=at))
    db.add(ParseLog(source="local", user_id=user.id, ok=True, created_at=at))
    db.add(ParseLog(source="local", user_id=user.id, ok=False, reason="network_timeout", created_at=at))
    db.add(ParseLog(source="robot", bili_uid="1", ok=True, created_at=at))
    db.add(
        VideoCard(
            user_id=user.id,
            bvid="BV1xx411c7mD",
            title="t",
            cover_url="",
            up_name="u",
            partition="",
            desc="",
            source_url="",
            source="local",
            collected_at=at,
            month="2026-09",
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id,
            bvid="BV1xx411c7mD",
            kind="watermarked",
            host="a.example.com",
            stage="resolve",
            status="success",
            created_at=at,
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id,
            bvid="BV1xx411c7mD",
            kind="watermarked",
            host="a.example.com",
            stage="download",
            status="success",
            created_at=at,
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id,
            bvid="BV1xx411c7mD",
            kind="audio",
            host="b.example.com",
            stage="download",
            status="fail",
            error_type="domain_not_configured",
            created_at=at,
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id,
            bvid="BV1xx411c7mD",
            stage="fallback",
            status="copy_link",
            created_at=at,
        )
    )
    db.add(FollowEvent(bili_uid="111", mtime=1, sent_code=True, bound=False, created_at=at))
    db.add(ActivationLog(bili_uid="111", code="ABC", sent_ok=True, created_at=at))
    db.add(
        Binding(
            bili_uid="111",
            activation_code="ABC",
            bound_at=at,
            created_at=at,
        )
    )
    db.add(
        BiliCdnDomain(
            host="b.example.com",
            is_configured=False,
            first_seen_at=at,
            last_seen_at=at,
        )
    )
    db.commit()


def test_build_report_counts_daily_metrics(db_engine):
    db = _db(db_engine)
    _seed(db)
    data = daily_report.build_report(db, date(2026, 9, 18))

    assert data["users"]["new"] == 1
    assert data["users"]["total"] == 1
    assert data["users"]["uv"] == 1
    assert data["users"]["pv"] == 3
    assert data["parse"]["local_total"] == 2
    assert data["parse"]["local_ok"] == 1
    assert data["parse"]["local_fail"] == 1
    assert data["parse"]["robot_ok"] == 1
    assert data["parse"]["new_cards"] == 1
    assert data["download"]["requests"] == 1
    assert data["download"]["success"] == 1
    assert data["download"]["fail"] == 1
    assert data["download"]["success_rate"] == 50.0
    assert data["download"]["fallback_copy"] == 1
    assert data["download"]["fail_reasons"] == [("domain_not_configured", 1)]
    assert data["robot"]["new_follows"] == 1
    assert data["robot"]["activation_sent"] == 1
    assert data["robot"]["bound"] == 1
    assert data["domain"]["unconfigured_total"] == 1
    assert data["domain"]["new_unconfigured"] == ["b.example.com"]
    db.close()


def test_render_report_contains_sections(db_engine):
    db = _db(db_engine)
    _seed(db)
    text = daily_report.render_report(daily_report.build_report(db, date(2026, 9, 18)))
    assert "壁咚咚运营日报 2026-09-18" in text
    assert "今日新增用户：1" in text
    assert "下载成功率：50.0%" in text
    assert "失败后复制链接：1" in text
    assert "domain_not_configured：1" in text
    db.close()


def test_maybe_send_daily_report_once_per_day(db_engine, monkeypatch):
    db = _db(db_engine)
    config_store.set_alert_config(
        db, report_enabled=True, report_time="09:00", serverchan_sendkey="SCTtestkey"
    )
    calls = []
    monkeypatch.setattr(
        daily_report,
        "send_daily_report",
        lambda db, day: calls.append(day) or {"email": False, "serverchan": True},
    )

    now = datetime(2026, 9, 19, 10, 0)
    assert daily_report.maybe_send_daily_report(db, now=now) is True
    assert calls == [date(2026, 9, 18)]
    assert daily_report.maybe_send_daily_report(db, now=now) is False
    assert len(calls) == 1
    db.close()


def test_maybe_send_daily_report_before_time_is_noop(db_engine, monkeypatch):
    db = _db(db_engine)
    config_store.set_alert_config(db, report_enabled=True, report_time="09:00")
    called = []
    monkeypatch.setattr(
        daily_report, "send_daily_report", lambda db, day: called.append(day) or {}
    )

    assert daily_report.maybe_send_daily_report(db, now=datetime(2026, 9, 19, 8, 0)) is False
    assert called == []
    db.close()
