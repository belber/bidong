import sys
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..db import Base, SessionLocal, engine
from ..errors import AppError
from ..models import Binding, RobotCursor, User
from ..models import AtEvent
from ..services import config_store, tracking
from ..services.activation import issue_activation
from ..services.bilibili_robot import BiliRobotClient
from ..services.collect import collect_video_by_bvid
from ..time import utcnow_naive
from .cookie import build_client, check_cookie


_LOG_TZ = timezone(timedelta(hours=8))


def log_message(message: str) -> str:
    """给 worker 日志加北京时间前缀。"""
    return f"{datetime.now(_LOG_TZ).strftime('%Y-%m-%d %H:%M:%S')} {message}"


def log(message: str) -> None:
    print(log_message(message), flush=True)


def activation_message(code: str) -> str:
    return (
        f"你的激活码：{code}\n"
        "复制整条消息，打开「壁咚咚藏链阁」小程序粘贴即可绑定 ✨"
    )


def already_bound_message() -> str:
    return (
        "你已经绑定过「壁咚咚藏链阁」啦，无需重复绑定。\n"
        "打开「壁咚咚藏链阁」小程序，即可查看收藏的视频。"
    )


def follow_guide_message() -> str:
    """没关注就 @ 我们的人：引导关注，不发码（关注才给码）。"""
    return (
        "想让我自动帮你收藏视频？先关注我 ✨\n"
        "关注后我会自动私信你激活码，去「壁咚咚藏链阁」小程序「我的 → 绑定」粘贴即可。"
    )


def collected_message(title: str) -> str:
    """已绑定用户 @ 收藏成功后的确认（带标题，他才知道收藏的是哪条）。"""
    name = title or "这条视频"
    return f"「{name}」已收藏到「壁咚咚藏链阁」✅ 打开小程序就能看到"


# 已经回复过的结果，用于 24 小时频控（同一个人不重复骚扰）
AT_REPLY_RESULTS = ("replied_code", "replied_follow")
AT_REPLY_COOLDOWN_HOURS = 24
# 收藏确认是"每次 @ 都有信息量"，所以按次数限流而不是完全静默
COLLECTED_REPLY_RESULT = "replied_collected"
COLLECTED_REPLY_LIMIT = 3


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
        if mtime > (binding.last_follow_mtime or 0):
            if bound:
                try:
                    client.send_msg(mid, already_bound_message())
                except AppError as exc:
                    reason = tracking.classify_send_error(exc)
                    log(f"已绑定用户 {mid}（{uname}）发送提示失败：{reason}")
                else:
                    binding.last_follow_mtime = mtime
                    db.commit()
                    sent_code = True
                    log(f"已向 {mid}（{uname}）发送已绑定提示")
            else:
                try:
                    client.send_msg(mid, activation_message(binding.activation_code))
                except AppError as exc:
                    reason = tracking.classify_send_error(exc)
                    log(f"新粉丝 {mid}（{uname}）发送激活码失败：{reason}")
                    tracking.log_activation(
                        db,
                        mid,
                        uname,
                        binding.activation_code,
                        sent_ok=False,
                        send_reason=reason,
                        bound=bound,
                    )
                else:
                    binding.code_sent_at = utcnow_naive()
                    binding.last_follow_mtime = mtime
                    db.commit()
                    sent_code = True
                    log(f"已向 {mid}（{uname}）发送激活码")
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
            _reply_unbound(db, client, it, mid)
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
            # 一条 @ 只落一行：收藏结果和"有没有回私信"合并成同一行的结果
            reply_result, reply_reason = _reply_collected(db, client, it, mid, title)
            _record_at(
                db,
                feed_id,
                it,
                reply_result,
                reply_reason,
                video_title=title,
            )
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


def _reply_collected(
    db: Session, client: BiliRobotClient, it: dict, mid: str, title: str
) -> tuple[str, str]:
    """已绑定用户收藏成功后的确认私信。

    不回复会让用户不确定成功没成功，于是再 @ 几条试探——重复 @ 反而制造更多互动量。
    但同样要限流：同一 UID 24 小时内最多回 COLLECTED_REPLY_LIMIT 条。

    返回 (记录用的结果, 失败原因)——一条 @ 只对应 at_event 里一行，
    所以回复结果并进这一行，而不是另写一行。
    """
    if not config_store.at_reply_enabled(db):
        return "collected", ""

    since = utcnow_naive() - timedelta(hours=AT_REPLY_COOLDOWN_HOURS)
    sent_recently = (
        db.query(AtEvent.id)
        .filter(
            AtEvent.bili_uid == mid,
            AtEvent.created_at >= since,
            AtEvent.result == COLLECTED_REPLY_RESULT,
        )
        .count()
    )
    if sent_recently >= COLLECTED_REPLY_LIMIT:
        return "collected_quiet", "24h 内已回复 3 条"

    try:
        client.send_msg(mid, collected_message(title))
    except AppError as exc:
        reason = tracking.classify_send_error(exc)
        log(f"回复已绑定用户 {mid} 收藏确认失败：{reason}")
        return "reply_failed", reason
    log(f"已回复已绑定用户 {mid}（收藏确认）")
    if settings.robot_send_interval_seconds > 0:
        time.sleep(settings.robot_send_interval_seconds)
    return COLLECTED_REPLY_RESULT, ""


def _reply_unbound(db: Session, client: BiliRobotClient, it: dict, mid: str) -> None:
    """未绑定的人 @ 了我们：引导关注 / 重发激活码。

    两种人分开对待：
    - 有 binding 行 = 关注过（关注时就会建行）→ 重发同一个激活码（多半是私信漏看了）；
    - 没有 binding 行 = 没关注过 → 引导关注，不发码（关注才是给码的回报）。

    带总开关与 24 小时频控：有人连 @ 十条不能回十条私信，那是刷屏也是风控高危动作。
    """
    feed_id = str(it.get("id") or "")
    if not config_store.at_reply_enabled(db):
        _record_at(db, feed_id, it, "unbound")
        return

    since = utcnow_naive() - timedelta(hours=AT_REPLY_COOLDOWN_HOURS)
    replied_recently = (
        db.query(AtEvent.id)
        .filter(
            AtEvent.bili_uid == mid,
            AtEvent.created_at >= since,
            AtEvent.result.in_(AT_REPLY_RESULTS),
        )
        .first()
    )
    if replied_recently is not None:
        _record_at(db, feed_id, it, "unbound_quiet")
        return

    followed = db.query(Binding).filter(Binding.bili_uid == mid).first()
    if followed is None:
        text, result = follow_guide_message(), "replied_follow"
    else:
        text, result = activation_message(followed.activation_code), "replied_code"

    try:
        client.send_msg(mid, text)
    except AppError as exc:
        reason = tracking.classify_send_error(exc)
        log(f"回复 @ 未绑定用户 {mid} 失败：{reason}")
        _record_at(db, feed_id, it, "reply_failed", reason)
    else:
        _record_at(db, feed_id, it, result)
        log(f"已回复 @ 未绑定用户 {mid}（{result}）")
        if settings.robot_send_interval_seconds > 0:
            time.sleep(settings.robot_send_interval_seconds)


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
        log("机器人未启用（ROBOT_ENABLED=false）")
        return
    if settings.dev_mode:
        Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        log("worker 已启动，开始轮询")
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
                    log(f"关注轮询出错：{exc}")
                finally:
                    client.close()
                last_follow = now
            if now - last_at >= int(cfg["at_poll_interval"]):
                client = build_worker_client(db)
                try:
                    process_at(db, client)
                except AppError as exc:
                    log(f"@轮询出错：{exc}")
                finally:
                    client.close()
                last_at = now
            if now - last_cookie >= int(cfg["cookie_check_interval"]):
                try:
                    check_cookie(db)
                except Exception as exc:  # noqa: BLE001
                    log(f"Cookie 检测出错：{exc}")
                last_cookie = now
            if once:
                break
            time.sleep(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
