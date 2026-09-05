import sys
import time

from sqlalchemy.orm import Session

from ..config import settings
from ..db import Base, SessionLocal, engine
from ..errors import AppError
from ..models import Binding, RobotCursor, User
from ..services import config_store, tracking
from ..services.activation import issue_activation
from ..services.bilibili_robot import BiliRobotClient
from ..services.collect import collect_video_by_bvid
from ..time import utcnow_naive
from .cookie import build_client, check_cookie


def activation_message(code: str) -> str:
    return (
        f"你的激活码：{code}\n"
        "复制整条消息，打开wx「小破站下载」粘贴即可绑定 ✨"
    )


def get_cursor(db: Session, kind: str) -> RobotCursor:
    cursor = db.query(RobotCursor).filter(RobotCursor.kind == kind).first()
    if cursor is None:
        cursor = RobotCursor(kind=kind, last_id="", last_time=0, updated_at=utcnow_naive())
        db.add(cursor)
        db.commit()
        db.refresh(cursor)
    return cursor


def update_cursor(db: Session, kind: str, last_id: str, last_time: int) -> None:
    cursor = db.query(RobotCursor).filter(RobotCursor.kind == kind).first()
    if cursor is None:
        cursor = RobotCursor(kind=kind)
        db.add(cursor)
    cursor.last_id = last_id
    cursor.last_time = last_time
    cursor.updated_at = utcnow_naive()
    db.commit()


def _new_items(items: list[dict], cursor: RobotCursor) -> list[dict]:
    out = []
    for it in items:
        t = int(it.get("time") or 0)
        i = str(it.get("id") or "")
        if t > cursor.last_time or (t == cursor.last_time and i > cursor.last_id):
            out.append(it)
    return out


def _max_cursor(items: list[dict]) -> tuple[str, int]:
    best_time = 0
    best_id = ""
    for it in items:
        t = int(it.get("time") or 0)
        i = str(it.get("id") or "")
        if t > best_time or (t == best_time and i > best_id):
            best_time, best_id = t, i
    return best_id, best_time


def process_follow(db: Session, client: BiliRobotClient) -> None:
    cfg = config_store.schedule(db)
    cutoff = int(time.time()) - int(cfg["follow_window"])
    for follower in client.get_followers():
        mtime = int(follower.get("mtime") or 0)
        mid = str(follower["mid"])
        uname = follower.get("uname") or ""
        if mtime < cutoff:
            # 旧粉丝：不入开码逻辑，但记录一次关注事件以支撑「累计粉丝」统计
            tracking.log_follow_event(
                db, mid, uname, mtime, sent_code=False, bound=False
            )
            continue
        binding = issue_activation(db, mid, uname)
        bound = binding.bound_at is not None
        sent_code = bound or binding.code_sent_at is not None
        if binding.bound_at is None and mtime > (binding.last_follow_mtime or 0):
            try:
                client.send_msg(mid, activation_message(binding.activation_code))
            except AppError as exc:
                tracking.log_activation(
                    db,
                    mid,
                    uname,
                    binding.activation_code,
                    sent_ok=False,
                    send_reason=tracking.classify_send_error(exc),
                    bound=bound,
                )
            else:
                binding.code_sent_at = utcnow_naive()
                binding.last_follow_mtime = mtime
                db.commit()
                sent_code = True
                tracking.log_activation(
                    db,
                    mid,
                    uname,
                    binding.activation_code,
                    sent_ok=True,
                    send_reason="",
                    bound=bound,
                )
            if settings.robot_send_interval_seconds > 0:
                time.sleep(settings.robot_send_interval_seconds)
        tracking.log_follow_event(
            db, mid, uname, mtime, sent_code=sent_code, bound=bound
        )


def process_at(
    db: Session,
    client: BiliRobotClient,
    collect=collect_video_by_bvid,
) -> None:
    cursor = get_cursor(db, "at")
    items = client.get_at_notifications()
    if not items:
        return

    for it in _new_items(items, cursor):
        mid = str(it["mid"])
        feed_id = str(it.get("id") or "")
        if feed_id and _at_exists(db, feed_id):
            continue
        binding = (
            db.query(Binding)
            .filter(Binding.bili_uid == mid, Binding.bound_at.isnot(None))
            .first()
        )
        if binding is None:
            _record_at(db, feed_id, it, "unbound")
            continue
        user = db.get(User, binding.user_id)
        if user is None:
            _record_at(db, feed_id, it, "error", "user_missing")
            continue
        start = time.monotonic()
        try:
            res = collect(db, user, it["bvid"], source="robot")
        except Exception as exc:  # noqa: BLE001
            reason = tracking.classify_error(exc)
            _record_at(db, feed_id, it, "parse_failed", reason)
            tracking.log_parse(
                db,
                source="robot",
                user_id=None,
                bili_uid=mid,
                input=it.get("bvid") or "",
                bvid=it.get("bvid"),
                ok=False,
                reason=reason,
                duration_ms=tracking.elapsed_ms(start),
                video_title="",
            )
        else:
            title = ""
            if isinstance(res, tuple) and res:
                title = getattr(res[0], "title", "") or ""
            _record_at(db, feed_id, it, "collected", video_title=title)
            tracking.log_parse(
                db,
                source="robot",
                user_id=None,
                bili_uid=mid,
                input=it.get("bvid") or "",
                bvid=it.get("bvid"),
                ok=True,
                reason="",
                duration_ms=tracking.elapsed_ms(start),
                video_title=title,
            )

    last_id, last_time = _max_cursor(items)
    update_cursor(db, "at", last_id, last_time)


def _at_exists(db: Session, feed_id: str) -> bool:
    from ..models import AtEvent

    return (
        db.query(AtEvent).filter(AtEvent.feed_id == feed_id).first() is not None
    )


def _record_at(
    db: Session,
    feed_id: str,
    item: dict,
    result: str,
    reason: str = "",
    video_title: str = "",
) -> None:
    tracking.log_at_event(
        db,
        feed_id or "",
        item.get("mid") or "",
        item.get("uname") or "",
        item.get("bvid") or "",
        item.get("comment") or "",
        result=result,
        reason=reason,
        video_title=video_title,
    )


def run_once(
    db: Session,
    client: BiliRobotClient,
    collect=collect_video_by_bvid,
) -> None:
    process_follow(db, client)
    process_at(db, client, collect)


def build_worker_client(db: Session) -> BiliRobotClient:
    return build_client(config_store.robot_cookie(db))


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    once = "--once" in argv
    if not settings.robot_enabled:
        print("机器人未启用（ROBOT_ENABLED=false）")
        return
    if settings.dev_mode:
        Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        last_follow = 0.0
        last_at = 0.0
        last_cookie = 0.0
        while True:
            now = time.time()
            cfg = config_store.schedule(db)
            if now - last_follow >= int(cfg["follow_poll_interval"]):
                client = build_worker_client(db)
                try:
                    process_follow(db, client)
                except AppError as exc:
                    print(f"关注轮询出错：{exc}")
                finally:
                    client.close()
                last_follow = now
            if now - last_at >= int(cfg["at_poll_interval"]):
                client = build_worker_client(db)
                try:
                    process_at(db, client)
                except AppError as exc:
                    print(f"@轮询出错：{exc}")
                finally:
                    client.close()
                last_at = now
            if now - last_cookie >= int(cfg["cookie_check_interval"]):
                try:
                    check_cookie(db)
                except Exception as exc:  # noqa: BLE001
                    print(f"Cookie 检测出错：{exc}")
                last_cookie = now
            if once:
                break
            time.sleep(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
