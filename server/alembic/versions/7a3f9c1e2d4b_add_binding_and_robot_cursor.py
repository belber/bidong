"""add binding and robot_cursor

Revision ID: 7a3f9c1e2d4b
Revises: 6f8a29b8a86c
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a3f9c1e2d4b"
down_revision: Union[str, None] = "6f8a29b8a86c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "binding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("bili_uid", sa.String(length=32), nullable=False),
        sa.Column("activation_code", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("code_sent_at", sa.DateTime(), nullable=True),
        sa.Column("bound_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activation_code", name="uq_binding_activation_code"),
        sa.UniqueConstraint("bili_uid", name="uq_binding_bili_uid"),
    )
    op.create_table(
        "robot_cursor",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("last_id", sa.String(length=64), nullable=True),
        sa.Column("last_time", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", name="uq_robot_cursor_kind"),
    )


def downgrade() -> None:
    op.drop_table("robot_cursor")
    op.drop_table("binding")
