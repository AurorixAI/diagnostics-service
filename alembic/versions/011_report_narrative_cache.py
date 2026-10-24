"""Keep a paid model answer between retries of the same report job.

Revision ID: 011_report_narrative_cache
Revises: 010_deep_scan_origin_link

``diag_reports.narrative_cache`` holds ``{"key": sha256(prompt), "ai_data": {...}}`` of the last
VALID narrative while the job is not yet current, so a retry (failure after the model call, a
stale claim returned to the queue) does not pay for the model again.  It is cleared when the
report becomes current.  Nullable, no default: metadata-only ADD COLUMN.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '011_report_narrative_cache'
down_revision = '010_deep_scan_origin_link'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column('diag_reports', sa.Column('narrative_cache', postgresql.JSONB(), nullable=True))


def downgrade():
    # An image older than this revision cannot start on a DB at 011: roll back with
    # `alembic downgrade 010_deep_scan_origin_link` first, then redeploy the old image.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_column('diag_reports', 'narrative_cache')
