"""add session_id to download_event

Revision ID: 5b6c7d8e9f0a
Revises: 4a5b6c7d8e9f
Create Date: 2026-09-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5b6c7d8e9f0a"
down_revision: Union[str, None] = "4a5b6c7d8e9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "download_event",
        sa.Column("session_id", sa.String(length=40), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_download_event_session_id", "download_event", ["session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_download_event_session_id", table_name="download_event")
    op.drop_column("download_event", "session_id")
