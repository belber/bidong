import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import (
    MediaAvailability,
    ParseFeatures,
    ParseRequest,
    ParseResult,
    SubtitleLine,
    VideoStats,
)
from ..services import config_store, tracking
from ..services.bilibili import BiliClient
from ..services.collect import card_to_out, collect_video_by_bvid
from ..services.parse_cache import parse_cache

router = APIRouter(tags=["parse"])


@router.post("/api/parse", response_model=ParseResult)
def parse(
    payload: ParseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start = time.monotonic()
    bvid = None
    try:
        client = BiliClient()
        try:
            bvid = client.resolve_bvid(payload.url)
        finally:
            client.close()

        key = (user.id, bvid)
        cached = parse_cache.get(key)
        if cached is not None:
            # 媒体/解析开关是动态配置，始终实时读取，不随缓存走
            media = config_store.media_switches(db)
            features = config_store.parse_switches(db)
            data = dict(cached)
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
        raise
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
    result = ParseResult(
        **out.model_dump(),
        subtitles=lines,
        stats=VideoStats(**stats),
        danmaku_count=danmaku_count,
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
