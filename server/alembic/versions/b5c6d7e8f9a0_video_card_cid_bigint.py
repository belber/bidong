"""video_card.cid 改 BIGINT

Revision ID: b5c6d7e8f9a0
Revises: a3b4c5d6e7f8
Create Date: 2026-09-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "video_card",
        "cid",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )


def downgrade() -> None:
    op.alter_column(
        "video_card",
        "cid",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )
