"""add client env diagnostics to binding / visit_event

Revision ID: d3c4e5f6a7b8
Revises: c2b3d4e5f6a7
Create Date: 2026-10-25 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3c4e5f6a7b8"
down_revision: Union[str, None] = "c2b3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("binding", "visit_event"):
        op.add_column(
            table,
            sa.Column("env_version", sa.String(length=16), nullable=False, server_default=""),
        )
        op.add_column(
            table,
            sa.Column("api_base", sa.String(length=128), nullable=False, server_default=""),
        )


def downgrade() -> None:
    for table in ("binding", "visit_event"):
        op.drop_column(table, "api_base")
        op.drop_column(table, "env_version")
