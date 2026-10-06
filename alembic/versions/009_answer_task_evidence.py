"""Keep the content evaluated for an answer; old evidence is left unknown.

Revision ID: 009_answer_task_evidence
Revises: 008_durable_auth_sync
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '009_answer_task_evidence'
down_revision = '008_durable_auth_sync'
branch_labels = None
depends_on = None


def upgrade():
    # ADD COLUMN (nullable, no default) is metadata-only but still needs a brief
    # ACCESS EXCLUSIVE lock on diag_answers.  Fail fast instead of queueing
    # behind a long open answer transaction (and blocking every writer behind it).
    # SET LOCAL is scoped to the migration transaction.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column('diag_answers', sa.Column('task_snapshot', postgresql.JSONB(), nullable=True))


def downgrade():
    # NOTE: an image older than this revision cannot start on a DB at 009
    # (unknown head).  Roll back with `alembic downgrade 008_durable_auth_sync`
    # first (this drops the snapshots), then redeploy the old image.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_column('diag_answers', 'task_snapshot')
