"""免登录的公开接口。

用途有两个：结果页被分享/被微信搜索爬虫打开时没有登录态，
以及后续给搜一搜推送页面内容时复用同一份数据。
这里只回视频的公开元数据与出处，不含任何用户信息。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import AppError
from ..models import VideoCard
from ..schemas import PublicCardOut
from ..services import repost_source

router = APIRouter(tags=["public"])


@router.get("/api/public/cards/{bvid}", response_model=PublicCardOut)
def public_card(bvid: str, db: Session = Depends(get_db)):
    bvid = (bvid or "").strip()
    if not repost_source.BVID_RE.match(bvid):
        raise AppError(400, "不是有效的 BV 号")

    # 同一条视频可能被多个用户收藏；取最早那张卡（元数据完全一样）
    card = (
        db.query(VideoCard)
        .filter(VideoCard.bvid == bvid)
        .order_by(VideoCard.id.asc())
        .first()
    )
    if card is None:
        raise AppError(404, "这条视频还没有人解析过")

    origin = repost_source.get_origin(db, bvid=bvid, up_mid=card.up_mid)
    return PublicCardOut(
        bvid=card.bvid,
        title=card.title,
        up_name=card.up_name,
        partition=card.partition,
        duration=card.duration,
        pubdate=card.pubdate,
        cover_url=card.cover_url,
        desc=card.desc,
        source_url=card.source_url,
        origin=origin,
    )
