#!/usr/bin/env python3
"""Re-send the auth completion sync of already-completed sessions (N02 backfill).

New completions carry the ready-made level (``overall_level``, ``level_status``,
``level_provisional``) in the auth completion payload.  Old
results in auth-service lack those fields.  This script re-queues the EXISTING
durable outbox (``diag_sessions.auth_sync_*`` + ``enqueue_auth_completion_sync``);
the normal lifespan worker then delivers the callback (retries, stale-claim
recovery and attempt limits are the ones already used for live completions).  It
makes no HTTP call itself and never touches answers, reports or theta.

Run it AFTER the reports were regenerated under the current
``REPORT_SCHEMA_VERSION`` (``report_jobs.enqueue_stale_report_generations`` /
the report worker).  A session is selected only when

  * it is completed and has an invite code (auth knows it),
  * its report is ready and on the current schema (``--allow-stale-report`` lifts
    this), and
  * auth was not synced after that report was generated
    (``auth_sync_completed_at`` is NULL or older than the report's
    ``generation_completed_at``),
  * and no sync is already queued (``pending``/``syncing``).

That makes the script idempotent: once the worker has delivered a session its
``auth_sync_completed_at`` is newer than the report, so a re-run selects nothing.

Usage (inside the service container, WORKDIR /app):
    python -m scripts.resync_auth_levels                 # dry-run: lists counts/ids only
    python -m scripts.resync_auth_levels --execute       # queue the callbacks
    python -m scripts.resync_auth_levels --force --execute   # re-send ALL (one-off, e.g. auth now stores totals)
Options: --limit N (max sessions), --session-id UUID (repeatable), --allow-stale-report,
--force (ignore "already synced after the report"; still needs a ready current-schema
report and skips sessions whose sync is already pending/syncing; running it twice before
the worker delivers queues nothing new, but after delivery --force queues them again).
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, or_  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.core.database import SessionLocal  # noqa: E402
from src.domain.auth_sync_jobs import enqueue_auth_completion_sync  # noqa: E402
from src.domain.report_generator import REPORT_SCHEMA_VERSION  # noqa: E402
from src.models.diag_models import DiagReport, DiagSession  # noqa: E402

log = logging.getLogger("resync_auth_levels")


def select_sessions(
    db: Session,
    *,
    limit: Optional[int] = None,
    session_ids: Optional[List[uuid.UUID]] = None,
    allow_stale_report: bool = False,
    force: bool = False,
) -> List[DiagSession]:
    query = (
        db.query(DiagSession)
        .outerjoin(DiagReport, DiagReport.session_id == DiagSession.id)
        .filter(
            DiagSession.phase == "completed",
            DiagSession.invite_code.isnot(None),
            DiagSession.auth_sync_status.notin_(("pending", "syncing")),
        )
    )
    if force:
        # Every completed session with a current-schema report, regardless of
        # when it was last synced (auth now also updates totals).
        query = query.filter(
            DiagReport.generation_status == "ready",
            DiagReport.report_json.isnot(None),
            DiagReport.report_schema_version >= REPORT_SCHEMA_VERSION,
        )
    elif not allow_stale_report:
        query = query.filter(
            DiagReport.generation_status == "ready",
            DiagReport.report_json.isnot(None),
            DiagReport.report_schema_version >= REPORT_SCHEMA_VERSION,
            or_(
                DiagSession.auth_sync_completed_at.is_(None),
                DiagSession.auth_sync_completed_at < DiagReport.generation_completed_at,
            ),
        )
    else:
        query = query.filter(
            or_(
                DiagSession.auth_sync_completed_at.is_(None),
                and_(
                    DiagReport.generation_completed_at.isnot(None),
                    DiagSession.auth_sync_completed_at < DiagReport.generation_completed_at,
                ),
            )
        )
    if session_ids:
        query = query.filter(DiagSession.id.in_(session_ids))
    query = query.order_by(DiagSession.completed_at, DiagSession.id)
    if limit:
        query = query.limit(limit)
    return query.all()


def run(*, execute: bool, limit: Optional[int], session_ids: Optional[List[uuid.UUID]],
        allow_stale_report: bool, force: bool = False, db: Optional[Session] = None) -> dict:
    own = db is None
    db = db or SessionLocal()
    try:
        sessions = select_sessions(
            db, limit=limit, session_ids=session_ids, allow_stale_report=allow_stale_report,
            force=force,
        )
        if execute:
            for session in sessions:
                enqueue_auth_completion_sync(db, session, commit=False)
            db.commit()
        return {
            "mode": "execute" if execute else "dry-run",
            "selected": len(sessions),
            "queued": len(sessions) if execute else 0,
            "session_ids": [str(s.id) for s in sessions],
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--execute", action="store_true", help="queue the callbacks (default: dry-run)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--session-id", action="append", type=uuid.UUID, default=None)
    parser.add_argument("--allow-stale-report", action="store_true",
                        help="do not require reports to be regenerated on the current schema first")
    parser.add_argument("--force", action="store_true",
                        help="re-queue every completed session with a current-schema report, "
                             "even if auth was already synced after the report")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run(
        execute=args.execute, limit=args.limit, session_ids=args.session_id,
        allow_stale_report=args.allow_stale_report, force=args.force,
    )
    log.info("%s: selected=%d queued=%d", result["mode"], result["selected"], result["queued"])
    for sid in result["session_ids"][:50]:
        log.info("  %s", sid)
    if not args.execute:
        log.info("dry-run only; add --execute to queue the callbacks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
