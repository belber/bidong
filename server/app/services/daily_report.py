"""每日运营报告。

数据口径与后台「概览」完全共用（`overview_stats.day_snapshot`），
区别只是概览看今天、日报看昨天——两边不会各说各话。
报告按概览的分区顺序组织：访问 / 机器人 / 解析 / 下载 / 音视频文本导出 / 域名。
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import config_store, notify, overview_stats

SH_OFFSET = timedelta(hours=8)

EXPORT_LABELS = {
    "audio": "音频",
    "comment": "评论",
    "danmaku": "弹幕",
    "subtitle": "字幕",
}


def now_shanghai() -> datetime:
    return datetime.now(timezone.utc) + SH_OFFSET


def build_report(db: Session, day: date) -> dict:
    """某一天的运营数据，口径与概览一致。"""
    return overview_stats.day_snapshot(db, day)


def _counters(rows: list[dict], key: str, limit: int = 5) -> str:
    parts = [f"{item[key]}：{item['count']}" for item in rows[:limit]]
    return " · ".join(parts) or "无"


def render_report(data: dict) -> str:
    visit = data["visit"]
    bot = data["bot"]
    parse = data["parse"]
    download = data["download"]
    exports = data["exports"]
    domains = data["domains"]

    export_lines = "\n".join(
        f"- {EXPORT_LABELS[kind]}：{stats['total']} 次 · {stats['users']} 人"
        + (f"（成功 {stats['success']} / 失败 {stats['fail']}）" if stats["total"] else "")
        for kind, stats in exports.items()
    )
    new_domains = "、".join(item["host"] for item in domains["new_unconfigured"]) or "无"
    cookie_state = "正常" if data["cookie"]["cookie_valid"] else "⚠ 已失效"

    return f"""# 壁咚咚运营日报 {data['day']}

机器人 Cookie：{cookie_state}

## 一、访问情况
- 当日访问用户：{visit['uv']} 人（访问 {visit['pv']} 次）
- 当日新增注册用户：{visit['new_users']}
- 累计访问用户：{visit['total_uv']} / {visit['target']}（{visit['progress']}%），还差 {visit['remaining']} 人
- 累计注册用户：{visit['total_users']}

## 二、机器人关注与绑定
- 当日新增关注：{bot['new_follows']}
- 关注总数：{bot['followers_total']}
- 已绑定：{bot['bound']}（关注→绑定 {bot['conversion']}%）
- 当日发码成功：{bot['sent_ok']}

## 三、视频解析
- 当日解析：{parse['total']} 次（成功 {parse['ok']} / 失败 {parse['fail']}）
- 贴链接触发：{parse['local_total']} 次 · {parse['local_users']} 人
- 评论 @ 触发：{parse['robot_total']} 次 · {parse['robot_users']} 人
- 新增收藏卡片：{parse['new_cards']}
- 失败原因：{_counters(parse['fail_by_reason'], 'reason')}

## 四、视频下载
- 当日下载：{download['total']} 次
- 成功：{download['success']}（保存 {download['saved']} + 复制链接 {download['copied']}）
- 失败：{download['fail']}
- 成功率：{download['success_rate']}%
- 失败原因：{_counters(download['fail_by_error'], 'error_type')}

## 五、音频 / 评论 / 弹幕 / 字幕
{export_lines}

## 六、B站 CDN 域名
- 当日命中域名：{domains['seen']} 个
- 当日新增未配置：{len(domains['new_unconfigured'])}（{new_domains}）
- 当前未配置总数：{domains['unconfigured']}
"""


def send_daily_report(db: Session, day: date) -> dict:
    data = build_report(db, day)
    body = render_report(data)
    return notify.send_notification(
        db, f"壁咚咚运营日报 {day.isoformat()}", body, kind="report"
    )


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
