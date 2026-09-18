"""add download_event and bili_cdn_domain

Revision ID: 1d2e3f4a5b6c
Revises: b5c6d7e8f9a0
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1d2e3f4a5b6c"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bili_cdn_domain",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("is_configured", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("seen_count", sa.Integer(), nullable=False),
        sa.Column("download_success_count", sa.Integer(), nullable=False),
        sa.Column("download_failure_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bili_cdn_domain_host", "bili_cdn_domain", ["host"], unique=True)

    op.create_table(
        "download_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("card_id", sa.Integer(), nullable=True),
        sa.Column("bvid", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("qn", sa.Integer(), nullable=True),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("candidate_index", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_type", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("wx_err_msg", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["video_card.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_download_event_bvid", "download_event", ["bvid"], unique=False)
    op.create_index("ix_download_event_card_id", "download_event", ["card_id"], unique=False)
    op.create_index("ix_download_event_error_type", "download_event", ["error_type"], unique=False)
    op.create_index("ix_download_event_host", "download_event", ["host"], unique=False)
    op.create_index("ix_download_event_kind", "download_event", ["kind"], unique=False)
    op.create_index("ix_download_event_stage", "download_event", ["stage"], unique=False)
    op.create_index("ix_download_event_status", "download_event", ["status"], unique=False)
    op.create_index("ix_download_event_user_id", "download_event", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_download_event_user_id", table_name="download_event")
    op.drop_index("ix_download_event_status", table_name="download_event")
    op.drop_index("ix_download_event_stage", table_name="download_event")
    op.drop_index("ix_download_event_kind", table_name="download_event")
    op.drop_index("ix_download_event_host", table_name="download_event")
    op.drop_index("ix_download_event_error_type", table_name="download_event")
    op.drop_index("ix_download_event_card_id", table_name="download_event")
    op.drop_index("ix_download_event_bvid", table_name="download_event")
    op.drop_table("download_event")
    op.drop_index("ix_bili_cdn_domain_host", table_name="bili_cdn_domain")
    op.drop_table("bili_cdn_domain")
