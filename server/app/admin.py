import re
import time
from datetime import timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .admin_security import create_admin_token, decode_admin_token, verify_password
from .db import get_db
from .models import Binding, BiliCdnDomain, DownloadEvent, User
from .robot.cookie import check_cookie, build_client
from .robot.worker import activation_message
from .services import config_store
from .services import admin_stats as stats
from .services import repost_source
from .services.activation import issue_activation
from .services.storage import get_storage
from .time import utcnow_naive

router = APIRouter(prefix="/api/admin", tags=["admin"])
bearer = HTTPBearer(auto_error=False)


def get_admin_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if creds is None or not decode_admin_token(creds.credentials):
        raise HTTPException(status_code=401, detail="需登录管理后台")
    return "admin"


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------
class LoginPayload(BaseModel):
    password: str


@router.post("/login")
def login(payload: LoginPayload):
    if not verify_password(payload.password):
        raise HTTPException(status_code=401, detail="密码错误")
    return {"token": create_admin_token(), "token_type": "bearer"}


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
@router.get("/stats/overview")
def overview(
    days: int = Query(30),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.overview(db, days)


@router.get("/stats/followers")
def followers_stats(
    days: int = Query(30),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.followers_summary(db, days)


@router.get("/stats/followers/detail")
def followers_detail(
    q: str = "",
    days: int = Query(30),
    page: int = Query(1),
    size: int = Query(20),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.followers_detail(db, q, days, page, size)


@router.get("/stats/follow-monitor")
def follow_monitor_stats(
    days: int = Query(30),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.follow_monitor_summary(db, days)


@router.get("/stats/follow-monitor/detail")
def follow_monitor_detail(
    q: str = "",
    days: int = Query(30),
    page: int = Query(1),
    size: int = Query(20),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.follow_monitor_detail(db, q, days, page, size)


@router.get("/stats/at")
def at_stats(
    days: int = Query(30),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.at_summary(db, days)


@router.get("/stats/at/detail")
def at_detail(
    q: str = "",
    days: int = Query(30),
    page: int = Query(1),
    size: int = Query(20),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.at_detail(db, q, days, page, size)


@router.get("/stats/activation")
def activation_stats(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.activation_summary(db)


@router.get("/stats/activation/detail")
def activation_detail(
    q: str = "",
    days: int = Query(30),
    page: int = Query(1),
    size: int = Query(20),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.activation_detail(db, q, days, page, size)


@router.get("/stats/parse")
def parse_stats(
    source: str = Query("local", pattern="^(local|robot)$"),
    days: int = Query(30),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.parse_summary(db, source, days)


@router.get("/stats/parse/detail")
def parse_detail(
    source: str = Query("local", pattern="^(local|robot)$"),
    q: str = "",
    result: str = Query("", pattern="^(ok|fail)?$"),
    days: int = Query(30),
    page: int = Query(1),
    size: int = Query(20),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.parse_detail(db, source, q, result, days, page, size)


# ---------------------------------------------------------------------------
# 下载监控
# ---------------------------------------------------------------------------
@router.get("/stats/download")
def download_stats(
    days: int = Query(30),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    cutoff = utcnow_naive().replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    start = cutoff - timedelta(days=days - 1)
    events = db.query(DownloadEvent).filter(DownloadEvent.created_at >= start).all()

    total = len(events)
    success = sum(1 for e in events if e.status == "success")
    fail = total - success

    by_stage: dict[str, int] = {}
    by_error_type: dict[str, int] = {}
    by_host: dict[str, dict] = {}
    for e in events:
        by_stage[e.stage] = by_stage.get(e.stage, 0) + 1
        if e.status == "fail":
            key = e.error_type or "unknown"
            by_error_type[key] = by_error_type.get(key, 0) + 1
            if e.host:
                item = by_host.setdefault(e.host, {"fail": 0, "success": 0})
                item["fail"] += 1
        elif e.host:
            item = by_host.setdefault(e.host, {"fail": 0, "success": 0})
            item["success"] += 1

    trend = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date()
        count = sum(
            1
            for e in events
            if e.created_at is not None and e.created_at.date() == day
        )
        trend.append({"date": day.isoformat(), "count": count})

    return {
        "total": total,
        "success": success,
        "fail": fail,
        "success_rate": round(success / total * 100, 1) if total else 0,
        "by_stage": [
            {"stage": k, "count": v} for k, v in sorted(by_stage.items(), key=lambda x: -x[1])
        ],
        "fail_by_error": [
            {"error_type": k, "count": v}
            for k, v in sorted(by_error_type.items(), key=lambda x: -x[1])
        ],
        "fail_by_host": [
            {"host": k, "fail": v["fail"], "success": v["success"]}
            for k, v in sorted(by_host.items(), key=lambda x: -x[1]["fail"])
        ],
        "trend": trend,
    }


@router.get("/stats/download/detail")
def download_detail(
    q: str = "",
    status: str = Query("", pattern="^(success|fail)?$"),
    days: int = Query(30),
    page: int = Query(1),
    size: int = Query(20),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from datetime import timedelta

    query = db.query(DownloadEvent).outerjoin(User, User.id == DownloadEvent.user_id)
    start = utcnow_naive() - timedelta(days=days)
    query = query.filter(DownloadEvent.created_at >= start)
    if status:
        query = query.filter(DownloadEvent.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (DownloadEvent.bvid.ilike(like))
            | (DownloadEvent.video_title.ilike(like))
            | (DownloadEvent.host.ilike(like))
            | (DownloadEvent.error_message.ilike(like))
            | (User.openid.ilike(like))
        )
    total = query.count()
    rows = (
        query.add_columns(User.openid)
        .order_by(DownloadEvent.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": e.id,
                "created_at": _iso_utc(e.created_at),
                "openid": openid or "",
                "bvid": e.bvid,
                "video_title": e.video_title or "",
                "source_url": e.source_url or "",
                "kind": e.kind,
                "qn": e.qn,
                "host": e.host,
                "stage": e.stage,
                "status": e.status,
                "error_type": e.error_type,
                "error_message": e.error_message,
                "http_status": e.http_status,
                "wx_err_msg": e.wx_err_msg,
            }
            for e, openid in rows
        ],
    }


def _iso_utc(dt) -> str:
    """把数据库里的 naive UTC 时间序列化成带 Z 的 ISO 字符串。"""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# 访问监控
# ---------------------------------------------------------------------------
@router.get("/stats/visit")
def visit_stats(
    days: int = Query(30),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.visit_summary(db, days)


@router.get("/stats/visit/detail")
def visit_detail_api(
    q: str = "",
    days: int = Query(30),
    page: int = Query(1),
    size: int = Query(20),
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return stats.visit_detail(db, q, days, page, size)


# ---------------------------------------------------------------------------
# B站 CDN 域名管理
# ---------------------------------------------------------------------------
def _domain_item(row: BiliCdnDomain) -> dict:
    now = utcnow_naive()
    days_since = (
        (now - row.last_seen_at).days if row.last_seen_at is not None else 0
    )
    if days_since >= 60:
        suggestion = "建议删除"
    elif days_since >= 30:
        suggestion = "可能闲置"
    elif not row.is_configured:
        suggestion = "需要配置"
    else:
        suggestion = "正常使用"
    total = row.download_success_count + row.download_failure_count
    failure_rate = round(row.download_failure_count / total * 100, 1) if total else 0.0
    return {
        "id": row.id,
        "host": row.host,
        "is_configured": row.is_configured,
        "first_seen_at": _iso_utc(row.first_seen_at),
        "last_seen_at": _iso_utc(row.last_seen_at),
        "seen_count": row.seen_count,
        "download_success_count": row.download_success_count,
        "download_failure_count": row.download_failure_count,
        "failure_rate": failure_rate,
        "days_since_seen": days_since,
        "suggestion": suggestion,
        "notes": row.notes,
    }


def _domain_priority(item: dict) -> tuple[int, float]:
    suggestion = item.get("suggestion") or ""
    if not item.get("is_configured"):
        return (0, item.get("failure_rate") or 0.0)
    if suggestion == "建议删除":
        return (1, item.get("failure_rate") or 0.0)
    if suggestion == "可能闲置":
        return (2, item.get("failure_rate") or 0.0)
    return (3, item.get("failure_rate") or 0.0)


@router.get("/download/domains")
def download_domains(
    q: str = "",
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    query = db.query(BiliCdnDomain)
    if q:
        query = query.filter(BiliCdnDomain.host.ilike(f"%{q}%"))
    rows = query.all()
    items = [_domain_item(r) for r in rows]
    items.sort(key=lambda item: (-_domain_priority(item)[0], -item["failure_rate"], item["host"]))
    return {"total": len(items), "items": items}


class DomainUpdatePayload(BaseModel):
    is_configured: bool | None = None
    notes: str | None = None


class DomainBulkPayload(BaseModel):
    text: str


_HOST_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def _parse_domain_input(text: str) -> tuple[list[str], list[str]]:
    """从微信后台粘贴的链接串里提取去重后的 host。"""
    raw = (text or "").strip()
    if not raw:
        return [], []

    candidates = re.findall(r"https?://[^\s;,)\]" + r"]+", raw)
    if not candidates:
        candidates = re.split(r"[\s,;]+", raw)

    hosts: list[str] = []
    invalid: list[str] = []
    for candidate in candidates:
        token = candidate.strip().strip("[]()")
        token = token.replace("\\", "")
        if not token:
            continue
        if not re.match(r"^[a-z][a-z0-9+.-]*://", token, re.I):
            token = "https://" + token
        try:
            host = (urlparse(token).hostname or "").lower().strip(".")
        except ValueError:
            invalid.append(candidate)
            continue
        if (
            not host
            or host == "localhost"
            or re.fullmatch(r"\d+(?:\.\d+){3}", host)
            or not _HOST_RE.match(host)
        ):
            invalid.append(candidate)
            continue
        if host not in hosts:
            hosts.append(host)
    return hosts, invalid


@router.post("/download/domains/bulk")
def bulk_import_domains(
    payload: DomainBulkPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    hosts, invalid = _parse_domain_input(payload.text)
    inserted: list[str] = []
    updated: list[str] = []
    already_configured: list[str] = []

    for host in hosts:
        row = db.query(BiliCdnDomain).filter(BiliCdnDomain.host == host).first()
        if row is None:
            db.add(BiliCdnDomain(host=host, is_configured=True))
            inserted.append(host)
        elif row.is_configured:
            already_configured.append(host)
        else:
            row.is_configured = True
            updated.append(host)

    db.commit()
    return {
        "parsed": len(hosts),
        "inserted": inserted,
        "updated": updated,
        "already_configured": already_configured,
        "invalid": invalid,
    }


@router.put("/download/domains/{host}")
def update_download_domain(
    host: str,
    payload: DomainUpdatePayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    row = db.query(BiliCdnDomain).filter(BiliCdnDomain.host == host).first()
    if row is None:
        row = BiliCdnDomain(host=host, is_configured=False, notes="")
        db.add(row)
    if payload.is_configured is not None:
        row.is_configured = payload.is_configured
    if payload.notes is not None:
        row.notes = payload.notes
    db.commit()
    return _domain_item(row)


# ---------------------------------------------------------------------------
# 发码运营
# ---------------------------------------------------------------------------
class ActivationSendPayload(BaseModel):
    uids: list[str] = Field(default_factory=list)


def _send_to_uids(db: Session, uids: list[str]) -> dict:
    cookie = config_store.robot_cookie(db)
    client = build_client(cookie)
    sched = config_store.schedule(db)
    sent = 0
    failed: dict[str, str] = {}
    try:
        for raw in uids:
            uid = str(raw).strip()
            if not uid:
                continue
            binding = issue_activation(db, uid, "")
            # 已绑定就不再发
            if binding.bound_at is not None:
                failed[uid] = "already_bound"
                continue
            try:
                client.send_msg(uid, activation_message(binding.activation_code))
            except Exception as exc:  # noqa: BLE001
                from .services import tracking

                reason = tracking.classify_send_error(exc)
                tracking.log_activation(
                    db, uid, "", binding.activation_code, sent_ok=False,
                    send_reason=reason, bound=False,
                )
                failed[uid] = reason
            else:
                from .services import tracking

                binding.code_sent_at = _now()
                db.commit()
                tracking.log_activation(
                    db, uid, "", binding.activation_code, sent_ok=True,
                    send_reason="", bound=False,
                )
                sent += 1
                if int(sched["send_interval"]) > 0:
                    time.sleep(int(sched["send_interval"]))
    finally:
        client.close()
    return {"sent": sent, "failed": failed, "total": len(uids)}


def _now():
    from .time import utcnow_naive

    return utcnow_naive()


@router.post("/activation/send")
def activation_send(
    payload: ActivationSendPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return _send_to_uids(db, payload.uids)


@router.post("/activation/resend")
def activation_resend(
    payload: ActivationSendPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    # 对指定粉丝重新发送激活码（未绑定的才能发），复用发送逻辑
    return _send_to_uids(db, payload.uids)


@router.post("/activation/retry-failed")
def activation_retry_failed(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from .models import ActivationLog
    from sqlalchemy import distinct

    uids = [
        uid
        for (uid,) in db.query(distinct(ActivationLog.bili_uid))
        .filter(ActivationLog.sent_ok.is_(False))
        .all()
    ]
    # 只重发未绑定的
    retryable = []
    for uid in uids:
        binding = (
            db.query(Binding)
            .filter(Binding.bili_uid == uid, Binding.bound_at.is_(None))
            .first()
        )
        if binding is not None:
            retryable.append(uid)
    return _send_to_uids(db, retryable)


class UnbindPayload(BaseModel):
    bili_uid: str


@router.post("/binding/unbind")
def admin_unbind(
    payload: UnbindPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    binding = (
        db.query(Binding)
        .filter(Binding.bili_uid == payload.bili_uid.strip())
        .first()
    )
    if binding is None:
        raise HTTPException(404, "未找到该绑定")
    binding.user_id = None
    binding.bound_at = None
    db.commit()
    return {"ok": True, "bili_uid": binding.bili_uid, "code": binding.activation_code}

# ---------------------------------------------------------------------------
# Cookie
# ---------------------------------------------------------------------------
class CookieUpdatePayload(BaseModel):
    SESSDATA: str = ""
    bili_jct: str = ""
    DedeUserID: str = ""
    buvid3: str = ""
    buvid4: str = ""
    robot_uid: str = ""
    cookie_text: str = ""


@router.get("/cookie/status")
def cookie_status(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    cookie = config_store.robot_cookie(db)
    status = config_store.cookie_status(db)
    return {
        "robot_uid": cookie.get("robot_uid"),
        "has_cookie": bool(cookie.get("SESSDATA")),
        "cookie_fields": {
            f: (cookie.get(f) or "")[-4:] for f in config_store.cookie_fields()
        },
        **status,
    }


@router.post("/cookie/check")
def cookie_check(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return check_cookie(db)


@router.post("/cookie/update")
def cookie_update(
    payload: CookieUpdatePayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    cookie = {
        "SESSDATA": payload.SESSDATA,
        "bili_jct": payload.bili_jct,
        "DedeUserID": payload.DedeUserID,
        "buvid3": payload.buvid3,
        "buvid4": payload.buvid4,
        "robot_uid": payload.robot_uid,
    }
    if payload.cookie_text:
        for pair in payload.cookie_text.split(";"):
            if "=" not in pair:
                continue
            k, v = pair.strip().split("=", 1)
            if k.strip() in cookie and v:
                cookie[k.strip()] = v
    config_store.set_robot_cookie(db, cookie)
    return {"ok": True, "saved_fields": [f for f in config_store.cookie_fields() if cookie.get(f)]}


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
class FeaturesPayload(BaseModel):
    watermarked: bool
    clean: bool
    audio: bool


@router.get("/config/features")
def get_features(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return config_store.media_switches(db)


@router.put("/config/features")
def set_features(
    payload: FeaturesPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    config_store.set_media_switches(db, payload.watermarked, payload.clean, payload.audio)
    return config_store.media_switches(db)


class ParseFeaturesPayload(BaseModel):
    comment: bool
    danmaku: bool


@router.get("/config/parse-features")
def get_parse_features(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return config_store.parse_switches(db)


@router.put("/config/parse-features")
def set_parse_features(
    payload: ParseFeaturesPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    config_store.set_parse_switches(db, payload.comment, payload.danmaku)
    return config_store.parse_switches(db)


class UiPayload(BaseModel):
    robot_guide: bool | None = None
    share: bool | None = None


@router.get("/config/ui")
def get_ui(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return {
        "robot_guide": config_store.robot_guide_enabled(db),
        "share": config_store.share_enabled(db),
    }


@router.put("/config/ui")
def set_ui(
    payload: UiPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if payload.robot_guide is not None:
        config_store.set_robot_guide_enabled(db, payload.robot_guide)
    if payload.share is not None:
        config_store.set_share_enabled(db, payload.share)
    return {
        "robot_guide": config_store.robot_guide_enabled(db),
        "share": config_store.share_enabled(db),
    }


class SchedulePayload(BaseModel):
    at_poll_interval: int | None = None
    follow_poll_interval: int | None = None
    send_interval: int | None = None
    follow_window: int | None = None
    cookie_check_interval: int | None = None


@router.get("/config/schedule")
def get_schedule(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return config_store.schedule(db)


@router.put("/config/schedule")
def set_schedule(
    payload: SchedulePayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    config_store.set_schedule(
        db,
        at_poll_interval=payload.at_poll_interval,
        follow_poll_interval=payload.follow_poll_interval,
        send_interval=payload.send_interval,
        follow_window=payload.follow_window,
        cookie_check_interval=payload.cookie_check_interval,
    )
    return config_store.schedule(db)


class AlertPayload(BaseModel):
    alert_enabled: bool | None = None
    alert_email: str | None = None
    serverchan_sendkey: str | None = None
    alert_cookie_enabled: bool | None = None
    alert_domain_enabled: bool | None = None
    report_enabled: bool | None = None
    report_time: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_pass: str | None = None


@router.get("/config/alert")
def get_alert(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return config_store.alert_config(db)


@router.put("/config/alert")
def set_alert(
    payload: AlertPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    config_store.set_alert_config(
        db,
        alert_enabled=payload.alert_enabled,
        alert_email=payload.alert_email,
        serverchan_sendkey=payload.serverchan_sendkey,
        alert_cookie_enabled=payload.alert_cookie_enabled,
        alert_domain_enabled=payload.alert_domain_enabled,
        report_enabled=payload.report_enabled,
        report_time=payload.report_time,
        smtp_host=payload.smtp_host,
        smtp_port=payload.smtp_port,
        smtp_user=payload.smtp_user,
        smtp_pass=payload.smtp_pass,
    )
    return config_store.alert_config(db)


@router.post("/config/alert/test")
def alert_test(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from .services import notify

    sent = notify.send_alert_email(db, "壁咚咚运营管理测试", "这是一封来自后台管理端的测试邮件。")
    if not sent:
        raise HTTPException(status_code=400, detail="未启用告警或 SMTP 未配置")
    return {"ok": True}


@router.post("/config/serverchan/test")
def serverchan_test(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from .services import notify

    sent = notify.send_serverchan(db, "壁咚咚 Server酱测试", "如果你收到这条消息，说明 Server 酱通道配置成功。")
    if not sent:
        raise HTTPException(status_code=400, detail="发送失败，请检查 SendKey")
    return {"ok": True}


@router.post("/config/report/test")
def report_test(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    from datetime import timedelta

    from .services import daily_report

    day = daily_report.now_shanghai().date() - timedelta(days=1)
    sent = daily_report.send_daily_report(db, day)
    if not (sent["email"] or sent["serverchan"]):
        raise HTTPException(status_code=400, detail="没有可用通道，或发送失败")
    return {"ok": True, "channels": sent}


class HelpPayload(BaseModel):
    qq_group: str = ""


@router.get("/config/help")
def get_help(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return config_store.get_help_config(db)


@router.put("/config/help")
def set_help(
    payload: HelpPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    config_store.set_help_config(db, payload.qq_group)
    return config_store.get_help_config(db)


# ---------------------------------------------------------------------------
# 视频出处（原up主）
# ---------------------------------------------------------------------------
class RepostConfigPayload(BaseModel):
    account_name: str | None = None
    account_avatar_url: str | None = None
    up_mid: str | None = None
    source_ingest_token: str | None = None


class SourceImportPayload(BaseModel):
    csv: str = ""


def _repost_config_out(db: Session) -> dict:
    payload = config_store.repost_config(db)
    payload["source_ingest_token"] = config_store.source_ingest_token(db)
    return payload


@router.get("/config/repost")
def get_repost_config(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return _repost_config_out(db)


@router.put("/config/repost")
def set_repost_config(
    payload: RepostConfigPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    config_store.set_repost_config(
        db,
        account_name=payload.account_name,
        account_avatar_url=payload.account_avatar_url,
        up_mid=payload.up_mid,
    )
    if payload.source_ingest_token is not None:
        config_store.set_source_ingest_token(db, payload.source_ingest_token)
    return _repost_config_out(db)


@router.get("/sources/stats")
def sources_stats(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    data = repost_source.summary(db)
    last = data.get("last_updated_at")
    data["last_updated_at"] = _iso_utc(last) if last else ""
    return data


@router.post("/sources/import")
def sources_import(
    payload: SourceImportPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        items = repost_source.parse_csv(payload.csv)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return repost_source.upsert_items(db, items)


AVATAR_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
AVATAR_MAX_BYTES = 2 * 1024 * 1024


@router.post("/sources/avatar")
async def upload_repost_avatar(
    request: Request,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """上传账号头像：跟封面一样转存（COS 或本地），不硬编码在小程序里。

    直接收原始字节，避免为一次上传引入 multipart 依赖。
    """
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip()
    if content_type not in AVATAR_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="只支持 jpg / png / webp / gif")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="图片内容为空")
    if len(body) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=400, detail="图片需小于 2MB")

    # 文件名带时间戳：换头像后 URL 变化，绕开微信/CDN 的图片缓存
    key = f"repost-avatar-{int(time.time())}"
    url = get_storage().save_cover(key, body, content_type)
    config_store.set_repost_config(db, account_avatar_url=url)
    return {"account_avatar_url": url}
