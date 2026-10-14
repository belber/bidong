"""抖音采集会话的保温与探活。

会话是抖音这条链路的命脉：掉线后解析会静默失败（抖音回的是 200 + 0 字节，
只看状态码根本发现不了），所以必须有独立进程定期检查 + 告警。

用法（在 server/ 目录下）：

    # 每 30 分钟跑一次：探活，连续空包就告警
    .venv/bin/python -m scripts.douyin_session probe

    # 看当前状态，不产生副作用
    .venv/bin/python -m scripts.douyin_session status

    # 刷新会话（需要装 playwright：pip install playwright && playwright install chromium）
    .venv/bin/python -m scripts.douyin_session warm

建议放到定时任务里：
    */30 * * * *  cd /app/server && .venv/bin/python -m scripts.douyin_session probe
    0 */5 * * *   cd /app/server && .venv/bin/python -m scripts.douyin_session warm
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import config_store, notify  # noqa: E402
from app.services.douyin_provider import DouyinProvider  # noqa: E402

# 连续空包多少次才告警：偶发一次空包属于正常抖动
ALERT_AFTER_FAILURES = 3
FAILURE_COUNT_KEY = "douyin_probe_fail_streak"
PROFILE_DIR = "var/dy_profile"


def _probe(db) -> dict:
    cookie = config_store.douyin_cookie(db)
    if not cookie:
        return {"ok": False, "status_code": 0, "bytes": 0, "error": "还没配置 Cookie"}
    # 探针作品要固定：换作品会让「空包 vs 作品不可见」的判断漂移
    probe_id = config_store.get_raw(db, "douyin_probe_aweme_id", "") or "7685688911658323392"
    provider = DouyinProvider(cookie=cookie)
    try:
        return provider.probe(probe_id)
    finally:
        provider.close()


def _streak(db, value: int | None = None) -> int:
    if value is not None:
        config_store.set_raw(db, FAILURE_COUNT_KEY, str(value))
        db.commit()
        return value
    return int(config_store.get_raw(db, FAILURE_COUNT_KEY, "0") or 0)


def cmd_status() -> int:
    db = SessionLocal()
    try:
        print(f"已配置 Cookie : {config_store.douyin_cookie_configured(db)}")
        print(f"Cookie 长度   : {len(config_store.douyin_cookie(db))}")
        print(f"解析节点      : {config_store.douyin_parse_node(db)}")
        print(f"连续空包次数  : {_streak(db)}")
        print(f"能力开关      : {config_store.douyin_switches(db)}")
    finally:
        db.close()
    return 0


def cmd_probe() -> int:
    db = SessionLocal()
    try:
        result = _probe(db)
        if result["ok"]:
            _streak(db, 0)
            print(f"✓ 会话正常 · 响应 {result['bytes']} 字节")
            return 0

        streak = _streak(db) + 1
        _streak(db, streak)
        print(f"✗ 探活失败（第 {streak} 次）· {result['error']} · {result['bytes']} 字节")
        if streak >= ALERT_AFTER_FAILURES:
            notify.send_notification(
                db,
                "抖音会话失效",
                "抖音采集会话连续 {} 次探活失败（{}）。\n"
                "私信/@ 之外的抖音解析会全部失败，请到管理端「账号/Cookie」更新 Cookie，"
                "或重新扫码登录一次。".format(streak, result["error"]),
                kind="douyin_session",
            )
            print("已发送告警")
        return 1
    finally:
        db.close()


def cmd_warm() -> int:
    """用真浏览器打开抖音首页，让站点自己刷新会话，然后把 Cookie 导回 DB。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("需要先安装 playwright：pip install playwright && playwright install chromium")
        return 2

    profile = Path(__file__).resolve().parent.parent / PROFILE_DIR
    profile.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile),
                headless=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = ctx.new_page()
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded")
            # 给站点一点时间自己刷新 ttwid / msToken / UIFID
            page.wait_for_timeout(6000)
            cookies = ctx.cookies()
            ctx.close()
    except Exception as exc:  # noqa: BLE001 - 最常见的是浏览器没装
        print(f"启动浏览器失败：{exc}")
        print("如果是「Executable doesn't exist」，先跑：.venv/bin/python -m playwright install chromium")
        return 1

    if not cookies:
        print("没拿到任何 Cookie —— 可能这个 profile 还没扫码登录过")
        return 1

    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    db = SessionLocal()
    try:
        if "sessionid=" not in header:
            print("拿到的 Cookie 里没有 sessionid —— profile 里没有登录态，需要人工扫码一次")
            print("做法：把本脚本的 headless 改成 False，跑一次，扫码后再改回来。")
            return 1
        config_store.set_douyin_cookie(db, header)
        db.commit()
        print(f"✓ 已刷新并写入，共 {len(cookies)} 条 / {len(header)} 字符")
    finally:
        db.close()
    return 0


COMMANDS = {"status": cmd_status, "probe": cmd_probe, "warm": cmd_warm}


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "status"
    handler = COMMANDS.get(name)
    if handler is None:
        print("用法：python -m scripts.douyin_session [status|probe|warm]")
        return 2
    return handler()


if __name__ == "__main__":
    raise SystemExit(main())
