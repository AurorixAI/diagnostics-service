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
content-service.  The rules:
  * only the ``task_snapshot`` column is written (UPDATE ... WHERE id AND task_snapshot = <read>), never
    ``outcome`` / ``student_answer``; ``display_*`` (what the student saw) is never replaced;
  * the old snapshots are first written to a JSONL backup (--backup PATH, default /app/backups/...);
    no backup, no write; --restore-from BACKUP [--execute] puts them back (newest backup first);
    each snapshot also keeps ``refresh_history`` (hash + provenance it replaced), provenance becomes
    "bank_refresh";
  * inactive tasks and live tasks with an empty question or key are skipped; a missing task, a fetch
    error, an unreadable snapshot or a build error are FAILURES: exit code 2, the session is not
    written and not queued (--allow-partial goes on, exit code 3);
  * dry-run lists per answer the changed fields and integrity flags (key_changed,
    student_answer_equals_new_key_but_outcome<1, new_key_not_in_display_options, question_changed);
    answers with a flag are NOT refreshed, unless --allow-key-change, which refreshes them WITHOUT
    replacing key and question - a report never contradicts the stored outcome;
  * the sessions' report rows are locked like the worker's claim (FOR UPDATE SKIP LOCKED): a
    ``generating`` report is "busy" (exit code 4) - run when the report worker is idle; a ``pending``
    job reads the new snapshots when it is claimed;
  * needs the NEW image on every worker (an older image rejects a "bank_refresh" snapshot).
With --affected-by-tasks only answers to those tasks are refreshed, otherwise every answer of the
selected sessions.

    python -m scripts.regenerate_reports --affected-by-tasks ds_llm_0007,ds_llm_0031 --refresh-task-content
    python -m scripts.regenerate_reports --affected-by-tasks-file fixed_tasks.txt --refresh-task-content --execute
    python -m scripts.regenerate_reports --session-id 3f1c...-... --session-id 9a2b...-... --execute
    python -m scripts.regenerate_reports --restore-from <backup.jsonl> --execute

RUNBOOK for --refresh-task-content (it rewrites diag_answers.task_snapshot; outcome / student_answer never)
  0. Image: run it ONLY after the new image is deployed on EVERY worker (an older image cannot read a
     "bank_refresh" snapshot and would fail those reports).  Do NOT roll the image back after --execute;
     restore the snapshots first (step 5) if you must.
  1. Worker idle: run when the report worker has nothing pending/generating.  The script locks each
     session's report row like the worker's claim (SKIP LOCKED) and refuses a generating session (exit 4,
     "busy": nothing of it is written, run again); a pending job simply reads the new snapshots.
  2. Dry-run first (no --execute): per answer the changed fields and flags (key_changed, ...); inactive
     / deleted (404) tasks are skipped with a warning; failures (fetch/build/unreadable/blank task) exit 2.
  3. Backup: --execute REQUIRES --backup PATH|-.  A file lives inside the container, copy it out at once:
         docker exec <svc> python -m scripts.regenerate_reports <selectors> --refresh-task-content --execute --backup /tmp/b.jsonl
         docker cp "$HOSTNAME":/tmp/b.jsonl ./        (the script prints the exact command, rows and sha256)
     or stream it to the host:  docker exec <svc> python -m scripts.regenerate_reports ... --backup - > backup.jsonl
  4. The pre-image also stays in each row: snapshot.refresh_history[-1].previous_task (verified against
     previous_sha256), so the backup file is a second copy, not the only one.
  5. Undo: --restore-last with the same selectors (from the rows themselves), or --restore-from backup.jsonl
     (newest backup first; rows that changed since are "diverged" and left alone).  Both are dry-run by
     default, take the report lock, and re-queue the affected reports (deterministic).
  6. Plain-SQL fallback (psql, per answer; the previous snapshot is rebuilt from the history):
         UPDATE diag_answers a SET task_snapshot = (a.task_snapshot - 'task' - 'sha256' - 'provenance' - 'refresh_history')
             || jsonb_build_object('version', 1, 'task', h->'previous_task', 'sha256', h->>'previous_sha256',
                'provenance', h->>'previous_provenance')
             || CASE WHEN jsonb_array_length(a.task_snapshot->'refresh_history') > 1
                     THEN jsonb_build_object('refresh_history', (a.task_snapshot->'refresh_history') - -1) ELSE '{}'::jsonb END
         FROM (SELECT id, task_snapshot->'refresh_history'->-1 AS h FROM diag_answers
               WHERE id = '<answer uuid>' AND task_snapshot->>'provenance' = 'bank_refresh') s
         WHERE a.id = s.id;
     (or load the backup rows: UPDATE ... SET task_snapshot = '<old json>'::jsonb WHERE id = '<answer uuid>').
     Then re-queue the reports: --session-id <uuid> --execute.
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
    BackupError,
    REFRESH_FAILURES,
    enqueue_forced_report_generations,
    enqueue_stale_report_generations,
    find_regeneration_targets,
    list_stale_report_sessions,
    refresh_answer_task_snapshots,
    restore_latest_refresh,
    restore_task_snapshots,
)

EXIT_OK, EXIT_FAILURES, EXIT_PARTIAL, EXIT_BUSY, EXIT_BACKUP = 0, 2, 3, 4, 5

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
    allow_key_change: bool = False,
    allow_partial: bool = False,
    backup_path: Optional[str] = None,
    db: Any = None,
    task_repo: Any = None,
) -> dict:
    """Stale mode without ``session_ids`` / ``task_ids``; targeted mode (forced) with either.

    The result carries ``exit_code``: 0 ok; 2 refresh failures, those sessions were NOT queued; 3 failures
    but ``allow_partial`` went on; 4 a session was busy (generating) - run again when the worker is idle.
    """
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
                "exit_code": EXIT_OK,
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
            "refresh_details": None,
            "exit_code": EXIT_OK,
            "sessions": [],
        }
        excluded: set = set()
        if refresh_task_content and selected:
            if task_repo is None:
                from src.repositories.knowledge_repo import TaskRepository
                task_repo = TaskRepository()
            details = refresh_answer_task_snapshots(
                db, task_repo, session_ids=[t["session_id"] for t in selected], task_ids=list(task_ids),
                execute=execute, allow_key_change=allow_key_change, allow_partial=allow_partial,
                backup_path=backup_path,
            )
            result["refresh"], result["refresh_details"] = details["stats"], details
            excluded = set(details["excluded_sessions"])
            failures = sum(details["stats"][k] for k in REFRESH_FAILURES)
            if failures and not allow_partial:
                result["exit_code"] = EXIT_FAILURES
            elif details["busy_sessions"]:
                result["exit_code"] = EXIT_BUSY
            elif failures:
                result["exit_code"] = EXIT_PARTIAL
        for t in targets:
            if t["skip"]:
                action = t["skip"]
            elif t["session_id"] in excluded:
                busy = refresh_task_content and t["session_id"] in set(result["refresh_details"]["busy_sessions"])
                action = "busy (generating): run again when the worker is idle" if busy else "held back: refresh failed"
            else:
                action = "already queued" if t["already_queued"] else "will queue"
            result["sessions"].append((
                str(t["session_id"]), "; ".join(t["reasons"]), t["report_status"], t["report_schema_version"], action,
            ))
        if execute:
            outcome = enqueue_forced_report_generations(
                [t["session_id"] for t in selected if t["session_id"] not in excluded],
                deterministic=not with_narrative, db=db,
            )
            result["queued"] = len(outcome["queued"])
            result["already_queued"] = len(outcome["already_queued"])
        return result
    finally:
        if own_session:
            db.close()


def _restore_exit_code(stats: dict) -> int:
    if stats.get("invalid_rows") or stats.get("diverged") or stats.get("unverifiable"):
        return EXIT_FAILURES
    if stats.get("busy") or stats.get("skipped_concurrent"):
        return EXIT_BUSY
    return EXIT_OK


def run_restore(*, backup_path: str, execute: bool, with_narrative: bool = False, db: Any = None) -> dict:
    """Snapshots back from a --backup file; the affected reports are re-queued (deterministic by default)."""
    own_session = db is None
    db = db or SessionLocal()
    try:
        stats = restore_task_snapshots(db, backup_path, execute=execute, deterministic=not with_narrative)
        return {"mode": "execute" if execute else "dry-run", "backup": backup_path, "restore": stats,
                "exit_code": _restore_exit_code(stats)}
    finally:
        if own_session:
            db.close()


def run_restore_last(
    *, session_ids: Sequence[uuid.UUID], task_ids: Sequence[str] = (), execute: bool, with_narrative: bool = False,
    db: Any = None,
) -> dict:
    """Undo the latest refresh of the selected answers from their own refresh_history (no file needed)."""
    own_session = db is None
    db = db or SessionLocal()
    try:
        stats = restore_latest_refresh(
            db, session_ids=_sessions_for(db, session_ids, task_ids), task_ids=task_ids, execute=execute,
            deterministic=not with_narrative,
        )
        return {"mode": "execute" if execute else "dry-run", "restore": stats, "exit_code": _restore_exit_code(stats)}
    finally:
        if own_session:
            db.close()


def _sessions_for(db: Any, session_ids: Sequence[uuid.UUID], task_ids: Sequence[str]) -> List[uuid.UUID]:
    targets = find_regeneration_targets(db, session_ids=list(session_ids), task_ids=list(task_ids))
    db.rollback()
    return [t["session_id"] for t in targets if not t["skip"]]


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
                        help="targeted: first refresh the affected answers' task snapshots from content-service. "
                             "Needs the NEW image on every worker (an older image cannot read a refreshed snapshot); "
                             "run it when the report worker is idle")
    parser.add_argument("--backup", metavar="PATH|-", default=None,
                        help="MANDATORY with --execute: JSONL backup of the snapshots about to be overwritten. A file "
                             "inside the container (then copy it out: docker cp \"$HOSTNAME\":PATH ./) or - for stdout "
                             "(logs go to stderr): docker exec ... --backup - > backup.jsonl")
    parser.add_argument("--allow-key-change", action="store_true",
                        help="refresh answers whose key / question changed or whose verdict would contradict the new "
                             "key - WITHOUT replacing key and question (default: such answers are skipped)")
    parser.add_argument("--allow-partial", action="store_true",
                        help="queue sessions although some of their answers failed to refresh (exit code 3)")
    parser.add_argument("--restore-from", metavar="BACKUP", default=None,
                        help="put the snapshots of a --backup file back (dry-run unless --execute); restore the newest "
                             "backup first; the affected reports are re-queued")
    parser.add_argument("--restore-last", action="store_true",
                        help="undo the latest refresh of the selected answers (--session-id / --affected-by-tasks[-file]) "
                             "from the pre-image kept in each row's refresh_history - no backup file needed "
                             "(dry-run unless --execute); the affected reports are re-queued")
    args = parser.parse_args(argv)
    task_ids = parse_task_ids(args.affected_by_tasks)
    for path in args.affected_by_tasks_file:
        task_ids = list(dict.fromkeys(task_ids + parse_task_ids([Path(path).read_text(encoding="utf-8")])))
    targeted = bool(args.session_id or task_ids)
    if (args.affected_by_tasks or args.affected_by_tasks_file) and not task_ids and not args.session_id:
        parser.error("no task ids found in --affected-by-tasks / --affected-by-tasks-file")
    if args.refresh_task_content and not targeted:
        parser.error("--refresh-task-content needs --session-id and/or --affected-by-tasks[-file]")
    if (args.allow_key_change or args.allow_partial or args.backup) and not args.refresh_task_content:
        parser.error("--backup / --allow-key-change / --allow-partial belong to --refresh-task-content")
    if args.refresh_task_content and args.execute and not args.backup:
        parser.error("--backup PATH (or - for stdout) is mandatory with --refresh-task-content --execute")
    if args.restore_from and (targeted or args.refresh_task_content or args.restore_last):
        parser.error("--restore-from is a mode of its own")
    if args.restore_last and (args.refresh_task_content or not targeted):
        parser.error("--restore-last needs --session-id and/or --affected-by-tasks[-file] and is a mode of its own")
    # stdout may carry the backup (--backup -): every log line goes to stderr
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)

    if args.restore_from or args.restore_last:
        if args.restore_from:
            result = run_restore(backup_path=args.restore_from, execute=args.execute, with_narrative=args.with_narrative)
            label = f"restore from {args.restore_from}"
        else:
            result = run_restore_last(session_ids=args.session_id, task_ids=task_ids, execute=args.execute,
                                      with_narrative=args.with_narrative)
            label = "restore-last (from refresh_history)"
        log.info("%s %s: %s", result["mode"], label, " ".join(f"{k}={v}" for k, v in result["restore"].items()))
        if not args.execute:
            log.info("dry-run only; add --execute to write the old snapshots back (the reports are then re-queued)")
        if result["exit_code"]:
            log.error("exit code %d (2 = rows that could not be restored: diverged / invalid / unverifiable; "
                      "4 = busy report or concurrent change: run again when the worker is idle)", result["exit_code"])
        return result["exit_code"]

    try:
        result = run(
            execute=args.execute, with_narrative=args.with_narrative, session_ids=args.session_id,
            task_ids=task_ids, refresh_task_content=args.refresh_task_content,
            allow_key_change=args.allow_key_change, allow_partial=args.allow_partial, backup_path=args.backup,
        )
    except BackupError as exc:
        log.error("%s - nothing was changed", exc)
        return EXIT_BACKUP
    if not result["targeted"]:
        log.info("%s: target schema %d, stale=%d queued=%d narrative=%s", result["mode"],
                 result["target_schema_version"], result["stale"], result["queued"], result["narrative"])
        for sid, version, status in result["sessions"][:100]:
            log.info("  %s schema=%s status=%s", sid, version, status)
        if not args.execute:
            log.info("dry-run only; add --execute to queue them")
        return result["exit_code"]
    log.info("%s (targeted): selected=%d queued=%d already_queued=%d skipped=%d narrative=%s", result["mode"],
             result["selected"], result["queued"], result["already_queued"], result["skipped"], result["narrative"])
    for sid, why, status, version, action in result["sessions"][:1000]:
        log.info("  %s  why: %s  report=%s schema=%s -> %s", sid, why, status, version, action)
    if len(result["sessions"]) > 1000:
        log.info("  ... and %d more", len(result["sessions"]) - 1000)
    details = result["refresh_details"]
    if details is not None:
        log.info("task snapshots (%s): %s", "written" if args.execute else "would be written",
                 " ".join(f"{k}={v}" for k, v in details["stats"].items() if v))
        backup = details["backup"]
        if backup:
            if backup["stdout"]:
                log.info("backup of the overwritten snapshots written to stdout: rows=%d sha256=%s",
                         backup["rows"], backup["sha256"])
            else:
                log.info("backup of the overwritten snapshots: %s rows=%d sha256=%s", backup["path"], backup["rows"],
                         backup["sha256"])
                log.info('copy it out of the container:  docker cp "$HOSTNAME":%s ./', backup["path"])
            log.info("undo: --restore-last (from the rows themselves) or --restore-from <backup> --execute")
        shown = 0
        for item in details["items"]:
            if (item["changed"] or item["flags"] or item["status"] in REFRESH_FAILURES) and shown < 1000:
                shown += 1
                log.info("  answer %s session %s task %s: %s changed=%s flags=%s %s", item["answer_id"],
                         item["session_id"], item["task_id"], item["status"], item["changed"] or "-",
                         item["flags"] or "-", item["reason"])
        if details["inactive_tasks"]:
            log.warning("inactive tasks skipped: %s", ", ".join(details["inactive_tasks"]))
        if details["missing_tasks"]:
            log.warning("tasks deleted from the bank (404) skipped: %s", ", ".join(details["missing_tasks"]))
        for failure in details["failed"]:
            log.error("FAILED answer %(answer_id)s task %(task_id)s session %(session_id)s: %(status)s %(reason)s", failure)
        if details["busy_sessions"]:
            log.warning("busy (report generating / locked, or an answer changed meanwhile) - NOT rewritten, not queued; "
                        "run again when the worker is idle: %s",
                        ", ".join(str(s) for s in details["busy_sessions"]))
    if result["exit_code"]:
        log.error("exit code %d (2 = refresh failures, those sessions not queued; 3 = failures with --allow-partial; "
                  "4 = busy sessions, run again when the worker is idle)", result["exit_code"])
    if not args.execute:
        log.info("dry-run only; add --execute to %squeue them", "refresh the snapshots and " if args.refresh_task_content else "")
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
