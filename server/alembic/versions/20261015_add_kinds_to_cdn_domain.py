"""给下载域名登记加 kinds：区分这个域名是给视频/音频/图片用的

Revision ID: c2b3d4e5f6a7
Revises: b1a2c3d4e5f6
Create Date: 2026-10-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2b3d4e5f6a7"
down_revision: Union[str, None] = "b1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bili_cdn_domain",
        sa.Column("kinds", sa.String(length=64), nullable=False, server_default=""),
    )
    # 存量域名按域名族回填：抖音的视频/音频/图片分属三个不同的域，
    # B站 的 bilivideo 域一律是视频轨
    op.execute(
        """
        UPDATE bili_cdn_domain
           SET kinds = CASE
                 WHEN host LIKE '%douyinvod.com'   THEN 'video'
                 WHEN host LIKE '%douyinstatic.com' THEN 'audio'
                 WHEN host LIKE '%douyinpic.com'   THEN 'image'
                 WHEN host LIKE '%bilivideo.com'   THEN 'video'
                 ELSE ''
               END
         WHERE kinds = ''
        """
    )


def downgrade() -> None:
    op.drop_column("bili_cdn_domain", "kinds")
