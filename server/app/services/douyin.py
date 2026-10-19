"""抖音解析：链接归一化 + 详情字段映射。

只负责「给一个链接/ID，拿回一份结构化结果」。真正的取数由 provider 承担
（见 `douyin_provider.py`），这样换出口节点 / 换数据来源时业务代码不用动。
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from ..errors import AppError

# 作品页形式：
#   https://www.douyin.com/video/<id>
#   https://www.douyin.com/note/<id>
#   https://www.iesdouyin.com/share/slides/<id>   ← 图文短链的终点，漏了它图文就解析不出
AWEME_ID_RE = re.compile(r"/(?:video|note|slides)/(\d{6,})")
SHORT_URL_RE = re.compile(r"https?://v\.douyin\.com/[0-9A-Za-z_-]+/?")
HASHTAG_RE = re.compile(r"#([^#\s]{1,30})")


def extract_aweme_id(text: str | None) -> str | None:
    """从链接/分享文案里取作品 ID。短链取不到（需要联网跟随 302）。"""
    if not text:
        return None
    hit = AWEME_ID_RE.search(text)
    return hit.group(1) if hit else None


def short_url(text: str | None) -> str | None:
    if not text:
        return None
    hit = SHORT_URL_RE.search(text)
    return hit.group(0) if hit else None


def source_url(aweme_id: str, kind: str) -> str:
    """回给用户的「去抖音查看」链接。图文用 note 路径。"""
    segment = "note" if kind == "note" else "video"
    return f"https://www.douyin.com/{segment}/{aweme_id}"


@dataclass
class DouyinMeta:
    aweme_id: str
    kind: str  # video | note
    title: str
    author_name: str
    author_unique_id: str
    author_sec_uid: str
    duration: int  # 秒
    created_at: int  # unix 秒
    cover_url: str
    video_urls: list[str] = field(default_factory=list)
    # 视频文件大小（字节）。detail 的 play_addr 自带，取不到就是 0。
    video_size: int = 0
    audio_urls: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def _urls(node) -> list[str]:
    if not isinstance(node, dict):
        return []
    return [u for u in (node.get("url_list") or []) if isinstance(u, str) and u.startswith("http")]


def _first_url(node) -> str:
    urls = _urls(node)
    return urls[0] if urls else ""


def _data_size(node) -> int:
    """play_addr 自带的文件大小：有它就不必再问 CDN 一次。"""
    if not isinstance(node, dict):
        return 0
    try:
        return max(int(node.get("data_size") or 0), 0)
    except (TypeError, ValueError):
        return 0


# `play_addr.url_list` 里混着两类地址：
#   1. 直出媒体的 CDN（`*.douyinvod.com/.../video/tos/...`）——客户端能直接下
#   2. 跳转型（`*.amemv.com/aweme/v1/play/?...`）——返回 302 + 几百字节的 text/plain
#      跳转页，真实文件还要再跳一到两次、落到动态第三方域名
# 小程序只看 HTTP 200，会把第 2 类的跳转页当成视频存下来（下载成功但打不开），
# 而且重定向的落地域名是动态的，域名白名单也配不全。所以候选只保留直出地址。
_PLAY_REDIRECT_PATH = "/aweme/v1/play/"


def is_direct_media_url(url: str) -> bool:
    """直出媒体的 CDN 地址才允许直接交给客户端下载。"""
    if not isinstance(url, str):
        return False
    try:
        path = urlparse(url).path
    except ValueError:
        return False
    return _PLAY_REDIRECT_PATH not in path


def direct_media_urls(urls: list[str]) -> list[str]:
    """丢掉跳转型地址；整组都是跳转型（罕见）时退回原列表。

    退回是为了不让这类作品直接变成「没有该类型的内容」——前端拿到跳转页会判失败，
    仍能走「复制链接用浏览器打开」的兜底弹窗。
    """
    direct = [u for u in urls if is_direct_media_url(u)]
    return direct or list(urls)


def _tags(detail: dict) -> list[str]:
    """话题标签优先取 text_extra.hashtag_name，缺失时退回从文案里抠 #。"""
    names = [
        (item.get("hashtag_name") or "").strip()
        for item in (detail.get("text_extra") or [])
        if isinstance(item, dict)
    ]
    names = [n for n in names if n]
    if not names:
        names = [m.group(1).strip() for m in HASHTAG_RE.finditer(detail.get("desc") or "")]
    return list(dict.fromkeys(n for n in names if n))


def meta_from_detail(detail: dict) -> DouyinMeta:
    """把移动端 detail 的 aweme_detail 映射成统一结构。

    抖音的统计字段和 B站 不是一套，这里直接对齐前端已有的四个格子：
    点赞 / 评论 / 收藏 / 分享。
    """
    if not isinstance(detail, dict) or not detail.get("aweme_id"):
        raise AppError(502, "抖音返回的数据不完整")

    video = detail.get("video") or {}
    music = detail.get("music") or {}
    author = detail.get("author") or {}
    stats = detail.get("statistics") or {}

    image_urls: list[str] = []
    for item in detail.get("images") or []:
        image_urls.extend(_urls(item))

    duration_ms = video.get("duration") or 0
    # aweme_type=68 是图文。不能只看 images 是否为空——接口可能把 images 摘掉，
    # 那时候作品仍然是图文，只是我们暂时拿不到图。
    is_note = bool(image_urls) or detail.get("aweme_type") == 68
    return DouyinMeta(
        aweme_id=str(detail["aweme_id"]),
        kind="note" if is_note else "video",
        title=(detail.get("desc") or "").strip(),
        author_name=(author.get("nickname") or "").strip(),
        author_unique_id=(author.get("unique_id") or "").strip(),
        author_sec_uid=(author.get("sec_uid") or "").strip(),
        duration=round(duration_ms / 1000),
        created_at=int(detail.get("create_time") or 0),
        cover_url=_first_url(video.get("cover")) or _first_url(video.get("origin_cover")),
        video_urls=direct_media_urls(_urls(video.get("play_addr"))),
        video_size=_data_size(video.get("play_addr")),
        audio_urls=direct_media_urls(_urls(music.get("play_url"))),
        image_urls=image_urls,
        tags=_tags(detail),
        stats={
            "like": int(stats.get("digg_count") or 0),
            "reply": int(stats.get("comment_count") or 0),
            "favorite": int(stats.get("collect_count") or 0),
            "share": int(stats.get("share_count") or 0),
        },
    )
