import time
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError
from ..models import User, VideoCard
from ..schemas import (
    MediaAvailability,
    ParseFeatures,
    ParseRequest,
    ParseResult,
    SubtitleLine,
    VideoStats,
)
from ..services import collect_douyin as collect_douyin_service
from ..services import config_store, link_platform, notify, repost_source, tracking
from ..services.bilibili import BiliClient
from ..services.collect import card_to_out, collect_video_by_bvid
from ..services.douyin_provider import build_douyin_provider
from ..services.parse_cache import parse_cache

router = APIRouter(tags=["parse"])
SERVICE_FAULT_MESSAGE = "管理员正在解决中，请稍后再试"
logger = logging.getLogger("bidong")


def _handle_parse_failure(db: Session, exc: Exception, *, platform: str, payload, bvid=None):
    reason = tracking.classify_error(exc)
    if tracking.is_service_fault(exc):
        try:
            notify.send_parse_fault_alert(
                db,
                platform=platform,
                reason=reason,
                input_url=payload.url,
                bvid=bvid,
                error=exc,
            )
        except Exception:  # noqa: BLE001 告警失败不能影响用户请求
            logger.exception("parse fault alert failed")
        raise AppError(503, SERVICE_FAULT_MESSAGE, error_type=reason) from exc
    raise exc


@router.post("/api/parse", response_model=ParseResult)
def parse(
    payload: ParseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if link_platform.detect_platform(payload.url) == "douyin":
        return _parse_douyin(payload, user, db)
    return _parse_bilibili(payload, user, db)


def _parse_douyin(payload: ParseRequest, user: User, db: Session) -> ParseResult:
    """抖音：解析 → 建卡 → 返回。所有媒体直链交给客户端自己去 CDN 拉，服务端不中转。"""
    start = time.monotonic()
    provider = build_douyin_provider(db)
    aweme_id = None
    try:
        meta = provider.resolve(payload.url)
        aweme_id = meta.aweme_id
        card = collect_douyin_service.collect_douyin(db, user, meta, source="local")
    except Exception as exc:  # noqa: BLE001
        logger.exception("douyin parse failed")
        db.rollback()
        tracking.log_parse(
            db,
            platform="douyin",
            source="local",
            user_id=user.id,
            bili_uid=None,
            input=payload.url,
            bvid=aweme_id,
            ok=False,
            reason=tracking.classify_error(exc),
            duration_ms=tracking.elapsed_ms(start),
        )
        _handle_parse_failure(
            db,
            exc,
            platform="douyin",
            payload=payload,
            bvid=aweme_id,
        )
    finally:
        provider.close()

    tracking.log_parse(
        db,
        platform="douyin",
        source="local",
        user_id=user.id,
        bili_uid=None,
        input=payload.url,
        bvid=card.bvid,
        ok=True,
        reason="",
        duration_ms=tracking.elapsed_ms(start),
        video_title=card.title,
    )
    out = card_to_out(card)
    return ParseResult(
        **out.model_dump(),
        subtitles=[],
        stats=VideoStats(**meta.stats),
        danmaku_count=0,
        origin=None,
        media=MediaAvailability(
            watermarked=False,
            clean=bool(meta.video_urls),
            audio=bool(meta.audio_urls),
            images=len(meta.image_urls),
            note=meta.kind == "note",
        ),
        # 抖音没有字幕 / 弹幕 / 评论下载，前端凭这个整块不渲染「文本」卡
        features=ParseFeatures(comment=False, danmaku=False),
    )


def _parse_bilibili(payload: ParseRequest, user: User, db: Session) -> ParseResult:
    start = time.monotonic()
    bvid = None
    try:
        client = BiliClient()
        try:
            bvid = client.resolve_bvid(payload.url)
        finally:
            client.close()

        key = (user.id, "bilibili", bvid)
        cached = parse_cache.get(key)
        if cached is not None:
            # 媒体/解析开关是动态配置，始终实时读取，不随缓存走
            media = config_store.media_switches(db)
            features = config_store.parse_switches(db)
            # 出处同理：解析结果缓存 60 秒，出处不能跟着缓存变旧
            cached_card = (
                db.query(VideoCard)
                .filter(
                    VideoCard.user_id == user.id,
                    VideoCard.platform == "bilibili",
                    VideoCard.bvid == bvid,
                )
                .first()
            )
            origin = repost_source.get_origin(
                db, bvid=bvid, up_mid=cached_card.up_mid if cached_card else ""
            )
            data = dict(cached)
            data["origin"] = origin.model_dump() if origin is not None else None
            data["media"] = {
                "watermarked": media["watermarked"],
                "clean": media["clean"],
                "audio": media["audio"],
            }
            data["features"] = {
                "comment": features["comment"],
                "danmaku": features["danmaku"],
            }
            tracking.log_parse(
                db,
                source="local",
                user_id=user.id,
                bili_uid=None,
                input=payload.url,
                bvid=bvid,
                ok=True,
                reason="cache",
                duration_ms=tracking.elapsed_ms(start),
            )
            return ParseResult(**data)

        card, subtitles, stats, danmaku_count = collect_video_by_bvid(
            db, user, bvid, source="local"
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("bilibili parse failed")
        db.rollback()
        tracking.log_parse(
            db,
            source="local",
            user_id=user.id,
            bili_uid=None,
            input=payload.url,
            bvid=bvid,
            ok=False,
            reason=tracking.classify_error(exc),
            duration_ms=tracking.elapsed_ms(start),
        )
        _handle_parse_failure(
            db,
            exc,
            platform="bilibili",
            payload=payload,
            bvid=bvid,
        )
    tracking.log_parse(
        db,
        source="local",
        user_id=user.id,
        bili_uid=None,
        input=payload.url,
        bvid=card.bvid,
        ok=True,
        reason="",
        duration_ms=tracking.elapsed_ms(start),
        video_title=card.title,
    )
    media = config_store.media_switches(db)
    features = config_store.parse_switches(db)
    out = card_to_out(card)
    lines = [SubtitleLine(t=s["t"], text=s["text"]) for s in subtitles[:500]]
    origin = repost_source.get_origin(db, bvid=card.bvid, up_mid=card.up_mid)
    result = ParseResult(
        **out.model_dump(),
        subtitles=lines,
        stats=VideoStats(**stats),
        danmaku_count=danmaku_count,
        origin=origin,
        media=MediaAvailability(
            watermarked=media["watermarked"],
            clean=media["clean"],
            audio=media["audio"],
        ),
        features=ParseFeatures(
            comment=features["comment"],
            danmaku=features["danmaku"],
        ),
    )
    parse_cache.set(key, result.model_dump())
    return result
