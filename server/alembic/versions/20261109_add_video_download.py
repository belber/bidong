"""Persistent complete-video preparation queue."""
from alembic import op
import sqlalchemy as sa
revision='b7c8d9e0f1a2'
down_revision='a6b7c8d9e0f1'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('video_download_queue',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('worker_token',sa.String(64),nullable=False),
        sa.Column('lease_until',sa.Integer(),nullable=False),sa.Column('heartbeat_at',sa.Integer(),nullable=False))
    op.execute("INSERT INTO video_download_queue (id,revision,worker_token,lease_until,heartbeat_at) VALUES (1,0,'',0,0)")
    op.create_table('video_download_job',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('cache_key',sa.String(64),nullable=False,unique=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('user.id'),nullable=False),
        sa.Column('card_id',sa.Integer(),sa.ForeignKey('video_card.id',ondelete='SET NULL'),nullable=True),
        sa.Column('qn',sa.Integer(),nullable=False),sa.Column('input_json',sa.Text(),nullable=False),
        sa.Column('status',sa.String(24),nullable=False),sa.Column('has_audio',sa.Boolean(),nullable=True),
        sa.Column('estimated_size',sa.BigInteger(),nullable=False),sa.Column('size_bytes',sa.BigInteger(),nullable=False),
        sa.Column('expires_at',sa.Integer(),nullable=False),sa.Column('serve_until',sa.Integer(),nullable=False),
        sa.Column('recoveries',sa.Integer(),nullable=False),sa.Column('error',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False))
    for key in ('user_id','card_id','status'):op.create_index('ix_video_download_job_'+key,'video_download_job',[key])


def downgrade():
    op.drop_table('video_download_job')
    op.drop_table('video_download_queue')
