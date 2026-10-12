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

TARGETED MODE (after content repairs).  Any of the flags below switches the script from "stale
reports" to "exactly these sessions", queued even when their report is current:
    --session-id UUID                 (repeatable) those sessions
    --affected-by-tasks T1,T2         completed sessions whose answers include any of these task ids
    --affected-by-tasks-file path     the same, ids from a file (commas / blanks / lines, '#' comments)
They combine (a session picked twice lists both reasons), and with --deterministic (default, no
LLM) / --with-narrative (paid, owner approval).  Dry-run by default: it lists every session id and
why it was selected; --execute queues them.  A session whose report is already pending/generating
is not queued again.

A report is built from the task copy stored with each answer (``diag_answers.task_snapshot``); the
live bank is read only for answers without a snapshot.  So a content repair does NOT reach a rebuilt
report by itself.  --refresh-task-content (targeted mode only) first refreshes, for the affected
answers, the report-facing snapshot fields (question, key, options, distractor explanations) from
content-service, marks the snapshot ``provenance = "bank_refresh"`` and never touches ``outcome`` or
``student_answer``; in dry-run it only counts.  With --affected-by-tasks only answers to those tasks
are refreshed, otherwise every answer of the selected sessions.

    python -m scripts.regenerate_reports --affected-by-tasks ds_llm_0007,ds_llm_0031 --refresh-task-content
    python -m scripts.regenerate_reports --affected-by-tasks-file fixed_tasks.txt --refresh-task-content --execute
    python -m scripts.regenerate_reports --session-id 3f1c...-... --session-id 9a2b...-... --execute
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.database import SessionLocal  # noqa: E402
from src.domain.report_generator import REPORT_SCHEMA_VERSION  # noqa: E402
from src.domain.report_jobs import (  # noqa: E402
    enqueue_forced_report_generations,
    enqueue_stale_report_generations,
    find_regeneration_targets,
    list_stale_report_sessions,
    refresh_answer_task_snapshots,
)

log = logging.getLogger("regenerate_reports")


def parse_task_ids(values: Sequence[str]) -> List[str]:
    """Task ids from ``--affected-by-tasks`` values / file text: commas, blanks and lines; '#' starts a comment."""
    ids: List[str] = []
    for value in values:
        for line in str(value).splitlines():
            line = line.split("#", 1)[0]
            ids.extend(part for part in re.split(r"[\s,;]+", line) if part)
    return list(dict.fromkeys(ids))


def run(
    *,
    execute: bool,
    with_narrative: bool = False,
    session_ids: Sequence[uuid.UUID] = (),
    task_ids: Sequence[str] = (),
    refresh_task_content: bool = False,
    db: Any = None,
    task_repo: Any = None,
) -> dict:
    """Stale mode without ``session_ids`` / ``task_ids``; targeted mode (forced) with either."""
    targeted = bool(session_ids or task_ids)
    if refresh_task_content and not targeted:
        raise ValueError("--refresh-task-content needs --session-id and/or --affected-by-tasks[-file]")
    own_session = db is None
    db = db or SessionLocal()
    try:
        if not targeted:
            stale = list_stale_report_sessions(db)
            result = {
                "mode": "execute" if execute else "dry-run",
                "target_schema_version": REPORT_SCHEMA_VERSION,
                "narrative": "llm" if with_narrative else "deterministic",
                "targeted": False,
                "stale": len(stale),
                "queued": 0,
                "sessions": [(str(sid), version, status) for sid, version, status in stale],
            }
            if execute:
                db.close() if own_session else None
                result["queued"] = enqueue_stale_report_generations(deterministic=not with_narrative)
            return result

        targets = find_regeneration_targets(db, session_ids=list(session_ids), task_ids=list(task_ids))
        selected = [t for t in targets if not t["skip"]]
        result = {
            "mode": "execute" if execute else "dry-run",
            "target_schema_version": REPORT_SCHEMA_VERSION,
            "narrative": "llm" if with_narrative else "deterministic",
            "targeted": True,
            "selected": len(selected),
            "queued": 0,
            "already_queued": sum(1 for t in selected if t["already_queued"]),
            "skipped": len(targets) - len(selected),
            "refresh": None,
            "sessions": [
                (str(t["session_id"]), "; ".join(t["reasons"]), t["report_status"], t["report_schema_version"],
                 t["skip"] or ("already queued" if t["already_queued"] else "will queue"))
                for t in targets
            ],
        }
        if refresh_task_content and selected:
            if task_repo is None:
                from src.repositories.knowledge_repo import TaskRepository
                task_repo = TaskRepository()
            result["refresh"] = refresh_answer_task_snapshots(
                db, task_repo, session_ids=[t["session_id"] for t in selected],
                task_ids=list(task_ids), execute=execute,
            )
        if execute:
            outcome = enqueue_forced_report_generations(
                [t["session_id"] for t in selected], deterministic=not with_narrative, db=db,
            )
            result["queued"] = len(outcome["queued"])
            result["already_queued"] = len(outcome["already_queued"])
        return result
    finally:
        if own_session:
            db.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--execute", action="store_true", help="queue the reports (default: dry-run)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--deterministic", action="store_true",
                       help="no LLM narrative (this is already the default)")
    group.add_argument("--with-narrative", action="store_true",
                       help="allow the paid narrative model (requires owner approval)")
    parser.add_argument("--session-id", action="append", type=uuid.UUID, default=[], metavar="UUID",
                        help="targeted: re-queue this session's report even if current (repeatable)")
    parser.add_argument("--affected-by-tasks", action="append", default=[], metavar="TASK_ID[,TASK_ID...]",
                        help="targeted: re-queue completed sessions whose answers include these task ids")
    parser.add_argument("--affected-by-tasks-file", action="append", default=[], metavar="PATH",
                        help="targeted: like --affected-by-tasks, ids read from a file")
    parser.add_argument("--refresh-task-content", action="store_true",
                        help="targeted: refresh the affected answers' task snapshots from content-service first")
    args = parser.parse_args(argv)
    task_ids = parse_task_ids(args.affected_by_tasks)
    for path in args.affected_by_tasks_file:
        task_ids = list(dict.fromkeys(task_ids + parse_task_ids([Path(path).read_text(encoding="utf-8")])))
    targeted = bool(args.session_id or task_ids)
    if (args.affected_by_tasks or args.affected_by_tasks_file) and not task_ids and not args.session_id:
        parser.error("no task ids found in --affected-by-tasks / --affected-by-tasks-file")
    if args.refresh_task_content and not targeted:
        parser.error("--refresh-task-content needs --session-id and/or --affected-by-tasks[-file]")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run(
        execute=args.execute, with_narrative=args.with_narrative, session_ids=args.session_id,
        task_ids=task_ids, refresh_task_content=args.refresh_task_content,
    )
    if not result["targeted"]:
        log.info("%s: target schema %d, stale=%d queued=%d narrative=%s", result["mode"],
                 result["target_schema_version"], result["stale"], result["queued"], result["narrative"])
        for sid, version, status in result["sessions"][:100]:
            log.info("  %s schema=%s status=%s", sid, version, status)
        if not args.execute:
            log.info("dry-run only; add --execute to queue them")
        return 0
    log.info("%s (targeted): selected=%d queued=%d already_queued=%d skipped=%d narrative=%s", result["mode"],
             result["selected"], result["queued"], result["already_queued"], result["skipped"], result["narrative"])
    for sid, why, status, version, action in result["sessions"][:1000]:
        log.info("  %s  why: %s  report=%s schema=%s -> %s", sid, why, status, version, action)
    if len(result["sessions"]) > 1000:
        log.info("  ... and %d more", len(result["sessions"]) - 1000)
    if result["refresh"] is not None:
        log.info("task snapshots (%s): %s", "written" if args.execute else "would be written",
                 " ".join(f"{k}={v}" for k, v in result["refresh"].items()))
    if not args.execute:
        log.info("dry-run only; add --execute to %squeue them", "refresh the snapshots and " if args.refresh_task_content else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
