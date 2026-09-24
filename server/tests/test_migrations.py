"""迁移链必须能在 SQLite 上从头跑通。

生产用 PostgreSQL，但本地开发库（`sqlite:///./var/bili.db`）走的是同一套 Alembic
迁移。PG 专有语法（ALTER COLUMN TYPE、改外键约束）会让本地库卡在中间某个版本，
于是"代码更新了、库没更新"这类 500 就会冒出来。
"""
import os
import subprocess
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]


def _alembic(tmp_path, *args):
    db_path = tmp_path / "migrate.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def test_alembic_upgrade_head_runs_on_sqlite(tmp_path):
    result = _alembic(tmp_path, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    current = _alembic(tmp_path, "current")
    assert current.returncode == 0, current.stderr
    head = _alembic(tmp_path, "heads").stdout.split()[0]
    assert head in current.stdout
