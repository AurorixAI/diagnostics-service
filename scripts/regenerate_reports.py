#!/usr/bin/env python3
"""Queue regeneration of diagnostic reports that are not on the current schema.

Bumping ``REPORT_SCHEMA_VERSION`` regenerates nothing by itself: stale reports
keep being served until a job is queued.  This script queues them through the
existing durable mechanism (``report_jobs.enqueue_stale_report_generations``);
the service's lifespan worker (polls every ~2 s) then rebuilds each one.  The
script itself builds nothing and makes no HTTP call.

A report is "stale" when it is missing, has no report_json, is on an older
``report_schema_version``, or was saved degraded (content-service was down while
it was built).  Answers are never modified; the rebuild reads the append-only
answer journal and the stored task snapshots.

NO LLM BY DEFAULT.  Paid narrative calls need the owner's approval, so the jobs
are queued with the per-job "deterministic" marker (the worker then writes the
deterministic summary/plan and does not call the model).  Pass --with-narrative
only with that approval.  --deterministic is accepted as an explicit no-op
spelling of the default.

Order of a rollout:
    1. deploy the image (alembic 010 runs at start-up),
    2. python -m scripts.regenerate_reports                      # dry-run: lists stale reports
    3. python -m scripts.regenerate_reports --execute            # queue (deterministic, no LLM)
    4. wait until the dry-run lists nothing / statuses are 'ready'
    5. python -m scripts.resync_auth_levels                      # dry-run, then --execute

Usage (inside the service container, WORKDIR /app):
    python -m scripts.regenerate_reports                 # dry-run
    python -m scripts.regenerate_reports --execute       # queue, deterministic
    python -m scripts.regenerate_reports --execute --with-narrative   # needs owner approval
Idempotent: a report that is current is never re-queued; re-running only queues
what is still stale.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.database import SessionLocal  # noqa: E402
from src.domain.report_generator import REPORT_SCHEMA_VERSION  # noqa: E402
from src.domain.report_jobs import (  # noqa: E402
    enqueue_stale_report_generations,
    list_stale_report_sessions,
)

log = logging.getLogger("regenerate_reports")


def run(*, execute: bool, with_narrative: bool = False) -> dict:
    db = SessionLocal()
    try:
        stale = list_stale_report_sessions(db)
    finally:
        db.close()
    result = {
        "mode": "execute" if execute else "dry-run",
        "target_schema_version": REPORT_SCHEMA_VERSION,
        "narrative": "llm" if with_narrative else "deterministic",
        "stale": len(stale),
        "queued": 0,
        "sessions": [(str(sid), version, status) for sid, version, status in stale],
    }
    if execute:
        result["queued"] = enqueue_stale_report_generations(deterministic=not with_narrative)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--execute", action="store_true", help="queue the stale reports (default: dry-run)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--deterministic", action="store_true",
                       help="no LLM narrative (this is already the default)")
    group.add_argument("--with-narrative", action="store_true",
                       help="allow the paid narrative model (requires owner approval)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run(execute=args.execute, with_narrative=args.with_narrative)
    log.info("%s: target schema %d, stale=%d queued=%d narrative=%s", result["mode"],
             result["target_schema_version"], result["stale"], result["queued"], result["narrative"])
    for sid, version, status in result["sessions"][:100]:
        log.info("  %s schema=%s status=%s", sid, version, status)
    if not args.execute:
        log.info("dry-run only; add --execute to queue them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
