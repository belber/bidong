import httpx
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
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
    seen = set()
    unique = []
    for s in streams:
        if s["qn"] and s["qn"] not in seen:
            seen.add(s["qn"])
            unique.append(s)
    return [MediaOption(qn=s["qn"], label=s["label"]) for s in unique]


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


def _fmt_srt_time(t: int) -> str:
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d},000"


def _to_srt(subs: list[dict]) -> str:
    out = []
    for i, s in enumerate(subs, 1):
        out.append(str(i))
        out.append(f"{_fmt_srt_time(s['t'])} --> {_fmt_srt_time(s['t'] + 2)}")
        out.append(s["text"])
        out.append("")
    return "\n".join(out)


def _to_txt(card: VideoCard, subs: list[dict], danmaku: str) -> str:
    lines = [f"标题：{card.title}", f"UP主：{card.up_name}", f"链接：{card.source_url}"]
    if card.partition:
        lines.append(f"分区：{card.partition}")
    if card.tags:
        lines.append("标签：" + " ".join("#" + t.name for t in card.tags))
    if card.desc:
        lines.append(f"简介：{card.desc}")
    if subs:
        lines.append("\n【字幕】")
        lines.extend(f"{_fmt_srt_time(s['t'])} {s['text']}" for s in subs)
    if danmaku:
        lines.append("\n【弹幕】")
        lines.append(danmaku)
    return "\n".join(lines)


def _format_danmaku(xml_text: str) -> str:
    if not xml_text:
        return ""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return xml_text
    lines = []
    for node in root.iter("d"):
        text = "".join(node.itertext()).strip()
        if not text:
            continue
        p = node.get("p") or ""
        t = float(p.split(",")[0]) if p else 0.0
        seconds = int(t)
        lines.append(f"{seconds // 60:02d}:{seconds % 60:02d} {text}")
    return "\n".join(lines)


@router.get("/api/cards/{card_id}/danmaku")
def danmaku(
    card_id: int,
    format: str = "txt",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = _get_owned_card(db, user, card_id)
    client = BiliClient()
    try:
        raw = client.get_danmaku(card.cid)
    finally:
        client.close()
    if format == "xml":
        content = raw or ""
        media_type = "application/xml; charset=utf-8"
        filename = f"{card.bvid}.xml"
    else:
        content = _format_danmaku(raw)
        media_type = "text/plain; charset=utf-8"
        filename = f"{card.bvid}_danmaku.txt"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/cards/{card_id}/export")
def export(
    card_id: int,
    kind: str = "txt",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = _get_owned_card(db, user, card_id)
    client = BiliClient()
    try:
        subs = client.get_subtitles(card.bvid, card.cid)
        if kind == "srt":
            content = _to_srt(subs)
            filename = f"{card.bvid}.srt"
            media_type = "text/plain; charset=utf-8"
        else:
            danmaku_text = _format_danmaku(client.get_danmaku(card.cid))
            content = _to_txt(card, subs, danmaku_text)
            filename = f"{card.bvid}.txt"
            media_type = "text/plain; charset=utf-8"
    finally:
        client.close()
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
