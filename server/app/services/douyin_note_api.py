"""第三方抖音图文解析（DTK v5 兼容）。

只在移动端详情接口返回 ``images_base`` 或图文缺少图片时使用。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..errors import AppError
from . import config_store

SERVICE_MESSAGE = "管理员正在解决中，请稍后再试"


def _first_url(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return next((u for u in items if isinstance(u, str) and u.startswith("http")), "")


def _best_image_url(item: dict) -> str:
    candidates = []
    for value in (item.get("url"), *(item.get("urls") or [])):
        if isinstance(value, str) and value.startswith("http") and value not in candidates:
            candidates.append(value)
    if not candidates:
        return ""
    plain = [u for u in candidates if "~tplv" not in u]
    return (plain or candidates)[0]


def _epoch(value: Any) -> int:
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return 0


def dtk_content_to_detail(content: dict) -> dict:
    """DTK v5 归一化 Content → 本项目现有 aweme_detail 结构。"""
    if not isinstance(content, dict) or content.get("kind") != "image_album":
        raise AppError(
            422,
            "第三方返回的不是抖音图文作品",
            error_type="douyin_note_api_not_note",
        )
    media = content.get("media") or {}
    author = content.get("author") or {}
    stats = content.get("stats") or {}
    music = content.get("music") or {}
    covers = media.get("covers") or []
    cover_url = _first_url([
        c.get("url") for c in covers if isinstance(c, dict) and c.get("url")
    ])
    image_urls = []
    for item in media.get("images") or []:
        if not isinstance(item, dict):
            continue
        url = _best_image_url(item)
        if url:
            image_urls.append(url)
    if not image_urls:
        raise AppError(
            502,
            SERVICE_MESSAGE,
            error_type="douyin_note_api_no_images",
        )
    tags = [str(t) for t in (content.get("tags") or []) if str(t).strip()]
    return {
        "aweme_id": str(content.get("content_id") or ""),
        "aweme_type": 68,
        "desc": content.get("description") or content.get("title") or "",
        "create_time": _epoch(content.get("created_at")),
        "duration": int(content.get("duration_ms") or 0),
        "video": {
            "duration": int(content.get("duration_ms") or 0),
            "cover": {"url_list": [cover_url] if cover_url else []},
        },
        "images": [{"url_list": [url]} for url in image_urls],
        "music": {
            "play_url": {
                "url_list": [music["play_url"]] if music.get("play_url") else []
            }
        },
        "author": {
            "nickname": author.get("nickname") or "",
            "unique_id": author.get("unique_id") or "",
            "sec_uid": author.get("sec_uid") or author.get("uid") or "",
        },
        "statistics": {
            "digg_count": int(stats.get("digg_count") or 0),
            "comment_count": int(stats.get("comment_count") or 0),
            "collect_count": int(stats.get("collect_count") or 0),
            "share_count": int(stats.get("share_count") or 0),
        },
        "text_extra": [{"hashtag_name": tag} for tag in tags],
    }


class DtkNoteClient:
    """调用 DTK v5 的 parse/task API，返回可由现有解析器消费的详情。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        wait_seconds: int = 20,
        timeout: float = 35.0,
        poll_interval: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.wait_seconds = max(1, min(30, int(wait_seconds)))
        self.poll_interval = max(0.0, float(poll_interval))
        self._owns_client = client is None
        self.client = client or httpx.Client(follow_redirects=True, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _request(self, method: str, path: str, **kwargs) -> tuple[int, dict]:
        if not self.base_url or not self.api_key:
            raise AppError(
                502,
                SERVICE_MESSAGE,
                error_type="douyin_note_api_not_configured",
            )
        try:
            resp = self.client.request(
                method,
                self.base_url + path,
                headers={"X-API-Key": self.api_key},
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                502,
                SERVICE_MESSAGE,
                error_type="douyin_note_api_network",
            ) from exc
        if resp.status_code in (401, 403):
            raise AppError(
                502,
                SERVICE_MESSAGE,
                error_type="douyin_note_api_auth",
            )
        try:
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                502,
                SERVICE_MESSAGE,
                error_type="douyin_note_api_bad_response",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                502,
                SERVICE_MESSAGE,
                error_type="douyin_note_api_bad_response",
            )
        if body.get("success") is False:
            code = str((body.get("error") or {}).get("code") or "unknown")
            raise AppError(
                502,
                SERVICE_MESSAGE,
                error_type=f"douyin_note_api_{code.lower()}",
            )
        return resp.status_code, body

    def _task_content(self, task_id: str) -> dict:
        deadline = time.monotonic() + max(15, self.wait_seconds + 10)
        while time.monotonic() < deadline:
            _, body = self._request("GET", f"/api/v1/tasks/{task_id}")
            data = body.get("data") or {}
            if data.get("state") == "done":
                return data.get("data") or {}
            if data.get("state") == "failed":
                code = str((data.get("error") or {}).get("code") or "failed")
                raise AppError(
                    502,
                    SERVICE_MESSAGE,
                    error_type=f"douyin_note_api_{code.lower()}",
                )
            if self.poll_interval:
                time.sleep(self.poll_interval)
        raise AppError(
            502,
            SERVICE_MESSAGE,
            error_type="douyin_note_api_timeout",
        )

    def fetch_detail(self, aweme_id: str) -> dict:
        url = f"https://www.douyin.com/note/{aweme_id}"
        status, body = self._request(
            "POST",
            "/api/v1/parse",
            params={"wait": str(self.wait_seconds)},
            json={"url": url},
        )
        data = body.get("data") or {}
        if status == 202 or data.get("task_id"):
            task_id = str(data.get("task_id") or "")
            if not task_id:
                raise AppError(
                    502,
                    SERVICE_MESSAGE,
                    error_type="douyin_note_api_bad_response",
                )
            content = self._task_content(task_id)
        else:
            content = data
        return dtk_content_to_detail(content)


def build_note_fetcher(db: Session) -> DtkNoteClient | None:
    cfg = config_store.douyin_note_api_config(db)
    if not cfg["enabled"] or not cfg["base_url"] or not cfg["api_key"]:
        return None
    return DtkNoteClient(
        cfg["base_url"],
        cfg["api_key"],
        wait_seconds=cfg["wait_seconds"],
    )
