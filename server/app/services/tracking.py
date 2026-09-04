import time

from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import ActivationLog, AtEvent, FollowEvent, ParseLog
from ..time import utcnow_naive


# ---------------------------------------------------------------------------
# 解析失败原因分类（细粒度）
# ---------------------------------------------------------------------------
def classify_error(exc: Exception) -> str:
    name = type(exc).__name__
    msg = str(exc)
    lowered = msg.lower()

    if name == "AppError":
        status = getattr(exc, "status_code", 0)
        if status == 400:
            return "invalid_url"
        if status == 404:
            return "video_unavailable"
        if "封面" in msg:
            return "cover_fail"
        if "存储" in msg or "cos" in lowered or "storage" in lowered:
            return "storage_fail"
        if "分区" in msg:
            return "partition_missing"
        if "接口" in msg or "请求" in msg or "http" in lowered:
            return "network_timeout"
        if "数据库" in msg or "db" in lowered:
            return "db_error"
        return "other"

    # 非 AppError（httpx / sqlalchemy 等）
    if "timeout" in name.lower() or "timeout" in lowered:
        return "network_timeout"
    if "connect" in name.lower() or "request" in name.lower():
        return "network_timeout"
    if "integrity" in name.lower() or "sqlalchemy" in lowered:
        return "db_error"
    return "other"


def classify_send_error(exc: Exception) -> str:
    msg = str(exc)
    lowered = msg.lower()
    if "风控" in msg or "频繁" in msg or "risk" in lowered:
        return "risk_control"
    if "不存在" in msg or "not found" in lowered:
        return "not_found"
    if "网络" in msg or "请求" in msg or "http" in lowered:
        return "network"
    return "other"


# ---------------------------------------------------------------------------
# 事件落库
# ---------------------------------------------------------------------------
def log_follow_event(
    db: Session,
    bili_uid: str,
    bili_name: str,
    mtime: int,
    *,
    sent_code: bool,
    bound: bool,
) -> None:
    row = (
        db.query(FollowEvent)
        .filter(FollowEvent.bili_uid == str(bili_uid), FollowEvent.mtime == mtime)
        .first()
    )
    if row is None:
        row = FollowEvent(
            bili_uid=str(bili_uid),
            bili_name=bili_name or "",
            mtime=mtime,
            sent_code=sent_code,
            bound=bound,
        )
        db.add(row)
    else:
        if bili_name:
            row.bili_name = bili_name
        row.sent_code = row.sent_code or sent_code
        row.bound = row.bound or bound
    db.commit()


def log_at_event(
    db: Session,
    feed_id: str,
    bili_uid: str,
    bili_name: str,
    bvid: str,
    comment: str,
    *,
    result: str,
    reason: str = "",
    video_title: str = "",
) -> bool:
    if db.query(AtEvent).filter(AtEvent.feed_id == feed_id).first() is not None:
        return False
    db.add(
        AtEvent(
            feed_id=feed_id,
            bili_uid=str(bili_uid),
            bili_name=bili_name or "",
            bvid=bvid or "",
            video_title=video_title or "",
            comment=comment or "",
            result=result,
            reason=reason,
            created_at=utcnow_naive(),
        )
    )
    db.commit()
    return True


def log_activation(
    db: Session,
    bili_uid: str,
    bili_name: str,
    code: str,
    *,
    sent_ok: bool,
    send_reason: str = "",
    bound: bool = False,
) -> None:
    db.add(
        ActivationLog(
            bili_uid=str(bili_uid),
            bili_name=bili_name or "",
            code=code or "",
            sent_ok=sent_ok,
            send_reason=send_reason or "",
            bound=bound,
            created_at=utcnow_naive(),
        )
    )
    db.commit()


def log_parse(
    db: Session,
    *,
    source: str,
    user_id: int | None,
    bili_uid: str | None,
    input: str,
    bvid: str | None,
    ok: bool,
    reason: str = "",
    duration_ms: int = 0,
    video_title: str = "",
) -> None:
    db.add(
        ParseLog(
            source=source,
            user_id=user_id,
            bili_uid=bili_uid,
            input=input or "",
            bvid=bvid,
            video_title=video_title or "",
            ok=ok,
            reason=reason or "",
            duration_ms=int(duration_ms),
            created_at=utcnow_naive(),
        )
    )
    db.commit()


def elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
