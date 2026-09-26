"""add crawler_visit table

记录微信搜索爬虫的访问（服务端按请求头/UA 识别 + 小程序按场景值 1129 上报），
用于诊断"为什么页面没被收录"。

Revision ID: 8e3f4a5b6c7d
Revises: 7d2e3f4a5b6c
Create Date: 2026-09-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8e3f4a5b6c7d"
down_revision: Union[str, None] = "7d2e3f4a5b6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crawler_visit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="header"),
        sa.Column("path", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("query", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("referer", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("scene", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signature_verified", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_crawler_visit_created_at", "crawler_visit", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_crawler_visit_created_at", table_name="crawler_visit")
    op.drop_table("crawler_visit")
