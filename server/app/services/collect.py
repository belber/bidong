from sqlalchemy.orm import Session

from ..models import User, VideoCard
from ..schemas import CardOut
from ..time import month_of, to_unix, utcnow_naive
from .bilibili import BiliClient
from .storage import get_storage
from .tags import get_or_create_tag


def card_to_out(card: VideoCard) -> CardOut:
    return CardOut(
        id=card.id,
        bvid=card.bvid,
        title=card.title,
        up_name=card.up_name,
        partition=card.partition,
        duration=card.duration,
        pubdate=card.pubdate,
        cover_url=card.cover_url,
        desc=card.desc,
        source_url=card.source_url,
        source=card.source,
        tags=sorted(t.name for t in card.tags),
        collected_at=to_unix(card.collected_at),
        month=card.month,
    )


def collect_video(db: Session, user: User, url: str) -> tuple[VideoCard, list[dict], dict, int]:
    client = BiliClient()
    try:
        bvid = client.resolve_bvid(url)
        existing = (
            db.query(VideoCard)
            .filter(VideoCard.user_id == user.id, VideoCard.bvid == bvid)
            .first()
        )
        if existing is not None:
            meta = client.get_video(existing.bvid)
            subtitles = client.get_subtitles(existing.bvid, existing.cid)
            stats = {
                "like": meta.like,
                "reply": meta.reply,
                "favorite": meta.favorite,
                "coin": meta.coin,
            }
            return existing, subtitles, stats, meta.danmaku

        meta = client.get_video(bvid)
        archive_tags = client.get_tags(bvid)
        image_bytes, content_type = client.download_cover(meta.cover_url)
        subtitles = client.get_subtitles(bvid, meta.cid)
    finally:
        client.close()

    cover_url = get_storage().save_cover(bvid, image_bytes, content_type)
    now = utcnow_naive()
    card = VideoCard(
        user_id=user.id,
        bvid=bvid,
        title=meta.title[:200],
        cover_url=cover_url,
        up_name=meta.up_name,
        partition=meta.partition,
        desc=meta.desc[:500],
        source_url=f"https://www.bilibili.com/video/{bvid}",
        duration=meta.duration,
        pubdate=meta.pubdate,
        cid=meta.cid,
        source="local",
        collected_at=now,
        month=month_of(now),
    )
    db.add(card)
    db.flush()

    for name in dict.fromkeys(t for t in archive_tags if t.strip()):
        tag = get_or_create_tag(db, user.id, name)
        card.tags.append(tag)

    db.commit()
    db.refresh(card)
    stats = {
        "like": meta.like,
        "reply": meta.reply,
        "favorite": meta.favorite,
        "coin": meta.coin,
    }
    return card, subtitles, stats, meta.danmaku
