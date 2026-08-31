import re
from dataclasses import dataclass

import httpx

from ..errors import AppError
from .wbi import WbiSigner

BVID_RE = re.compile(r"BV[0-9A-Za-z]{10}")
B23_RE = re.compile(r"https?://b23\.tv/[0-9A-Za-z]+")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class VideoMeta:
    bvid: str
    title: str
    cover_url: str
    up_name: str
    partition: str
    desc: str
    duration: int
    pubdate: int
    cid: int


class BiliClient:
    def __init__(self) -> None:
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=10,
            headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
        )

    def close(self) -> None:
        self.client.close()

    def resolve_bvid(self, url: str) -> str:
        text = (url or "").strip()
        if B23_RE.search(text):
            return self._resolve_short(text)
        m = BVID_RE.search(text)
        if m:
            return m.group(0)
        raise AppError(400, "不是有效的 B站视频链接或 BV 号")

    def _resolve_short(self, text: str) -> str:
        short = B23_RE.search(text).group(0)
        try:
            resp = self.client.get(short, follow_redirects=False)
        except Exception as exc:
            raise AppError(502, "解析短链失败") from exc
        if resp.status_code in (301, 302, 303, 307, 308):
            target = resp.headers.get("location", "")
        else:
            target = str(resp.url)
        m = BVID_RE.search(target)
        if not m:
            raise AppError(400, "短链未指向有效视频")
        return m.group(0)

    def get_video(self, bvid: str) -> VideoMeta:
        try:
            resp = self.client.get(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": bvid},
            )
            data = resp.json()
        except Exception as exc:
            raise AppError(502, "B站接口请求失败") from exc

        if data.get("code") != 0 or not data.get("data"):
            raise AppError(404, "视频不存在或已被删除")

        d = data["data"]
        pic = d.get("pic") or ""
        if pic.startswith("//"):
            pic = "https:" + pic
        owner = d.get("owner") or {}
        return VideoMeta(
            bvid=bvid,
            title=d.get("title") or "",
            cover_url=pic,
            up_name=owner.get("name") or "",
            partition=d.get("tname") or "",
            desc=d.get("desc") or "",
            duration=int(d.get("duration") or 0),
            pubdate=int(d.get("pubdate") or 0),
            cid=int(d.get("cid") or 0),
        )

    def get_tags(self, bvid: str) -> list[str]:
        try:
            resp = self.client.get(
                "https://api.bilibili.com/x/tag/archive/tags",
                params={"bvid": bvid},
            )
            data = resp.json()
        except Exception:
            return []

        if data.get("code") != 0 or not isinstance(data.get("data"), list):
            return []
        out: list[str] = []
        for item in data["data"]:
            if isinstance(item, dict):
                name = item.get("tag_name") or item.get("tag")
                if name:
                    out.append(str(name))
        return out

    def download_cover(self, url: str) -> tuple[bytes, str]:
        if not url:
            raise AppError(502, "封面地址为空")
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except Exception as exc:
            raise AppError(502, "封面下载失败") from exc
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return resp.content, content_type

    def get_subtitles(self, bvid: str, cid: int) -> list[dict]:
        """拉取视频字幕，返回 [{t: 秒, text: 内容}, ...]。失败或无字幕时返回空列表。"""
        if not cid:
            return []
        try:
            params = WbiSigner(self.client).sign({"bvid": bvid, "cid": str(cid)})
            resp = self.client.get("https://api.bilibili.com/x/player/wbi/v2", params=params)
            data = resp.json()
        except Exception:
            return []

        subtitles = (((data.get("data") or {}).get("subtitle") or {}).get("subtitles")) or []
        if not subtitles:
            return []

        target = None
        for item in subtitles:
            if isinstance(item, dict) and (item.get("lan") or "").lower() in ("zh-cn", "zh", "ai-zh"):
                target = item
                break
        if target is None:
            target = subtitles[0]

        url = target.get("subtitle_url") if isinstance(target, dict) else None
        if not url:
            return []
        if url.startswith("//"):
            url = "https:" + url

        try:
            r = self.client.get(url)
            payload = r.json()
        except Exception:
            return []

        out: list[dict] = []
        for item in payload.get("body") or []:
            if not isinstance(item, dict):
                continue
            t = item.get("from")
            text = item.get("content")
            if t is None or not text:
                continue
            out.append({"t": int(float(t)), "text": str(text)})
        return out
