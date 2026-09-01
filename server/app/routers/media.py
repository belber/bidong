import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError
from ..models import User, VideoCard
from ..schemas import MediaOption
from ..services.bilibili import BiliClient, UA

router = APIRouter(tags=["media"])

MEDIA_HEADERS = {"Referer": "https://www.bilibili.com/", "User-Agent": UA}


def _get_owned_card(db: Session, user: User, card_id: int) -> VideoCard:
    card = (
        db.query(VideoCard)
        .filter(VideoCard.id == card_id, VideoCard.user_id == user.id)
        .first()
    )
    if card is None:
        raise AppError(404, "卡片不存在")
    return card


def _require_enabled(kind: str) -> None:
    if kind == "watermarked" and not settings.enable_watermarked_video:
        raise AppError(403, "该下载未开放")
    if kind == "clean" and not settings.enable_clean_video:
        raise AppError(403, "该下载未开放")
    if kind == "audio" and not settings.enable_audio:
        raise AppError(403, "该下载未开放")


def _streams(client: BiliClient, card: VideoCard, kind: str) -> list[dict]:
    if kind == "watermarked":
        return client.get_durl(card.bvid, card.cid)
    if kind == "clean":
        return client.get_dash_video(card.bvid, card.cid)
    if kind == "audio":
        return client.get_dash_audio(card.bvid, card.cid)
    raise AppError(400, "未知下载类型")


@router.get("/api/cards/{card_id}/media-options", response_model=list[MediaOption])
def media_options(
    card_id: int,
    kind: str = "watermarked",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_enabled(kind)
    card = _get_owned_card(db, user, card_id)
    client = BiliClient()
    try:
        streams = _streams(client, card, kind)
    finally:
        client.close()
    return [MediaOption(qn=s["qn"], label=s["label"]) for s in streams if s["qn"]]


@router.get("/api/cards/{card_id}/download")
def download(
    card_id: int,
    kind: str = "watermarked",
    qn: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_enabled(kind)
    card = _get_owned_card(db, user, card_id)
    client = BiliClient()
    try:
        streams = _streams(client, card, kind)
        if qn is not None:
            streams = [s for s in streams if s["qn"] == qn]
        if not streams:
            raise AppError(404, "无可用清晰度")
        url = streams[0]["url"] or (streams[0]["backup_urls"][0] if streams[0]["backup_urls"] else "")
        if not url:
            raise AppError(502, "无可用下载地址")
    finally:
        client.close()

    media_type = "audio/mp4" if kind == "audio" else "video/mp4"
    suffix = "m4a" if kind == "audio" else "mp4"

    def gen():
        with httpx.stream("GET", url, headers=MEDIA_HEADERS, timeout=30, follow_redirects=True) as resp:
            resp.raise_for_status()
            yield from resp.iter_bytes(chunk_size=65536)

    return StreamingResponse(
        gen(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{card.bvid}_{kind}.{suffix}"'},
    )
