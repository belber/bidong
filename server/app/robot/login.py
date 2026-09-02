import sys
import time
from pathlib import Path

import httpx

GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

COOKIE_FIELDS = ["SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"]

ENV_MAP = {
    "SESSDATA": "ROBOT_SESSDATA",
    "bili_jct": "ROBOT_BILI_JCT",
    "DedeUserID": "ROBOT_DEDEUSERID",
    "buvid3": "ROBOT_BUVID3",
    "buvid4": "ROBOT_BUVID4",
}


def print_qr(url: str) -> None:
    try:
        import qrcode
    except ImportError:
        print("未安装 qrcode，无法在终端画二维码。")
        print("可先执行：pip install qrcode[pil]")
        print(f"或手动打开该链接生成二维码：{url}")
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def _get_json(client: httpx.Client, url: str, **kwargs) -> dict:
    resp = client.get(url, **kwargs)
    if resp.status_code != 200:
        raise RuntimeError(f"请求失败 HTTP {resp.status_code}")
    try:
        return resp.json()
    except Exception as exc:
        raise RuntimeError(
            f"响应不是 JSON（HTTP {resp.status_code}），可能是被风控拦截：{resp.text[:200]!r}"
        ) from exc


def login_flow() -> dict[str, str]:
    client = httpx.Client(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
    )
    try:
        # 预热拿到 buvid3 等基础 cookie，降低被反爬拦截的概率
        try:
            client.get("https://www.bilibili.com/")
        except Exception:
            pass

        gen_data = _get_json(client, GENERATE_URL)
        if gen_data.get("code") != 0:
            raise RuntimeError(f"生成二维码失败：{gen_data.get('message') or gen_data}")
        key = gen_data["data"]["qrcode_key"]
        url = gen_data["data"]["url"]
        print("请用 B站 App 扫码登录机器人账号：")
        print_qr(url)
        print(f"\n若终端二维码扫不了，可复制此链接到任意二维码生成器：\n{url}\n")

        while True:
            poll_data = _get_json(client, POLL_URL, params={"qrcode_key": key})
            data = poll_data.get("data") or {}
            code = data.get("code")
            if code == 0:
                cookie = {}
                for field in COOKIE_FIELDS:
                    value = client.cookies.get(field)
                    if value:
                        cookie[field] = value
                missing = [f for f in ("SESSDATA", "bili_jct", "DedeUserID") if not cookie.get(f)]
                if missing:
                    raise RuntimeError(f"登录成功但缺少关键 cookie：{missing}")
                return cookie
            if code in (86038, 86090):  # 未扫码 / 已扫码未确认
                time.sleep(2)
                continue
            raise RuntimeError(f"登录失败：{data.get('message') or code}")
    finally:
        client.close()


def save_to_env(cookie: dict[str, str]) -> Path:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    mapping = {line.split("=", 1)[0]: line for line in lines if "=" in line}

    mapping["ROBOT_ENABLED"] = "ROBOT_ENABLED=true"
    mapping["ROBOT_UID"] = f"ROBOT_UID={cookie.get('DedeUserID', '')}"
    for field, env_name in ENV_MAP.items():
        if cookie.get(field):
            mapping[env_name] = f"{env_name}={cookie[field]}"

    env_path.write_text("\n".join(mapping.values()) + "\n", encoding="utf-8")
    return env_path


def verify_login() -> None:
    from ..config import settings
    from ..services.bilibili_robot import BiliRobotClient

    client = BiliRobotClient(
        cookie={
            "SESSDATA": settings.robot_sessdata,
            "bili_jct": settings.robot_bili_jct,
            "DedeUserID": settings.robot_dedeuserid,
            "buvid3": settings.robot_buvid3,
            "buvid4": settings.robot_buvid4,
        },
        robot_uid=settings.robot_uid,
    )
    try:
        info = client.get_self_info()
        print("登录态校验通过，账号信息：")
        print(f"  UID: {info.get('mid')}")
        print(f"  昵称: {info.get('uname')}")
        print(f"  isLogin: {info.get('isLogin')}")
    finally:
        client.close()


def send_test(uid: str, content: str) -> None:
    from ..config import settings
    from ..services.bilibili_robot import BiliRobotClient

    client = BiliRobotClient(
        cookie={
            "SESSDATA": settings.robot_sessdata,
            "bili_jct": settings.robot_bili_jct,
            "DedeUserID": settings.robot_dedeuserid,
            "buvid3": settings.robot_buvid3,
            "buvid4": settings.robot_buvid4,
        },
        robot_uid=settings.robot_uid,
    )
    try:
        status, body = client.raw_send_msg(uid, content)
        print(f"HTTP {status}")
        print(body)
    finally:
        client.close()


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if "--check" in argv:
        verify_login()
        return
    if "--send" in argv:
        idx = argv.index("--send")
        uid = argv[idx + 1] if idx + 1 < len(argv) else ""
        content = " ".join(argv[idx + 2 :]) or "壁咚测试消息"
        if not uid:
            print("用法：python -m app.robot.login --send <UID> [内容]")
            return
        send_test(uid, content)
        return
    cookie = login_flow()
    path = save_to_env(cookie)
    print(f"登录成功，cookie 已写入 {path}")


if __name__ == "__main__":
    main()
