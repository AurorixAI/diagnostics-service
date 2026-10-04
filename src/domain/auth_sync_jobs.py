"""Durable auth-service synchronisation for completed diagnostic attempts.

The diagnostic database remains the source of truth for answers and CAT
results.  This small outbox only mirrors a completed attempt to auth-service
so that its invite registry and student profile have the same final status.
It never restarts a diagnostic and never changes student answers.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.core import auth_client
from src.core.database import SessionLocal
from src.models.diag_models import DiagAnswer, DiagSession

log = logging.getLogger(__name__)

MAX_SYNC_ATTEMPTS = 5
STALE_SYNC_AFTER = timedelta(minutes=2)


def enqueue_auth_completion_sync(db: Session, session: DiagSession, *, commit: bool = True) -> None:
    """Queue a new completion callback without touching historic sessions."""
    if session.phase != "completed" or not session.invite_code:
        return
    session.auth_sync_status = "pending"
    session.auth_sync_attempts = 0
    session.auth_sync_requested_at = datetime.now(timezone.utc)
    session.auth_sync_started_at = None
    session.auth_sync_completed_at = None
    session.auth_sync_error = None
    if commit:
        db.commit()


def _claim_next_sync(db: Session) -> Optional[DiagSession]:
    session = (
        db.query(DiagSession)
        .filter(
            DiagSession.phase == "completed",
            DiagSession.invite_code.isnot(None),
            DiagSession.auth_sync_status == "pending",
            DiagSession.auth_sync_requested_at.isnot(None),
            DiagSession.auth_sync_attempts < MAX_SYNC_ATTEMPTS,
        )
        .order_by(DiagSession.auth_sync_requested_at, DiagSession.created_at)
        .with_for_update(skip_locked=True)
        .first()
    )
    if not session:
        return None
    session.auth_sync_status = "syncing"
    session.auth_sync_attempts += 1
    session.auth_sync_started_at = datetime.now(timezone.utc)
    session.auth_sync_error = None
    db.commit()
    return session


def _completion_payload(db: Session, session: DiagSession) -> dict:
    answers = db.query(DiagAnswer).filter(DiagAnswer.session_id == session.id).all()
    correct_answers = sum(1 for answer in answers if float(answer.outcome or 0) >= 1.0)
    total_answers = len(answers)
    return {
        "session_started_at": session.created_at.isoformat() if session.created_at else None,
        "final_theta": float(session.theta) if session.theta is not None else None,
        "se": float(session.theta_se) if session.theta_se is not None else None,
        "total_items": total_answers,
        "correct_answers": correct_answers,
        "accuracy": round(correct_answers / total_answers, 4) if total_answers else None,
        "identified_gaps": list(session.weak_skills or []),
        "topic_breakdown": session.topic_breakdown or {},
    }


def recover_stale_auth_sync_jobs(db: Session) -> int:
    """Recover abandoned HTTP callbacks without stealing a recent claim."""
    stale = (
        db.query(DiagSession)
        .filter(
            DiagSession.phase == "completed",
            DiagSession.auth_sync_status == "syncing",
            DiagSession.auth_sync_requested_at.isnot(None),
            DiagSession.auth_sync_started_at.isnot(None),
            DiagSession.auth_sync_started_at < datetime.now(timezone.utc) - STALE_SYNC_AFTER,
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    for session in stale:
        session.auth_sync_status = "failed" if session.auth_sync_attempts >= MAX_SYNC_ATTEMPTS else "pending"
        session.auth_sync_error = "Previous completion callback was interrupted"
        log.warning("diagnostic_auth_sync_recovered session_id=%s status=%s attempts=%s",
                    session.id, session.auth_sync_status, session.auth_sync_attempts)
    if stale:
        db.commit()
    return len(stale)


def _owns_claim(session: DiagSession, attempt: int, started_at: Optional[datetime]) -> bool:
    return (session.auth_sync_status == "syncing"
            and session.auth_sync_attempts == attempt
            and session.auth_sync_started_at == started_at)


def process_next_auth_completion_sync() -> bool:
    """Deliver one queued completion callback; safe across service replicas."""
    db = SessionLocal()
    session_id: Optional[uuid.UUID] = None
    claim_attempt = 0
    claim_started_at: Optional[datetime] = None
    try:
        recover_stale_auth_sync_jobs(db)
        session = _claim_next_sync(db)
        if session is None:
            return False
        session_id = session.id
        claim_attempt, claim_started_at = session.auth_sync_attempts, session.auth_sync_started_at
        delivered = auth_client.notify_complete(
            session.invite_code or "",
            str(session.id),
            _completion_payload(db, session),
        )

        fresh = (
            db.query(DiagSession)
            .filter(DiagSession.id == session.id)
            .populate_existing()
            .with_for_update()
            .first()
        )
        if fresh is None or not _owns_claim(fresh, claim_attempt, claim_started_at):
            return False
        if delivered:
            fresh.auth_sync_status = "synced"
            fresh.auth_sync_completed_at = datetime.now(timezone.utc)
            fresh.auth_sync_error = None
        elif fresh.auth_sync_attempts >= MAX_SYNC_ATTEMPTS:
            fresh.auth_sync_status = "failed"
            fresh.auth_sync_error = "Auth-service did not confirm diagnostic completion"
        else:
            fresh.auth_sync_status = "pending"
            fresh.auth_sync_error = "Auth-service is temporarily unavailable"
        db.commit()
        return delivered
    except Exception as exc:
        db.rollback()
        log.error("diagnostic_auth_sync_failed session_id=%s error_type=%s", session_id, type(exc).__name__)
        if session_id is not None:
            repair_db = SessionLocal()
            try:
                fresh = (
                    repair_db.query(DiagSession)
                    .filter(DiagSession.id == session_id)
                    .with_for_update()
                    .first()
                )
                if fresh and _owns_claim(fresh, claim_attempt, claim_started_at):
                    if fresh.auth_sync_attempts >= MAX_SYNC_ATTEMPTS:
                        fresh.auth_sync_status = "failed"
                    else:
                        fresh.auth_sync_status = "pending"
                    fresh.auth_sync_error = "Completion callback failed: " + type(exc).__name__
                    repair_db.commit()
            except Exception:
                repair_db.rollback()
                log.exception("Could not persist auth-sync recovery state")
            finally:
                repair_db.close()
        return False
    finally:
        db.close()
