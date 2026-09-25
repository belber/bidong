"""add video_source table and video_card.up_mid

「视频出处（原up主）」功能：小主机上报帅哥录屏稿件的出处（video_source），
同时把视频 UP主 mid 落到 video_card，供解析时判断归属。

Revision ID: 9c1d2e3f4a5b
Revises: 5b6c7d8e9f0a
Create Date: 2026-09-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c1d2e3f4a5b"
down_revision: Union[str, None] = "5b6c7d8e9f0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_card",
        sa.Column("up_mid", sa.String(length=32), nullable=False, server_default=""),
    )
    op.create_table(
        "video_source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bvid", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("platform", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("author_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("author_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("author_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_video_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("bili_published_at", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_video_source_bvid", "video_source", ["bvid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_video_source_bvid", table_name="video_source")
    op.drop_table("video_source")
    op.drop_column("video_card", "up_mid")
