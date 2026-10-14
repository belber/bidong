"""判断用户贴进来的一段文本属于哪个平台。

首页只有一个「贴链接」入口，所以归一化放在一处，两个平台共用。
"""

from .bilibili import B23_RE, BVID_RE
from .douyin import AWEME_ID_RE, SHORT_URL_RE


def detect_platform(text: str | None) -> str | None:
    """返回 'douyin' / 'bilibili' / None。"""
    raw = (text or "").strip()
    if not raw:
        return None
    if SHORT_URL_RE.search(raw) or AWEME_ID_RE.search(raw) or "douyin.com" in raw:
        return "douyin"
    if B23_RE.search(raw) or BVID_RE.search(raw) or "bilibili.com" in raw:
        return "bilibili"
    return None
