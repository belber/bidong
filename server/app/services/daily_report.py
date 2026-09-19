from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import (
    ActivationLog,
    BiliCdnDomain,
    Binding,
    DownloadEvent,
    FollowEvent,
    ParseLog,
    User,
    VideoCard,
    VisitEvent,
)
from . import config_store, notify

SH_OFFSET = timedelta(hours=8)
USER_TARGET = 500


def now_shanghai() -> datetime:
    return datetime.now(timezone.utc) + SH_OFFSET


def _day_range(day: date) -> tuple[datetime, datetime]:
    """把上海自然日转成 naive UTC 区间。"""
    start = datetime(day.year, day.month, day.day) - SH_OFFSET
    return start, start + timedelta(days=1)


def _top(counter: dict[str, int], limit: int = 5) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda x: -x[1])[:limit]


def build_report(db: Session, day: date) -> dict:
    start, end = _day_range(day)

    new_users = db.query(User).filter(User.created_at >= start, User.created_at < end).count()
    total_users = db.query(User).count()
    visits = db.query(VisitEvent).filter(VisitEvent.created_at >= start, VisitEvent.created_at < end).all()
    visit_uv = len({v.user_id for v in visits})
    visit_pv = len(visits)

    parses = db.query(ParseLog).filter(ParseLog.created_at >= start, ParseLog.created_at < end).all()
    local = [p for p in parses if p.source == "local"]
    robot = [p for p in parses if p.source == "robot"]
    new_cards = db.query(VideoCard).filter(VideoCard.collected_at >= start, VideoCard.collected_at < end).count()

    events = db.query(DownloadEvent).filter(DownloadEvent.created_at >= start, DownloadEvent.created_at < end).all()
    resolve_ok = [e for e in events if e.stage == "resolve" and e.status == "success"]
    download_ok = [e for e in events if e.stage == "download" and e.status == "success"]
    download_fail = [e for e in events if e.stage == "download" and e.status == "fail"]
    fallback_copy = [e for e in events if e.stage == "fallback" and e.status == "copy_link"]
    video_ok = [e for e in download_ok if e.kind == "watermarked"]
    audio_ok = [e for e in download_ok if e.kind == "audio"]
    total_download = len(download_ok) + len(download_fail)
    success_rate = round(len(download_ok) / total_download * 100, 1) if total_download else 0.0
    fail_reasons: dict[str, int] = {}
    fail_hosts: dict[str, int] = {}
    for e in download_fail:
        fail_reasons[e.error_type or "unknown"] = fail_reasons.get(e.error_type or "unknown", 0) + 1
        if e.host:
            fail_hosts[e.host] = fail_hosts.get(e.host, 0) + 1

    new_follows = db.query(FollowEvent).filter(FollowEvent.created_at >= start, FollowEvent.created_at < end).count()
    activation_sent = (
        db.query(ActivationLog)
        .filter(ActivationLog.created_at >= start, ActivationLog.created_at < end, ActivationLog.sent_ok.is_(True))
        .count()
    )
    bound = db.query(Binding).filter(Binding.bound_at >= start, Binding.bound_at < end).count()

    unconfigured = db.query(BiliCdnDomain).filter(BiliCdnDomain.is_configured.is_(False)).all()
    new_unconfigured = [d for d in unconfigured if start <= d.first_seen_at < end]
    cookie = config_store.cookie_status(db)

    return {
        "day": day.isoformat(),
        "users": {
            "new": new_users,
            "total": total_users,
            "target": USER_TARGET,
            "progress": round(total_users / USER_TARGET * 100, 1) if USER_TARGET else 0,
            "remaining": max(USER_TARGET - total_users, 0),
            "uv": visit_uv,
            "pv": visit_pv,
        },
        "parse": {
            "local_total": len(local),
            "local_ok": sum(1 for p in local if p.ok),
            "local_fail": sum(1 for p in local if not p.ok),
            "robot_total": len(robot),
            "robot_ok": sum(1 for p in robot if p.ok),
            "robot_fail": sum(1 for p in robot if not p.ok),
            "new_cards": new_cards,
        },
        "download": {
            "requests": len(resolve_ok),
            "success": len(download_ok),
            "fail": len(download_fail),
            "success_rate": success_rate,
            "video": len(video_ok),
            "audio": len(audio_ok),
            "fail_reasons": _top(fail_reasons),
            "fail_hosts": _top(fail_hosts),
            "fallback_copy": len(fallback_copy),
        },
        "robot": {
            "new_follows": new_follows,
            "activation_sent": activation_sent,
            "bound": bound,
        },
        "domain": {
            "unconfigured_total": len(unconfigured),
            "new_unconfigured": [d.host for d in new_unconfigured],
        },
        "cookie": cookie,
    }


def render_report(data: dict) -> str:
    u = data["users"]
    p = data["parse"]
    d = data["download"]
    r = data["robot"]
    dm = data["domain"]

    reason_lines = "\n".join(
        f"- {name}：{count}" for name, count in d["fail_reasons"]
    ) or "- 无"
    host_lines = "\n".join(
        f"- {name}：{count}" for name, count in d["fail_hosts"]
    ) or "- 无"
    new_domains = "、".join(dm["new_unconfigured"]) or "无"
    cookie_state = "正常" if data["cookie"]["cookie_valid"] else "失效"

    return f"""# 壁咚咚运营日报 {data['day']}

## 用户
- 今日新增用户：{u['new']}
- 累计用户：{u['total']} / {u['target']}（{u['progress']}%）
- 距离目标还差：{u['remaining']}
- 今日访问 UV：{u['uv']}
- 今日访问 PV：{u['pv']}

## 解析
- 手动解析：{p['local_total']} 次（成功 {p['local_ok']} / 失败 {p['local_fail']}）
- 机器人解析：{p['robot_total']} 次（成功 {p['robot_ok']} / 失败 {p['robot_fail']}）
- 新增收藏卡片：{p['new_cards']}

## 下载
- 下载请求：{d['requests']}
- 下载成功：{d['success']}
- 下载失败：{d['fail']}
- 下载成功率：{d['success_rate']}%
- 视频下载：{d['video']}
- 音频转发：{d['audio']}
- 失败后复制链接：{d['fallback_copy']}

失败原因 Top：
{reason_lines}

失败域名 Top：
{host_lines}

## 机器人与域名
- 今日新增关注：{r['new_follows']}
- 发码成功：{r['activation_sent']}
- 绑定成功：{r['bound']}
- 未配置域名总数：{dm['unconfigured_total']}
- 今日新出现未配置域名：{new_domains}
- Cookie 状态：{cookie_state}
"""


def send_daily_report(db: Session, day: date) -> dict:
    data = build_report(db, day)
    body = render_report(data)
    return notify.send_notification(db, f"壁咚咚运营日报 {day.isoformat()}", body, kind="report")


def _target_minutes(report_time: str) -> int:
    try:
        hh, mm = report_time.split(":")
        return int(hh) * 60 + int(mm)
    except (AttributeError, ValueError):
        return 9 * 60


def maybe_send_daily_report(db: Session, now: datetime | None = None) -> bool:
    cfg = config_store.alert_config(db)
    if not cfg["report_enabled"]:
        return False
    now = now or now_shanghai()
    if now.hour * 60 + now.minute < _target_minutes(cfg["report_time"]):
        return False
    today_key = now.date().isoformat()
    if config_store.get_raw(db, "report_last_sent_date") == today_key:
        return False

    sent = send_daily_report(db, now.date() - timedelta(days=1))
    if sent["email"] or sent["serverchan"]:
        config_store.set_raw(db, "report_last_sent_date", today_key)
        return True
    return False
