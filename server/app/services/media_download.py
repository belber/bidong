from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from ..models import BiliCdnDomain, DownloadEvent, User, VideoCard
from ..time import utcnow_naive


def url_host(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def is_allowed_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.endswith(".mcdn.bilivideo.cn"):
        return False
    if parsed.port not in (None, 80, 443):
        return False
    return bool(host)


def _url_expires_at(url: str) -> int | None:
    if not url:
        return None
    query = parse_qs(urlparse(url).query)
    deadline = query.get("deadline", [])
    if not deadline:
        return None
    try:
        return int(deadline[0])
    except (TypeError, ValueError):
        return None


# 下载类型归一：B站 的 watermarked/clean 都是视频轨，和抖音的 video 是同一个类别
_KIND_CATEGORY = {
    "video": "video",
    "watermarked": "video",
    "clean": "video",
    "audio": "audio",
    "image": "image",
}


def kind_category(kind: str) -> str:
    """把各平台的下载类型归成 video / audio / image，认不出来就返回空串。"""
    return _KIND_CATEGORY.get((kind or "").strip(), "")


def _record_domain(db: Session, host: str, kind: str = "") -> None:
    """记录域名，并把见过的下载类型累积起来。

    类型要落库而不是只看下载事件：域名是在「取下载地址」时登记的，
    用户可能还没真的下载过，但运营此刻就需要知道这是视频域名还是音频域名，
    好优先把视频的配置进微信白名单。
    """
    if not host:
        return
    category = kind_category(kind)
    row = db.query(BiliCdnDomain).filter(BiliCdnDomain.host == host).first()
    if row is None:
        db.add(BiliCdnDomain(host=host, seen_count=1, kinds=category))
        # session 是 autoflush=False：不 flush 的话同一个会话里再登记同一个域名，
        # 上面的查询看不到刚 add 的行，会插出重复的 host 撞唯一约束
        db.flush()
        return
    row.seen_count += 1
    row.last_seen_at = utcnow_naive()
    if category:
        known = [k for k in (row.kinds or "").split(",") if k]
        if category not in known:
            row.kinds = ",".join(known + [category])


def configured_map(db: Session, hosts: set[str]) -> dict[str, bool]:
    rows = db.query(BiliCdnDomain).filter(BiliCdnDomain.host.in_(hosts)).all()
    return {row.host: row.is_configured for row in rows}


def build_candidates(db: Session, streams: list[dict], kind: str = "") -> list[dict]:
    """把 B站 stream 转成有序候选，记录域名，返回 candidates。"""
    hosts: set[str] = set()
    for stream in streams:
        for url in [stream.get("url")] + list(stream.get("backup_urls") or []):
            if not is_allowed_url(url):
                continue
            host = url_host(url)
            if host:
                hosts.add(host)

    for host in hosts:
        _record_domain(db, host, kind)

    cfg = configured_map(db, hosts)
    seen: set[str] = set()
    candidates: list[dict] = []
    for stream in streams:
        for url in [stream.get("url")] + list(stream.get("backup_urls") or []):
            if not is_allowed_url(url):
                continue
            host = url_host(url)
            if not host or host in seen:
                continue
            seen.add(host)
            candidates.append({"url": url, "host": host, "configured": bool(cfg.get(host))})
    db.commit()
    return candidates


def candidates_from_urls(
    db: Session, urls: list[str], dedup_by_host: bool = True, kind: str = ""
) -> list[dict]:
    """抖音等「直接给一串直链」的平台用这个。

    `dedup_by_host=True` 适合同一个文件的多个 CDN 备选（前端逐个试）；
    图文要设成 False —— 每张图是不同文件，同一域名下会有很多张。
    """
    valid = [u for u in urls if is_allowed_url(u)]
    hosts = {url_host(u) for u in valid if url_host(u)}
    for host in hosts:
        _record_domain(db, host, kind)

    cfg = configured_map(db, hosts)
    seen: set[str] = set()
    candidates: list[dict] = []
    for url in valid:
        host = url_host(url)
        if not host:
            continue
        if dedup_by_host:
            if host in seen:
                continue
            seen.add(host)
        candidates.append({"url": url, "host": host, "configured": bool(cfg.get(host))})
    db.commit()
    return candidates


def _card_title_and_url(
    db: Session, user: User | None, card_id, bvid: str
) -> tuple[str, str]:
    """从该用户自己的卡片回填标题与 B站链接；找不到就留空，不采信客户端传值。"""
    if user is None:
        return "", ""
    query = db.query(VideoCard).filter(VideoCard.user_id == user.id)
    card = None
    if card_id:
        card = query.filter(VideoCard.id == card_id).first()
    if card is None and bvid:
        card = query.filter(VideoCard.bvid == bvid).first()
    if card is None:
        return "", ""
    return card.title or "", card.source_url or ""


def _platform_of(db: Session, user: User | None, card_id, bvid: str) -> str:
    """事件要按平台分账，平台以卡片为准；卡片已删就按 ID 形状猜一个。"""
    if user is not None:
        query = db.query(VideoCard).filter(VideoCard.user_id == user.id)
        card = None
        if card_id:
            card = query.filter(VideoCard.id == card_id).first()
        if card is None and bvid:
            card = query.filter(VideoCard.bvid == bvid).first()
        if card is not None:
            return card.platform
    return "douyin" if bvid.isdigit() else "bilibili"


def report_event(db: Session, user: User, payload: dict) -> DownloadEvent:
    bvid = (payload.get("bvid") or "").strip()
    video_title, source_url = _card_title_and_url(db, user, payload.get("card_id"), bvid)
    event = DownloadEvent(
        user_id=user.id if user is not None else None,
        platform=_platform_of(db, user, payload.get("card_id"), bvid),
        card_id=payload.get("card_id"),
        bvid=bvid,
        video_title=video_title,
        source_url=source_url,
        session_id=(payload.get("session_id") or "").strip()[:40],
        kind=(payload.get("kind") or "").strip(),
        qn=payload.get("qn"),
        host=(payload.get("host") or "").strip(),
        candidate_index=int(payload.get("candidate_index") or 0),
        stage=(payload.get("stage") or "download").strip(),
        status=(payload.get("status") or "success").strip(),
        error_type=(payload.get("error_type") or "").strip(),
        error_message=(payload.get("error_message") or "")[:1000],
        http_status=payload.get("http_status"),
        wx_err_msg=(payload.get("wx_err_msg") or "")[:1000],
    )
    db.add(event)
    if event.host:
        row = db.query(BiliCdnDomain).filter(BiliCdnDomain.host == event.host).first()
        if row is not None:
            if event.status == "success":
                row.download_success_count += 1
            else:
                row.download_failure_count += 1
    db.commit()
    return event


def expiry_from_streams(streams: list[dict]) -> int | None:
    for stream in streams:
        for url in [stream.get("url")] + list(stream.get("backup_urls") or []):
            value = _url_expires_at(url)
            if value is not None:
                return value
    return None
