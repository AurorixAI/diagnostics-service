"""Track report generation and schema freshness durably.

Revision ID: 006_report_generation_lifecycle
Revises: 005_diag_session_stop_reason
"""
from alembic import op
import sqlalchemy as sa


revision = "006_report_generation_lifecycle"
down_revision = "005_diag_session_stop_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Local development databases may have been created through SQLAlchemy
    # metadata between code releases.  Make this migration safe for that schema
    # drift while preserving normal Alembic behaviour on a clean database.
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("diag_reports")
    }

    def add_if_missing(name: str, column: sa.Column) -> None:
        if name not in existing:
            op.add_column("diag_reports", column)

    add_if_missing(
        "report_schema_version",
        sa.Column("report_schema_version", sa.Integer(), nullable=False, server_default="0"),
    )
    add_if_missing(
        "generation_status",
        sa.Column("generation_status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    add_if_missing("generation_stage", sa.Column("generation_stage", sa.String(length=40), nullable=True))
    add_if_missing(
        "generation_attempts",
        sa.Column("generation_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    add_if_missing("generation_requested_at", sa.Column("generation_requested_at", sa.DateTime(), nullable=True))
    add_if_missing("generation_error", sa.Column("generation_error", sa.Text(), nullable=True))
    add_if_missing("generation_started_at", sa.Column("generation_started_at", sa.DateTime(), nullable=True))
    add_if_missing("generation_completed_at", sa.Column("generation_completed_at", sa.DateTime(), nullable=True))

    # Existing reports remain readable.  They are intentionally marked as
    # legacy schema (0) so the durable worker can rebuild derived fields from
    # append-only answers without altering historic student responses.
    op.execute(
        "UPDATE diag_reports "
        "SET generation_status = CASE WHEN report_json IS NULL THEN 'pending' ELSE 'ready' END"
    )


def downgrade() -> None:
    op.drop_column("diag_reports", "generation_completed_at")
    op.drop_column("diag_reports", "generation_started_at")
    op.drop_column("diag_reports", "generation_error")
    op.drop_column("diag_reports", "generation_requested_at")
    op.drop_column("diag_reports", "generation_attempts")
    op.drop_column("diag_reports", "generation_stage")
    op.drop_column("diag_reports", "generation_status")
    op.drop_column("diag_reports", "report_schema_version")
