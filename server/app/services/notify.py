import smtplib
import threading
from datetime import datetime, timedelta, timezone
from email.header import Header
from email.mime.text import MIMEText

import httpx
from sqlalchemy.orm import Session

from . import config_store

DOMAIN_ALERT_INTERVAL = timedelta(hours=24)
SERVERCHAN_API = "https://sctapi.ftqq.com/{sendkey}.send"
FAULT_ALERT_TYPES_KEY = "fault_alert_sent_types"
FAULT_ALERT_LAST_DATE_KEY = "fault_alert_last_date"
SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
_fault_alert_lock = threading.Lock()


def _build_message(subject: str, body: str, to_email: str) -> MIMEText:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["To"] = to_email
    msg["From"] = "bili-collector <no-reply@example.com>"
    return msg


def send_email(
    host: str,
    port: int,
    user: str,
    password: str,
    to_email: str,
    subject: str,
    body: str,
) -> None:
    msg = _build_message(subject, body, to_email)
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=10)
    else:
        server = smtplib.SMTP(host, port, timeout=10)
    try:
        server.starttls()
        if user:
            server.login(user, password)
        server.sendmail(msg["From"], [to_email], msg.as_string())
    finally:
        server.quit()


def send_alert_email(db: Session, subject: str, body: str) -> bool:
    cfg = config_store.alert_config(db)
    if not cfg["alert_enabled"] or not cfg["alert_email"]:
        return False
    if not cfg["smtp_host"]:
        return False
    send_email(
        cfg["smtp_host"],
        cfg["smtp_port"],
        cfg["smtp_user"],
        cfg["smtp_pass"],
        cfg["alert_email"],
        subject,
        body,
    )
    return True


def send_serverchan(db: Session, subject: str, body: str) -> bool:
    cfg = config_store.alert_config(db)
    sendkey = (cfg.get("serverchan_sendkey") or "").strip()
    if not sendkey:
        return False
    try:
        resp = httpx.post(
            SERVERCHAN_API.format(sendkey=sendkey),
            data={"title": subject, "desp": body},
            timeout=10,
        )
        data = resp.json()
    except Exception:
        return False
    return resp.status_code == 200 and data.get("code") == 0


def send_notification(db: Session, subject: str, body: str, *, kind: str = "") -> dict:
    """按配置向所有可用通道发送；kind 用于按告警类型过滤。"""
    cfg = config_store.alert_config(db)
    if kind == "cookie_alert" and not cfg["alert_cookie_enabled"]:
        return {"email": False, "serverchan": False}
    if kind == "domain_alert" and not cfg["alert_domain_enabled"]:
        return {"email": False, "serverchan": False}

    sent = {"email": False, "serverchan": False}
    if cfg["alert_enabled"] and cfg["alert_email"] and cfg["smtp_host"]:
        try:
            send_email(
                cfg["smtp_host"],
                cfg["smtp_port"],
                cfg["smtp_user"],
                cfg["smtp_pass"],
                cfg["alert_email"],
                subject,
                body,
            )
            sent["email"] = True
        except Exception:
            sent["email"] = False
    if cfg.get("serverchan_sendkey"):
        sent["serverchan"] = send_serverchan(db, subject, body)
    return sent


def send_fault_alert(
    db: Session,
    fault_type: str,
    subject: str,
    body: str,
    *,
    now: datetime | None = None,
) -> bool:
    """服务故障告警：同类型永久一次，同一自然日最多一条，仅走 Server 酱。"""
    fault_type = (fault_type or "").strip()
    if not fault_type:
        return False
    cfg = config_store.alert_config(db)
    if not cfg["alert_fault_enabled"] or not (cfg.get("serverchan_sendkey") or "").strip():
        return False

    current = now or datetime.now(SHANGHAI)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SHANGHAI)
    today = current.astimezone(SHANGHAI).date().isoformat()

    # API 进程内串行化检查与发送，避免并发故障请求突破每日上限。
    with _fault_alert_lock:
        sent_types = config_store.get_json(db, FAULT_ALERT_TYPES_KEY, []) or []
        if fault_type in sent_types:
            return False
        if config_store.get_raw(db, FAULT_ALERT_LAST_DATE_KEY) == today:
            return False
        if not send_serverchan(db, subject, body):
            return False
        config_store.set_json(db, FAULT_ALERT_TYPES_KEY, sent_types + [fault_type])
        config_store.set_raw(db, FAULT_ALERT_LAST_DATE_KEY, today)
        return True


def send_parse_fault_alert(
    db: Session,
    *,
    platform: str,
    reason: str,
    input_url: str,
    bvid: str | None,
    error: Exception,
) -> bool:
    fault_type = f"{platform}:{reason}"
    body = (
        f"平台：{platform}\n"
        f"故障类型：{reason}\n"
        f"时间：{datetime.now(SHANGHAI).isoformat(timespec='seconds')}\n"
        f"输入：{(input_url or '')[:500]}\n"
        f"稿件：{bvid or '—'}\n"
        f"异常：{type(error).__name__}: {str(error)[:500]}\n\n"
        f"用户侧已统一提示「管理员正在解决中，请稍后再试」。"
    )
    return send_fault_alert(db, fault_type, f"壁咚咚解析故障：{platform}", body)


def send_unconfigured_domain_alert(db: Session, host: str, bvid: str = "") -> bool:
    """同一个 host 24 小时内只告警一次。"""
    if not host:
        return False
    key = "domain_alert_at:" + host
    last = config_store.get_raw(db, key)
    if last:
        try:
            if datetime.now() - datetime.fromisoformat(last) < DOMAIN_ALERT_INTERVAL:
                return False
        except ValueError:
            pass

    body = (
        f"发现未配置到微信后台的 B站 CDN 域名。\n\n"
        f"域名：{host}\n"
        f"触发视频：{bvid or '—'}\n"
        f"时间：{datetime.now().isoformat(timespec='seconds')}\n\n"
        f"请到微信小程序后台的 downloadFile 合法域名中新增该域名，"
        f"然后到管理端「B站域名管理」把它标记为已配置。"
    )
    sent = send_notification(db, "发现未配置的 B站 CDN 域名", body, kind="domain_alert")
    if sent["email"] or sent["serverchan"]:
        config_store.set_raw(db, key, datetime.now().isoformat(timespec="seconds"))
    return sent["email"] or sent["serverchan"]
