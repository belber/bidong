"""概览页的聚合口径。

按运营真正关心的五件事组织：访问 / 机器人关注与绑定 / 视频解析 / 视频下载 / B站域名。
这里只做组合与少量补算，下载的会话切分仍沿用 `admin_stats` 那一套，
两个模块不互相侵入。
"""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import BiliCdnDomain, ParseLog
from . import admin_stats
from .daily_report import USER_TARGET

# 概览要看全量会话，一次取完（个人级数据量，不必分页）
SESSION_FETCH_LIMIT = 100000


def parse_users(db: Session, days: int = 30) -> dict:
    """解析去重用户数。

    贴链接触发是小程序用户（`user_id`），评论 @ 触发走机器人、没有小程序用户，
    所以按 B站 UID 去重——两个口径不要混着加。
    """
    start = admin_stats._range_start_utc(days)
    today = admin_stats._range_start_utc(1)

    def distinct_users(source: str, since: datetime) -> int:
        column = ParseLog.user_id if source == "local" else ParseLog.bili_uid
        query = db.query(func.count(func.distinct(column))).filter(
            ParseLog.source == source, ParseLog.created_at >= since, column.isnot(None)
        )
        if source == "robot":
            query = query.filter(ParseLog.bili_uid != "")
        return query.scalar() or 0

    local = admin_stats.parse_summary(db, "local", days)
    robot = admin_stats.parse_summary(db, "robot", days)
    return {
        "local_users": distinct_users("local", start),
        "local_users_today": distinct_users("local", today),
        "robot_users": distinct_users("robot", start),
        "robot_users_today": distinct_users("robot", today),
        "local_ok": local["ok"],
        "local_fail": local["fail"],
        "robot_ok": robot["ok"],
        "robot_fail": robot["fail"],
        "fail_by_reason": local["fail_by_reason"] + robot["fail_by_reason"],
    }


def download_outcomes(db: Session, days: int = 30) -> dict:
    """下载结果三分类：保存成功 / 改用复制链接 / 彻底失败。

    用户下载失败后改用「复制链接到浏览器保存」是正常路径，算成功，
    否则成功率会被低估。
    """
    sessions = admin_stats.download_sessions(
        db, days=days, size=SESSION_FETCH_LIMIT
    )["items"]
    total = len(sessions)
    saved = copied = fail = 0
    by_error: dict[str, int] = {}

    for session in sessions:
        if session["result"] == "success":
            saved += 1
        elif session["copied_link"]:
            copied += 1
        else:
            fail += 1
            key = session["fail_error_type"] or "unknown"
            by_error[key] = by_error.get(key, 0) + 1

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
    }


def domain_summary(db: Session) -> dict:
    rows = db.query(BiliCdnDomain).all()
    unconfigured = [row for row in rows if not row.is_configured]
    unconfigured.sort(key=lambda row: row.last_seen_at or datetime.min, reverse=True)
    return {
        "total": len(rows),
        "configured": len(rows) - len(unconfigured),
        "unconfigured": len(unconfigured),
        "hits": sum(int(row.seen_count or 0) for row in rows),
        "recent_unconfigured": [
            {"host": row.host, "last_seen_at": row.last_seen_at}
            for row in unconfigured[:3]
        ],
    }


def bot_section(db: Session, days: int = 30) -> dict:
    followers = admin_stats.followers_summary(db, days)
    activation = admin_stats.activation_summary(db, days)
    total = followers.get("total", 0)
    bound = activation.get("bound", 0)
    return {
        "followers_total": total,
        "followers_today": followers.get("today", 0),
        "sent_ok": activation.get("sent_ok", 0),
        "bound": bound,
        "conversion": round(bound / total * 100, 1) if total else 0.0,
        "trend": followers.get("trend", []),
    }


def overview(db: Session, days: int = 30) -> dict:
    """概览接口的完整响应：新的五段 + 旧的平铺字段（保持兼容）。"""
    visit = admin_stats.visit_summary(db, days)
    # 500 访客目标沿用每日报告里的常量，避免两处各写一份
    visit["target"] = USER_TARGET
    visit["progress"] = (
        round(visit["total_uv"] / USER_TARGET * 100, 1) if USER_TARGET else 0.0
    )
    return {
        **admin_stats.overview(db, days),
        "visit": visit,
        "bot": bot_section(db, days),
        "parse": parse_users(db, days),
        "download": download_outcomes(db, days),
        "domains": domain_summary(db),
    }
