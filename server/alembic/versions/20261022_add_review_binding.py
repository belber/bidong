"""add reusable WeChat review binding

Revision ID: e4f5a6b7c8d9
Revises: c2b3d4e5f6a7
Create Date: 2026-10-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "c2b3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_binding",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("activation_code", sa.String(length=32), nullable=False),
        sa.Column("bound_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("review_binding")
