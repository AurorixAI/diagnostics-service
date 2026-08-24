"""Enforce one resumable diagnostic session for each invite code.

Revision ID: 007_active_invite_session
Revises: 006_report_generation_lifecycle
"""
from alembic import op
import sqlalchemy as sa


revision = "007_active_invite_session"
down_revision = "006_report_generation_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A 24-hour invite is no longer a usable attempt once it has no answers
    # and has outlived that deadline. Preserve those historic rows verbatim,
    # but remove them from the active queue before enforcing uniqueness.
    # This is a lifecycle correction, not a deletion or a data rewrite.
    op.execute(
        sa.text(
            """
            UPDATE diag_sessions
            SET phase = 'expired',
                stop_reason = COALESCE(stop_reason, 'expired_empty_invite'),
                updated_at = NOW()
            WHERE phase IN ('warmup', 'navigation', 'deep_scan')
              AND COALESCE(items_answered, 0) = 0
              AND created_at < NOW() - INTERVAL '24 hours'
            """
        )
    )

    # Preserve every non-empty historical attempt. Any remaining duplicate is
    # ambiguous and must be reviewed rather than silently choosing a winner.
    duplicates = op.get_bind().execute(
        sa.text(
            """
            SELECT invite_code
            FROM diag_sessions
            WHERE invite_code IS NOT NULL
              AND phase IN ('warmup', 'navigation', 'deep_scan')
            GROUP BY invite_code
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicates:
        sample = ", ".join(str(row[0]) for row in duplicates[:5])
        raise RuntimeError(
            "Cannot enforce one active diagnostic session per invite; "
            f"resolve duplicate active invite codes first: {sample}"
        )
    op.create_index(
        "uq_diag_sessions_active_invite_code",
        "diag_sessions",
        ["invite_code"],
        unique=True,
        postgresql_where=sa.text(
            "invite_code IS NOT NULL AND phase IN ('warmup', 'navigation', 'deep_scan')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_diag_sessions_active_invite_code", table_name="diag_sessions")
