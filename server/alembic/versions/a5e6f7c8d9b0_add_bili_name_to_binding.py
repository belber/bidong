"""add bili_name to binding

Revision ID: a5e6f7c8d9b0
Revises: 7a3f9c1e2d4b
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5e6f7c8d9b0"
down_revision: Union[str, None] = "7a3f9c1e2d4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("binding", sa.Column("bili_name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("binding", "bili_name")
