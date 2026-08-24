"""Persist the adaptive-diagnostic completion reason.

Revision ID: 005_diag_session_stop_reason
Revises: 004_diag_answers_outcome_check
Create Date: 2026-08-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "005_diag_session_stop_reason"
down_revision: str = "004_diag_answers_outcome_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Some existing local databases were created from ORM metadata before this
    # Alembic revision existed.  Treat that harmless schema drift as already
    # applied so the startup migration remains safe and can record its version.
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("diag_sessions")
    }
    if "stop_reason" not in columns:
        op.add_column(
            "diag_sessions",
            sa.Column("stop_reason", sa.String(length=40), nullable=True),
        )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("diag_sessions")
    }
    if "stop_reason" in columns:
        op.drop_column("diag_sessions", "stop_reason")
