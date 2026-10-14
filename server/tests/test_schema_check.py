"""启动检查：结构落后要能被发现，而不是等到查询时才崩 no such column。"""

import logging

from sqlalchemy import create_engine, text

from app.schema_check import check_schema


def _engine_with_version(version: str | None):
    engine = create_engine("sqlite://")
    if version is None:
        return engine
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": version})
    return engine


def test_up_to_date_passes(db_engine):
    """建表用的是 Base.metadata，没有 alembic_version，所以这里直接造一个最新的。"""
    from app.schema_check import _head_revision

    engine = _engine_with_version(_head_revision())
    assert check_schema(engine) is True


def test_behind_reports_error(caplog):
    engine = _engine_with_version("8e3f4a5b6c7d")
    with caplog.at_level(logging.ERROR):
        assert check_schema(engine) is False
    assert "落后" in caplog.text
    assert "alembic upgrade head" in caplog.text


def test_uninitialized_reports_error(caplog):
    engine = _engine_with_version(None)
    with caplog.at_level(logging.ERROR):
        assert check_schema(engine) is False
    assert "还没初始化" in caplog.text
