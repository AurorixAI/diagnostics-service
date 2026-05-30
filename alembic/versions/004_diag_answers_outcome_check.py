"""Add CHECK constraint on diag_answers.outcome (must be in [0, 1])

outcome is Numeric(3,1) — values outside [0, 1] are semantically invalid
(it represents a correctness score, 0.0 = wrong, 1.0 = correct).

Revision ID: 004_diag_answers_outcome_check
Revises: 003_drop_grade_topic_map
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "004_diag_answers_outcome_check"
down_revision = "003_drop_grade_topic_map"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clamp any out-of-range values before adding the constraint
    op.execute(
        "UPDATE diag_answers SET outcome = 0.0 WHERE outcome < 0"
    )
    op.execute(
        "UPDATE diag_answers SET outcome = 1.0 WHERE outcome > 1"
    )
    op.create_check_constraint(
        "ck_diag_answers_outcome_range",
        "diag_answers",
        sa.text("outcome >= 0 AND outcome <= 1"),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_diag_answers_outcome_range", "diag_answers", type_="check"
    )
