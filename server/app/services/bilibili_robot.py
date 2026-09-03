import json
import re
import time
import uuid

import httpx

from ..errors import AppError

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 接口地址集中在此，实测后如需调整只改这里。
FOLLOWERS_URL = "https://api.bilibili.com/x/relation/followers"
AT_FEED_URL = "https://api.bilibili.com/x/msgfeed/at"
SEND_MSG_URL = "https://api.vc.bilibili.com/web_im/v1/web_im/send_msg"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

BVID_RE = re.compile(r"BV[0-9A-Za-z]{10}")


class BiliRobotClient:
    def __init__(self, cookie: dict[str, str], robot_uid: str = "") -> None:
        self.cookie = cookie
        self.robot_uid = str(robot_uid or cookie.get("DedeUserID") or "")
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=10,
            headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
            cookies=cookie,
        )

    def close(self) -> None:
        self.client.close()

    def _get_json(self, url: str, params: dict | None = None) -> dict:
        try:
            resp = self.client.get(url, params=params)
        except Exception as exc:
            raise AppError(502, "B站机器人接口请求失败") from exc
        if resp.status_code != 200:
            raise AppError(502, f"B站机器人接口请求失败（HTTP {resp.status_code}）")
        try:
            data = resp.json()
        except Exception as exc:
            raise AppError(
                502,
                f"B站机器人接口返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]!r}",
            ) from exc
        if data.get("code") != 0:
            raise AppError(
                502,
                f"B站机器人接口返回错误：code={data.get('code')} message={data.get('message')}",
            )
        return data

    def raw_response(self, url: str, params: dict | None = None) -> tuple[int, str]:
        try:
            resp = self.client.get(url, params=params)
        except Exception as exc:
            return 0, f"请求异常：{exc}"
        return resp.status_code, resp.text[:3000]

    def get_followers(self, pn: int = 1, ps: int = 50) -> list[dict]:
        data = self._get_json(
            FOLLOWERS_URL, params={"vmid": self.robot_uid, "pn": pn, "ps": ps}
        )
        items = ((data.get("data") or {}).get("list")) or []
        out: list[dict] = []
        for u in items:
            if isinstance(u, dict) and u.get("mid") is not None:
                out.append(
                    {
                        "mid": str(u["mid"]),
                        "uname": u.get("uname") or "",
                        "mtime": int(u.get("mtime") or 0),
                    }
                )
        return out

    def get_at_notifications(self) -> list[dict]:
        data = self._get_json(AT_FEED_URL)
        items = ((data.get("data") or {}).get("items")) or []
        out: list[dict] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            user = it.get("user") or {}
            mid = user.get("mid")
            if mid is None:
                continue
            bvid = self._extract_bvid(it)
            if not bvid:
                continue
            out.append(
                {
                    "id": str(it.get("id") or ""),
                    "time": int(it.get("at_time") or it.get("time") or 0),
                    "mid": str(mid),
                    "uname": user.get("uname") or user.get("nickname") or "",
                    "bvid": bvid,
                }
            )
        return out

    def _extract_bvid(self, item: dict) -> str:
        inner = item.get("item")
        if isinstance(inner, dict):
            for key in ("bvid", "bvid_str", "source_id"):
                value = inner.get(key)
                if isinstance(value, str):
                    m = BVID_RE.search(value)
                    if m:
                        return m.group(0)
            for key in ("source_content", "content", "uri", "url", "biz"):
                value = inner.get(key)
                if isinstance(value, str):
                    m = BVID_RE.search(value)
                    if m:
                        return m.group(0)
        for key in ("source_content", "content", "biz", "uri", "url", "bvid"):
            value = item.get(key)
            if isinstance(value, str):
                m = BVID_RE.search(value)
                if m:
                    return m.group(0)
        return ""

    def send_msg(self, receiver_uid: str, content: str) -> None:
        status, body = self.raw_send_msg(receiver_uid, content)
        if status != 200:
            raise AppError(502, f"发送私信失败（HTTP {status}）：{body[:200]!r}")
        try:
            payload = json.loads(body)
        except Exception as exc:
            raise AppError(
                502, f"发送私信返回非 JSON（HTTP {status}）：{body[:200]!r}"
            ) from exc
        if payload.get("code") != 0:
            raise AppError(
                502,
                f"发送私信失败：code={payload.get('code')} message={payload.get('message')}",
            )

    def raw_send_msg(self, receiver_uid: str, content: str) -> tuple[int, str]:
        csrf = self.cookie.get("bili_jct", "")
        data = {
            "msg[sender_uid]": self.robot_uid,
            "msg[receiver_id]": str(receiver_uid),
            "msg[receiver_type]": "1",
            "msg[msg_type]": "1",
            "msg[msg_status]": "0",
            "msg[content]": json.dumps({"content": content}, ensure_ascii=False),
            "msg[timestamp]": str(int(time.time())),
            "msg[new_face_version]": "0",
            "msg[dev_id]": str(uuid.uuid4()),
            "from_firework": "0",
            "build": "0",
            "mobi_app": "web",
            "csrf_token": csrf,
            "csrf": csrf,
        }
        headers = {
            "Referer": "https://message.bilibili.com/",
            "Origin": "https://message.bilibili.com",
        }
        try:
            resp = self.client.post(SEND_MSG_URL, data=data, headers=headers)
        except Exception as exc:
            return 0, f"请求异常：{exc}"
        return resp.status_code, resp.text[:2000]

    def get_self_info(self) -> dict:
        data = self._get_json(NAV_URL)
        return data.get("data") or {}
