"""启动时的表结构检查。

背景：开发模式下曾经用 `Base.metadata.create_all()` 建表，它只补「缺的表」，
不会补「缺的列」，也不会盖 alembic 的版本章。于是库会悄悄漂移：
表看着在，alembic 版本却停在旧位置，直到某次查询撞上 `no such column` 才炸。

这里改成只检查不建表：版本落后就大声报出来，明确告诉运维该跑什么。
"""

import logging
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)


def _head_revision() -> str | None:
    """取迁移脚本里的最新版本号。"""
    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    if not ini.exists():
        return None
    script = ScriptDirectory.from_config(Config(str(ini)))
    return script.get_current_head()


def _current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        try:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
        except Exception:  # noqa: BLE001 - 表不存在说明库还没初始化
            return None
    return row[0] if row else None


def check_schema(engine: Engine) -> bool:
    """返回 True 表示结构是最新的。落后或未初始化时打 ERROR，但不阻塞启动。"""
    head = _head_revision()
    if head is None:
        return True

    current = _current_revision(engine)
    if current == head:
        return True

    if current is None:
        logger.error(
            "数据库还没初始化。请先执行：cd server && .venv/bin/python -m alembic upgrade head"
        )
    else:
        logger.error(
            "数据库结构落后于代码（当前 %s，最新 %s）。请执行："
            "cd server && .venv/bin/python -m alembic upgrade head —— "
            "不跑迁移的话，用到新字段的接口会报 no such column。",
            current,
            head,
        )
    return False
