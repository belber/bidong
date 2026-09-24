"""set download_event.card_id on delete set null

Revision ID: 3f4a5b6c7d8e
Revises: 2e3f4a5b6c7d
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op


revision: str = "3f4a5b6c7d8e"
down_revision: Union[str, None] = "2e3f4a5b6c7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # SQLite 不支持 ALTER 约束，且默认不强制外键；卡片删除时由应用层把
        # download_event.card_id 置空（见 routers/cards.py），语义不受影响。
        return
    op.drop_constraint(
        "download_event_card_id_fkey", "download_event", type_="foreignkey"
    )
    op.create_foreign_key(
        "download_event_card_id_fkey",
        "download_event",
        "video_card",
        ["card_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.drop_constraint(
        "download_event_card_id_fkey", "download_event", type_="foreignkey"
    )
    op.create_foreign_key(
        "download_event_card_id_fkey",
        "download_event",
        "video_card",
        ["card_id"],
        ["id"],
    )
