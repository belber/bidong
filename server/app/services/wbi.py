import hashlib
import time
import urllib.parse

import httpx

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _mixin_key(img_key: str, sub_key: str) -> str:
    orig = img_key + sub_key
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


class WbiSigner:
    """B站 wbi 签名：nav 接口取 img/sub key，拼 mixin_key 后 MD5 生成 w_rid。"""

    def __init__(self, client: httpx.Client):
        self.client = client
        self._key: str | None = None

    def _load_key(self) -> None:
        resp = self.client.get("https://api.bilibili.com/x/web-interface/nav")
        data = resp.json()
        wbi = (data.get("data") or {}).get("wbi_img") or {}
        img_url = wbi.get("img_url") or ""
        sub_url = wbi.get("sub_url") or ""
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
        self._key = _mixin_key(img_key, sub_key)

    def sign(self, params: dict) -> dict:
        if self._key is None:
            self._load_key()

        signed = {k: str(v) for k, v in params.items()}
        signed["wts"] = str(int(time.time()))
        query = urllib.parse.urlencode(sorted(signed.items()))
        query = query.replace("!", "").replace("'", "").replace("(", "").replace(")", "").replace("*", "")
        signed["w_rid"] = hashlib.md5((query + self._key).encode()).hexdigest()
        return signed
