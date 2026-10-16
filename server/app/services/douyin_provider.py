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
    def __init__(self, cookie: str, client: httpx.Client | None = None, timeout: float = 25.0):
        self.cookie = (cookie or "").strip()
        self._owns_client = client is None
        self.client = client or httpx.Client(follow_redirects=True, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

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
                    raise AppError(
                        422,
                        "这是抖音图文作品，暂不支持解析保存",
                        error_type="douyin_note_unsupported",
                    )
                raise AppError(
                    404, "作品不可见或已被删除", error_type="douyin_video_unavailable"
                )
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
