"""add visit_event

Revision ID: 2e3f4a5b6c7d
Revises: 1d2e3f4a5b6c
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2e3f4a5b6c7d"
down_revision: Union[str, None] = "1d2e3f4a5b6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visit_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_visit_event_user_id", "visit_event", ["user_id"], unique=False)
    op.create_index("ix_visit_event_created_at", "visit_event", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_visit_event_created_at", table_name="visit_event")
    op.drop_index("ix_visit_event_user_id", table_name="visit_event")
    op.drop_table("visit_event")
