"""add video_title to parse_log

Revision ID: a3b4c5d6e7f8
Revises: f2a1b3c4d5e6
Create Date: 2026-09-04 00:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a1b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("parse_log", sa.Column("video_title", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("parse_log", "video_title")
