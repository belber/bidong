# 解析结果页（字段化 + 媒体下载）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把解析结果页改成字段化清单，并新增三档媒体下载（有水印视频 / 无水印视频 / 纯音频）与文本导出。

**Architecture:** 后端先扩展解析返回字段和新增四个接口（media-options / download / danmaku / export），媒体下载走中转流式、按需取链、不落库；前端随后重写 result 页对接到新接口。

**Tech Stack:** FastAPI + SQLAlchemy + httpx + pytest/respx（后端）；微信原生小程序 WXML/WXSS/JS（前端）。

---

## Phase A：后端（TDD 先行）

### Task 1: 三个媒体下载开关

**Files:**
- Modify: `server/app/config.py`
- Modify: `server/.env.example`
- Test: `server/tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
from app.config import Settings


def test_media_switches_default_off(monkeypatch):
    for key in ("ENABLE_WATERMARKED_VIDEO", "ENABLE_CLEAN_VIDEO", "ENABLE_AUDIO"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.enable_watermarked_video is False
    assert s.enable_clean_video is False
    assert s.enable_audio is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: FAIL（`Settings` 没有这三个属性）

- [ ] **Step 3: 在 `Settings` 增加三个字段**

在 `server/app/config.py` 的 `Settings` 类里（`wechat_secret` 之后）加：

```python
    enable_watermarked_video: bool = False
    enable_clean_video: bool = False
    enable_audio: bool = False
```

并在 `server/.env.example` 末尾追加：

```
# 媒体下载开关（默认关闭，审核期间保持 false）
ENABLE_WATERMARKED_VIDEO=false
ENABLE_CLEAN_VIDEO=false
ENABLE_AUDIO=false
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/config.py server/.env.example server/tests/test_config.py
git commit -m "feat: 增加三档媒体下载开关"
```

### Task 2: 新增解析返回 schema

**Files:**
- Modify: `server/app/schemas.py`
- Test: `server/tests/test_schemas.py`

- [ ] **Step 1: 写失败测试**

```python
from app.schemas import MediaAvailability, ParseResult, VideoStats


def test_parse_result_defaults():
    r = ParseResult(
        id=1, bvid="BV1xx411c7mD", title="t", up_name="u", partition="p",
        duration=1, pubdate=1, cover_url="c", desc="", source_url="s",
        source="local", tags=[], collected_at=1, month="2026-09",
    )
    assert r.stats == VideoStats()
    assert r.danmaku_count == 0
    assert r.media == MediaAvailability()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_schemas.py -q`
Expected: FAIL（`ParseResult` 没有 `stats` / `danmaku_count` / `media`）

- [ ] **Step 3: 新增 schema**

在 `server/app/schemas.py` 顶部 `CardOut` 之前加：

```python
class VideoStats(BaseModel):
    like: int = 0
    reply: int = 0
    favorite: int = 0
    coin: int = 0


class MediaAvailability(BaseModel):
    watermarked: bool = False
    clean: bool = False
    audio: bool = False


class MediaOption(BaseModel):
    qn: int
    label: str
```

并把 `ParseResult` 改为：

```python
class ParseResult(CardOut):
    subtitles: list[SubtitleLine] = Field(default_factory=list)
    stats: VideoStats = Field(default_factory=VideoStats)
    danmaku_count: int = 0
    media: MediaAvailability = Field(default_factory=MediaAvailability)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_schemas.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/schemas.py server/tests/test_schemas.py
git commit -m "feat: 解析结果 schema 增加统计/弹幕/媒体开关字段"
```

### Task 3: `get_video` 返回统计与弹幕条数

**Files:**
- Modify: `server/app/services/bilibili.py`
- Modify: `server/tests/helpers.py`
- Test: `server/tests/test_bilibili.py`

- [ ] **Step 1: 写失败测试**

在 `server/tests/test_bilibili.py` 的 `test_get_video_maps_fields` 里，把 view 返回体的 `data` 增加：

```python
                    "stat": {
                        "like": 100,
                        "reply": 20,
                        "favorite": 300,
                        "coin": 40,
                        "danmaku": 500,
                    },
```

并在断言末尾追加：

```python
    assert meta.like == 100
    assert meta.reply == 20
    assert meta.favorite == 300
    assert meta.coin == 40
    assert meta.danmaku == 500
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_bilibili.py::test_get_video_maps_fields -q`
Expected: FAIL（`VideoMeta` 没有这些字段）

- [ ] **Step 3: 扩展 `VideoMeta` 并解析 `stat`**

在 `server/app/services/bilibili.py`：

```python
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
    like: int = 0
    reply: int = 0
    favorite: int = 0
    coin: int = 0
    danmaku: int = 0
```

`get_video` 里 `d = data["data"]` 之后取 `stat = d.get("stat") or {}`，返回值追加：

```python
            like=int(stat.get("like") or 0),
            reply=int(stat.get("reply") or 0),
            favorite=int(stat.get("favorite") or 0),
            coin=int(stat.get("coin") or 0),
            danmaku=int(stat.get("danmaku") or 0),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_bilibili.py::test_get_video_maps_fields -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/services/bilibili.py server/tests/test_bilibili.py
git commit -m "feat: 解析 view 接口的统计数与弹幕条数"
```

### Task 4: `BiliClient` 播放地址解析（durl / DASH）

**Files:**
- Modify: `server/app/services/bilibili.py`
- Test: `server/tests/test_bilibili.py`

- [ ] **Step 1: 写失败测试**

```python
@respx.mock
def test_get_playurl_dash_and_durl():
    respx.get("https://api.bilibili.com/x/web-interface/nav").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/0123456789abcdef0123456789abcdef.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/fedcba9876543210fedcba9876543210.png",
                    }
                },
            },
        )
    )
    respx.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*fnval=16.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "dash": {
                        "video": [
                            {"id": 64, "baseUrl": "https://v.example.com/v.m4s", "backupUrl": ["https://v.example.com/v2.m4s"]},
                        ],
                        "audio": [
                            {"id": 30280, "baseUrl": "https://a.example.com/a.m4s", "backupUrl": []},
                        ],
                    }
                },
            },
        )
    )
    respx.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*fnval=1(?![0-9]).*").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "quality": 32,
                    "durl": [{"url": "https://d.example.com/d.mp4", "backup_url": ["https://d.example.com/d2.mp4"]}],
                },
            },
        )
    )

    client = BiliClient()
    dash = client.get_playurl("BV1xx411c7mD", 987654, fnval=16)
    assert dash["video"][0]["qn"] == 64
    assert dash["video"][0]["label"] == "720P"
    assert dash["video"][0]["url"] == "https://v.example.com/v.m4s"
    assert dash["audio"][0]["qn"] == 30280

    durl = client.get_playurl("BV1xx411c7mD", 987654, fnval=1)
    assert durl["durl"][0]["qn"] == 32
    assert durl["durl"][0]["url"] == "https://d.example.com/d.mp4"
    client.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_bilibili.py::test_get_playurl_dash_and_durl -q`
Expected: FAIL（没有 `get_playurl`）

- [ ] **Step 3: 实现播放地址解析**

在 `server/app/services/bilibili.py` 顶部加：

```python
_QN_LABELS = {
    16: "360P", 32: "480P", 64: "720P", 80: "1080P",
    112: "1080P+", 116: "1080P60", 120: "4K", 125: "HDR",
    126: "杜比视界", 127: "8K",
    30216: "64K", 30232: "132K", 30280: "192K", 30250: "杜比", 30251: "Hi-Res",
}


def _qn_label(qn: int) -> str:
    return _QN_LABELS.get(qn, str(qn))
```

在 `BiliClient` 类里加：

```python
    def _normalize_stream(self, item: dict) -> dict:
        url = item.get("baseUrl") or item.get("base_url") or ""
        backups = item.get("backupUrl") or item.get("backup_url") or []
        if isinstance(backups, str):
            backups = [backups]
        qn = int(item.get("id") or 0)
        return {
            "qn": qn,
            "label": _qn_label(qn),
            "url": url,
            "backup_urls": [u for u in backups if u],
        }

    def get_playurl(self, bvid: str, cid: int, fnval: int = 16) -> dict:
        if not cid:
            return {"durl": [], "video": [], "audio": []}
        try:
            params = WbiSigner(self.client).sign(
                {"bvid": bvid, "cid": str(cid), "fnval": str(fnval), "fourk": "1"}
            )
            resp = self.client.get(
                "https://api.bilibili.com/x/player/wbi/playurl", params=params
            )
            data = resp.json()
        except Exception as exc:
            raise AppError(502, "获取播放地址失败") from exc
        if data.get("code") != 0 or not data.get("data"):
            raise AppError(502, "获取播放地址失败")

        d = data["data"]
        dash = d.get("dash") or {}
        durl = d.get("durl") or []
        durl_streams = []
        if durl:
            first = durl[0] or {}
            qn = int(d.get("quality") or 0)
            durl_streams = [{
                "qn": qn,
                "label": _qn_label(qn),
                "url": first.get("url") or "",
                "backup_urls": [u for u in (first.get("backup_url") or []) if u],
            }]
        return {
            "durl": durl_streams,
            "video": [self._normalize_stream(i) for i in (dash.get("video") or [])],
            "audio": [self._normalize_stream(i) for i in (dash.get("audio") or [])],
        }

    def get_durl(self, bvid: str, cid: int) -> list[dict]:
        return self.get_playurl(bvid, cid, fnval=1)["durl"]

    def get_dash_video(self, bvid: str, cid: int) -> list[dict]:
        return self.get_playurl(bvid, cid, fnval=16)["video"]

    def get_dash_audio(self, bvid: str, cid: int) -> list[dict]:
        return self.get_playurl(bvid, cid, fnval=16)["audio"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_bilibili.py::test_get_playurl_dash_and_durl -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/services/bilibili.py server/tests/test_bilibili.py
git commit -m "feat: 解析播放地址（durl 与 DASH 音视频轨）"
```

### Task 5: `get_danmaku`

**Files:**
- Modify: `server/app/services/bilibili.py`
- Test: `server/tests/test_bilibili.py`

- [ ] **Step 1: 写失败测试**

```python
@respx.mock
def test_get_danmaku():
    respx.get("https://comment.bilibili.com/987654.xml").mock(
        return_value=httpx.Response(200, text="<i><d p='1,1,25'>哈哈</d></i>")
    )
    client = BiliClient()
    assert client.get_danmaku(987654).startswith("<i>")
    client.close()


@respx.mock
def test_get_danmaku_empty_on_error():
    respx.get("https://comment.bilibili.com/987654.xml").mock(
        return_value=httpx.Response(404)
    )
    client = BiliClient()
    assert client.get_danmaku(987654) == ""
    client.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_bilibili.py::test_get_danmaku -q`
Expected: FAIL（没有 `get_danmaku`）

- [ ] **Step 3: 实现**

在 `BiliClient` 类里加：

```python
    def get_danmaku(self, cid: int) -> str:
        if not cid:
            return ""
        try:
            resp = self.client.get(
                f"https://comment.bilibili.com/{cid}.xml",
                headers={"Referer": "https://www.bilibili.com/"},
            )
            resp.raise_for_status()
            return resp.text
        except Exception:
            return ""
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_bilibili.py::test_get_danmaku tests/test_bilibili.py::test_get_danmaku_empty_on_error -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/services/bilibili.py server/tests/test_bilibili.py
git commit -m "feat: 读取弹幕 XML"
```

### Task 6: `collect_video` 返回统计与弹幕条数

**Files:**
- Modify: `server/app/services/collect.py`
- Modify: `server/app/routers/parse.py`
- Test: `server/tests/test_parse.py`

- [ ] **Step 1: 写失败测试**

在 `server/tests/test_parse.py` 的 `test_parse_auto_collect_and_idempotent` 里，`first = resp.json()` 后追加：

```python
    assert first["stats"] == {"like": 0, "reply": 0, "favorite": 0, "coin": 0}
    assert first["danmaku_count"] == 0
    assert first["media"] == {"watermarked": False, "clean": False, "audio": False}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_parse.py::test_parse_auto_collect_and_idempotent -q`
Expected: FAIL（返回体没有 `stats` / `danmaku_count` / `media`）

- [ ] **Step 3: 改 `collect_video` 与 `parse` 路由**

把 `server/app/services/collect.py` 的 `collect_video` 改成返回四元组。现有 `return existing, subtitles` 分支改为：

```python
        if existing is not None:
            meta = client.get_video(existing.bvid)
            subtitles = client.get_subtitles(existing.bvid, existing.cid)
            stats = {
                "like": meta.like,
                "reply": meta.reply,
                "favorite": meta.favorite,
                "coin": meta.coin,
            }
            return existing, subtitles, stats, meta.danmaku
```

函数末尾的 `return card, subtitles` 改为：

```python
    stats = {
        "like": meta.like,
        "reply": meta.reply,
        "favorite": meta.favorite,
        "coin": meta.coin,
    }
    return card, subtitles, stats, meta.danmaku
```

并把 `server/app/routers/parse.py` 改成：

```python
from ..config import settings
from ..schemas import MediaAvailability, ParseRequest, ParseResult, SubtitleLine, VideoStats


@router.post("/api/parse", response_model=ParseResult)
def parse(
    payload: ParseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card, subtitles, stats, danmaku_count = collect_video(db, user, payload.url)
    out = card_to_out(card)
    lines = [SubtitleLine(t=s["t"], text=s["text"]) for s in subtitles[:500]]
    return ParseResult(
        **out.model_dump(),
        subtitles=lines,
        stats=VideoStats(**stats),
        danmaku_count=danmaku_count,
        media=MediaAvailability(
            watermarked=settings.enable_watermarked_video,
            clean=settings.enable_clean_video,
            audio=settings.enable_audio,
        ),
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_parse.py -q`
Expected: PASS（`mock_bili` 未提供 `stat`，统计为 0）

- [ ] **Step 5: 提交**

```bash
git add server/app/services/collect.py server/app/routers/parse.py server/tests/test_parse.py
git commit -m "feat: 解析流程返回统计数与弹幕条数"
```

### Task 7: media-options 与 download 中转接口

**Files:**
- Create: `server/app/routers/media.py`
- Test: `server/tests/test_media.py`

- [ ] **Step 1: 写失败测试**

```python
import httpx
import respx

from helpers import BVID, mock_bili


def _playurl_video(qn=64):
    return httpx.Response(
        200,
        json={
            "code": 0,
            "data": {
                "dash": {
                    "video": [
                        {"id": qn, "baseUrl": "https://v.example.com/v.m4s", "backupUrl": []}
                    ],
                    "audio": [
                        {"id": 30280, "baseUrl": "https://a.example.com/a.m4s", "backupUrl": []}
                    ],
                }
            },
        },
    )


def _mock_playurl():
    respx.get(url__regex=r"https://api\.bilibili\.com/x/player/wbi/playurl.*fnval=16.*").mock(
        return_value=_playurl_video()
    )
    respx.get("https://v.example.com/v.m4s").mock(
        return_value=httpx.Response(200, content=b"video-bytes")
    )
    respx.get("https://a.example.com/a.m4s").mock(
        return_value=httpx.Response(200, content=b"audio-bytes")
    )


def _make_card(client, auth_headers):
    mock_bili()
    resp = client.post("/api/parse", json={"url": BVID}, headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()


@respx.mock
def test_media_options_disabled_by_default(client, auth_headers, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "enable_clean_video", False)
    card = _make_card(client, auth_headers)
    resp = client.get(
        f"/api/cards/{card['id']}/media-options",
        params={"kind": "clean"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


@respx.mock
def test_media_options_and_download(client, auth_headers, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "enable_clean_video", True)
    _mock_playurl()
    card = _make_card(client, auth_headers)

    opts = client.get(
        f"/api/cards/{card['id']}/media-options",
        params={"kind": "clean"},
        headers=auth_headers,
    )
    assert opts.status_code == 200
    assert opts.json() == [{"qn": 64, "label": "720P"}]

    resp = client.get(
        f"/api/cards/{card['id']}/download",
        params={"kind": "clean", "qn": 64},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.content == b"video-bytes"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_media.py -q`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 创建 media 路由**

```python
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError
from ..models import User, VideoCard
from ..schemas import MediaOption
from ..services.bilibili import BiliClient, UA

router = APIRouter(tags=["media"])

MEDIA_HEADERS = {"Referer": "https://www.bilibili.com/", "User-Agent": UA}


def _get_owned_card(db: Session, user: User, card_id: int) -> VideoCard:
    card = (
        db.query(VideoCard)
        .filter(VideoCard.id == card_id, VideoCard.user_id == user.id)
        .first()
    )
    if card is None:
        raise AppError(404, "卡片不存在")
    return card


def _require_enabled(kind: str) -> None:
    if kind == "watermarked" and not settings.enable_watermarked_video:
        raise AppError(403, "该下载未开放")
    if kind == "clean" and not settings.enable_clean_video:
        raise AppError(403, "该下载未开放")
    if kind == "audio" and not settings.enable_audio:
        raise AppError(403, "该下载未开放")


def _streams(client: BiliClient, card: VideoCard, kind: str) -> list[dict]:
    if kind == "watermarked":
        return client.get_durl(card.bvid, card.cid)
    if kind == "clean":
        return client.get_dash_video(card.bvid, card.cid)
    if kind == "audio":
        return client.get_dash_audio(card.bvid, card.cid)
    raise AppError(400, "未知下载类型")


@router.get("/api/cards/{card_id}/media-options", response_model=list[MediaOption])
def media_options(
    card_id: int,
    kind: str = "watermarked",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_enabled(kind)
    card = _get_owned_card(db, user, card_id)
    client = BiliClient()
    try:
        streams = _streams(client, card, kind)
    finally:
        client.close()
    return [MediaOption(qn=s["qn"], label=s["label"]) for s in streams if s["qn"]]


@router.get("/api/cards/{card_id}/download")
def download(
    card_id: int,
    kind: str = "watermarked",
    qn: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_enabled(kind)
    card = _get_owned_card(db, user, card_id)
    client = BiliClient()
    try:
        streams = _streams(client, card, kind)
        if qn is not None:
            streams = [s for s in streams if s["qn"] == qn]
        if not streams:
            raise AppError(404, "无可用清晰度")
        url = streams[0]["url"] or (streams[0]["backup_urls"][0] if streams[0]["backup_urls"] else "")
        if not url:
            raise AppError(502, "无可用下载地址")
    finally:
        client.close()

    media_type = "audio/mp4" if kind == "audio" else "video/mp4"
    suffix = "m4a" if kind == "audio" else "mp4"

    def gen():
        with httpx.stream("GET", url, headers=MEDIA_HEADERS, timeout=30, follow_redirects=True) as resp:
            resp.raise_for_status()
            yield from resp.iter_bytes(chunk_size=65536)

    return StreamingResponse(
        gen(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{card.bvid}_{kind}.{suffix}"'},
    )
```

注：计划里接口参数名用 `kind`，前端调用时也统一用 `kind`（避免与 Python 内置 `type` 冲突）。

- [ ] **Step 4: 在 main.py 注册路由**

`server/app/main.py` 顶部 import 里加 `from .routers import auth, cards, media, parse, tags`，`app.include_router` 循环改为 `for router in (auth.router, parse.router, cards.router, tags.router, media.router):`。

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_media.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add server/app/routers/media.py server/app/main.py server/tests/test_media.py
git commit -m "feat: 媒体清晰度与中转下载接口"
```

### Task 8: 弹幕与文本导出接口

**Files:**
- Modify: `server/app/routers/media.py`
- Test: `server/tests/test_media.py`（追加）

- [ ] **Step 1: 写失败测试**

在 `server/tests/test_media.py` 追加：

```python
@respx.mock
def test_danmaku_and_export(client, auth_headers):
    respx.get("https://comment.bilibili.com/987654.xml").mock(
        return_value=httpx.Response(200, text="<i><d>哈哈</d></i>")
    )
    card = _make_card(client, auth_headers)

    dm = client.get(f"/api/cards/{card['id']}/danmaku", headers=auth_headers)
    assert dm.status_code == 200
    assert "哈哈" in dm.text

    txt = client.get(f"/api/cards/{card['id']}/export", params={"kind": "txt"}, headers=auth_headers)
    assert txt.status_code == 200
    assert "测试标题" in txt.text
    assert "第一句" in txt.text
    assert "哈哈" in txt.text

    srt = client.get(f"/api/cards/{card['id']}/export", params={"kind": "srt"}, headers=auth_headers)
    assert srt.status_code == 200
    assert "00:00:05,000 --> 00:00:07,000" in srt.text
    assert "第一句" in srt.text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_media.py::test_danmaku_and_export -q`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 在 media.py 增加两个接口与文本生成函数**

顶部 import 加 `from fastapi.responses import Response`。

在文件底部加：

```python
def _fmt_srt_time(t: int) -> str:
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d},000"


def _to_srt(subs: list[dict]) -> str:
    out = []
    for i, s in enumerate(subs, 1):
        out.append(str(i))
        out.append(f"{_fmt_srt_time(s['t'])} --> {_fmt_srt_time(s['t'] + 2)}")
        out.append(s["text"])
        out.append("")
    return "\n".join(out)


def _to_txt(card: VideoCard, subs: list[dict], danmaku: str) -> str:
    lines = [f"标题：{card.title}", f"UP主：{card.up_name}", f"链接：{card.source_url}"]
    if card.partition:
        lines.append(f"分区：{card.partition}")
    if card.tags:
        lines.append("标签：" + " ".join("#" + t.name for t in card.tags))
    if card.desc:
        lines.append(f"简介：{card.desc}")
    if subs:
        lines.append("\n【字幕】")
        lines.extend(f"{_fmt_srt_time(s['t'])} {s['text']}" for s in subs)
    if danmaku:
        lines.append("\n【弹幕】")
        lines.append(danmaku)
    return "\n".join(lines)


@router.get("/api/cards/{card_id}/danmaku")
def danmaku(
    card_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = _get_owned_card(db, user, card_id)
    client = BiliClient()
    try:
        text = client.get_danmaku(card.cid)
    finally:
        client.close()
    return Response(
        content=text or "",
        media_type="application/xml; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{card.bvid}.xml"'},
    )


@router.get("/api/cards/{card_id}/export")
def export(
    card_id: int,
    kind: str = "txt",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = _get_owned_card(db, user, card_id)
    client = BiliClient()
    try:
        subs = client.get_subtitles(card.bvid, card.cid)
        if kind == "srt":
            content = _to_srt(subs)
            filename = f"{card.bvid}.srt"
            media_type = "text/plain; charset=utf-8"
        else:
            danmaku_text = client.get_danmaku(card.cid)
            content = _to_txt(card, subs, danmaku_text)
            filename = f"{card.bvid}.txt"
            media_type = "text/plain; charset=utf-8"
    finally:
        client.close()
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_media.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/routers/media.py server/tests/test_media.py
git commit -m "feat: 弹幕与文本导出接口"
```

### Task 9: 后端全量回归

- [ ] **Step 1: 跑全部后端测试**

Run: `.venv/bin/python -m pytest -q`
Expected: 全部 PASS

---

## Phase B：前端

### Task 10: api.js 增加下载/导出辅助函数

**Files:**
- Modify: `miniprogram/utils/api.js`

- [ ] **Step 1: 加文件下载辅助函数**

在 `module.exports` 前加：

```javascript
function fileDownload(path) {
  return ensureToken().then((token) => ({
    url: baseUrl() + path,
    header: token ? { Authorization: 'Bearer ' + token } : {}
  }));
}
```

在 `module.exports` 里追加：

```javascript
  mediaOptions(id, kind) {
    return request('GET', '/api/cards/' + id + '/media-options?kind=' + encodeURIComponent(kind));
  },
  download(id, kind, qn) {
    const suffix = qn ? '&qn=' + qn : '';
    return fileDownload('/api/cards/' + id + '/download?kind=' + kind + suffix);
  },
  danmaku(id) {
    return fileDownload('/api/cards/' + id + '/danmaku');
  },
  exportFile(id, kind) {
    return fileDownload('/api/cards/' + id + '/export?kind=' + kind);
  }
```

- [ ] **Step 2: 提交**

```bash
git add miniprogram/utils/api.js
git commit -m "feat: 前端增加媒体下载与导出 API"
```

### Task 11: 重写 result.js

**Files:**
- Modify: `miniprogram/pages/result/result.js`

- [ ] **Step 1: 替换 result.js 为字段化数据模型**

```javascript
const api = require('../../utils/api.js');
const { formatDuration, formatDateTime } = require('../../utils/format.js');

function toast(title) {
  wx.showToast({ title: title, icon: 'none' });
}

Page({
  data: {
    cardId: 0,
    bvid: '',
    sourceUrl: '',
    title: '',
    upName: '',
    pubText: '',
    tags: [],
    desc: '',
    stats: { like: 0, reply: 0, favorite: 0, coin: 0 },
    coverUrl: '',
    media: { watermarked: false, clean: false, audio: false },
    subtitles: [],
    subPreview: [],
    showAllSub: false,
    danmakuCount: 0
  },

  onLoad() {
    const r = getApp().globalData.pendingResult;
    if (!r) {
      toast('暂无解析数据');
      return;
    }
    const subtitles = (r.subtitles || []).map((s) => ({
      t: s.t,
      text: s.text,
      timeText: formatDuration(s.t)
    }));
    this.setData({
      cardId: r.id,
      bvid: r.bvid,
      sourceUrl: r.source_url,
      title: r.title,
      upName: r.up_name,
      pubText: formatDateTime(r.pubdate),
      tags: r.tags || [],
      desc: r.desc,
      stats: r.stats || { like: 0, reply: 0, favorite: 0, coin: 0 },
      coverUrl: r.cover_url,
      media: r.media || { watermarked: false, clean: false, audio: false },
      danmakuCount: r.danmaku_count || 0,
      subtitles,
      subPreview: subtitles.slice(0, 5)
    });
  },

  copy(field) {
    const v = this.data[field];
    if (!v) {
      toast('没有可复制的内容');
      return;
    }
    const text = Array.isArray(v) ? v.map((t) => '#' + t).join(' ') : String(v);
    wx.setClipboardData({ data: text, success() { toast('已复制'); } });
  },

  onCopyTag(e) {
    this.copy(e.currentTarget.dataset.field);
  },

  onPreviewCover() {
    if (this.data.coverUrl) {
      wx.previewImage({ urls: [this.data.coverUrl] });
    }
  },

  onSaveCover() {
    const url = this.data.coverUrl;
    if (!url) { return; }
    wx.downloadFile({
      url,
      success(res) {
        if (res.statusCode !== 200) { toast('下载失败'); return; }
        wx.saveImageToPhotosAlbum({
          filePath: res.tempFilePath,
          success() { toast('已保存到相册'); },
          fail() { toast('保存失败'); }
        });
      },
      fail() { toast('下载失败'); }
    });
  },

  onDownloadVideo(e) {
    const kind = e.currentTarget.dataset.kind;
    api.mediaOptions(this.data.cardId, kind).then((options) => {
      if (!options.length) {
        toast('无可用清晰度');
        return;
      }
      wx.showActionSheet({
        itemList: options.map((o) => o.label),
        success: (res) => {
          const chosen = options[res.tapIndex];
          api.download(this.data.cardId, kind, chosen.qn).then(({ url, header }) => {
            this.downloadToAlbum(url, header);
          }).catch(() => toast('下载失败'));
        }
      });
    }).catch(() => toast('获取清晰度失败'));
  },

  downloadToAlbum(url, header) {
    wx.downloadFile({
      url,
      header,
      success(res) {
        if (res.statusCode !== 200) { toast('下载失败'); return; }
        wx.saveVideoToPhotosAlbum({
          filePath: res.tempFilePath,
          success() { toast('已保存到相册'); },
          fail() { toast('保存失败'); }
        });
      },
      fail() { toast('下载失败'); }
    });
  },

  onDownloadAudio() {
    api.download(this.data.cardId, 'audio').then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success(res) {
          if (res.statusCode !== 200) { toast('下载失败'); return; }
          wx.shareFileMessage({ filePath: res.tempFilePath });
        },
        fail() { toast('下载失败'); }
      });
    }).catch(() => toast('下载失败'));
  },

  onExport() {
    api.exportFile(this.data.cardId, 'txt').then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success(res) {
          if (res.statusCode !== 200) { toast('导出失败'); return; }
          wx.openDocument({ filePath: res.tempFilePath, fileType: 'txt' });
        },
        fail() { toast('导出失败'); }
      });
    }).catch(() => toast('导出失败'));
  },

  onToggleSub() {
    this.setData({ showAllSub: !this.data.showAllSub });
  },

  onCopySub() {
    const lines = this.data.subtitles.map((s) => s.timeText + ' ' + s.text);
    if (!lines.length) { toast('无字幕'); return; }
    wx.setClipboardData({ data: lines.join('\n'), success() { toast('已复制'); } });
  },

  onDownloadSrt() {
    api.exportFile(this.data.cardId, 'srt').then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success(res) {
          if (res.statusCode !== 200) { toast('导出失败'); return; }
          wx.openDocument({ filePath: res.tempFilePath, fileType: 'txt' });
        },
        fail() { toast('导出失败'); }
      });
    }).catch(() => toast('导出失败'));
  },

  onDownloadDanmaku() {
    api.danmaku(this.data.cardId).then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success(res) {
          if (res.statusCode !== 200) { toast('下载失败'); return; }
          wx.openDocument({ filePath: res.tempFilePath, fileType: 'txt' });
        },
        fail() { toast('下载失败'); }
      });
    }).catch(() => toast('下载失败'));
  },

  onOpenBili() {
    const appId = getApp().globalData.biliMiniProgramAppId;
    if (!appId) {
      toast('B站小程序 appId 尚未配置');
      return;
    }
    wx.navigateToMiniProgram({ appId, path: '/pages/video/video?bvid=' + this.data.bvid });
  }
});
```

- [ ] **Step 2: 提交**

```bash
git add miniprogram/pages/result/result.js
git commit -m "feat: 结果页字段化数据与下载逻辑"
```

### Task 12: 重写 result.wxml 与 result.wxss

**Files:**
- Modify: `miniprogram/pages/result/result.wxml`
- Modify: `miniprogram/pages/result/result.wxss`

- [ ] **Step 1: 替换 result.wxml**

```xml
<view class="page">
  <view class="top-actions">
    <button class="export" bindtap="onExport">下载解析结果.txt</button>
  </view>

  <view class="field">
    <text class="label">标题</text>
    <view class="content">{{title || '无标题'}}</view>
    <text class="op" bindtap="onCopyTag" data-field="title">复制</text>
  </view>

  <view class="field">
    <text class="label">up主</text>
    <view class="content">{{upName || '未知'}}</view>
    <text class="op" bindtap="onCopyTag" data-field="upName">复制</text>
  </view>

  <view class="field">
    <text class="label">发布时间</text>
    <view class="content">{{pubText || '未知'}}</view>
    <text class="op" bindtap="onCopyTag" data-field="pubText">复制</text>
  </view>

  <view class="field">
    <text class="label">标签</text>
    <view class="content">{{tags.length ? tags.join(' ') : '无标签'}}</view>
    <text class="op" bindtap="onCopyTag" data-field="tags">复制</text>
  </view>

  <view class="field">
    <text class="label">简介</text>
    <view class="content">{{desc || '无简介'}}</view>
    <text class="op" bindtap="onCopyTag" data-field="desc">复制</text>
  </view>

  <view class="field">
    <text class="label">统计</text>
    <view class="stats">
      <text>点赞 {{stats.like}}</text>
      <text>评论 {{stats.reply}}</text>
      <text>收藏 {{stats.favorite}}</text>
      <text>投币 {{stats.coin}}</text>
    </view>
  </view>

  <view class="field">
    <text class="label">封面</text>
    <view class="content">
      <image wx:if="{{coverUrl}}" class="cover" src="{{coverUrl}}" mode="aspectFill" bindtap="onPreviewCover" />
      <text wx:else>无封面</text>
    </view>
    <view class="ops">
      <text class="op" bindtap="onPreviewCover">预览</text>
      <text class="op" bindtap="onSaveCover">保存相册</text>
    </view>
  </view>

  <view class="field" wx:if="{{media.watermarked}}">
    <text class="label">有水印视频（含音频）</text>
    <view class="content">单文件流，下载即含音频</view>
    <text class="op" bindtap="onDownloadVideo" data-kind="watermarked">下载</text>
  </view>

  <view class="field" wx:if="{{media.clean}}">
    <text class="label">无水印视频（不含音频）</text>
    <view class="content">高清视频轨，不含音频</view>
    <text class="op" bindtap="onDownloadVideo" data-kind="clean">下载</text>
  </view>

  <view class="field" wx:if="{{media.audio}}">
    <text class="label">纯音频</text>
    <view class="content">音频轨</view>
    <text class="op" bindtap="onDownloadAudio">下载</text>
  </view>

  <view class="field">
    <text class="label">字幕</text>
    <view class="content" wx:if="{{subtitles.length}}">
      <view wx:for="{{showAllSub ? subtitles : subPreview}}" wx:key="t" class="sub">{{item.timeText}} {{item.text}}</view>
      <view class="ops">
        <text class="op" bindtap="onToggleSub">{{showAllSub ? '收起' : '查看全部'}}</text>
        <text class="op" bindtap="onCopySub">复制全文</text>
        <text class="op" bindtap="onDownloadSrt">下载 .srt</text>
      </view>
    </view>
    <view class="content" wx:else>无字幕</view>
  </view>

  <view class="field">
    <text class="label">弹幕</text>
    <view class="content">{{danmakuCount ? '共 ' + danmakuCount + ' 条' : '无弹幕'}}</view>
    <view class="ops" wx:if="{{danmakuCount}}">
      <text class="op" bindtap="onDownloadDanmaku">下载 .xml</text>
    </view>
  </view>

  <view class="field">
    <text class="label">评论正文</text>
    <view class="content muted">暂不支持（本期不做）</view>
  </view>

  <button class="bili" bindtap="onOpenBili">去 B站查看</button>
</view>
```

- [ ] **Step 2: 替换 result.wxss**

```css
.page { padding: 24rpx 28rpx 60rpx; background: #fff; min-height: 100vh; }
.top-actions { display: flex; justify-content: flex-end; margin-bottom: 8rpx; }
.export { margin: 0; padding: 10rpx 26rpx; font-size: 26rpx; color: #fb7299; background: #fff4f7; border-radius: 999rpx; }
.field { display: flex; align-items: flex-start; gap: 16rpx; padding: 24rpx 0; border-bottom: 1rpx solid #f3edf0; }
.label { flex: none; width: 140rpx; font-size: 26rpx; font-weight: 700; color: #2b1e23; }
.content { flex: 1; min-width: 0; font-size: 26rpx; color: #5a4a50; line-height: 1.5; }
.content.muted { color: #b7aab0; }
.op { flex: none; font-size: 24rpx; color: #fb7299; }
.ops { display: flex; flex-direction: column; align-items: flex-end; gap: 12rpx; }
.stats { display: flex; flex-wrap: wrap; gap: 8rpx 20rpx; }
.stats text { font-size: 24rpx; color: #5a4a50; }
.cover { width: 220rpx; height: 124rpx; border-radius: 12rpx; }
.sub { font-size: 24rpx; color: #5a4a50; line-height: 1.6; }
.bili { margin-top: 32rpx; color: #fff; background: #fb7299; border-radius: 999rpx; }
```

- [ ] **Step 3: 提交**

```bash
git add miniprogram/pages/result/result.wxml miniprogram/pages/result/result.wxss
git commit -m "feat: 结果页字段化布局与样式"
```

### Task 13: 前端手工联调清单

- [ ] 启动后端并打开三个开关验证：`ENABLE_WATERMARKED_VIDEO=true ENABLE_CLEAN_VIDEO=true ENABLE_AUDIO=true .venv/bin/python -m uvicorn app.main:app --port 8000`
- [ ] 在微信开发者工具里，粘贴 B站链接解析，确认字段顺序与空态
- [ ] 关闭一个开关重启后端，确认对应媒体行隐藏
- [ ] 分别点击三档下载与封面、字幕、弹幕、导出，确认落盘/分享行为
