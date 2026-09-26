"""微信搜索爬虫的识别、签名校验与访问汇总。

用来回答一个很实在的问题：**爬虫到底来过没有**。
没来过 → 是"没有入口"（要靠分享/主动推送）；来过但页面空 → 是页面本身的问题。
"""

import hashlib
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..models import CrawlerVisit
from ..time import utcnow_naive
from . import admin_stats

CRAWLER_UA_MARK = "mpcrawler"
SIGNATURE_HEADER = "x-wxapp-crawler-signature"
TIMESTAMP_HEADER = "x-wxapp-crawler-timestamp"
NONCE_HEADER = "x-wxapp-crawler-nonce"
SCENE_SEARCH_CRAWLER = 1129


def _get(headers, name: str) -> str:
    try:
        return (headers.get(name) or "").strip()
    except AttributeError:
        return ""


def looks_like_crawler(headers) -> bool:
    """按官方指南的两条线索识别：UA 含 mpcrawler，或带爬虫签名头。"""
    ua = _get(headers, "user-agent").lower()
    if CRAWLER_UA_MARK in ua:
        return True
    return bool(_get(headers, SIGNATURE_HEADER))


def verify_signature(token: str, timestamp: str, nonce: str, signature: str) -> bool | None:
    """与微信消息推送同一套签名算法：token+timestamp+nonce 字典序拼接后 sha1。

    没配置 Token 时返回 None（无法校验），而不是 False——避免把真爬虫当假的。
    """
    if not token or not signature:
        return None
    raw = "".join(sorted([token, timestamp, nonce]))
    return hashlib.sha1(raw.encode()).hexdigest() == signature


def record(
    db: Session,
    *,
    source: str,
    path: str = "",
    query: str = "",
    user_agent: str = "",
    referer: str = "",
    scene: int = 0,
    verified: bool | None = None,
    created_at: datetime | None = None,
) -> CrawlerVisit:
    row = CrawlerVisit(
        source=source[:16],
        path=(path or "")[:255],
        query=(query or "")[:255],
        user_agent=(user_agent or "")[:255],
        referer=(referer or "")[:255],
        scene=int(scene or 0),
        signature_verified=verified,
        created_at=created_at or utcnow_naive(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def summary(db: Session, days: int = 30, limit: int = 50) -> dict:
    start = admin_stats._range_start_utc(days)
    today_start = admin_stats._range_start_utc(1)
    rows = (
        db.query(CrawlerVisit)
        .filter(CrawlerVisit.created_at >= start)
        .order_by(CrawlerVisit.created_at.desc())
        .all()
    )
    today_rows = [row for row in rows if row.created_at >= today_start]

    by_path: dict[str, int] = {}
    for row in rows:
        by_path[row.path or "(空)"] = by_path.get(row.path or "(空)", 0) + 1

    last = rows[0] if rows else None
    return {
        "days": days,
        "today": len(today_rows),
        "total": len(rows),
        "last_seen": admin_stats._fmt_dt_sh(last.created_at) if last else "",
        "verified": sum(1 for row in rows if row.signature_verified is True),
        "unverified": sum(1 for row in rows if row.signature_verified is False),
        "unknown_signature": sum(1 for row in rows if row.signature_verified is None),
        "by_path": [
            {"path": path, "count": count}
            for path, count in sorted(by_path.items(), key=lambda item: -item[1])
        ],
        "items": [
            {
                "created_at": admin_stats._fmt_dt_sh(row.created_at),
                "source": row.source,
                "scene": row.scene,
                "path": row.path,
                "query": row.query,
                "user_agent": row.user_agent,
                "signature_verified": row.signature_verified,
            }
            for row in rows[:limit]
        ],
    }


def record_from_headers(db: Session, headers, path: str, query: str = "") -> None:
    """服务端中间件用：请求头里出现爬虫特征就记一笔。"""
    verified = verify_signature(
        settings.wechat_msg_token,
        _get(headers, TIMESTAMP_HEADER),
        _get(headers, NONCE_HEADER),
        _get(headers, SIGNATURE_HEADER),
    )
    record(
        db,
        source="header",
        path=path,
        query=query,
        user_agent=_get(headers, "user-agent"),
        referer=_get(headers, "referer"),
        verified=verified,
    )
