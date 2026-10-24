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
    text,
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

    # Phase: warmup | navigation | deep_scan | completed | expired
    phase = Column(String(20), nullable=False, default="warmup")
    items_answered = Column(Integer, default=0)
    stop_reason = Column(String(40), nullable=True)

    # IRT result
    theta = Column(Numeric(8, 4), default=0.0)
    theta_se = Column(Numeric(8, 4), default=1.0)

    # Outcome
    overall_level = Column(String(20))          # below_grade | at_grade | above_grade
    weak_skills = Column(JSONB, default=list)    # [skill_id, ...]
    topic_breakdown = Column(JSONB, default=dict)  # {topic_id: {alpha, level}}

    is_valid = Column(Boolean, default=True)
    completed_at = Column(DateTime, nullable=True)

    # Auth-service owns the public invite and student projection.  Completion
    # is therefore synchronised through a durable, retryable outbox state
    # rather than relying on a best-effort HTTP callback in the request path.
    # ``requested_at`` stays null for historical rows so a deploy never sends
    # unrequested callbacks for old diagnostics.
    auth_sync_status = Column(String(20), nullable=False, default="not_requested")
    auth_sync_attempts = Column(Integer, nullable=False, default=0)
    auth_sync_requested_at = Column(DateTime, nullable=True)
    auth_sync_started_at = Column(DateTime, nullable=True)
    auth_sync_completed_at = Column(DateTime, nullable=True)
    auth_sync_error = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("grade_level BETWEEN 5 AND 11", name="ck_diag_session_grade"),
        # Completed and expired rows remain auditable.  Only resumable phases
        # reserve an invite code and can prevent another concurrent start.
        Index(
            "uq_diag_sessions_active_invite_code",
            "invite_code",
            unique=True,
            postgresql_where=text(
                "invite_code IS NOT NULL AND phase IN ('warmup', 'navigation', 'deep_scan')"
            ),
        ),
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
    # Deep Scan link (NULL for measurement items and for answers recorded before
    # migration 010): the navigation skill whose failure started the scan and
    # this answer's 1-based step inside it.  The report builds chains from this
    # link instead of guessing from neighbouring answers.
    deep_scan_origin_skill_id = Column(String(30), nullable=True)
    deep_scan_step = Column(Integer, nullable=True)

    # New answers retain the exact evaluated/displayed task (provenance
    # "issued"). Legacy rows are NULL until scripts/backfill_task_snapshots.py
    # stores a best-effort copy of today's bank (provenance
    # "legacy_bank_backfill"), which is never presented as exactly issued content.
    task_snapshot = Column(JSONB, nullable=True)

    answered_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_diag_answers_session", "session_id"),
        Index("idx_diag_answers_skill", "skill_id"),
    )


class DiagReport(Base):
    """Derived diagnostic report with a durable, observable generation lifecycle."""

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

    # LLM narrative — structured JSON (new) + text fallback (legacy)
    report_json = Column(JSONB)                         # structured 8-block JSON
    narrative_ru = Column(Text)                         # legacy text (kept for compat)
    narrative_generated = Column(Boolean, default=False)
    # A valid model answer kept between retries of the SAME job ({"key": sha256(prompt), "ai_data": {...}})
    # so that a retry never pays for the narrative twice.  Cleared when the report becomes current.
    narrative_cache = Column(JSONB, nullable=True)

    # Report generation is deliberately tracked in the database rather than
    # only in an in-memory thread.  A restart therefore cannot silently lose a
    # completed student's report, and the UI can render an honest progress
    # state while deterministic data / the narrative are being prepared.
    report_schema_version = Column(Integer, nullable=False, default=0)
    generation_status = Column(String(20), nullable=False, default="pending")
    generation_stage = Column(String(40), nullable=True)
    generation_attempts = Column(Integer, nullable=False, default=0)
    # Null for reports that predate the durable queue.  Workers process only
    # explicit requests, never historic diagnostics merely due to ordering.
    generation_requested_at = Column(DateTime, nullable=True)
    generation_error = Column(Text, nullable=True)
    generation_started_at = Column(DateTime, nullable=True)
    generation_completed_at = Column(DateTime, nullable=True)

    # PDF
    pdf_url = Column(Text)
    pdf_generated = Column(Boolean, default=False)

    generated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_diag_reports_student", "student_id"),
    )
