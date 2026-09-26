"""概览页与运营日报共用的统计口径。

按运营真正关心的几件事组织：访问 / 机器人关注与绑定 / 视频解析 / 视频下载 /
音频·评论·弹幕·字幕 / B站 CDN 域名。

两者唯一的区别是「统计哪一天」：概览看今天（实时），日报看昨天（已收口）。
所以核心是 `day_snapshot(db, day)`，两个入口都从它取数，口径不会各写一份。

下载沿用 `admin_stats` 那套会话切分（一次下载算一次），不重新发明。
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import (
    BiliCdnDomain,
    Binding,
    DownloadEvent,
    FollowEvent,
    ParseLog,
    User,
    VideoCard,
    VisitEvent,
)
from . import admin_stats, config_store

SH_OFFSET = timedelta(hours=8)
# 500 访客目标（微信小程序开广告/流量主的门槛），概览与日报共用
USER_TARGET = 500

VIDEO_KINDS = ("watermarked", "clean")
EXPORT_KINDS = ("audio", "comment", "danmaku", "subtitle")


def _day_range(day: date) -> tuple[datetime, datetime]:
    """上海自然日 -> naive UTC 区间。"""
    start = datetime(day.year, day.month, day.day) - SH_OFFSET
    return start, start + timedelta(days=1)


def _day_sessions(db: Session, start: datetime, end: datetime) -> list[dict]:
    """某一天内的下载会话。

    按显式日期区间取数，因为日报统计的是"昨天"，不是"最近 N 天"。
    会话切分规则复用 admin_stats，避免两处口径不一致。
    """
    rows = (
        db.query(DownloadEvent, User)
        .outerjoin(User, User.id == DownloadEvent.user_id)
        .filter(DownloadEvent.created_at >= start, DownloadEvent.created_at < end)
        .order_by(DownloadEvent.created_at.asc())
        .all()
    )
    sessions: list[dict] = []
    for raw in admin_stats._build_download_sessions(rows):
        view = admin_stats._session_view(raw)
        view["user_id"] = raw["key"][0]
        sessions.append(view)
    return sessions


def _download_stats(sessions: list[dict]) -> dict:
    """只看视频下载（音频/评论/弹幕/字幕在 exports 里单独统计）。

    用户下载失败后改用「复制链接到浏览器保存」是正常路径，算成功。
    """
    videos = [s for s in sessions if (s.get("kind") or "") in VIDEO_KINDS]
    saved = copied = fail = 0
    by_error: dict[str, int] = {}
    by_host: dict[str, int] = {}
    for session in videos:
        if session["result"] == "success":
            saved += 1
        elif session["copied_link"]:
            copied += 1
        else:
            fail += 1
            key = session["fail_error_type"] or "unknown"
            by_error[key] = by_error.get(key, 0) + 1
            if session.get("host"):
                by_host[session["host"]] = by_host.get(session["host"], 0) + 1

    total = len(videos)
    success = saved + copied
    return {
        "total": total,
        "saved": saved,
        "copied": copied,
        "success": success,
        "fail": fail,
        "success_rate": round(success / total * 100, 1) if total else 0.0,
        "fail_by_error": [
            {"error_type": key, "count": value}
            for key, value in sorted(by_error.items(), key=lambda item: -item[1])
        ],
        "fail_by_host": [
            {"host": host, "count": count}
            for host, count in sorted(by_host.items(), key=lambda item: -item[1])
        ],
    }


def _export_stats(sessions: list[dict]) -> dict:
    """音频 / 评论 / 弹幕 / 字幕：有没有人用、用了多少次、成没成。"""
    result: dict[str, dict] = {}
    for kind in EXPORT_KINDS:
        items = [s for s in sessions if (s.get("kind") or "") == kind]
        success = sum(1 for s in items if s["result"] == "success")
        result[kind] = {
            "total": len(items),
            "users": len({s["user_id"] for s in items if s.get("user_id")}),
            "success": success,
            "fail": len(items) - success,
        }
    return result


def day_snapshot(db: Session, day: date) -> dict:
    """某一天的完整快照：概览看今天，运营日报看昨天。"""
    start, end = _day_range(day)
    sessions = _day_sessions(db, start, end)

    # ---- 访问 ----
    visits = (
        db.query(VisitEvent)
        .filter(VisitEvent.created_at >= start, VisitEvent.created_at < end)
        .all()
    )
    total_uv = db.query(func.count(func.distinct(VisitEvent.user_id))).scalar() or 0
    visit = {
        "uv": len({v.user_id for v in visits}),
        "pv": len(visits),
        "new_users": db.query(User)
        .filter(User.created_at >= start, User.created_at < end)
        .count(),
        "total_uv": total_uv,
        "total_users": db.query(User).count(),
        "target": USER_TARGET,
        "progress": round(total_uv / USER_TARGET * 100, 1) if USER_TARGET else 0.0,
        "remaining": max(USER_TARGET - total_uv, 0),
    }

    # ---- 机器人 ----
    follow_uids = {
        uid
        for (uid,) in db.query(FollowEvent.bili_uid)
        .filter(FollowEvent.created_at >= start, FollowEvent.created_at < end)
        .all()
    }
    followers_total = (
        db.query(func.count(func.distinct(FollowEvent.bili_uid))).scalar() or 0
    )
    bound = db.query(Binding).filter(Binding.bound_at.isnot(None)).count()
    bot = {
        "new_follows": len(follow_uids),
        "followers_total": followers_total,
        "sent_ok": db.query(Binding)
        .filter(
            Binding.created_at >= start,
            Binding.created_at < end,
            or_(Binding.code_sent_at.isnot(None), Binding.bound_at.isnot(None)),
        )
        .count(),
        "bound": bound,
        "conversion": round(bound / followers_total * 100, 1) if followers_total else 0.0,
    }

    # ---- 解析 ----
    parses = (
        db.query(ParseLog)
        .filter(ParseLog.created_at >= start, ParseLog.created_at < end)
        .all()
    )
    local = [p for p in parses if p.source == "local"]
    robot = [p for p in parses if p.source == "robot"]
    reasons: dict[str, int] = {}
    for item in parses:
        if not item.ok:
            key = item.reason or "other"
            reasons[key] = reasons.get(key, 0) + 1
    parse = {
        "total": len(parses),
        "ok": sum(1 for p in parses if p.ok),
        "fail": sum(1 for p in parses if not p.ok),
        "fail_by_reason": [
            {"reason": key, "count": value}
            for key, value in sorted(reasons.items(), key=lambda item: -item[1])
        ],
        "local_total": len(local),
        "robot_total": len(robot),
        "local_users": len({p.user_id for p in local if p.user_id}),
        "robot_users": len({p.bili_uid for p in robot if p.bili_uid}),
        "new_cards": db.query(VideoCard)
        .filter(VideoCard.collected_at >= start, VideoCard.collected_at < end)
        .count(),
    }

    # ---- B站 CDN 域名 ----
    domains_rows = db.query(BiliCdnDomain).all()
    unconfigured = [row for row in domains_rows if not row.is_configured]
    new_unconfigured = [
        row
        for row in unconfigured
        if row.first_seen_at is not None and start <= row.first_seen_at < end
    ]
    seen = [
        row
        for row in domains_rows
        if row.last_seen_at is not None and start <= row.last_seen_at < end
    ]
    recent_unconfigured = sorted(
        unconfigured, key=lambda row: row.last_seen_at or datetime.min, reverse=True
    )[:3]
    domains = {
        "total": len(domains_rows),
        "configured": len(domains_rows) - len(unconfigured),
        "unconfigured": len(unconfigured),
        "hits": sum(int(row.seen_count or 0) for row in domains_rows),
        "seen": len(seen),
        "new_unconfigured": [
            {"host": row.host, "first_seen_at": row.first_seen_at}
            for row in new_unconfigured
        ],
        "recent_unconfigured": [
            {"host": row.host, "last_seen_at": row.last_seen_at}
            for row in recent_unconfigured
        ],
    }

    return {
        "day": day.isoformat(),
        "visit": visit,
        "bot": bot,
        "parse": parse,
        "download": _download_stats(sessions),
        "exports": _export_stats(sessions),
        "domains": domains,
        "cookie": config_store.cookie_status(db),
    }


def overview(db: Session, days: int = 30) -> dict:
    """概览接口：今天的快照 + 近 N 天访问趋势 + 旧字段（保持兼容）。"""
    snapshot = day_snapshot(db, admin_stats._today_shanghai())
    snapshot["visit"]["trend"] = admin_stats.visit_summary(db, days)["trend"]
    return {**admin_stats.overview(db, days), **snapshot}
