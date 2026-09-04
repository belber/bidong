"""add video_title to at_event

Revision ID: f2a1b3c4d5e6
Revises: e8f1c2d3a4b5
Create Date: 2026-09-03 23:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a1b3c4d5e6"
down_revision: Union[str, None] = "e8f1c2d3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("at_event", sa.Column("video_title", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("at_event", "video_title")
