"""抖音建卡。

网络相关的部分（取详情、拉封面）都从这里解耦出去：
详情由 `douyin_provider` 负责，封面通过 `fetch_cover` 注入，
这样建卡逻辑本身可以离线测试。
"""

from typing import Callable

import httpx
from sqlalchemy.orm import Session

from ..models import User, VideoCard
from ..time import month_of, utcnow_naive
from .douyin import DouyinMeta, source_url
from .storage import get_storage
from .tags import get_or_create_tag

CoverFetcher = Callable[[str], tuple[bytes, str]]


def fit(model, field: str, value: str) -> str:
    """把值裁到列定义的长度以内。

    SQLite 不校验 VARCHAR 长度，PostgreSQL 校验——所以本地测试全绿、线上直接
    500（StringDataRightTruncation）。列定义本身就是唯一事实来源，这里按它裁。
    只用于纯展示字段；ID 类字段裁了就变成错误数据，宁可让它报错。
    """
    column = model.__table__.columns.get(field)
    limit = getattr(getattr(column, "type", None), "length", None)
    text = value or ""
    return text[:limit] if limit else text


def _http_cover_fetcher(url: str) -> tuple[bytes, str]:
    """封面是公开图片，不需要登录态，也不校验 Referer。"""
    resp = httpx.get(url, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type", "image/jpeg")


def _label(meta: DouyinMeta) -> str:
    """抖音的 desc 是「文案 + #话题」，标题取第一行并把话题去掉更耐看。"""
    text = (meta.title or "").strip() or f"抖音作品 {meta.aweme_id}"
    return text[:200]


def collect_douyin(
    db: Session,
    user: User,
    meta: DouyinMeta,
    source: str = "local",
    fetch_cover: CoverFetcher | None = None,
) -> VideoCard:
    """按 aweme_id 幂等建卡；重复解析只刷新元数据。"""
    fetcher = fetch_cover or _http_cover_fetcher

    existing = (
        db.query(VideoCard)
        .filter(
            VideoCard.user_id == user.id,
            VideoCard.platform == "douyin",
            VideoCard.bvid == meta.aweme_id,
        )
        .first()
    )

    if existing is not None:
        dirty = False
        for field, value in (
            ("title", _label(meta)),
            ("up_name", fit(VideoCard, "up_name", meta.author_name)),
            ("up_mid", fit(VideoCard, "up_mid", meta.author_unique_id)),
            ("duration", meta.duration),
            ("pubdate", meta.created_at),
        ):
            if value and getattr(existing, field) != value:
                setattr(existing, field, value)
                dirty = True
        if dirty:
            db.commit()
            db.refresh(existing)
        return existing

    cover_url = ""
    if meta.cover_url:
        try:
            image_bytes, content_type = fetcher(meta.cover_url)
            cover_url = get_storage().save_cover(f"dy_{meta.aweme_id}", image_bytes, content_type)
        except Exception:  # noqa: BLE001 - 封面挂了不该让整次解析失败
            cover_url = ""

    now = utcnow_naive()
    card = VideoCard(
        user_id=user.id,
        platform="douyin",
        bvid=meta.aweme_id,
        title=_label(meta),
        cover_url=cover_url,
        up_name=fit(VideoCard, "up_name", meta.author_name),
        # 抖音号（author.unique_id）才是用户能拿去抖音搜到人的字段；
        # sec_uid 是主页链接里那串 MS4wLjABAAAA…，比这一列宽得多，别往这塞。
        up_mid=fit(VideoCard, "up_mid", meta.author_unique_id),
        partition="",
        desc=(meta.title or "")[:500],
        source_url=source_url(meta.aweme_id, meta.kind),
        duration=meta.duration,
        pubdate=meta.created_at,
        cid=0,
        source=source,
        collected_at=now,
        month=month_of(now),
    )
    db.add(card)
    db.flush()

    for name in meta.tags:
        tag = get_or_create_tag(db, user.id, name)
        card.tags.append(tag)

    db.commit()
    db.refresh(card)
    return card
