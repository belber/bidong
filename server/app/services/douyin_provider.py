"""抖音取数 provider。

业务侧只依赖 `DouyinProvider` 暴露的三个动作：解析链接、取详情、探活。
换出口节点（机房 ↔ 住宅）或将来换数据来源时，只替换这一层的实现。

关键判据：身份失效时抖音回的是 **200 + 0 字节**，不是错误状态码，
所以成功与否必须看响应体大小。
"""

import httpx

from ..errors import AppError
from .douyin import SHORT_URL_RE, extract_aweme_id, meta_from_detail

DETAIL_API = "https://aweme.snssdk.com/aweme/v1/aweme/detail/"
HOSTS = (
    "https://aweme.snssdk.com",
    "https://api.amemv.com",
    "https://api3-normal-c-lf.amemv.com",
)
IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
REFERER = "https://www.douyin.com/"

# 小于这个字节数就认定不是有效响应（空包通常是 0 字节）
MIN_VALID_BYTES = 1024

# 接口把图文作品按这个理由过滤掉
NOTE_FILTER_REASON = "images_base"

# 给用户看的文案：会话失效、接口异常这类问题都属于我方内部故障，
# 用户既看不懂也帮不上忙，说细了只会让人以为是自己链接的问题。
# 真实原因走 error_type 落进 parse_log，运营在管理端看得到。
MAINTENANCE_MESSAGE = "服务维护中，请稍后再试"
BUSY_MESSAGE = "服务繁忙，请稍后再试"


def _filter_reason(payload: dict) -> str:
    """接口拒绝返回作品时给的过滤理由。"""
    return ((payload or {}).get("filter_detail") or {}).get("filter_reason") or ""


class DouyinProvider:
    def __init__(
        self,
        cookie: str,
        client: httpx.Client | None = None,
        timeout: float = 25.0,
        note_fetcher=None,
    ):
        self.cookie = (cookie or "").strip()
        self._owns_client = client is None
        self.client = client or httpx.Client(follow_redirects=True, timeout=timeout)
        self.note_fetcher = note_fetcher

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
        if self.note_fetcher is not None and hasattr(self.note_fetcher, "close"):
            self.note_fetcher.close()

    def _fetch_note_detail(self, aweme_id: str) -> dict:
        if hasattr(self.note_fetcher, "fetch_detail"):
            detail = self.note_fetcher.fetch_detail(aweme_id)
        else:
            detail = self.note_fetcher(aweme_id)
        return self._fill_note_bgm(detail)

    def _note_music_urls(self, music_id: str) -> list[str]:
        """按 music_id 查 BGM 直链（图集详情里常常没有 play_url）。"""
        try:
            resp = self.client.get(
                HOSTS[0] + "/aweme/v1/music/detail/",
                params={
                    "music_id": music_id,
                    "version_code": "9.9.0",
                    "device_platform": "iphone",
                    "aid": 1128,
                },
                headers={
                    "User-Agent": IPHONE_UA,
                    "Referer": REFERER,
                    "Cookie": self.cookie,
                },
            )
            info = (resp.json() or {}).get("music_info") or {}
            play = info.get("play_url") or {}
        except Exception:  # noqa: BLE001 - 补不到 BGM 不该影响图文解析
            return []
        urls = play.get("url_list") if isinstance(play, dict) else []
        return [u for u in (urls or []) if isinstance(u, str) and u.startswith("http")]

    def _fill_note_bgm(self, detail: dict) -> dict:
        """图集第三方结果只给 music_id 时，补一次 BGM 直链。

        已有 play_url 就不发请求；补不到只是结果页不出现「音频」行，
        图片解析和保存完全不受影响，所以这里吞掉所有异常。
        """
        if not isinstance(detail, dict):
            return detail
        music = detail.get("music")
        if not isinstance(music, dict):
            music = {}
            detail["music"] = music
        play = music.get("play_url")
        if isinstance(play, dict) and play.get("url_list"):
            return detail
        music_id = str(music.get("music_id") or music.get("id_str") or music.get("id") or "")
        if not music_id:
            return detail
        found = self._note_music_urls(music_id)
        if found:
            music["play_url"] = {"url_list": found}
        return detail

    # -- 链接 --------------------------------------------------------------
    def resolve_aweme_id(self, text: str) -> str:
        """链接/分享文案 → 作品 ID。短链需要联网跟随 302。"""
        aweme_id = extract_aweme_id(text)
        if aweme_id:
            return aweme_id

        hit = SHORT_URL_RE.search(text or "")
        if not hit:
            raise AppError(400, "不是有效的抖音链接")

        url = hit.group(0)
        try:
            resp = self.client.get(url)
        except Exception as exc:  # noqa: BLE001 - 统一转成业务错误
            raise AppError(502, "解析抖音短链失败") from exc

        aweme_id = extract_aweme_id(str(resp.url)) or extract_aweme_id(resp.text)
        if not aweme_id:
            raise AppError(400, "短链未指向有效作品")
        return aweme_id

    # -- 详情 --------------------------------------------------------------
    def _detail_request(self, aweme_id: str, base: str) -> httpx.Response:
        return self.client.get(
            base + "/aweme/v1/aweme/detail/",
            params={
                "aweme_id": aweme_id,
                "version_code": "9.9.0",
                "device_platform": "iphone",
                "aid": 1128,
            },
            headers={
                "User-Agent": IPHONE_UA,
                "Referer": REFERER,
                "Cookie": self.cookie,
            },
        )

    def fetch_detail(self, aweme_id: str) -> dict:
        if not self.cookie:
            # 没配会话就别白跑一趟接口了；对用户统一说维护中
            raise AppError(
                502, MAINTENANCE_MESSAGE, error_type="douyin_session_missing"
            )
        last_error: Exception | None = None
        for base in HOSTS:
            try:
                resp = self._detail_request(aweme_id, base)
            except Exception as exc:  # noqa: BLE001 - 换备用 host 再试
                last_error = exc
                continue

            # 身份失效时抖音回的是 200 + 0 字节，所以判「空包」要看**字节数**。
            # 但不能一刀切：图文被过滤时的响应体也很小，却是合法 JSON。
            # 顺序必须是「先试着当 JSON 解析，解析不出来再判空包」。
            try:
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                if len(resp.content) < MIN_VALID_BYTES:
                    raise AppError(
                        502,
                        MAINTENANCE_MESSAGE,
                        error_type="douyin_session_invalid",
                    ) from exc
                raise AppError(
                    502, BUSY_MESSAGE, error_type="douyin_bad_response"
                ) from exc
            if not isinstance(payload, dict):
                raise AppError(502, BUSY_MESSAGE, error_type="douyin_bad_response")

            detail = payload.get("aweme_detail") or {}
            if not detail:
                # 图文作品会被接口按 images_base 过滤掉。这不是「作品被删了」，
                # 文案必须分开，否则用户会以为这条作品不存在。
                if _filter_reason(payload) == NOTE_FILTER_REASON:
                    if self.note_fetcher is not None:
                        return self._fetch_note_detail(aweme_id)
                    raise AppError(
                        422,
                        "这是抖音图文作品，暂不支持解析保存",
                        error_type="douyin_note_unsupported",
                    )
                raise AppError(
                    404, "作品不可见或已被删除", error_type="douyin_video_unavailable"
                )
            if detail.get("aweme_type") == 68 and not (detail.get("images") or []):
                if self.note_fetcher is not None:
                    return self._fetch_note_detail(aweme_id)
            return detail

        raise AppError(502, BUSY_MESSAGE, error_type="douyin_busy") from last_error

    def resolve(self, text: str):
        """链接 → 结构化结果，业务层的主入口。"""
        aweme_id = self.resolve_aweme_id(text)
        return meta_from_detail(self.fetch_detail(aweme_id))

    # -- 探活 --------------------------------------------------------------
    def probe(self, aweme_id: str) -> dict:
        """给管理端用：拿响应体字节数判断会话是否还活着。"""
        try:
            resp = self._detail_request(aweme_id, HOSTS[0])
            size = len(resp.content)
            return {
                "ok": size >= MIN_VALID_BYTES,
                "status_code": resp.status_code,
                "bytes": size,
                "error": "" if size >= MIN_VALID_BYTES else "空包",
            }
        except Exception as exc:  # noqa: BLE001 - 探活要把异常变成结果返回
            return {"ok": False, "status_code": 0, "bytes": 0, "error": str(exc)}


def build_douyin_provider(db) -> DouyinProvider:
    """生产解析入口：移动会话 + 可选第三方图文兜底。"""
    from . import config_store
    from .douyin_note_api import build_note_fetcher

    return DouyinProvider(
        cookie=config_store.douyin_cookie(db),
        note_fetcher=build_note_fetcher(db),
    )
