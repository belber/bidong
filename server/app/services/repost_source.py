"""「帅哥录屏」稿件出处：上报入库、读取、平台名映射。

归属判断用 UP主 mid 白名单，而不是「表里有没有这个 bvid」——台账漏记过的稿件
也要显示成「出处还在整理」，不能让它们整块消失。
"""

import re
from csv import DictReader
from io import StringIO
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from ..config import settings
from ..errors import AppError
from ..models import VideoSource
from ..schemas import OriginOut
from ..time import utcnow_naive
from . import config_store

BVID_RE = re.compile(r"^BV[0-9A-Za-z]{10}$")
MAX_ITEMS = 500

# 平台代号 -> 展示名；表里没有的原样展示（空串按「查不到」处理）
PLATFORM_LABELS = {
    "douyin": "抖音",
    "x": "X",
    "twitter": "X",
    "youtube": "YouTube",
    "kuaishou": "快手",
    "xiaohongshu": "小红书",
    "weibo": "微博",
    "bilibili": "B站",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "other": "其他",
    "unknown": "",
}

FIELD_LIMITS = {
    "bvid": 32,
    "title": 500,
    "platform": 32,
    "author_name": 128,
    "author_handle": 128,
    "author_id": 128,
    "author_url": 500,
    "source_url": 500,
    "source_video_id": 64,
    "bili_published_at": 10,
    "note": 200,
}

VALUE_FIELDS = (
    "title",
    "platform",
    "author_name",
    "author_handle",
    "author_id",
    "author_url",
    "source_url",
    "source_video_id",
    "bili_published_at",
    "note",
)


def platform_label(platform: str) -> str:
    key = (platform or "").strip().lower()
    label = PLATFORM_LABELS.get(key)
    return label if label is not None else key


# 这些是 X 的功能路径，不是账号名
X_RESERVED_PATHS = {
    "i", "home", "search", "explore", "intent", "hashtag", "settings",
    "notifications", "messages", "compose", "login", "signup", "share",
}


def derive_handle(platform: str, author_url: str) -> str:
    """从主页链接里推导「可搜索的账号标识」；推不出来就返回空，不要编。

    抖音主页链接里是 sec_uid（MS4wLjABAAAA…），粘到抖音搜索框搜不到，
    所以抖音只能靠上报方给抖音号，这里一律返回空。
    """
    key = (platform or "").strip().lower()
    url = (author_url or "").strip()
    if not url:
        return ""

    parsed = urlparse(url if "://" in url else "https://" + url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www.") or host.startswith("m."):
        host = host.split(".", 1)[1]
    parts = host.split(".")
    root = ".".join(parts[-2:]) if len(parts) >= 2 else host
    segments = [s for s in (parsed.path or "").split("/") if s]

    if key in ("x", "twitter") and root in ("x.com", "twitter.com"):
        if not segments:
            return ""
        first = segments[0]
        return "" if first.lower() in X_RESERVED_PATHS else first

    if key == "youtube" and root in ("youtube.com", "youtu.be"):
        if not segments:
            return ""
        first = segments[0]
        if first.startswith("@"):
            return first[1:]
        if first in ("c", "user") and len(segments) > 1:
            return segments[1]
        # /channel/UCxxx、/shorts/xxx、/watch?v= 都不是可搜索的账号名
        return ""

    return ""


def effective_handle(row: VideoSource) -> str:
    """上报方给的优先；没给就从主页链接推导（只对 X / YouTube 有效）。"""
    stored = (row.author_handle or "").strip()
    return stored or derive_handle(row.platform, row.author_url)


# ---------------------------------------------------------------------------
# 上报
# ---------------------------------------------------------------------------
def normalize_payload(raw: Any) -> list[dict]:
    """把 {items:[...]} / 单条对象 / 数组三种形态统一成 list[dict]。"""
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if "items" in raw:
            items = raw["items"]
            if not isinstance(items, list):
                raise AppError(400, "items 必须是数组")
        elif "bvid" in raw:
            items = [raw]
        else:
            raise AppError(400, "请求体需要是 {items:[...]}、单条对象或数组")
    else:
        raise AppError(400, "请求体需要是 JSON 对象或数组")

    if len(items) > MAX_ITEMS:
        raise AppError(400, f"单次最多上报 {MAX_ITEMS} 条，本次 {len(items)} 条")
    for item in items:
        if not isinstance(item, dict):
            raise AppError(400, "items 里每一项都必须是对象")
    return items


def _clean_item(raw: dict) -> tuple[str, dict[str, str]]:
    bvid = str(raw.get("bvid") or "").strip()
    if not BVID_RE.match(bvid):
        return bvid, {}
    fields: dict[str, str] = {}
    for name in VALUE_FIELDS:
        value = raw.get(name)
        value = "" if value is None else str(value).strip()
        fields[name] = value[: FIELD_LIMITS[name]]
    return bvid, fields


def upsert_items(db: Session, raw_items: list[dict]) -> dict:
    """按 bvid 幂等写入：非空字段覆盖，空值跳过。

    跳过空值是为了「重发」安全：历史行只有平台、没有作者，
    重发时不该把后来补好的作者信息冲掉。
    """
    created = 0
    updated = 0
    rejected: list[dict] = []
    now = utcnow_naive()

    for raw in raw_items:
        bvid, fields = _clean_item(raw)
        if not fields:
            rejected.append({"bvid": bvid, "reason": "invalid bvid"})
            continue

        row = db.query(VideoSource).filter(VideoSource.bvid == bvid).first()
        if row is None:
            row = VideoSource(bvid=bvid, created_at=now)
            db.add(row)
            created += 1
        else:
            updated += 1

        for name, value in fields.items():
            if value or not getattr(row, name):
                setattr(row, name, value)
        row.updated_at = now

    db.commit()
    return {"ok": True, "created": created, "updated": updated, "rejected": rejected}


def parse_csv(text: str) -> list[dict]:
    """解析管理端粘贴/上传的 CSV。表头必须是英文列名（见设计 §4.1）。

    只认 bvid 一列必需；其余列缺了就当空值，交给 `_clean_item` 统一处理。
    """
    content = (text or "").lstrip("\ufeff")
    if not content.strip():
        raise ValueError("CSV 内容为空")
    reader = DictReader(StringIO(content))
    fields = [name.strip() for name in (reader.fieldnames or [])]
    if "bvid" not in fields:
        raise ValueError("CSV 缺少 bvid 列")
    items: list[dict] = []
    for row in reader:
        items.append({(k or "").strip(): v for k, v in row.items() if k})
    if not items:
        raise ValueError("CSV 没有数据行")
    return items


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
def repost_up_mids(db: Session) -> set[str]:
    # 白名单语义：显式存空串 = 关掉这个功能（空名单谁也不匹配），
    # 只有「没有这一行配置」时才回退到 env 默认值。
    raw = config_store.get_raw(db, "repost_up_mid")
    if raw is None:
        raw = settings.repost_up_mid
    return {part.strip() for part in (raw or "").split(",") if part.strip()}


def is_repost_channel(db: Session, up_mid: str | int | None) -> bool:
    mid = str(up_mid or "").strip()
    if not mid:
        return False
    return mid in repost_up_mids(db)


def get_origin(db: Session, *, bvid: str, up_mid: str | int | None) -> OriginOut | None:
    """返回解析结果页要用的出处；不是白名单账号的视频时返回 None（前端不渲染）。"""
    if not is_repost_channel(db, up_mid):
        return None

    row = db.query(VideoSource).filter(VideoSource.bvid == bvid).first()
    cfg = config_store.repost_config(db)
    if row is None:
        return OriginOut(
            account_name=cfg["account_name"],
            account_avatar_url=cfg["account_avatar_url"],
        )
    return OriginOut(
        account_name=cfg["account_name"],
        account_avatar_url=cfg["account_avatar_url"],
        platform=row.platform,
        platform_label=platform_label(row.platform),
        author_name=row.author_name,
        author_handle=effective_handle(row),
        author_url=row.author_url,
    )


def summary(db: Session) -> dict:
    total = db.query(VideoSource).count()
    with_author = db.query(VideoSource).filter(VideoSource.author_name != "").count()
    last = db.query(VideoSource).order_by(VideoSource.id.desc()).first()
    platform_rows = (
        db.query(VideoSource.platform, func.count(VideoSource.id))
        .group_by(VideoSource.platform)
        .order_by(func.count(VideoSource.id).desc())
        .all()
    )
    return {
        "total": total,
        "with_author": with_author,
        "without_author": total - with_author,
        "last_updated_at": last.updated_at if last is not None else None,
        "up_mids": sorted(repost_up_mids(db)),
        "by_platform": [
            {"platform": value or "", "label": platform_label(value or ""), "count": count}
            for value, count in platform_rows
        ],
    }


def _source_item(row: VideoSource) -> dict:
    return {
        "bvid": row.bvid,
        "title": row.title,
        "platform": row.platform,
        "platform_label": platform_label(row.platform),
        "author_name": row.author_name,
        "author_handle": effective_handle(row),
        "author_id": row.author_id,
        "author_url": row.author_url,
        "source_url": row.source_url,
        "bili_published_at": row.bili_published_at,
        "note": row.note,
        "updated_at": row.updated_at,
    }


def list_sources(
    db: Session,
    *,
    q: str = "",
    platform: str = "",
    status: str = "",
    page: int = 1,
    size: int = 20,
) -> dict:
    """管理端明细：分页 + 关键字 / 平台 / 完整度筛选。"""
    size = max(1, min(int(size or 20), 100))
    page = max(1, int(page or 1))

    query = db.query(VideoSource)
    text = (q or "").strip()
    if text:
        like = f"%{text}%"
        query = query.filter(
            or_(
                VideoSource.bvid.ilike(like),
                VideoSource.title.ilike(like),
                VideoSource.author_name.ilike(like),
                VideoSource.author_handle.ilike(like),
                VideoSource.author_id.ilike(like),
                VideoSource.author_url.ilike(like),
                VideoSource.source_url.ilike(like),
            )
        )

    platform = (platform or "").strip()
    if platform:
        query = query.filter(VideoSource.platform == platform)

    status = (status or "").strip()
    if status == "with_author":
        query = query.filter(VideoSource.author_name != "")
    elif status == "without_author":
        query = query.filter(
            VideoSource.author_name == "", VideoSource.platform != ""
        )
    elif status == "empty":
        query = query.filter(VideoSource.author_name == "", VideoSource.platform == "")

    total = query.count()
    rows = (
        query.order_by(
            VideoSource.bili_published_at.desc(), VideoSource.id.desc()
        )
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "items": [_source_item(row) for row in rows],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }
