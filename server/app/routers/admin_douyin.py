"""管理端：抖音采集会话与能力开关。

和 B站 机器人 Cookie 并列放在「账号/Cookie」页里，各管各的凭据。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..admin_security import get_admin_user
from ..models import AdminConfig
from ..services import config_store
from ..services.douyin_provider import DouyinProvider

router = APIRouter(prefix="/api/admin", tags=["admin-douyin"])

# 会话健康用固定探针作品，避免每次换作品导致判断漂移
PROBE_AWEME_ID_KEY = "douyin_probe_aweme_id"
DEFAULT_PROBE_AWEME_ID = "7685688911658323392"


class DouyinCookiePayload(BaseModel):
    cookie: str = ""
    probe_aweme_id: str | None = None


class DouyinSwitchPayload(BaseModel):
    parse: bool | None = None
    video: bool | None = None
    audio: bool | None = None
    images: bool | None = None


class DouyinNodePayload(BaseModel):
    node: str = Field(pattern="^(tencent|home)$")


class DouyinNoteApiPayload(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    api_key: str | None = None
    wait_seconds: int | None = Field(default=None, ge=1, le=30)


def _note_api_view(db: Session) -> dict:
    cfg = config_store.douyin_note_api_config(db)
    return {
        "enabled": cfg["enabled"],
        "configured": bool(cfg["base_url"] and cfg["api_key"]),
        "base_url": cfg["base_url"],
        "wait_seconds": cfg["wait_seconds"],
    }


def probe_aweme_id(db: Session) -> str:
    row = db.query(AdminConfig).filter(AdminConfig.key == PROBE_AWEME_ID_KEY).first()
    return (row.value if row and row.value else "") or DEFAULT_PROBE_AWEME_ID


def _health(db: Session) -> dict:
    """一次探活：判据是响应体字节数，不是状态码。"""
    provider = DouyinProvider(cookie=config_store.douyin_cookie(db))
    try:
        return provider.probe(probe_aweme_id(db))
    finally:
        provider.close()


@router.get("/douyin/session")
def douyin_session(
    probe: int = 0,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """probe=1 时才真的打一次抖音，平时只读配置，避免每次开页面都触发风控。"""
    configured = config_store.douyin_cookie_configured(db)
    data = {
        "configured": configured,
        "cookie_length": len(config_store.douyin_cookie(db)),
        "parse_node": config_store.douyin_parse_node(db),
        "probe_aweme_id": probe_aweme_id(db),
        "switches": config_store.douyin_switches(db),
        "note_api": _note_api_view(db),
    }
    if probe:
        data["probe"] = _health(db) if configured else {
            "ok": False, "status_code": 0, "bytes": 0, "error": "还没配置 Cookie"
        }
    return data


@router.post("/douyin/cookie")
def update_douyin_cookie(
    payload: DouyinCookiePayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if payload.cookie.strip():
        config_store.set_douyin_cookie(db, payload.cookie)
    if payload.probe_aweme_id:
        row = db.query(AdminConfig).filter(AdminConfig.key == PROBE_AWEME_ID_KEY).first()
        if row is None:
            db.add(AdminConfig(key=PROBE_AWEME_ID_KEY, value=payload.probe_aweme_id.strip()))
        else:
            row.value = payload.probe_aweme_id.strip()
    db.commit()
    return {
        "configured": config_store.douyin_cookie_configured(db),
        "probe": _health(db) if config_store.douyin_cookie_configured(db) else None,
    }


@router.post("/douyin/probe")
def douyin_probe(
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    if not config_store.douyin_cookie_configured(db):
        return {"ok": False, "status_code": 0, "bytes": 0, "error": "还没配置 Cookie"}
    return _health(db)


@router.put("/douyin/switches")
def update_douyin_switches(
    payload: DouyinSwitchPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    config_store.set_douyin_switches(db, **patch)
    db.commit()
    return config_store.douyin_switches(db)


@router.put("/douyin/node")
def update_douyin_node(
    payload: DouyinNodePayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    config_store.set_douyin_parse_node(db, payload.node)
    db.commit()
    return {"node": config_store.douyin_parse_node(db)}


@router.put("/douyin/note-api")
def update_douyin_note_api(
    payload: DouyinNoteApiPayload,
    _: str = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    config_store.set_douyin_note_api_config(
        db,
        enabled=payload.enabled,
        base_url=payload.base_url,
        api_key=payload.api_key,
        wait_seconds=payload.wait_seconds,
    )
    db.commit()
    return _note_api_view(db)
