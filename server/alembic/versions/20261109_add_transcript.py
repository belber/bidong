"""Persistent transcript jobs and serialized queue."""
from alembic import op
import sqlalchemy as sa
revision = 'a6b7c8d9e0f1'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('transcript_queue', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('worker_token', sa.String(64), nullable=False),
        sa.Column('lease_until', sa.Integer(), nullable=False),
        sa.Column('heartbeat_at', sa.Integer(), nullable=False))
    op.execute("INSERT INTO transcript_queue (id, revision, worker_token, lease_until, heartbeat_at) VALUES (1,0,'',0,0)")
    op.create_table('transcript_job', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cache_key', sa.String(64), unique=True, nullable=False),
        sa.Column('input_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('source', sa.String(16), nullable=False),
        sa.Column('language', sa.String(32), nullable=False),
        sa.Column('segments_json', sa.Text(), nullable=False),
        sa.Column('error', sa.Text(), nullable=False),
        sa.Column('recoveries', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False))
    op.create_index('ix_transcript_job_status', 'transcript_job', ['status'])
    op.create_table('transcript_request', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('transcript_job.id'), nullable=False),
        sa.UniqueConstraint('user_id','job_id'))
    op.create_index('ix_transcript_request_user_id','transcript_request',['user_id'])
    op.create_index('ix_transcript_request_job_id','transcript_request',['job_id'])


def downgrade():
    op.drop_table('transcript_request')
    op.drop_table('transcript_job')
    op.drop_table('transcript_queue')
