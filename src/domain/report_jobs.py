"""Durable report-generation jobs backed by ``diag_reports``.

The table itself is the queue: completed diagnostics create a pending derived
report, workers claim it with a row lock, and a service restart simply resumes
unfinished work.  No student answer or source task is changed here.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.database import SessionLocal
from src.domain.report_generator import REPORT_SCHEMA_VERSION, generate_and_save_report
from src.models.diag_models import DiagAnswer, DiagReport, DiagSession

log = logging.getLogger(__name__)

MAX_GENERATION_ATTEMPTS = 3
STALE_GENERATING_AFTER = timedelta(minutes=10)


def _snapshot_value(session: DiagSession, key: str, default):
    snapshot = session.state_snapshot if isinstance(session.state_snapshot, dict) else {}
    return snapshot.get(key, default)


def enqueue_report_generation(db: Session, session_id: uuid.UUID, *, commit: bool = True) -> DiagReport:
    """Create or refresh a durable pending job for a completed diagnostic."""
    session = db.query(DiagSession).filter(DiagSession.id == session_id).first()
    if session is None or session.phase != "completed":
        raise ValueError("Нельзя создать отчёт для незавершённой диагностики")

    report = db.query(DiagReport).filter(DiagReport.session_id == session.id).first()
    if report is None:
        report = DiagReport(
            session_id=session.id,
            student_id=session.student_id,
            grade_level=session.grade_level,
            overall_theta=session.theta,
            overall_level=session.overall_level,
            confidence_interval_lo=None,
            confidence_interval_hi=None,
            topic_breakdown=session.topic_breakdown or {},
            weak_skills=session.weak_skills or [],
            recommended_start=(session.weak_skills or [None])[0],
            report_schema_version=0,
            generation_status="pending",
            generation_stage="queued",
            generation_attempts=0,
            generation_requested_at=datetime.now(timezone.utc),
        )
        db.add(report)
    elif report.report_schema_version < REPORT_SCHEMA_VERSION or not report.report_json:
        report.generation_status = "pending"
        report.generation_stage = "queued"
        report.generation_error = None
        report.generation_attempts = 0
        report.generation_requested_at = datetime.now(timezone.utc)

    if commit:
        db.commit()
        db.refresh(report)
    else:
        db.flush()
    return report


# Per-job switch read by the worker: a queued report whose report_json carries
# ``{"_regeneration": {"narrative": "deterministic"}}`` is rebuilt without any
# call to the (paid) narrative model.  The marker lives in the row being
# regenerated, so it survives retries and stale-claim recovery, and disappears
# automatically when the new report_json replaces it.  New completions are never
# marked and keep their normal narrative.
REGENERATION_KEY = "_regeneration"


def is_deterministic_job(report: DiagReport) -> bool:
    marker = (report.report_json or {}).get(REGENERATION_KEY) if isinstance(report.report_json, dict) else None
    return isinstance(marker, dict) and marker.get("narrative") == "deterministic"


def _is_current(report: Optional[DiagReport]) -> bool:
    return bool(
        report
        and report.report_json
        and report.report_schema_version >= REPORT_SCHEMA_VERSION
        and not (isinstance(report.report_json, dict) and report.report_json.get("report_meta", {}).get("degraded"))
    )


def list_stale_report_sessions(db: Session) -> list[tuple[uuid.UUID, int, str]]:
    """(session_id, current schema version, status) of every report that is not current."""
    out = []
    for session in db.query(DiagSession).filter(DiagSession.phase == "completed").order_by(DiagSession.completed_at, DiagSession.id).all():
        report = db.query(DiagReport).filter(DiagReport.session_id == session.id).first()
        if not _is_current(report):
            out.append((session.id, int(report.report_schema_version or 0) if report else -1,
                        report.generation_status if report else "missing"))
    return out


def enqueue_stale_report_generations(*, deterministic: bool = False) -> int:
    """Materialise missing reports and queue only stale derived documents.

    ``deterministic=True`` marks each queued job so that the worker skips the
    narrative model (see ``REGENERATION_KEY``).
    """
    db = SessionLocal()
    try:
        completed = db.query(DiagSession).filter(DiagSession.phase == "completed").all()
        queued = 0
        requested_at = datetime.now(timezone.utc)
        for session in completed:
            report = db.query(DiagReport).filter(DiagReport.session_id == session.id).first()
            # A manual stale rebuild must not resurrect a structurally current
            # report solely because an old worker wrote an operational status
            # incorrectly. In particular, startup must never create a new
            # external-model request for it.
            if _is_current(report):
                continue
            if report is None:
                report = DiagReport(
                    session_id=session.id,
                    student_id=session.student_id,
                    grade_level=session.grade_level,
                    overall_theta=session.theta,
                    overall_level=session.overall_level,
                    topic_breakdown=session.topic_breakdown or {},
                    weak_skills=session.weak_skills or [],
                    recommended_start=(session.weak_skills or [None])[0],
                    generation_attempts=0,
                )
                db.add(report)
            report.report_schema_version = 0
            if deterministic:
                report.report_json = {**(report.report_json or {}), REGENERATION_KEY: {"narrative": "deterministic"}}
            elif isinstance(report.report_json, dict) and REGENERATION_KEY in report.report_json:
                report.report_json = {k: v for k, v in report.report_json.items() if k != REGENERATION_KEY}
            report.generation_status = "pending"
            report.generation_stage = "queued"
            report.generation_error = None
            report.generation_attempts = 0
            # _claim_next_report deliberately accepts only explicitly queued
            # work. Without this timestamp a historical rebuild is displayed
            # as pending forever but can never be claimed by a worker.
            report.generation_requested_at = requested_at
            report.generation_started_at = None
            report.generation_completed_at = None
            queued += 1
        db.commit()
        return queued
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Targeted regeneration (content repairs) ───────────────────────────────────

_IN_CHUNK = 500
REFRESH_SOURCE = "regenerate_reports:refresh-task-content"


def _chunks(items: Sequence[Any], size: int = _IN_CHUNK):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _unique(items: Iterable[Any]) -> list:
    return list(dict.fromkeys(items))


def is_queued(report: Optional[DiagReport]) -> bool:
    """The report already has a live job: claimable ``pending`` (requested) or ``generating``."""
    if report is None:
        return False
    if report.generation_status == "generating":
        return True
    return report.generation_status == "pending" and report.generation_requested_at is not None


def find_regeneration_targets(
    db: Session, *, session_ids: Sequence[uuid.UUID] = (), task_ids: Sequence[str] = (),
) -> List[Dict[str, Any]]:
    """Sessions whose report should be rebuilt even if it is current, with the reason for each.

    * ``session_ids`` - exactly those sessions (a missing / not completed one is reported with ``skip``);
    * ``task_ids`` - completed sessions whose answers include any of those tasks.
    Both may be combined; a session picked twice lists both reasons.  Nothing is written.
    """
    reasons: Dict[uuid.UUID, List[str]] = {}
    skipped: Dict[uuid.UUID, str] = {}
    for session_id in _unique(session_ids):
        session = db.query(DiagSession).filter(DiagSession.id == session_id).first()
        if session is None:
            skipped[session_id] = "session not found"
        elif session.phase != "completed":
            skipped[session_id] = f"session is not completed (phase={session.phase})"
        else:
            reasons.setdefault(session_id, []).append("--session-id")

    wanted = _unique(str(t).strip() for t in task_ids if str(t).strip())
    answered: Dict[uuid.UUID, set] = {}
    for chunk in _chunks(wanted):
        rows = (
            db.query(DiagAnswer.session_id, DiagAnswer.task_id)
            .join(DiagSession, DiagSession.id == DiagAnswer.session_id)
            .filter(DiagSession.phase == "completed", DiagAnswer.task_id.in_(chunk))
            .distinct()
            .all()
        )
        for session_id, task_id in rows:
            answered.setdefault(session_id, set()).add(task_id)
    for session_id, tasks in answered.items():
        reasons.setdefault(session_id, []).append("answered task " + ", ".join(sorted(tasks)))

    completed_at: Dict[uuid.UUID, Any] = {}
    for chunk in _chunks(list(reasons)):
        for sid, when in db.query(DiagSession.id, DiagSession.completed_at).filter(DiagSession.id.in_(chunk)).all():
            completed_at[sid] = when
    ordered = sorted(reasons, key=lambda sid: (completed_at.get(sid) is None, completed_at.get(sid) or datetime.min, str(sid)))

    targets: List[Dict[str, Any]] = []
    for session_id in ordered:
        report = db.query(DiagReport).filter(DiagReport.session_id == session_id).first()
        targets.append({
            "session_id": session_id,
            "reasons": reasons[session_id],
            "skip": None,
            "report_status": report.generation_status if report else "missing",
            "report_schema_version": int(report.report_schema_version or 0) if report else None,
            "already_queued": is_queued(report),
        })
    for session_id, why in skipped.items():
        targets.append({
            "session_id": session_id, "reasons": ["--session-id"], "skip": why,
            "report_status": None, "report_schema_version": None, "already_queued": False,
        })
    return targets


def enqueue_forced_report_generations(
    session_ids: Sequence[uuid.UUID], *, deterministic: bool = True, db: Optional[Session] = None,
) -> Dict[str, List]:
    """Queue exactly these sessions' reports even when they are current (a content repair, not a schema bump).

    Same durable mechanism as the stale rebuild: the row becomes ``pending`` with ``generation_requested_at``
    set, the worker claims it and rebuilds with ``force=True``.  ``deterministic=True`` writes the per-job
    marker so the paid narrative model is not called.  The existing report stays readable until the new one
    replaces it (its schema version is not lowered).  A session that already has a live job (``pending`` /
    ``generating``) is not queued again; a missing or not completed session is reported as skipped.
    """
    own_session = db is None
    db = db or SessionLocal()
    queued: List[uuid.UUID] = []
    already: List[uuid.UUID] = []
    skipped: List[tuple] = []
    try:
        requested_at = datetime.now(timezone.utc)
        for session_id in _unique(session_ids):
            session = db.query(DiagSession).filter(DiagSession.id == session_id).first()
            if session is None or session.phase != "completed":
                skipped.append((session_id, "session not found" if session is None else "session is not completed"))
                continue
            report = db.query(DiagReport).filter(DiagReport.session_id == session_id).with_for_update().first()
            if is_queued(report):
                already.append(session_id)
                continue
            if report is None:
                report = DiagReport(
                    session_id=session.id,
                    student_id=session.student_id,
                    grade_level=session.grade_level,
                    overall_theta=session.theta,
                    overall_level=session.overall_level,
                    topic_breakdown=session.topic_breakdown or {},
                    weak_skills=session.weak_skills or [],
                    recommended_start=(session.weak_skills or [None])[0],
                    report_schema_version=0,
                    generation_attempts=0,
                )
                db.add(report)
            if deterministic:
                report.report_json = {**(report.report_json or {}), REGENERATION_KEY: {"narrative": "deterministic"}}
            elif isinstance(report.report_json, dict) and REGENERATION_KEY in report.report_json:
                report.report_json = {k: v for k, v in report.report_json.items() if k != REGENERATION_KEY}
            report.generation_status = "pending"
            report.generation_stage = "queued"
            report.generation_error = None
            report.generation_attempts = 0
            report.generation_requested_at = requested_at
            report.generation_started_at = None
            report.generation_completed_at = None
            queued.append(session_id)
        db.commit()
        return {"queued": queued, "already_queued": already, "skipped": skipped}
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()


def refresh_answer_task_snapshots(
    db: Session,
    task_repo: Any,
    *,
    session_ids: Sequence[uuid.UUID],
    task_ids: Sequence[str] = (),
    execute: bool = False,
    now: Optional[datetime] = None,
) -> Dict[str, int]:
    """Refresh the report-facing fields of ``diag_answers.task_snapshot`` from the current bank.

    A report is built from the snapshot stored with each answer (the live bank is read only for answers
    without one), so a content repair reaches a rebuilt report only after this refresh.  Only the
    ``task_snapshot`` column is written - never ``outcome``, ``student_answer`` or any other column of the
    append-only journal.  With ``task_ids`` only answers to those tasks are refreshed, otherwise every
    answer of the given sessions.  Answers without a snapshot are left as they are (the rebuild reads
    them live).  Dry-run (``execute=False``) fetches and counts but writes nothing.
    """
    from src.domain.task_display import build_diag_answer_options
    from src.domain.task_evidence import refresh_snapshot

    stats = {
        "examined": 0, "refreshed": 0, "would_refresh": 0, "unchanged": 0, "null_snapshot": 0,
        "missing_task": 0, "fetch_errors": 0, "build_errors": 0, "invalid_snapshot": 0,
        "display_options_kept": 0,
    }
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    wanted = _unique(str(t).strip() for t in task_ids if str(t).strip())
    live: Dict[str, Any] = {}

    def fetch(task_id: str):
        if task_id not in live:
            try:
                live[task_id] = task_repo.get_by_id(task_id)             # None == 404
            except Exception as exc:
                log.warning("refresh: cannot fetch task %s: %s", task_id, exc)
                live[task_id] = Ellipsis
        return live[task_id]

    for chunk in _chunks(_unique(session_ids)):
        query = db.query(DiagAnswer.id, DiagAnswer.session_id, DiagAnswer.task_id, DiagAnswer.task_snapshot).filter(
            DiagAnswer.session_id.in_(chunk)
        )
        if wanted:
            query = query.filter(DiagAnswer.task_id.in_(wanted))
        for answer_id, session_id, task_id, snapshot in query.order_by(DiagAnswer.id).all():
            stats["examined"] += 1
            if not snapshot:
                stats["null_snapshot"] += 1
                continue
            task = fetch(task_id)
            if task is Ellipsis:
                stats["fetch_errors"] += 1
                continue
            if task is None:
                stats["missing_task"] += 1
                continue
            try:
                options, options_latex = build_diag_answer_options(task, seed=f"{session_id}:{task.id}")
                refreshed, info = refresh_snapshot(
                    snapshot, task_id, task, options, options_latex, source=REFRESH_SOURCE, refreshed_at=stamp,
                )
            except ValueError as exc:                                     # invalid envelope / hash mismatch
                log.warning("refresh: answer %s has an unreadable snapshot: %s", answer_id, exc)
                stats["invalid_snapshot"] += 1
                continue
            except Exception as exc:
                log.warning("refresh: cannot rebuild answer %s task %s: %s", answer_id, task_id, exc)
                stats["build_errors"] += 1
                continue
            if info["display_options_kept"]:
                stats["display_options_kept"] += 1
            if refreshed is None:
                stats["unchanged"] += 1
                continue
            if not execute:
                stats["would_refresh"] += 1
                continue
            db.execute(update(DiagAnswer).where(DiagAnswer.id == answer_id).values(task_snapshot=refreshed))
            stats["refreshed"] += 1
    if execute:
        db.commit()
    else:
        db.rollback()
    return stats


def _claim_next_report(db: Session) -> Optional[tuple[DiagReport, DiagSession]]:
    report = (
        db.query(DiagReport)
        .filter(
            DiagReport.generation_status == "pending",
            # Historic rows created before the durable lifecycle are not
            # eligible for an implicit model call. They require an explicit
            # staff-triggered rebuild, which will set this timestamp.
            DiagReport.generation_requested_at.isnot(None),
            DiagReport.generation_attempts < MAX_GENERATION_ATTEMPTS,
        )
        .order_by(DiagReport.generated_at, DiagReport.id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if report is None:
        return None
    session = db.query(DiagSession).filter(DiagSession.id == report.session_id).first()
    if session is None or session.phase != "completed":
        report.generation_status = "failed"
        report.generation_stage = "failed"
        report.generation_error = "Completed diagnostic session is unavailable"
        report.generation_completed_at = datetime.now(timezone.utc)
        db.commit()
        return None

    report.generation_status = "generating"
    report.generation_stage = "collecting_evidence"
    report.generation_attempts += 1
    report.generation_started_at = datetime.now(timezone.utc)
    report.generation_error = None
    db.commit()
    return report, session


def recover_stale_report_jobs(db: Session) -> int:
    """Return abandoned worker claims to the durable queue.

    A web-process restart can interrupt a model call after a row has been
    claimed.  Those jobs must not remain ``generating`` forever.  We only
    recover genuinely stale claims, so an actively running worker keeps its
    exclusive claim.
    """
    cutoff = datetime.now(timezone.utc) - STALE_GENERATING_AFTER
    stale = (
        db.query(DiagReport)
        .filter(
            DiagReport.generation_status == "generating",
            DiagReport.generation_started_at.isnot(None),
            DiagReport.generation_started_at < cutoff,
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    for report in stale:
        if report.generation_attempts >= MAX_GENERATION_ATTEMPTS:
            report.generation_status = "failed"
            report.generation_stage = "failed"
            report.generation_error = "Превышено число попыток подготовки отчёта"
            report.generation_completed_at = datetime.now(timezone.utc)
        else:
            report.generation_status = "pending"
            report.generation_stage = "retry_queued"
            report.generation_error = "Предыдущая попытка была прервана"
    if stale:
        db.commit()
    return len(stale)


def process_next_report_job() -> bool:
    """Claim and process one pending report.  Safe to call from many workers."""
    db = SessionLocal()
    report_id: Optional[uuid.UUID] = None
    try:
        recover_stale_report_jobs(db)
        claimed = _claim_next_report(db)
        if claimed is None:
            return False
        report, session = claimed
        report_id = report.id
        settings = get_settings()
        from src.domain.alpha_engine import ThetaState, level_confidence
        snapshot_theta = _snapshot_value(session, "theta", {})
        classification_confidence = (
            level_confidence(ThetaState(**snapshot_theta))
            if snapshot_theta and snapshot_theta.get("posterior") else None
        )
        generated = generate_and_save_report(
            db,
            session_id=session.id,
            student_id=session.student_id,
            grade_level=session.grade_level,
            theta=float(session.theta or 0),
            theta_se=float(session.theta_se or 1),
            overall_level=session.overall_level or "at_grade",
            topic_breakdown=session.topic_breakdown or {},
            weak_skills=session.weak_skills or [],
            items_total=session.items_answered or 0,
            stop_reason=session.stop_reason,
            items_max=settings.max_items,
            covered_section_ids=_snapshot_value(session, "covered_section_ids", []),
            deep_scan_incomplete=bool(_snapshot_value(session, "deep_scan_incomplete", False)),
            deep_scan_params=_snapshot_value(session, "deep_scan_params", None),
            classification_confidence=classification_confidence,
            force=True,
            skip_narrative=is_deterministic_job(report),
        )
        if generated and generated.generation_status == "ready":
            return True

        # A deterministic report-building failure is retryable twice; after
        # that the UI exposes a recoverable failed state rather than hiding it.
        fresh = db.query(DiagReport).filter(DiagReport.id == report.id).first()
        if fresh and fresh.generation_attempts < MAX_GENERATION_ATTEMPTS:
            fresh.generation_status = "pending"
            fresh.generation_stage = "retry_queued"
            db.commit()
        return False
    except Exception as exc:
        db.rollback()
        log.exception("Report job failed before persistence: %s", exc)
        # Persist a deterministic lifecycle state in a fresh transaction.
        # Otherwise a failure after the claim would strand the row in
        # ``generating`` until a manual database repair.
        if report_id is not None:
            repair_db = SessionLocal()
            try:
                fresh = (
                    repair_db.query(DiagReport)
                    .filter(DiagReport.id == report_id)
                    .with_for_update()
                    .first()
                )
                if fresh:
                    fresh.generation_error = str(exc)[:1000]
                    if fresh.generation_attempts >= MAX_GENERATION_ATTEMPTS:
                        fresh.generation_status = "failed"
                        fresh.generation_stage = "failed"
                        fresh.generation_completed_at = datetime.now(timezone.utc)
                    else:
                        fresh.generation_status = "pending"
                        fresh.generation_stage = "retry_queued"
                    repair_db.commit()
            except Exception:
                repair_db.rollback()
                log.exception("Could not persist report-job recovery state")
            finally:
                repair_db.close()
        return False
    finally:
        db.close()
