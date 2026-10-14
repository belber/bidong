"""加 platform：卡片 / 解析日志 / 下载事件都按平台区分

Revision ID: b1a2c3d4e5f6
Revises: 8e3f4a5b6c7d
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, None] = "8e3f4a5b6c7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("video_card", "parse_log", "download_event")
OLD_CONSTRAINT = "uq_video_card_user_bvid"
NEW_CONSTRAINT = "uq_video_card_user_platform_bvid"


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "platform",
                sa.String(length=16),
                nullable=False,
                server_default="bilibili",
            ),
        )
        op.create_index(f"ix_{table}_platform", table, ["platform"])

    # 唯一约束从 (user_id, bvid) 放宽到 (user_id, platform, bvid)：
    # 同一用户可以在两个平台各留一张卡片。
    with op.batch_alter_table("video_card") as batch:
        batch.drop_constraint(OLD_CONSTRAINT, type_="unique")
        batch.create_unique_constraint(NEW_CONSTRAINT, ["user_id", "platform", "bvid"])


def downgrade() -> None:
    with op.batch_alter_table("video_card") as batch:
        batch.drop_constraint(NEW_CONSTRAINT, type_="unique")
        batch.create_unique_constraint(OLD_CONSTRAINT, ["user_id", "bvid"])

    for table in TABLES:
        op.drop_index(f"ix_{table}_platform", table_name=table)
        op.drop_column(table, "platform")
