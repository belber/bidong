import sys
import time

from sqlalchemy.orm import Session

from ..config import settings
from ..db import Base, SessionLocal, engine
from ..errors import AppError
from ..models import Binding, RobotCursor, User
from ..services.activation import issue_activation
from ..services.bilibili_robot import BiliRobotClient
from ..services.collect import collect_video_by_bvid
from ..time import utcnow_naive


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
    for follower in client.get_followers():
        mid = str(follower["mid"])
        binding = issue_activation(db, mid)
        if binding.bound_at is None and binding.code_sent_at is None:
            client.send_msg(mid, f"壁咚激活码：{binding.activation_code}")
            binding.code_sent_at = utcnow_naive()
            db.commit()
            if settings.robot_send_interval_seconds > 0:
                time.sleep(settings.robot_send_interval_seconds)


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
        binding = (
            db.query(Binding)
            .filter(Binding.bili_uid == mid, Binding.bound_at.isnot(None))
            .first()
        )
        if binding is None:
            continue
        user = db.get(User, binding.user_id)
        if user is None:
            continue
        collect(db, user, it["bvid"], source="robot")

    last_id, last_time = _max_cursor(items)
    update_cursor(db, "at", last_id, last_time)


def run_once(
    db: Session,
    client: BiliRobotClient,
    collect=collect_video_by_bvid,
) -> None:
    process_follow(db, client)
    process_at(db, client, collect)


def build_client() -> BiliRobotClient:
    return BiliRobotClient(
        cookie={
            "SESSDATA": settings.robot_sessdata,
            "bili_jct": settings.robot_bili_jct,
            "DedeUserID": settings.robot_dedeuserid,
            "buvid3": settings.robot_buvid3,
            "buvid4": settings.robot_buvid4,
        },
        robot_uid=settings.robot_uid,
    )


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
    client = build_client()
    try:
        while True:
            try:
                run_once(db, client)
            except AppError as exc:
                print(f"本轮处理出错：{exc}")
            if once:
                break
            time.sleep(settings.robot_poll_interval_seconds)
    finally:
        client.close()
        db.close()


if __name__ == "__main__":
    main()
