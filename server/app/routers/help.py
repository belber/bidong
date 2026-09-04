from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import config_store

router = APIRouter(tags=["help"])


@router.get("/api/help/config")
def help_config(db: Session = Depends(get_db)):
    """帮助与反馈页配置（QQ 群号等），无需登录，供小程序公开读取。"""
    return config_store.get_help_config(db)
