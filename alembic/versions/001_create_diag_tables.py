"""Create diagnostic service tables

Revision ID: 001_diag_tables
Revises:
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_diag_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── diag_sessions ──────────────────────────────────────────────────────
    op.create_table(
        "diag_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grade_level", sa.Integer, nullable=False),
        sa.Column("invite_code", sa.String(50), nullable=True),
        sa.Column("state_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("phase", sa.String(20), nullable=False, server_default="warmup"),
        sa.Column("items_answered", sa.Integer, server_default="0"),
        sa.Column("theta", sa.Numeric(8, 4), server_default="0.0"),
        sa.Column("theta_se", sa.Numeric(8, 4), server_default="1.0"),
        sa.Column("overall_level", sa.String(20), nullable=True),
        sa.Column("weak_skills", postgresql.JSONB, server_default="[]"),
        sa.Column("topic_breakdown", postgresql.JSONB, server_default="{}"),
        sa.Column("is_valid", sa.Boolean, server_default="true"),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.CheckConstraint("grade_level BETWEEN 5 AND 11", name="ck_diag_session_grade"),
    )
    op.create_index("idx_diag_sessions_student", "diag_sessions", ["student_id"])
    op.create_index("idx_diag_sessions_invite", "diag_sessions", ["invite_code"])

    # ── diag_answers ───────────────────────────────────────────────────────
    op.create_table(
        "diag_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("diag_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(30), nullable=False),
        sa.Column("skill_id", sa.String(30), nullable=False),
        sa.Column("topic_id", sa.String(30), nullable=False),
        sa.Column("subtopic_id", sa.String(30), nullable=True),
        sa.Column("student_answer", sa.Text, nullable=False),
        sa.Column("time_ms", sa.Integer, nullable=True),
        sa.Column("outcome", sa.Numeric(3, 1), nullable=False),
        sa.Column("eval_category", sa.String(20), nullable=True),
        sa.Column("ai_evaluated", sa.Boolean, server_default="false"),
        sa.Column("theta_before", sa.Numeric(8, 4), nullable=True),
        sa.Column("theta_after", sa.Numeric(8, 4), nullable=True),
        sa.Column("se_after", sa.Numeric(8, 4), nullable=True),
        sa.Column("phase", sa.String(20), nullable=True),
        sa.Column("is_deep_scan", sa.Boolean, server_default="false"),
        sa.Column("answered_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_diag_answers_session", "diag_answers", ["session_id"])
    op.create_index("idx_diag_answers_skill", "diag_answers", ["skill_id"])

    # ── diag_reports ───────────────────────────────────────────────────────
    op.create_table(
        "diag_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("diag_sessions.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grade_level", sa.Integer, nullable=False),
        sa.Column("overall_theta", sa.Numeric(8, 4), nullable=True),
        sa.Column("overall_level", sa.String(20), nullable=True),
        sa.Column("confidence_interval_lo", sa.Numeric(8, 4), nullable=True),
        sa.Column("confidence_interval_hi", sa.Numeric(8, 4), nullable=True),
        sa.Column("topic_breakdown", postgresql.JSONB, nullable=True),
        sa.Column("weak_skills", postgresql.JSONB, nullable=True),
        sa.Column("recommended_start", sa.String(30), nullable=True),
        sa.Column("narrative_ru", sa.Text, nullable=True),
        sa.Column("narrative_generated", sa.Boolean, server_default="false"),
        sa.Column("pdf_url", sa.Text, nullable=True),
        sa.Column("pdf_generated", sa.Boolean, server_default="false"),
        sa.Column("generated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_diag_reports_student", "diag_reports", ["student_id"])

    # ── grade_topic_map ────────────────────────────────────────────────────
    op.create_table(
        "grade_topic_map",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("grade_level", sa.Integer, nullable=False),
        sa.Column("topic_id", sa.String(30), nullable=False),
        sa.Column("section_id", sa.String(30), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("importance", sa.Integer, nullable=False, server_default="5"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.CheckConstraint("grade_level BETWEEN 5 AND 11", name="ck_gtm_grade"),
        sa.CheckConstraint("importance BETWEEN 1 AND 10", name="ck_gtm_importance"),
    )
    op.create_index("idx_gtm_grade", "grade_topic_map", ["grade_level"])

    # ── Seed grade 5 topics ────────────────────────────────────────────────
    # G5_NAT = Natural Numbers section (5 topics, positions 0-4)
    # G5_FRAC = Fractions section     (5 topics, positions 0-4)
    op.execute("""
        INSERT INTO grade_topic_map
            (grade_level, topic_id, section_id, position, importance)
        VALUES
            (5, 'G5_T01', 'G5_NAT',  0, 6),
            (5, 'G5_T02', 'G5_NAT',  1, 7),
            (5, 'G5_T03', 'G5_NAT',  2, 9),
            (5, 'G5_T04', 'G5_NAT',  3, 5),
            (5, 'G5_T05', 'G5_NAT',  4, 6),
            (5, 'G5_T06', 'G5_FRAC', 0, 9),
            (5, 'G5_T07', 'G5_FRAC', 1, 8),
            (5, 'G5_T08', 'G5_FRAC', 2, 8),
            (5, 'G5_T09', 'G5_FRAC', 3, 5),
            (5, 'G5_T10', 'G5_FRAC', 4, 6)
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table("grade_topic_map")
    op.drop_table("diag_reports")
    op.drop_table("diag_answers")
    op.drop_table("diag_sessions")
