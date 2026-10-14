"""抖音直链可行性探针。

回答一个问题：抖音的视频 / 音频直链，在**没有 douyin.com Referer** 的时候能不能下载？
这决定小程序能不能像 B站 那样把直链直接交给客户端去拉（零服务端中转流量），
还是必须走服务端中转。

用法（在 server/ 目录下）：

    # 1) 把专用小号的整段 cookie 存成一行（sessionid=...; sid_tt=...; uid_tt=...; ...）
    #    var/ 已在 .gitignore 里，不会误提交
    echo 'sessionid=...; sid_tt=...' > var/dy_cookie.txt

    # 2) 跑探针。参数可以是分享文案、短链、或纯 aweme_id
    .venv/bin/python -m scripts.probe_douyin "7.43 复制打开抖音，看看【...】 https://v.douyin.com/xxxx/"

不带参数时只跑「不带 cookie」的基线对照。
"""

import json
import re
import sys
from pathlib import Path

import httpx

IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
DETAIL_API = "https://aweme.snssdk.com/aweme/v1/aweme/detail/"
WECHAT_REFERER = "https://servicewechat.com/wx0000/1/page-frame.html"
COOKIE_FILE = Path(__file__).resolve().parent.parent / "var" / "dy_cookie.txt"

ID_RE = re.compile(r"(?:video|note|slides)/(\d{6,})")
SHORT_RE = re.compile(r"https?://v\.douyin\.com/[0-9A-Za-z_-]+/?")
CHUNK = 128 * 1024


def resolve_aweme_id(raw: str) -> tuple[str, str]:
    """从分享文案 / 短链 / 纯 ID 里取出 aweme_id，返回 (id, 说明)。"""
    raw = (raw or "").strip()
    if not raw:
        return "", "参数为空"
    if raw.isdigit():
        return raw, "直接给了 aweme_id"

    hit = ID_RE.search(raw)
    if hit:
        return hit.group(1), "文案里直接有作品 ID"

    short = SHORT_RE.search(raw)
    if not short:
        return "", "没找到抖音链接或作品 ID"

    with httpx.Client(follow_redirects=True, timeout=20) as client:
        r = client.get(short.group(0), headers={"User-Agent": IPHONE_UA})
    hit = ID_RE.search(str(r.url))
    if not hit:
        return "", f"短链跳到了 {r.url}，里面没有作品 ID（可能是直播或已失效）"
    return hit.group(1), f"短链 302 → {r.url}"


def fetch_detail(aweme_id: str, cookie: str) -> tuple[int, int, dict | None]:
    params = {
        "aweme_id": aweme_id,
        "version_code": "9.9.0",
        "device_platform": "iphone",
        "aid": 1128,
    }
    headers = {"User-Agent": IPHONE_UA, "Referer": "https://www.douyin.com/"}
    if cookie:
        headers["Cookie"] = cookie
    with httpx.Client(timeout=25) as client:
        r = client.get(DETAIL_API, params=params, headers=headers)
    size = len(r.content)
    try:
        return r.status_code, size, r.json()
    except Exception:  # noqa: BLE001 - 空包不是 JSON
        return r.status_code, size, None


def probe(headers: dict, label: str, url: str) -> str:
    """只读前 CHUNK 字节，判断这个 URL 在给定请求头下能不能下。"""
    try:
        with httpx.Client(follow_redirects=True, timeout=25) as client:
            with client.stream("GET", url, headers=headers) as r:
                got = 0
                for chunk in r.iter_bytes():
                    got += len(chunk)
                    if got >= CHUNK:
                        break
                code = r.status_code
                ctype = r.headers.get("content-type", "?")
        return f"{label:<24} http={code} 收到={got}B type={ctype}"
    except Exception as exc:  # noqa: BLE001 - 探针只看结果
        return f"{label:<24} 请求异常: {exc}"


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else ""
    cookie = ""
    if COOKIE_FILE.exists():
        cookie = COOKIE_FILE.read_text(encoding="utf-8").strip()

    print("=" * 74)
    print("抖音直链探针")
    print("=" * 74)
    state = f"已加载（{len(cookie)} 字符）" if cookie else "未配置 —— 只能跑基线对照"
    print(f"cookie: {state}")

    aweme_id = ""
    if raw:
        aweme_id, how = resolve_aweme_id(raw)
        print(f"作品 ID: {aweme_id or '(没解析出来)'}  ← {how}")

    print()
    print("[1] 基线：不带 cookie 打移动端 detail")
    code, size, _ = fetch_detail(aweme_id or "7662997337493491129", "")
    verdict = "空包，符合预期（登录态是硬门槛）" if size < 1024 else "居然有数据！"
    print(f"    http={code} bytes={size}  →  {verdict}")

    if not cookie or not aweme_id:
        print()
        print("没有 cookie 或没有作品 ID，后面的直链测试跑不了。")
        print("准备：echo 'sessionid=...; sid_tt=...' > var/dy_cookie.txt")
        return

    print()
    print("[2] 带 cookie 打移动端 detail")
    code, size, data = fetch_detail(aweme_id, cookie)
    print(f"    http={code} bytes={size}")
    if not data or size < 1024:
        print("    空包 —— cookie 失效，或这个出口 IP 不被接受")
        return

    # 图文作品会被接口按 filter_reason 过滤掉：先把原始理由打出来，
    # 免得把「图文不支持」误判成「作品被删了」
    filter_detail = data.get("filter_detail") or {}
    if filter_detail:
        print(f"    ⚠ 接口给了过滤理由: {filter_detail}")
    if not data.get("aweme_detail"):
        print(f"    没有 aweme_detail。响应顶层字段: {sorted(data.keys())}")
        if filter_detail.get("filter_reason") == "images_base":
            print("    → 这是图文作品的正常表现：接口对图文一律过滤掉图片。")
            print("      结论：走接口拿不到图集，图文这条得另想办法。")
        return

    detail = data.get("aweme_detail") or {}

    author = detail.get("author") or {}
    print(f"    aweme_type={detail.get('aweme_type')} media_type={detail.get('media_type')}")
    print(f"    描述: {(detail.get('desc') or '')[:50]}")
    print(f"    作者: {author.get('nickname')} / 抖音号 {author.get('unique_id')}")
    print(f"    统计: {detail.get('statistics')}")

    targets: list[tuple[str, str]] = []
    play = ((detail.get("video") or {}).get("play_addr") or {}).get("url_list") or []
    if play:
        targets.append(("视频", play[0]))
    audio = ((detail.get("music") or {}).get("play_url") or {}).get("url_list") or []
    if audio:
        targets.append(("音频", audio[0]))

    images = detail.get("images") or []
    aweme_type = detail.get("aweme_type")
    is_note = bool(images) or aweme_type == 68
    print(f"    aweme_type={aweme_type} → {'图文作品' if is_note else '视频作品'}")
    if is_note and not images:
        print("    ⚠ 图文作品但 images 为空：接口把图片摘掉了，图集存不了")
    elif images:
        print(f"    ✓ 图文作品拿到 {len(images)} 张图的 URL")

    if not targets:
        print("    没拿到任何媒体直链")
        return

    combos = [
        ("无 Referer（浏览器打开）", {"User-Agent": IPHONE_UA}),
        ("微信 Referer（小程序）", {"User-Agent": IPHONE_UA, "Referer": WECHAT_REFERER}),
        ("douyin Referer（文档配方）", {"User-Agent": IPHONE_UA, "Referer": "https://www.douyin.com/"}),
    ]

    for kind, url in targets:
        print()
        print(f"[3] {kind}直链 {url[:76]}…")
        for label, headers in combos:
            print("    " + probe(headers, label, url))

    print()
    print("判读：")
    print("  · 无 Referer 和 微信 Referer 都 200 → 客户端可直连，零中转")
    print("  · 只有 douyin Referer 200 → 必须中转，兜底也只能去抖音 App 保存")


if __name__ == "__main__":
    main()
