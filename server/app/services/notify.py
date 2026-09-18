import smtplib
from datetime import datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from . import config_store

DOMAIN_ALERT_INTERVAL = timedelta(hours=24)


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
    sent = send_alert_email(db, "发现未配置的 B站 CDN 域名", body)
    if sent:
        config_store.set_raw(db, key, datetime.now().isoformat(timespec="seconds"))
    return sent
