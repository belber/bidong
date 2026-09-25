"""小主机（Hermes）上报「帅哥录屏」稿件出处。"""

import hmac

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import AppError
from ..services import config_store, repost_source

router = APIRouter(tags=["sources"])


@router.post("/api/sources/ingest")
async def ingest(request: Request, db: Session = Depends(get_db)):
    expected = config_store.source_ingest_token(db)
    if not expected:
        raise AppError(503, "上报接口未配置 token，请在管理后台设置")

    provided = request.headers.get("X-Ingest-Token", "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise AppError(401, "上报 token 不正确")

    try:
        raw = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise AppError(400, "请求体不是合法 JSON") from exc

    items = repost_source.normalize_payload(raw)
    return repost_source.upsert_items(db, items)
