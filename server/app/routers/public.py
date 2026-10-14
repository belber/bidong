"""免登录的公开接口。

用途有两个：结果页被分享/被微信搜索爬虫打开时没有登录态，
以及后续给搜一搜推送页面内容时复用同一份数据。
这里只回视频的公开元数据与出处，不含任何用户信息。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..errors import AppError
from ..models import VideoCard
from ..schemas import PublicCardOut
from ..services import crawler, repost_source
from ..services.storage import media_url

router = APIRouter(tags=["public"])


@router.get("/api/public/cards/{bvid}", response_model=PublicCardOut)
def public_card(
    bvid: str,
    platform: str = "bilibili",
    db: Session = Depends(get_db),
):
    bvid = (bvid or "").strip()
    platform = platform if platform in ("bilibili", "douyin") else "bilibili"
    if platform == "bilibili":
        if not repost_source.BVID_RE.match(bvid):
            raise AppError(400, "不是有效的 BV 号")
    elif not bvid.isdigit():
        raise AppError(400, "不是有效的抖音作品 ID")

    # 同一条视频可能被多个用户收藏；取最早那张卡（元数据完全一样）
    card = (
        db.query(VideoCard)
        .filter(VideoCard.platform == platform, VideoCard.bvid == bvid)
        .order_by(VideoCard.id.asc())
        .first()
    )
    if card is None:
        raise AppError(404, "这条视频还没有人解析过")

    # 出处是 B站 稿件专属的功能，抖音没有
    origin = (
        repost_source.get_origin(db, bvid=bvid, up_mid=card.up_mid)
        if platform == "bilibili"
        else None
    )
    return PublicCardOut(
        bvid=card.bvid,
        platform=card.platform,
        title=card.title,
        up_name=card.up_name,
        partition=card.partition,
        duration=card.duration,
        pubdate=card.pubdate,
        # 爬虫/分享这类外部消费方拿到相对路径没法用，这里补成绝对地址
        cover_url=media_url(card.cover_url),
        desc=card.desc,
        source_url=card.source_url,
        origin=origin,
    )


@router.post("/api/public/crawler-visit")
def report_crawler_visit(payload: schemas.CrawlerVisitRequest, db: Session = Depends(get_db)):
    """小程序端上报"微信搜索爬虫打开过页面"（场景值 1129）。

    小程序运行时发起请求时不一定带爬虫头，所以场景值是最可靠的信号。
    """
    crawler.record(
        db,
        source="scene",
        path=payload.path,
        query=payload.query,
        scene=payload.scene or crawler.SCENE_SEARCH_CRAWLER,
    )
    return {"ok": True}
