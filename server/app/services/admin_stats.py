from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import (
    ActivationLog,
    AtEvent,
    Binding,
    FollowEvent,
    ParseLog,
    User,
    VideoCard,
)
from ..time import utcnow_naive

SH_OFFSET = timedelta(hours=8)


def _shanghai_date(dt: datetime):
    return (dt + SH_OFFSET).date()


def _today_shanghai():
    return _shanghai_date(utcnow_naive())


def _range_start_utc(days: int) -> datetime:
    start_date = _today_shanghai() - timedelta(days=days - 1)
    return datetime(start_date.year, start_date.month, start_date.day) - SH_OFFSET


def _date_labels(days: int) -> list[str]:
    start = _today_shanghai() - timedelta(days=days - 1)
    return [
        (start + timedelta(days=i)).isoformat() for i in range(days)
    ]


def _trend_from_created_at(created_ats: list[datetime], days: int) -> list[dict]:
    counts: dict[str, int] = {}
    for dt in created_ats:
        key = _shanghai_date(dt).isoformat()
        counts[key] = counts.get(key, 0) + 1
    return [{"date": d, "count": counts.get(d, 0)} for d in _date_labels(days)]


def followers_summary(db: Session, days: int = 30) -> dict:
    start = _range_start_utc(days)
    total = (
        db.query(func.count(func.distinct(FollowEvent.bili_uid)))
        .scalar()
        or 0
    )
    today = (
        db.query(func.count(func.distinct(FollowEvent.bili_uid)))
        .filter(FollowEvent.created_at >= _range_start_utc(1))
        .scalar()
        or 0
    )
    rows = (
        db.query(FollowEvent.created_at, FollowEvent.bili_uid)
        .filter(FollowEvent.created_at >= start)
        .all()
    )
    # 按上海日期去重 bili_uid，得到「新增关注」趋势
    buckets: dict[str, set[str]] = {}
    for dt, uid in rows:
        key = _shanghai_date(dt).isoformat()
        buckets.setdefault(key, set()).add(uid)
    trend = [
        {"date": d, "count": len(buckets.get(d, set()))} for d in _date_labels(days)
    ]
    return {
        "total": total,
        "today": today,
        "trend": trend,
    }


def followers_detail(
    db: Session, q: str = "", days: int = 30, page: int = 1, size: int = 20
) -> dict:
    query = db.query(FollowEvent)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (FollowEvent.bili_uid.like(like)) | (FollowEvent.bili_name.like(like))
        )
    query = query.filter(FollowEvent.created_at >= _range_start_utc(days))
    total = query.count()
    items = (
        query.order_by(FollowEvent.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "created_at": _fmt_dt_sh(e.created_at),
                "bili_uid": e.bili_uid,
                "bili_name": e.bili_name,
                "sent_code": e.sent_code,
                "bound": e.bound,
            }
            for e in items
        ],
    }


def _fmt_unix_sh(t: int) -> str:
    if not t:
        return ""
    dt = datetime.fromtimestamp(int(t), timezone.utc).replace(tzinfo=None)
    return (dt + SH_OFFSET).strftime("%Y-%m-%d %H:%M")


def _fmt_dt_sh(dt: datetime | None) -> str:
    if not dt:
        return ""
    return (dt + SH_OFFSET).strftime("%Y-%m-%d %H:%M")


def follow_monitor_summary(db: Session, days: int = 30) -> dict:
    """关注 + 发码 合并后的概览。"""
    f = followers_summary(db, days)
    start = _range_start_utc(days)
    sent_ok = (
        db.query(Binding)
        .filter(
            Binding.created_at >= start,
            or_(Binding.code_sent_at.isnot(None), Binding.bound_at.isnot(None)),
        )
        .count()
    )
    sent_fail = (
        db.query(func.count(func.distinct(ActivationLog.bili_uid)))
        .filter(ActivationLog.created_at >= start, ActivationLog.sent_ok.is_(False))
        .scalar()
        or 0
    )
    bound = db.query(Binding).filter(Binding.bound_at.isnot(None)).count()
    return {**f, "sent_ok": sent_ok, "sent_fail": sent_fail, "bound": bound}


def follow_monitor_detail(
    db: Session, q: str = "", days: int = 30, page: int = 1, size: int = 20
) -> dict:
    """粉丝 + 激活码 明细（每条关注记录一行）。"""
    filters = [FollowEvent.created_at >= _range_start_utc(days)]
    if q:
        like = f"%{q}%"
        filters.append(
            (FollowEvent.bili_uid.like(like)) | (FollowEvent.bili_name.like(like))
        )
    total = db.query(FollowEvent).filter(*filters).count()
    rows = (
        db.query(FollowEvent, Binding)
        .outerjoin(Binding, Binding.bili_uid == FollowEvent.bili_uid)
        .filter(*filters)
        .order_by(FollowEvent.mtime.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    uids = [str(f.bili_uid) for f, _ in rows]
    fail_reason: dict[str, str] = {}
    if uids:
        fails = (
            db.query(ActivationLog.bili_uid, ActivationLog.send_reason)
            .filter(
                ActivationLog.bili_uid.in_(uids),
                ActivationLog.sent_ok.is_(False),
            )
            .order_by(ActivationLog.created_at.desc())
            .all()
        )
        for uid, reason in fails:
            uid = str(uid)
            if uid not in fail_reason and reason:
                fail_reason[uid] = reason
    return {
        "total": total,
        "items": [
            {
                "bili_uid": f.bili_uid,
                "bili_name": (b.bili_name if b and b.bili_name else f.bili_name),
                "follow_time": _fmt_unix_sh(f.mtime),
                "code": b.activation_code if b else "",
                "sent_ok": bool(
                    b and (b.code_sent_at is not None or b.bound_at is not None)
                ),
                "send_reason": fail_reason.get(str(f.bili_uid), ""),
                "bound": bool(b and b.bound_at is not None),
                "bound_at": _fmt_dt_sh(b.bound_at) if b and b.bound_at else "",
            }
            for f, b in rows
        ],
    }


def at_summary(db: Session, days: int = 30) -> dict:
    start = _range_start_utc(days)
    total = db.query(AtEvent).count()
    today = db.query(AtEvent).filter(AtEvent.created_at >= _range_start_utc(1)).count()
    created_ats = [
        dt
        for (dt,) in db.query(AtEvent.created_at)
        .filter(AtEvent.created_at >= start)
        .all()
    ]
    collected = (
        db.query(AtEvent)
        .filter(AtEvent.created_at >= start, AtEvent.result == "collected")
        .count()
    )
    failed = (
        db.query(AtEvent)
        .filter(AtEvent.created_at >= start, AtEvent.result == "parse_failed")
        .count()
    )
    reasons = (
        db.query(AtEvent.reason, func.count(AtEvent.id))
        .filter(
            AtEvent.created_at >= start,
            AtEvent.result == "parse_failed",
        )
        .group_by(AtEvent.reason)
        .all()
    )
    return {
        "total": total,
        "today": today,
        "trend": _trend_from_created_at(created_ats, days),
        "collected": collected,
        "failed": failed,
        "fail_by_reason": [{"reason": r or "other", "count": c} for r, c in reasons],
    }


def at_detail(
    db: Session, q: str = "", days: int = 30, page: int = 1, size: int = 20
) -> dict:
    query = db.query(AtEvent)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (AtEvent.bili_uid.like(like))
            | (AtEvent.bvid.like(like))
            | (AtEvent.bili_name.like(like))
            | (AtEvent.comment.like(like))
            | (AtEvent.video_title.like(like))
        )
    query = query.filter(AtEvent.created_at >= _range_start_utc(days))
    total = query.count()
    items = (
        query.order_by(AtEvent.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    # 回填视频标题（历史记录或未成功收藏时 from video_card）
    titles: dict[str, str] = {}
    missing = [e.bvid for e in items if e.bvid and not (e.video_title or "").strip()]
    if missing:
        for bvid, title in (
            db.query(VideoCard.bvid, VideoCard.title)
            .filter(VideoCard.bvid.in_(missing))
            .all()
        ):
            if bvid not in titles:
                titles[bvid] = title or ""
    return {
        "total": total,
        "items": [
            {
                "created_at": _shanghai_date(e.created_at).isoformat()
                if e.created_at
                else "",
                "bili_uid": e.bili_uid,
                "bili_name": e.bili_name,
                "bvid": e.bvid,
                "video_title": e.video_title or titles.get(e.bvid, ""),
                "comment": e.comment,
                "result": e.result,
                "reason": e.reason,
            }
            for e in items
        ],
    }


def activation_summary(db: Session, days: int = 30) -> dict:
    start = _range_start_utc(days)
    sent_ok = (
        db.query(Binding)
        .filter(
            Binding.created_at >= start,
            or_(Binding.code_sent_at.isnot(None), Binding.bound_at.isnot(None)),
        )
        .count()
    )
    sent_fail = (
        db.query(func.count(func.distinct(ActivationLog.bili_uid)))
        .filter(ActivationLog.created_at >= start, ActivationLog.sent_ok.is_(False))
        .scalar()
        or 0
    )
    bound = db.query(Binding).filter(Binding.bound_at.isnot(None)).count()
    return {"sent_ok": sent_ok, "sent_fail": sent_fail, "bound": bound}


def activation_detail(
    db: Session, q: str = "", days: int = 30, page: int = 1, size: int = 20
) -> dict:
    """列出所有已发放的激活码（以 binding 为准），并标注发送/绑定状态与失败原因。"""
    query = db.query(Binding)
    query = query.filter(Binding.created_at >= _range_start_utc(days))
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Binding.bili_uid.like(like))
            | (Binding.bili_name.like(like))
            | (Binding.activation_code.like(like))
        )
    total = query.count()
    items = (
        query.order_by(Binding.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    uids = [e.bili_uid for e in items]
    fail_reason: dict[str, str] = {}
    if uids:
        fails = (
            db.query(ActivationLog.bili_uid, ActivationLog.send_reason)
            .filter(
                ActivationLog.bili_uid.in_(uids),
                ActivationLog.sent_ok.is_(False),
            )
            .order_by(ActivationLog.created_at.desc())
            .all()
        )
        for uid, reason in fails:
            uid = str(uid)
            if uid not in fail_reason and reason:
                fail_reason[uid] = reason
    return {
        "total": total,
        "items": [
            {
                "created_at": _shanghai_date(e.created_at).isoformat()
                if e.created_at
                else "",
                "bili_uid": e.bili_uid,
                "bili_name": e.bili_name,
                "code": e.activation_code,
                "sent_ok": e.code_sent_at is not None or e.bound_at is not None,
                "send_reason": fail_reason.get(e.bili_uid, ""),
                "bound": e.bound_at is not None,
                "bound_at": _shanghai_date(e.bound_at).isoformat()
                if e.bound_at
                else "",
            }
            for e in items
        ],
    }


def parse_summary(db: Session, source: str, days: int = 30) -> dict:
    start = _range_start_utc(days)
    base = db.query(ParseLog).filter(
        ParseLog.source == source, ParseLog.created_at >= start
    )
    total = base.count()
    ok = base.filter(ParseLog.ok.is_(True)).count()
    fail = total - ok
    reasons = (
        db.query(ParseLog.reason, func.count(ParseLog.id))
        .filter(ParseLog.source == source, ParseLog.created_at >= start, ParseLog.ok.is_(False))
        .group_by(ParseLog.reason)
        .all()
    )
    return {
        "total": total,
        "ok": ok,
        "fail": fail,
        "fail_by_reason": [{"reason": r or "other", "count": c} for r, c in reasons],
    }


def parse_detail(
    db: Session,
    source: str,
    q: str = "",
    result: str = "",
    days: int = 30,
    page: int = 1,
    size: int = 20,
) -> dict:
    filters = [
        ParseLog.source == source,
        ParseLog.created_at >= _range_start_utc(days),
    ]
    if q:
        like = f"%{q}%"
        filters.append(
            (ParseLog.input.like(like))
            | (ParseLog.bvid.like(like))
            | (ParseLog.bili_uid.like(like))
        )
    if result == "ok":
        filters.append(ParseLog.ok.is_(True))
    elif result == "fail":
        filters.append(ParseLog.ok.is_(False))
    total = db.query(ParseLog).filter(*filters).count()
    rows = (
        db.query(ParseLog, User)
        .outerjoin(User, User.id == ParseLog.user_id)
        .filter(*filters)
        .order_by(ParseLog.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    # 回填视频标题（历史记录或解析失败时 from video_card）
    titles: dict[str, str] = {}
    missing = [p.bvid for p, _ in rows if p.bvid and not (p.video_title or "").strip()]
    if missing:
        for bvid, title in (
            db.query(VideoCard.bvid, VideoCard.title)
            .filter(VideoCard.bvid.in_(missing))
            .all()
        ):
            if bvid not in titles:
                titles[bvid] = title or ""
    return {
        "total": total,
        "items": [
            {
                "created_at": _fmt_dt_sh(p.created_at),
                "source": p.source,
                "bili_uid": p.bili_uid,
                "origin": _user_origin(user),
                "input": p.input,
                "bvid": p.bvid,
                "video_title": p.video_title or titles.get(p.bvid, ""),
                "ok": p.ok,
                "reason": p.reason,
            }
            for p, user in rows
        ],
    }


def _user_origin(user: User | None) -> str:
    if user is None:
        return ""
    return (user.nickname or "") or (user.openid or "")


def overview(db: Session, days: int = 30) -> dict:
    from . import config_store

    followers = followers_summary(db, days)
    at = at_summary(db, days)
    activation = activation_summary(db, days)
    local_parse = parse_summary(db, "local", days)
    robot_parse = parse_summary(db, "robot", days)
    cookie = config_store.cookie_status(db)
    return {
        "followers": followers,
        "at": at,
        "activation": activation,
        "local_parse": local_parse,
        "robot_parse": robot_parse,
        "cookie": cookie,
    }
