from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import config_store

router = APIRouter(tags=["meta"])


@router.get("/api/config/public")
def public_config(db: Session = Depends(get_db)):
    """小程序公开 UI 配置（无需登录），用于按开关控制前端展示。"""
    return {
        "robot_guide": config_store.robot_guide_enabled(db),
        "share": config_store.share_enabled(db),
    }
