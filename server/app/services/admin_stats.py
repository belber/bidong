from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import (
    ActivationLog,
    AtEvent,
    Binding,
    DownloadEvent,
    FollowEvent,
    ParseLog,
    User,
    VideoCard,
    VideoSource,
    VisitEvent,
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
    # 收集已绑定用户的 user_id，批量查 User 表
    user_ids = list({b.user_id for _, b in rows if b and b.user_id})
    user_map: dict[int, dict] = {}
    if user_ids:
        from ..models import User
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            user_map[u.id] = {"openid": u.openid or "", "nickname": u.nickname or ""}
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
                "wx_openid": (user_map.get(b.user_id, {}).get("openid", "") if b and b.user_id else ""),
                "wx_nickname": (user_map.get(b.user_id, {}).get("nickname", "") if b and b.user_id else ""),
            }
            for f, b in rows
        ],
    }


def at_summary(db: Session, days: int = 30) -> dict:
    filters = [AtEvent.created_at >= _range_start_utc(days)] if days > 0 else []
    total = db.query(AtEvent).count()
    today = db.query(AtEvent).filter(AtEvent.created_at >= _range_start_utc(1)).count()
    created_ats = [
        dt
        for (dt,) in db.query(AtEvent.created_at)
        .filter(*filters)
        .all()
    ]
    collected = (
        db.query(AtEvent)
        .filter(*filters, AtEvent.result == "collected")
        .count()
    )
    failed = (
        db.query(AtEvent)
        .filter(*filters, AtEvent.result == "parse_failed")
        .count()
    )
    reasons = (
        db.query(AtEvent.reason, func.count(AtEvent.id))
        .filter(
            *filters,
            AtEvent.result == "parse_failed",
        )
        .group_by(AtEvent.reason)
        .all()
    )
    if days > 0:
        trend = _trend_from_created_at(created_ats, days)
    else:
        counts: dict[str, int] = {}
        for dt in created_ats:
            key = _shanghai_date(dt).isoformat()
            counts[key] = counts.get(key, 0) + 1
        trend = [{"date": d, "count": counts[d]} for d in sorted(counts)]
    return {
        "total": total,
        "today": today,
        "trend": trend,
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
    if days > 0:
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
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
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
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
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


def parse_summary(
    db: Session,
    source: str,
    days: int = 30,
    platform: str = "",
    reporter: str = "",
) -> dict:
    # days=0 和下载监控一致，表示全部历史（只影响接口，页面给的是 7 / 30 / 90）
    filters = [ParseLog.source == source]
    if platform:
        filters.append(ParseLog.platform == platform)
    if days > 0:
        filters.append(ParseLog.created_at >= _range_start_utc(days))
    # B站 链接解析按 bvid 关联出处台账，用 reporter 区分多方上报
    base = db.query(ParseLog).outerjoin(
        VideoSource, VideoSource.bvid == ParseLog.bvid
    )
    if reporter:
        if reporter == "unknown":
            base = base.filter(
                or_(VideoSource.reporter.is_(None), VideoSource.reporter == "")
            )
        else:
            base = base.filter(VideoSource.reporter == reporter)
    base = base.filter(*filters)
    total = base.count()
    ok = base.filter(ParseLog.ok.is_(True)).count()
    fail = total - ok
    reasons = (
        base.with_entities(ParseLog.reason, func.count(ParseLog.id))
        .filter(ParseLog.ok.is_(False))
        .group_by(ParseLog.reason)
        .all()
    )
    reporter_rows = (
        base.with_entities(
            VideoSource.reporter, func.count(ParseLog.id)
        )
        .group_by(VideoSource.reporter)
        .all()
    )

    # 趋势和关注 / 下载 / 访问几个页面同一口径：按上海时区日期分桶。
    # 成功和失败分开数，图上是堆叠柱——一眼能看出解析量掉没掉、失败集中在哪几天。
    per_day: dict[str, dict[str, int]] = {}
    for created_at, row_ok in base.with_entities(
        ParseLog.created_at, ParseLog.ok
    ).all():
        bucket = per_day.setdefault(
            _shanghai_date(created_at).isoformat(), {"ok": 0, "fail": 0}
        )
        bucket["ok" if row_ok else "fail"] += 1
    dates = sorted(per_day) if days <= 0 else _date_labels(days)

    return {
        "total": total,
        "ok": ok,
        "fail": fail,
        "fail_by_reason": [{"reason": r or "other", "count": c} for r, c in reasons],
        "by_reporter": [
            {"reporter": r or "未知", "count": c}
            for r, c in sorted(reporter_rows, key=lambda item: -item[1])
        ],
        "trend": [
            {
                "date": d,
                "ok": per_day.get(d, {}).get("ok", 0),
                "fail": per_day.get(d, {}).get("fail", 0),
            }
            for d in dates
        ],
    }


def parse_detail(
    db: Session,
    source: str,
    q: str = "",
    result: str = "",
    days: int = 30,
    page: int = 1,
    size: int = 20,
    platform: str = "",
    reporter: str = "",
) -> dict:
    filters = [ParseLog.source == source]
    if platform:
        filters.append(ParseLog.platform == platform)
    if days > 0:  # 同下载监控：days=0 是全部历史
        filters.append(ParseLog.created_at >= _range_start_utc(days))
    if q:
        like = f"%{q}%"
        filters.append(
            (ParseLog.input.like(like))
            | (ParseLog.bvid.like(like))
            | (ParseLog.bili_uid.like(like))
            | (VideoSource.reporter.ilike(like))
        )
    if reporter:
        if reporter == "unknown":
            filters.append(
                or_(VideoSource.reporter.is_(None), VideoSource.reporter == "")
            )
        else:
            filters.append(VideoSource.reporter == reporter)
    if result == "ok":
        filters.append(ParseLog.ok.is_(True))
    elif result == "fail":
        filters.append(ParseLog.ok.is_(False))
    query = (
        db.query(ParseLog, User, VideoSource.reporter)
        .outerjoin(User, User.id == ParseLog.user_id)
        .outerjoin(VideoSource, VideoSource.bvid == ParseLog.bvid)
    )
    total = query.filter(*filters).count()
    rows = (
        query
        .filter(*filters)
        .order_by(ParseLog.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    # 回填视频标题（历史记录或解析失败时 from video_card）
    titles: dict[str, str] = {}
    missing = [
        p.bvid for p, _, _ in rows if p.bvid and not (p.video_title or "").strip()
    ]
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
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
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
                "reporter": reporter_value or "",
            }
            for p, user, reporter_value in rows
        ],
    }


def _user_origin(user: User | None) -> str:
    if user is None:
        return ""
    return (user.nickname or "") or (user.openid or "")


# ---------------------------------------------------------------------------
# 下载会话：明细的默认口径——一次下载一行
# ---------------------------------------------------------------------------
SESSION_DONE_STAGES = ("save", "share")


def _download_rows(db: Session, q: str, days: int) -> list:
    filters = []
    if days > 0:
        filters.append(DownloadEvent.created_at >= _range_start_utc(days))
    if q:
        like = f"%{q}%"
        filters.append(
            (DownloadEvent.bvid.like(like))
            | (DownloadEvent.video_title.like(like))
            | (DownloadEvent.host.like(like))
            | (DownloadEvent.error_message.like(like))
            | (User.openid.like(like))
        )
    return (
        db.query(DownloadEvent, User)
        .outerjoin(User, User.id == DownloadEvent.user_id)
        .filter(*filters)
        .order_by(DownloadEvent.created_at.asc())
        .all()
    )


def _build_download_sessions(rows: list) -> list[dict]:
    """把下载事件归并成「一次下载」。

    rows 为 (DownloadEvent, User | None)，需按 created_at 升序。
    优先按客户端上报的 session_id 切分；历史数据没有该字段时，退化为
    「同一 (user, bvid, kind) 内遇到 resolve 就开新会话」——resolve 是每次点下载的第一个动作。
    """
    sessions: list[dict] = []
    current: dict | None = None
    for event, user in rows:
        key = (event.user_id, event.bvid, event.kind)
        start_new = (
            current is None
            or current["key"] != key
            or (event.session_id and event.session_id != current["session_id"])
            or (
                not event.session_id
                and not current["session_id"]
                and event.stage == "resolve"
            )
        )
        if start_new:
            current = {
                "key": key,
                "session_id": event.session_id or "",
                "started_at": event.created_at,
                "ended_at": event.created_at,
                "events": [],
                "user": user,
            }
            sessions.append(current)
        current["events"].append(event)
        current["ended_at"] = event.created_at
        if current.get("user") is None and user is not None:
            current["user"] = user
    return sessions


def _session_view(session: dict) -> dict:
    events = session["events"]
    first = events[0]
    user = session.get("user")
    done = next(
        (e for e in events if e.status == "success" and e.stage in SESSION_DONE_STAGES),
        None,
    )
    failed = next((e for e in events if e.status == "fail"), None)
    if done is not None:
        # 成功会话不展示失败点，避免"先失败后成功"的同一次下载被误读
        failed = None
    host = ""
    if failed is not None and failed.host:
        host = failed.host
    else:
        host = next((e.host for e in reversed(events) if e.host), "")
    return {
        "started_at": _fmt_dt_sh(session["started_at"]),
        "ended_at": _fmt_dt_sh(session["ended_at"]),
        "platform": getattr(first, "platform", "bilibili") or "bilibili",
        "openid": ((user.openid if user else "") or ""),
        "nickname": ((user.nickname if user else "") or ""),
        "bvid": first.bvid,
        "video_title": next((e.video_title for e in events if e.video_title), ""),
        "source_url": next((e.source_url for e in events if e.source_url), ""),
        "kind": first.kind,
        "host": host,
        "result": "fail" if failed is not None else "success",
        "fail_stage": failed.stage if failed is not None else "",
        "fail_error_type": failed.error_type if failed is not None else "",
        "fail_message": (
            (failed.error_message or failed.wx_err_msg or "") if failed is not None else ""
        ),
        "copied_link": any(e.stage == "fallback" for e in events),
        "event_count": len(events),
    }


def download_sessions(
    db: Session,
    q: str = "",
    days: int = 30,
    page: int = 1,
    size: int = 20,
    platform: str = "",
) -> dict:
    views = [_session_view(s) for s in _build_download_sessions(_download_rows(db, q, days))]
    if platform:
        views = [v for v in views if v["platform"] == platform]
    views.sort(key=lambda v: v["started_at"], reverse=True)
    total = len(views)
    offset = (page - 1) * size
    return {"total": total, "items": views[offset : offset + size]}


def download_session_summary(db: Session, days: int = 30, platform: str = "") -> dict:
    raw = _build_download_sessions(_download_rows(db, "", days))
    views = [_session_view(s) for s in raw]
    if platform:
        views = [v for v in views if v["platform"] == platform]
    total = len(views)
    success = sum(1 for v in views if v["result"] == "success")
    fail = total - success

    by_error: dict[str, int] = {}
    by_host: dict[str, dict] = {}
    for view in views:
        if view["result"] == "fail":
            key = view["fail_error_type"] or "unknown"
            by_error[key] = by_error.get(key, 0) + 1
        if view["host"]:
            item = by_host.setdefault(view["host"], {"fail": 0, "success": 0})
            item["fail" if view["result"] == "fail" else "success"] += 1

    per_day: dict[str, int] = {}
    for session in raw:
        key = _shanghai_date(session["started_at"]).isoformat()
        per_day[key] = per_day.get(key, 0) + 1

    return {
        "total": total,
        "success": success,
        "fail": fail,
        "success_rate": round(success / total * 100, 1) if total else 0.0,
        "fail_by_error": [
            {"error_type": k, "count": v}
            for k, v in sorted(by_error.items(), key=lambda x: -x[1])
        ],
        "fail_by_host": [
            {"host": h, "fail": v["fail"], "success": v["success"]}
            for h, v in sorted(by_host.items(), key=lambda x: -x[1]["fail"])
        ],
        "trend": (
            [{"date": d, "count": per_day[d]} for d in sorted(per_day)]
            if days <= 0
            else [{"date": d, "count": per_day.get(d, 0)} for d in _date_labels(days)]
        ),
    }


def visit_summary(db: Session, days: int = 30) -> dict:
    """访问汇总：UV 按 visit_event.user_id 去重（只有登录用户才会上报）。"""
    start = _range_start_utc(days)
    rows = (
        db.query(VisitEvent.user_id, VisitEvent.created_at)
        .filter(VisitEvent.created_at >= start)
        .all()
    )
    today = _today_shanghai()
    today_pv = 0
    today_users: set[int] = set()
    per_day: dict[str, dict] = {}
    for user_id, created_at in rows:
        date = _shanghai_date(created_at)
        bucket = per_day.setdefault(date.isoformat(), {"pv": 0, "users": set()})
        bucket["pv"] += 1
        bucket["users"].add(user_id)
        if date == today:
            today_pv += 1
            today_users.add(user_id)

    trend = []
    for label in _date_labels(days):
        bucket = per_day.get(label) or {"pv": 0, "users": set()}
        trend.append({"date": label, "pv": bucket["pv"], "uv": len(bucket["users"])})

    return {
        "days": days,
        "pv": len(rows),
        "uv": len({user_id for user_id, _ in rows}),
        "today_pv": today_pv,
        "today_uv": len(today_users),
        # 累计去重用户不受天数区间限制，用于对齐 500 访客目标
        "total_uv": db.query(func.count(func.distinct(VisitEvent.user_id))).scalar() or 0,
        "trend": trend,
    }


def visit_detail(
    db: Session,
    q: str = "",
    days: int = 30,
    page: int = 1,
    size: int = 20,
) -> dict:
    filters = [VisitEvent.created_at >= _range_start_utc(days)]
    if q:
        like = f"%{q}%"
        filters.append(
            (User.openid.like(like))
            | (User.nickname.like(like))
            | (VisitEvent.path.like(like))
        )
    total = (
        db.query(VisitEvent)
        .outerjoin(User, User.id == VisitEvent.user_id)
        .filter(*filters)
        .count()
    )
    rows = (
        db.query(VisitEvent, User)
        .outerjoin(User, User.id == VisitEvent.user_id)
        .filter(*filters)
        .order_by(VisitEvent.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "created_at": _fmt_dt_sh(event.created_at),
                "openid": (user.openid if user else "") or "",
                "nickname": (user.nickname if user else "") or "",
                "path": event.path,
                "env_version": event.env_version or "",
                "api_base": event.api_base or "",
            }
            for event, user in rows
        ],
    }


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
