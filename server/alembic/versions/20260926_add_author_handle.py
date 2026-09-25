"""add author_handle to video_source

昵称会改，抖音号 / X 的 screen_name / YouTube 的 @handle 才是唯一可搜索的账号标识，
结果页的复制按钮改为优先复制它。

Revision ID: 7d2e3f4a5b6c
Revises: 9c1d2e3f4a5b
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7d2e3f4a5b6c"
down_revision: Union[str, None] = "9c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_source",
        sa.Column(
            "author_handle", sa.String(length=128), nullable=False, server_default=""
        ),
    )


def downgrade() -> None:
    op.drop_column("video_source", "author_handle")
