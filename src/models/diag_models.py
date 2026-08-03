"""
Diagnostic Service — ORM Models (owned tables)

Tables managed exclusively by this service:
  diag_sessions  — one row per diagnostic attempt
  diag_answers   — append-only log of every answer
  diag_reports   — final report generated at completion
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from src.models.base import Base


class DiagSession(Base):
    """Active or completed diagnostic session."""

    __tablename__ = "diag_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    grade_level = Column(Integer, nullable=False)
    invite_code = Column(String(50), index=True)

    # Algorithm state — stored in Redis during session, persisted here on completion
    state_snapshot = Column(JSONB, nullable=True)

    # Phase: warmup | navigation | deep_scan | completed
    phase = Column(String(20), nullable=False, default="warmup")
    items_answered = Column(Integer, default=0)

    # IRT result
    theta = Column(Numeric(8, 4), default=0.0)
    theta_se = Column(Numeric(8, 4), default=1.0)

    # Outcome
    overall_level = Column(String(20))          # below_grade | at_grade | above_grade
    weak_skills = Column(JSONB, default=list)    # [skill_id, ...]
    topic_breakdown = Column(JSONB, default=dict)  # {topic_id: {alpha, level}}

    is_valid = Column(Boolean, default=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("grade_level BETWEEN 5 AND 11", name="ck_diag_session_grade"),
    )


class DiagAnswer(Base):
    """Append-only log of every answer in a diagnostic session."""

    __tablename__ = "diag_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("diag_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id = Column(String(30), nullable=False)
    skill_id = Column(String(30), nullable=False)
    topic_id = Column(String(30), nullable=False)     # L2
    subtopic_id = Column(String(30), nullable=True)   # L3

    # Student answer
    student_answer = Column(Text, nullable=False)
    time_ms = Column(Integer, nullable=True)

    # Evaluation
    outcome = Column(Numeric(3, 1), nullable=False)  # 0.0 (wrong/distractor/idk) | 1.0 (correct)
    eval_category = Column(String(20))               # correct | distractor | wrong | idk
    ai_evaluated = Column(Boolean, default=False)

    # IRT state
    theta_before = Column(Numeric(8, 4))
    theta_after = Column(Numeric(8, 4))
    se_after = Column(Numeric(8, 4))

    # Navigation context
    phase = Column(String(20))
    is_deep_scan = Column(Boolean, default=False)

    answered_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_diag_answers_session", "session_id"),
        Index("idx_diag_answers_skill", "skill_id"),
    )


class DiagReport(Base):
    """Final diagnostic report — generated once per completed session."""

    __tablename__ = "diag_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("diag_sessions.id"),
        unique=True,
        nullable=False,
    )
    student_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    grade_level = Column(Integer, nullable=False)

    # Core metrics
    overall_theta = Column(Numeric(8, 4))
    overall_level = Column(String(20))
    confidence_interval_lo = Column(Numeric(8, 4))
    confidence_interval_hi = Column(Numeric(8, 4))

    # Breakdown
    topic_breakdown = Column(JSONB)   # [{topic_id, alpha, level, weak_skills[]}]
    weak_skills = Column(JSONB)       # [skill_id, ...]
    recommended_start = Column(String(30))  # skill_id to start from

    # LLM narrative
    narrative_ru = Column(Text)
    narrative_generated = Column(Boolean, default=False)

    # PDF
    pdf_url = Column(Text)
    pdf_generated = Column(Boolean, default=False)

    generated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_diag_reports_student", "student_id"),
    )


