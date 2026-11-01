"""Backoff and hourly requeue for the auth-service completion sync (B-03).

Revision ID: 012_auth_sync_backoff
Revises: 011_report_narrative_cache

``auth_sync_next_attempt_at`` is the earliest moment of the next attempt (retry pause of a ``pending`` row, hourly
requeue of a ``failed`` one); ``auth_sync_requeues`` counts those requeues.  Both are cheap ADD COLUMNs.

Rows that the old worker already gave up on (``failed`` after 5 attempts in a minute) are due again at once: they
are exactly the results that never reached auth-service.
"""
from alembic import op
import sqlalchemy as sa

revision = '012_auth_sync_backoff'
down_revision = '011_report_narrative_cache'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column('diag_sessions', sa.Column('auth_sync_next_attempt_at', sa.DateTime(), nullable=True))
    op.add_column(
        'diag_sessions',
        sa.Column('auth_sync_requeues', sa.Integer(), nullable=False, server_default='0'),
    )
    op.execute(
        "UPDATE diag_sessions SET auth_sync_next_attempt_at = NOW() AT TIME ZONE 'UTC' "
        "WHERE auth_sync_status = 'failed' AND phase = 'completed'"
    )


def downgrade():
    # An image older than this revision cannot start on a DB at 012: roll back with
    # `alembic downgrade 011_report_narrative_cache` first, then redeploy the old image.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_column('diag_sessions', 'auth_sync_requeues')
    op.drop_column('diag_sessions', 'auth_sync_next_attempt_at')
