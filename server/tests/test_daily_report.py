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
            session_id="v1",
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
            session_id="v1",
            host="a.example.com",
            stage="save",
            status="success",
            created_at=at,
        )
    )
    # 视频：下载失败后改用复制链接 → 算成功
    db.add(
        DownloadEvent(
            user_id=user.id, bvid="BV1xx411c7mD", kind="watermarked", session_id="v2",
            stage="resolve", status="success", created_at=at,
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id, bvid="BV1xx411c7mD", kind="watermarked", session_id="v2",
            host="a.example.com", stage="download", status="fail",
            error_type="domain_not_registered", created_at=at,
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id, bvid="BV1xx411c7mD", kind="watermarked", session_id="v2",
            stage="fallback", status="copy_link", created_at=at,
        )
    )
    # 视频：彻底失败
    db.add(
        DownloadEvent(
            user_id=user.id, bvid="BV1xx411c7mD", kind="watermarked", session_id="v3",
            stage="resolve", status="success", created_at=at,
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id, bvid="BV1xx411c7mD", kind="watermarked", session_id="v3",
            host="c.example.com", stage="download", status="fail",
            error_type="expired", created_at=at,
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id,
            bvid="BV1xx411c7mD",
            kind="comment",
            session_id="c1",
            stage="download",
            status="success",
            created_at=at,
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id,
            bvid="BV1xx411c7mD",
            kind="danmaku",
            session_id="d1",
            stage="download",
            status="fail",
            error_type="download_error",
            created_at=at,
        )
    )
    db.add(
        DownloadEvent(
            user_id=user.id,
            bvid="BV1xx411c7mD",
            kind="audio",
            session_id="a1",
            host="b.example.com",
            stage="download",
            status="fail",
            error_type="domain_not_configured",
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

    # 口径与后台概览完全一致：同一份 day_snapshot
    assert data["visit"]["new_users"] == 1
    assert data["visit"]["total_users"] == 1
    assert data["visit"]["uv"] == 1
    assert data["visit"]["pv"] == 3
    assert data["parse"]["local_total"] == 2
    assert data["parse"]["ok"] == 2
    assert data["parse"]["fail"] == 1
    assert data["parse"]["local_users"] == 1
    assert data["parse"]["robot_users"] == 1
    assert data["parse"]["new_cards"] == 1
    # 视频下载按「一次下载」算：保存成功 / 复制链接兜底 / 彻底失败各 1 次
    assert data["download"]["total"] == 3
    assert data["download"]["saved"] == 1
    assert data["download"]["copied"] == 1
    assert data["download"]["success"] == 2
    assert data["download"]["fail"] == 1
    assert data["download"]["success_rate"] == 66.7
    assert data["download"]["fail_by_error"] == [{"error_type": "expired", "count": 1}]
    assert data["exports"]["audio"]["users"] == 1
    assert data["exports"]["audio"]["success"] == 0
    assert data["exports"]["audio"]["fail"] == 1
    assert data["exports"]["comment"]["users"] == 1
    assert data["exports"]["comment"]["success"] == 1
    assert data["exports"]["danmaku"]["fail"] == 1
    # 概览里也有字幕了（原来漏了）
    assert "subtitle" in data["exports"]
    assert data["exports"]["subtitle"]["total"] == 0
    assert data["bot"]["new_follows"] == 1
    assert data["bot"]["sent_ok"] == 1
    assert data["bot"]["bound"] == 1
    assert data["domains"]["unconfigured"] == 1
    assert [d["host"] for d in data["domains"]["new_unconfigured"]] == ["b.example.com"]
    db.close()


def test_render_report_contains_sections(db_engine):
    db = _db(db_engine)
    _seed(db)
    text = daily_report.render_report(daily_report.build_report(db, date(2026, 9, 18)))
    assert "壁咚咚运营日报 2026-09-18" in text
    # 报告按概览的分区顺序组织
    for section in (
        "## 一、访问情况",
        "## 二、机器人关注与绑定",
        "## 三、视频解析",
        "## 四、视频下载",
        "## 五、音频 / 评论 / 弹幕 / 字幕",
        "## 六、B站 CDN 域名",
    ):
        assert section in text, section
    assert "当日访问用户：1 人（访问 3 次）" in text
    assert "累计访问用户：1 / 500" in text
    assert "当日下载：3 次" in text
    assert "成功：2（保存 1 + 复制链接 1）" in text
    assert "成功率：66.7%" in text
    assert "失败原因：expired：1" in text
    assert "音频：1 次 · 1 人（成功 0 / 失败 1）" in text
    assert "评论：1 次 · 1 人（成功 1 / 失败 0）" in text
    assert "弹幕：1 次 · 1 人（成功 0 / 失败 1）" in text
    assert "- 字幕：0 次 · 0 人" in text
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
