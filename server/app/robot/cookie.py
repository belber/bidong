from datetime import datetime

from sqlalchemy.orm import Session

from ..errors import AppError
from ..services import config_store, notify
from ..services.bilibili_robot import BiliRobotClient


def build_client(cookie: dict[str, str] | None = None) -> BiliRobotClient:
    if cookie is None:
        cookie = {}
    fields = ["SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"]
    robot_uid = str(cookie.get("robot_uid") or cookie.get("DedeUserID") or "")
    return BiliRobotClient(
        cookie={f: cookie.get(f, "") for f in fields},
        robot_uid=robot_uid,
    )


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def check_cookie(db: Session) -> dict:
    cookie = config_store.robot_cookie(db)
    client = build_client(cookie)
    try:
        info = client.get_self_info()
        valid = bool(info.get("isLogin"))
        error = "" if valid else f"登录态失效（isLogin={info.get('isLogin')}）"
    except AppError as exc:
        valid = False
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        valid = False
        error = f"检测异常：{exc}"
    finally:
        client.close()

    prev_valid = config_store.cookie_status(db)["cookie_valid"]
    prev_checked = config_store.cookie_status(db)["cookie_last_checked"]
    checked = _now_iso()
    config_store.set_cookie_status(
        db, valid=valid, last_checked=checked, last_error=error
    )

    # 仅在「曾经校验过且由有效转失效」时告警，避免首次启动/未配置就误发。
    if prev_valid and prev_checked and not valid:
        notify.send_alert_email(
            db,
            "壁咚机器人 Cookie 失效",
            f"检测时间：{checked}\n机器人 UID：{cookie.get('robot_uid')}\n原因：{error}",
        )

    return {
        "cookie_valid": valid,
        "cookie_last_checked": checked,
        "cookie_last_error": error,
    }
