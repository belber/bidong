from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from ..models import BiliCdnDomain, DownloadEvent, User
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


def _record_domain(db: Session, host: str) -> None:
    if not host:
        return
    row = db.query(BiliCdnDomain).filter(BiliCdnDomain.host == host).first()
    if row is None:
        db.add(BiliCdnDomain(host=host, seen_count=1))
        return
    row.seen_count += 1
    row.last_seen_at = utcnow_naive()


def configured_map(db: Session, hosts: set[str]) -> dict[str, bool]:
    rows = db.query(BiliCdnDomain).filter(BiliCdnDomain.host.in_(hosts)).all()
    return {row.host: row.is_configured for row in rows}


def build_candidates(db: Session, streams: list[dict]) -> list[dict]:
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
        _record_domain(db, host)

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


def report_event(db: Session, user: User, payload: dict) -> DownloadEvent:
    event = DownloadEvent(
        user_id=user.id if user is not None else None,
        card_id=payload.get("card_id"),
        bvid=(payload.get("bvid") or "").strip(),
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
