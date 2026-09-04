import smtplib
from email.header import Header
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from . import config_store


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
