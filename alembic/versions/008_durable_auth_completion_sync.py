"""Persist retryable auth-service completion synchronisation.

Revision ID: 008_durable_auth_sync
Revises: 007_active_invite_session
"""
from alembic import op
import sqlalchemy as sa


revision = "008_durable_auth_sync"
down_revision = "007_active_invite_session"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("diag_sessions")
    }
    existing_indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("diag_sessions")
    }

    def add_if_missing(name: str, column: sa.Column) -> None:
        if name not in existing:
            op.add_column("diag_sessions", column)

    add_if_missing(
        "auth_sync_status",
        sa.Column("auth_sync_status", sa.String(length=20), nullable=False, server_default="not_requested"),
    )
    add_if_missing(
        "auth_sync_attempts",
        sa.Column("auth_sync_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    add_if_missing("auth_sync_requested_at", sa.Column("auth_sync_requested_at", sa.DateTime(), nullable=True))
    add_if_missing("auth_sync_started_at", sa.Column("auth_sync_started_at", sa.DateTime(), nullable=True))
    add_if_missing("auth_sync_completed_at", sa.Column("auth_sync_completed_at", sa.DateTime(), nullable=True))
    add_if_missing("auth_sync_error", sa.Column("auth_sync_error", sa.Text(), nullable=True))
    if "idx_diag_sessions_auth_sync_pending" not in existing_indexes:
        op.create_index(
            "idx_diag_sessions_auth_sync_pending",
            "diag_sessions",
            ["auth_sync_status", "auth_sync_requested_at"],
        )


def downgrade() -> None:
    op.drop_index("idx_diag_sessions_auth_sync_pending", table_name="diag_sessions")
    op.drop_column("diag_sessions", "auth_sync_error")
    op.drop_column("diag_sessions", "auth_sync_completed_at")
    op.drop_column("diag_sessions", "auth_sync_started_at")
    op.drop_column("diag_sessions", "auth_sync_requested_at")
    op.drop_column("diag_sessions", "auth_sync_attempts")
    op.drop_column("diag_sessions", "auth_sync_status")
