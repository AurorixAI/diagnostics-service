"""Link every Deep Scan answer to the skill that started the scan and its step.

Revision ID: 010_deep_scan_origin_link
Revises: 009_answer_task_evidence

Before this revision a prerequisite chain was *guessed* from neighbouring
answers in the report.  Now each deep-scan answer records which navigation skill
triggered the scan (``deep_scan_origin_skill_id``) and its 1-based position in
that scan (``deep_scan_step``).  Both columns are nullable: answers recorded
before this revision keep NULL and the report falls back to the old inference.
"""
from alembic import op
import sqlalchemy as sa

revision = '010_deep_scan_origin_link'
down_revision = '009_answer_task_evidence'
branch_labels = None
depends_on = None


def upgrade():
    # ADD COLUMN (nullable, no default) is metadata-only but still needs a brief
    # ACCESS EXCLUSIVE lock on diag_answers.  Fail fast instead of queueing
    # behind a long open answer transaction (and blocking every writer behind it).
    # SET LOCAL is scoped to the migration transaction.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column('diag_answers', sa.Column('deep_scan_origin_skill_id', sa.String(length=30), nullable=True))
    op.add_column('diag_answers', sa.Column('deep_scan_step', sa.Integer(), nullable=True))


def downgrade():
    # NOTE: an image older than this revision cannot start on a DB at 010
    # (unknown head).  Roll back with `alembic downgrade 009_answer_task_evidence`
    # first (this drops the links; reports then fall back to inference), then
    # redeploy the old image.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_column('diag_answers', 'deep_scan_step')
    op.drop_column('diag_answers', 'deep_scan_origin_skill_id')
