import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .admin_security import create_admin_token, decode_admin_token, verify_password
from .db import get_db
from .models import Binding
from .robot.cookie import check_cookie, build_client
from .services import config_store
from .services import admin_stats as stats
from .services.activation import issue_activation

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
                client.send_msg(uid, f"壁咚激活码：{binding.activation_code}")
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

    sent = notify.send_alert_email(db, "壁咚管理端测试", "这是一封来自后台管理端的测试邮件。")
    if not sent:
        raise HTTPException(status_code=400, detail="未启用告警或 SMTP 未配置")
    return {"ok": True}


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
