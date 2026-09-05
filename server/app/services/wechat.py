import httpx

from ..config import settings
from ..errors import AppError


def resolve_openid(code: str) -> str:
    """code -> openid。dev 模式下用固定映射，生产模式调微信 jscode2session。"""
    if settings.dev_mode:
        # dev_ 前缀允许手动指定多个测试用户；其余（wx.login 的真实 code）统一落到
        # 固定 openid，保证开发者工具反复登录仍是同一个用户。
        return code if code.startswith("dev_") else "oqG0jxq67cTHa76elBgLm-LHSfJM"

    if not settings.wechat_appid or not settings.wechat_secret:
        raise AppError(500, "服务端未配置微信登录")

    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": settings.wechat_appid,
        "secret": settings.wechat_secret,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    try:
        resp = httpx.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception as exc:
        raise AppError(502, "微信登录服务不可用") from exc

    openid = data.get("openid")
    if not openid:
        errmsg = data.get("errmsg", "未知错误")
        raise AppError(401, f"微信登录失败：{errmsg}")
    return openid
