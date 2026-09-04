"""add admin tracking tables

Revision ID: e8f1c2d3a4b5
Revises: c7d8e9f0a1b2
Create Date: 2026-09-03 23:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f1c2d3a4b5"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "follow_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bili_uid", sa.String(length=32), nullable=False),
        sa.Column("bili_name", sa.String(length=128), nullable=False),
        sa.Column("mtime", sa.Integer(), nullable=False),
        sa.Column("sent_code", sa.Boolean(), nullable=False),
        sa.Column("bound", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bili_uid", "mtime", name="uq_follow_event_uid_mtime"),
    )
    op.create_index(op.f("ix_follow_event_bili_uid"), "follow_event", ["bili_uid"], unique=False)

    op.create_table(
        "at_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feed_id", sa.String(length=64), nullable=False),
        sa.Column("bili_uid", sa.String(length=32), nullable=False),
        sa.Column("bili_name", sa.String(length=128), nullable=False),
        sa.Column("bvid", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_id"),
    )
    op.create_index(op.f("ix_at_event_bili_uid"), "at_event", ["bili_uid"], unique=False)

    op.create_table(
        "activation_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bili_uid", sa.String(length=32), nullable=False),
        sa.Column("bili_name", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("sent_ok", sa.Boolean(), nullable=False),
        sa.Column("send_reason", sa.String(length=64), nullable=False),
        sa.Column("bound", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activation_log_bili_uid"), "activation_log", ["bili_uid"], unique=False)

    op.create_table(
        "parse_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("bili_uid", sa.String(length=32), nullable=True),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("bvid", sa.String(length=32), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_parse_log_source"), "parse_log", ["source"], unique=False)
    op.create_index(op.f("ix_parse_log_user_id"), "parse_log", ["user_id"], unique=False)
    op.create_index(op.f("ix_parse_log_bili_uid"), "parse_log", ["bili_uid"], unique=False)
    op.create_index(op.f("ix_parse_log_bvid"), "parse_log", ["bvid"], unique=False)

    op.create_table(
        "admin_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_admin_config_key"), "admin_config", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_config_key"), table_name="admin_config")
    op.drop_table("admin_config")
    op.drop_index(op.f("ix_parse_log_bvid"), table_name="parse_log")
    op.drop_index(op.f("ix_parse_log_bili_uid"), table_name="parse_log")
    op.drop_index(op.f("ix_parse_log_user_id"), table_name="parse_log")
    op.drop_index(op.f("ix_parse_log_source"), table_name="parse_log")
    op.drop_table("parse_log")
    op.drop_index(op.f("ix_activation_log_bili_uid"), table_name="activation_log")
    op.drop_table("activation_log")
    op.drop_index(op.f("ix_at_event_bili_uid"), table_name="at_event")
    op.drop_table("at_event")
    op.drop_index(op.f("ix_follow_event_bili_uid"), table_name="follow_event")
    op.drop_table("follow_event")
