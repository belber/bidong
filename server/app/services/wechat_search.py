"""搜一搜数据推送（submitpages）。

把「视频结果页」主动推给微信搜索，比等爬虫自己发现快得多。
接口：POST /wxa/search/wxaapi_submitpages?access_token=...

两个阶段（微信自己的设计）：先用 wxsearch_testcpdata 走格式审核，
审核通过后再用 wxsearch_cpdata 推正式数据，正式数据才会出现在搜索结果里。
"""

import json
import time

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import VideoCard
from ..time import utcnow_naive, to_unix
from . import admin_stats, config_store, repost_source

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
PUSH_URL = "https://api.weixin.qq.com/wxa/search/wxaapi_submitpages"

TYPE_AUDIT = "wxsearch_testcpdata"
TYPE_PROD = "wxsearch_cpdata"

TITLE_LIMIT = 20        # 微信建议标题 20 字以内
PAGE_TYPE = 2           # 接口要求固定填 2

ERROR_HINTS = {
    40066: "sitemap 配置把该页面挡住了（检查 sitemap.json）",
    40211: "数据结构校验失败，按返回里的字段提示修",
    40212: "页面 query 不合法",
    40219: "pages 为空",
    45002: "请求包太大，分批推",
    47004: "一次提交超过 1000 个页面",
    47006: "今天的推送配额用完了，明天再试",
    85083: "小程序的搜索功能被禁用",
    85091: "小程序的「搜索」开关被关闭，去小程序后台设置里打开",
    108002: "单个页面内容超过 1M",
    108003: "内容接入还没审核通过（或还没提交申请）",
}

STATE_KEY = "wechat_search_state"
TOKEN_KEY = "wechat_access_token"


class SearchPushError(Exception):
    """推送失败，message 已经是能直接给运营看的中文。"""


def _api_error(errcode: int, errmsg: str, prefix: str = "微信接口报错") -> SearchPushError:
    hint = ERROR_HINTS.get(errcode)
    text = f"{prefix}：{errcode} {errmsg}"
    return SearchPushError(f"{text}（{hint}）" if hint else text)


# ---------------------------------------------------------------------------
# access_token
# ---------------------------------------------------------------------------
def get_access_token(db: Session) -> str:
    """取 access_token，缓存到本地（微信限制每天调用次数，不能每次现换）。"""
    cached = config_store.get_json(db, TOKEN_KEY) or {}
    token = (cached.get("token") or "").strip()
    if token and float(cached.get("expires_at") or 0) > time.time() + 300:
        return token

    appid = settings.wechat_appid
    secret = settings.wechat_secret
    if not appid or not secret:
        raise SearchPushError("还没配置小程序 appid / secret，无法调用微信接口")

    try:
        resp = httpx.get(
            TOKEN_URL,
            params={
                "grant_type": "client_credential",
                "appid": appid,
                "secret": secret,
            },
            timeout=10,
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise SearchPushError(f"获取 access_token 失败：{exc}") from exc

    if not data.get("access_token"):
        raise _api_error(
            int(data.get("errcode") or 0),
            data.get("errmsg") or "",
            "获取 access_token 失败",
        )
    config_store.set_json(
        db,
        TOKEN_KEY,
        {
            "token": data["access_token"],
            "expires_at": time.time() + int(data.get("expires_in") or 7200),
        },
    )
    return data["access_token"]


# ---------------------------------------------------------------------------
# 组装页面
# ---------------------------------------------------------------------------
def _short(text: str, limit: int = TITLE_LIMIT) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit]


def build_video_page(db: Session, card: VideoCard, type_value: str) -> dict:
    """把一张卡片组装成搜一搜能吃的页面结构。"""
    origin = repost_source.get_origin(db, bvid=card.bvid, up_mid=card.up_mid)
    lines = [f"{card.title}", f"UP主：{card.up_name}"]
    if card.partition:
        lines.append(f"分区：{card.partition}")
    if origin is not None:
        if origin.platform_label:
            lines.append(f"原平台：{origin.platform_label}")
        if origin.author_name:
            who = f"原up主：{origin.author_name}"
            if origin.author_handle:
                who += f"（{origin.author_handle}）"
            lines.append(who)
    if card.desc:
        lines.append(card.desc)
    lines.append(f"B站原视频：{card.source_url}")

    # 正文不能带 html 标签
    mainbody = "\n".join(lines).replace("<", " ").replace(">", " ")
    return {
        "path": "pages/result/result",
        "query": f"bvid={card.bvid}",
        "data_list": [
            {
                "@type": type_value,
                "update": 1,  # 1=新增，路径相同微信会覆盖更新
                "content_id": card.bvid,
                "page_type": PAGE_TYPE,
                "title": _short(card.title),
                "abstract": [_short(card.desc, 60)] if card.desc else [],
                "cover_img_url": card.cover_url,
                "mainbody": mainbody,
                "time_publish": int(card.pubdate or 0) or to_unix(utcnow_naive()),
                "time_modify": to_unix(utcnow_naive()),
            }
        ],
    }


def submit_pages(db: Session, pages: list[dict]) -> dict:
    if not pages:
        return {"ok": True, "count": 0}
    token = get_access_token(db)
    try:
        resp = httpx.post(
            PUSH_URL,
            params={"access_token": token},
            content=json.dumps({"pages": pages}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise SearchPushError(f"推送失败：{exc}") from exc

    if int(data.get("errcode") or 0) != 0:
        raise _api_error(int(data.get("errcode") or 0), data.get("errmsg") or "", "推送被拒")
    return {"ok": True, "count": len(pages)}


# ---------------------------------------------------------------------------
# 推送状态与入口
# ---------------------------------------------------------------------------
def state(db: Session) -> dict:
    return config_store.get_json(db, STATE_KEY) or {}


def enabled(db: Session) -> bool:
    return bool(config_store.get_bool(db, "enable_wechat_search_push", default=False))


def set_enabled(db: Session, value: bool) -> None:
    config_store.set_raw(db, "enable_wechat_search_push", str(bool(value)))


def mode(db: Session) -> str:
    return config_store.get_raw(db, "wechat_search_mode") or "audit"


def set_mode(db: Session, value: str) -> None:
    config_store.set_raw(db, "wechat_search_mode", "prod" if value == "prod" else "audit")


def pending_count(db: Session) -> int:
    """还没推过的视频数（按上次推送时间之后的卡片算）。"""
    last = state(db).get("last_push_at")
    query = db.query(VideoCard)
    if last:
        from datetime import datetime

        try:
            query = query.filter(VideoCard.collected_at >= datetime.fromisoformat(last))
        except ValueError:
            pass
    return query.count()


def set_state(db: Session, **fields) -> None:
    payload = state(db)
    payload.update({k: v for k, v in fields.items()})
    config_store.set_json(db, STATE_KEY, payload)


def push_videos(db: Session, mode: str = "audit", limit: int = 1000) -> dict:
    """把库里的视频结果页推给微信搜索。mode=audit 用审核数据，prod 用正式数据。"""
    type_value = TYPE_PROD if mode == "prod" else TYPE_AUDIT
    last_push_at = state(db).get("last_push_at") or ""
    query = db.query(VideoCard).order_by(VideoCard.id.desc())
    if last_push_at:
        from datetime import datetime

        try:
            since = datetime.fromisoformat(last_push_at)
            query = query.filter(VideoCard.collected_at >= since)
        except ValueError:
            pass
    cards = query.limit(limit).all()

    pages = [build_video_page(db, card, type_value) for card in cards]
    result = submit_pages(db, pages)
    set_state(
        db,
        last_push_at=utcnow_naive().isoformat(),
        last_mode=mode,
        last_ok=result.get("count", 0),
        last_fail=0,
        last_error="",
    )
    return {"ok": result.get("count", 0), "fail": 0, "mode": mode}


def push_all(db: Session, mode: str = "audit") -> dict:
    """全量重推（审核/正式都可以），用于首次接入或修数据后重来一遍。"""
    type_value = TYPE_PROD if mode == "prod" else TYPE_AUDIT
    cards = db.query(VideoCard).order_by(VideoCard.id.desc()).limit(1000).all()
    pages = [build_video_page(db, card, type_value) for card in cards]
    total = 0
    try:
        for start in range(0, len(pages), 100):  # 分批，避免单包过大
            chunk = pages[start : start + 100]
            result = submit_pages(db, chunk)
            total += result.get("count", 0)
    except SearchPushError as exc:
        set_state(db, last_ok=total, last_fail=len(pages) - total, last_error=str(exc))
        raise
    set_state(
        db,
        last_push_at=utcnow_naive().isoformat(),
        last_mode=mode,
        last_ok=total,
        last_fail=0,
        last_error="",
    )
    return {"ok": total, "fail": 0, "mode": mode}


def maybe_push_search(db: Session, now=None) -> bool:
    """每天推一次增量（有开关控制）。失败只记状态，不打断其它定时任务。"""
    if not enabled(db):
        return False
    now = now or utcnow_naive()
    last = state(db).get("last_push_at")
    if last:
        from datetime import datetime, timedelta

        try:
            if now - datetime.fromisoformat(last) < timedelta(hours=24):
                return False
        except ValueError:
            pass
    if pending_count(db) == 0:
        set_state(db, last_push_at=now.isoformat(), last_error="")
        return False
    try:
        push_videos(db, mode=mode(db))
        return True
    except SearchPushError as exc:
        set_state(db, last_error=str(exc))
        return False
