import json
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models import AdminConfig
from ..time import utcnow_naive

TRUE_VALUES = {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# 基础读写
# ---------------------------------------------------------------------------
def get_raw(db: Session, key: str, default: str | None = None) -> str | None:
    row = db.query(AdminConfig).filter(AdminConfig.key == key).first()
    return row.value if row is not None else default


def set_raw(db: Session, key: str, value: str) -> None:
    row = db.query(AdminConfig).filter(AdminConfig.key == key).first()
    if row is None:
        row = AdminConfig(key=key, value=value, updated_at=utcnow_naive())
        db.add(row)
    else:
        row.value = value
        row.updated_at = utcnow_naive()
    db.commit()


def seed_defaults(db: Session) -> None:
    """把 env 的有效值播种到 admin_config（仅在缺失时写入），使 DB 成为唯一事实源。

    需在所有进程环境一致的前提下调用（见 dev.sh）。
    """
    bool_defaults = {
        "enable_watermarked_video": settings.enable_watermarked_video,
        "enable_clean_video": settings.enable_clean_video,
        "enable_audio": settings.enable_audio,
        "enable_comment": settings.enable_comment,
        "enable_danmaku": settings.enable_danmaku,
        "enable_robot_guide": settings.enable_robot_guide,
        "enable_share": settings.enable_share,
        "alert_enabled": settings.alert_enabled,
        "cookie_valid": True,
    }
    int_defaults = {
        "at_poll_interval": 30,
        "follow_poll_interval": settings.robot_poll_interval_seconds,
        "send_interval": settings.robot_send_interval_seconds,
        "follow_window": settings.robot_follow_window_seconds,
        "cookie_check_interval": settings.cookie_check_interval_seconds,
        "smtp_port": settings.smtp_port,
    }
    str_defaults = {
        "alert_email": settings.alert_email,
        "smtp_host": settings.smtp_host,
        "smtp_user": settings.smtp_user,
        "smtp_pass": settings.smtp_pass,
        "help_qq_group": settings.help_qq_group,
    }
    for key, value in bool_defaults.items():
        if get_raw(db, key) is None:
            set_raw(db, key, str(value))
    for key, value in int_defaults.items():
        if get_raw(db, key) is None:
            set_raw(db, key, str(int(value)))
    for key, value in str_defaults.items():
        if get_raw(db, key) is None:
            set_raw(db, key, value or "")


def get_bool(
    db: Session, key: str, default: bool | None = None
) -> bool | None:
    raw = get_raw(db, key)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


def get_int(db: Session, key: str, default: int | None = None) -> int | None:
    raw = get_raw(db, key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_json(db: Session, key: str, default: Any = None) -> Any:
    raw = get_raw(db, key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def set_json(db: Session, key: str, value: Any) -> None:
    set_raw(db, key, json.dumps(value, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 业务读取：媒体开关
# ---------------------------------------------------------------------------
def media_switches(db: Session) -> dict[str, bool]:
    return {
        "watermarked": bool(
            get_bool(
                db,
                "enable_watermarked_video",
                default=settings.enable_watermarked_video,
            )
        ),
        "clean": bool(
            get_bool(
                db,
                "enable_clean_video",
                default=settings.enable_clean_video,
            )
        ),
        "audio": bool(
            get_bool(db, "enable_audio", default=settings.enable_audio)
        ),
    }


def set_media_switches(db: Session, watermarked: bool, clean: bool, audio: bool) -> None:
    set_raw(db, "enable_watermarked_video", str(watermarked))
    set_raw(db, "enable_clean_video", str(clean))
    set_raw(db, "enable_audio", str(audio))


# ---------------------------------------------------------------------------
# 业务读取：解析能力开关（评论 / 弹幕）
# ---------------------------------------------------------------------------
def parse_switches(db: Session) -> dict[str, bool]:
    return {
        "comment": bool(
            get_bool(db, "enable_comment", default=settings.enable_comment)
        ),
        "danmaku": bool(
            get_bool(db, "enable_danmaku", default=settings.enable_danmaku)
        ),
    }


def set_parse_switches(db: Session, comment: bool, danmaku: bool) -> None:
    set_raw(db, "enable_comment", str(comment))
    set_raw(db, "enable_danmaku", str(danmaku))


# ---------------------------------------------------------------------------
# 业务读取：展示/入口开关（机器人引导等）
# ---------------------------------------------------------------------------
def robot_guide_enabled(db: Session) -> bool:
    return bool(
        get_bool(db, "enable_robot_guide", default=settings.enable_robot_guide)
    )


def set_robot_guide_enabled(db: Session, enabled: bool) -> None:
    set_raw(db, "enable_robot_guide", str(enabled))


def share_enabled(db: Session) -> bool:
    return bool(get_bool(db, "enable_share", default=settings.enable_share))


def set_share_enabled(db: Session, enabled: bool) -> None:
    set_raw(db, "enable_share", str(enabled))


# ---------------------------------------------------------------------------
# 业务读取：机器人 Cookie
# ---------------------------------------------------------------------------
def cookie_fields() -> list[str]:
    return ["SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"]


def robot_cookie(db: Session) -> dict[str, str]:
    stored = get_json(db, "robot_cookie") or {}
    robot_uid = stored.get("robot_uid") or settings.robot_uid
    result = {
        field: stored.get(field) or getattr(settings, _env_field_name(field), "")
        for field in cookie_fields()
    }
    result["robot_uid"] = robot_uid
    return result


def set_robot_cookie(db: Session, cookie: dict[str, str]) -> None:
    payload = {field: (cookie.get(field) or "") for field in cookie_fields()}
    payload["robot_uid"] = cookie.get("robot_uid") or settings.robot_uid
    set_json(db, "robot_cookie", payload)


def _env_field_name(cookie_field: str) -> str:
    table = {
        "SESSDATA": "robot_sessdata",
        "bili_jct": "robot_bili_jct",
        "DedeUserID": "robot_dedeuserid",
        "buvid3": "robot_buvid3",
        "buvid4": "robot_buvid4",
    }
    return table.get(cookie_field, "")


# ---------------------------------------------------------------------------
# 业务读取：调度（定时任务）
# ---------------------------------------------------------------------------
def schedule(db: Session) -> dict[str, int]:
    return {
        "at_poll_interval": int(
            get_int(db, "at_poll_interval", default=30)
        ),
        "follow_poll_interval": int(
            get_int(db, "follow_poll_interval", default=settings.robot_poll_interval_seconds)
        ),
        "send_interval": int(
            get_int(db, "send_interval", default=settings.robot_send_interval_seconds)
        ),
        "follow_window": int(
            get_int(db, "follow_window", default=settings.robot_follow_window_seconds)
        ),
        "cookie_check_interval": int(
            get_int(
                db,
                "cookie_check_interval",
                default=settings.cookie_check_interval_seconds,
            )
        ),
    }


def set_schedule(
    db: Session,
    at_poll_interval: int | None = None,
    follow_poll_interval: int | None = None,
    send_interval: int | None = None,
    follow_window: int | None = None,
    cookie_check_interval: int | None = None,
) -> None:
    mapping = {
        "at_poll_interval": at_poll_interval,
        "follow_poll_interval": follow_poll_interval,
        "send_interval": send_interval,
        "follow_window": follow_window,
        "cookie_check_interval": cookie_check_interval,
    }
    for key, value in mapping.items():
        if value is not None:
            set_raw(db, key, str(int(value)))


# ---------------------------------------------------------------------------
# 业务读取：告警配置
# ---------------------------------------------------------------------------
def alert_config(db: Session) -> dict[str, Any]:
    return {
        "alert_enabled": bool(
            get_bool(db, "alert_enabled", default=settings.alert_enabled)
        ),
        "alert_email": get_raw(db, "alert_email") or settings.alert_email,
        "smtp_host": get_raw(db, "smtp_host") or settings.smtp_host,
        "smtp_port": int(get_int(db, "smtp_port", default=settings.smtp_port)),
        "smtp_user": get_raw(db, "smtp_user") or settings.smtp_user,
        "smtp_pass": get_raw(db, "smtp_pass") or settings.smtp_pass,
    }


def set_alert_config(
    db: Session,
    *,
    alert_enabled: bool | None = None,
    alert_email: str | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    smtp_user: str | None = None,
    smtp_pass: str | None = None,
) -> None:
    mapping = {
        "alert_enabled": (None if alert_enabled is None else str(alert_enabled)),
        "alert_email": alert_email,
        "smtp_host": smtp_host,
        "smtp_port": (None if smtp_port is None else str(int(smtp_port))),
        "smtp_user": smtp_user,
        "smtp_pass": smtp_pass,
    }
    for key, value in mapping.items():
        if value is not None:
            set_raw(db, key, value)


# ---------------------------------------------------------------------------
# Cookie 状态
# ---------------------------------------------------------------------------
def cookie_status(db: Session) -> dict[str, Any]:
    return {
        "cookie_valid": bool(get_bool(db, "cookie_valid", default=True)),
        "cookie_last_checked": get_raw(db, "cookie_last_checked") or "",
        "cookie_last_error": get_raw(db, "cookie_last_error") or "",
    }


def set_cookie_status(
    db: Session, *, valid: bool, last_checked: str, last_error: str = ""
) -> None:
    set_raw(db, "cookie_valid", str(valid))
    set_raw(db, "cookie_last_checked", last_checked)
    set_raw(db, "cookie_last_error", last_error)


# ---------------------------------------------------------------------------
# 帮助与反馈（QQ 群号）
# ---------------------------------------------------------------------------
def get_help_config(db: Session) -> dict[str, str]:
    return {"qq_group": get_raw(db, "help_qq_group") or ""}


def set_help_config(db: Session, qq_group: str) -> None:
    set_raw(db, "help_qq_group", (qq_group or "").strip())
