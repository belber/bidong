"""add last_follow_mtime to binding

Revision ID: c7d8e9f0a1b2
Revises: a5e6f7c8d9b0
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "a5e6f7c8d9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("binding", sa.Column("last_follow_mtime", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("binding", "last_follow_mtime")
