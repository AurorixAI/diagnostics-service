#!/usr/bin/env python3
"""Backfill diag_answers.task_snapshot for answers recorded before migration 009.

For every answer whose snapshot is NULL the task is fetched from content-service
through the same repository / option builder / capture function the live service
uses (``TaskRepository.get_by_id`` -> ``build_diag_answer_options`` with the
per-session seed -> ``capture_task``), so the snapshot has the identical shape.

Honest provenance: the bank may have been repaired since the student answered, so
the stored copy is best-effort, NOT the exact issued content.  It is marked
``provenance = "legacy_bank_backfill"`` and carries ``backfill_source`` (script
tag) and ``backfilled_at`` next to ``version/task/sha256``.  ``sha256`` still
covers only ``task`` so ``read_task`` verifies it unchanged.

Safe to re-run: only rows with a NULL (SQL NULL or JSON null) snapshot are
touched, each UPDATE re-checks that condition, tasks missing in the bank (or
unreachable) stay NULL and are only counted.

Usage (inside the service container, WORKDIR /app):
    python -m scripts.backfill_task_snapshots               # dry-run: counts only
    python -m scripts.backfill_task_snapshots --execute     # write, commit per batch
Options: --batch-size N (default 200), --limit N (max rows to examine).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, or_, update  # noqa: E402

from src.domain.task_display import (  # noqa: E402
    build_diag_answer_options,
    diag_answer_type_for_display,
)
from src.domain.task_evidence import capture_task  # noqa: E402
from src.models.diag_models import DiagAnswer  # noqa: E402

BACKFILL_SOURCE = "backfill_2026-10-06"
PROVENANCE = "legacy_bank_backfill"

log = logging.getLogger("backfill_task_snapshots")

_MISSING = object()


def _no_snapshot():
    return or_(
        DiagAnswer.task_snapshot.is_(None),
        func.jsonb_typeof(DiagAnswer.task_snapshot) == "null",
    )


def build_snapshot(task, session_id) -> Dict[str, Any]:
    """Same pipeline as SessionService's legacy answer lookup."""
    options, options_latex = build_diag_answer_options(task, seed=f"{session_id}:{task.id}")
    snapshot = capture_task(
        task, options, options_latex, diag_answer_type_for_display(task, options),
        provenance=PROVENANCE,
    )
    snapshot["backfill_source"] = BACKFILL_SOURCE
    snapshot["backfilled_at"] = datetime.now(timezone.utc).isoformat()
    return snapshot


def run(db, task_repo, *, execute: bool = False, batch_size: int = 200,
        limit: int = 0) -> Dict[str, int]:
    """Process NULL-snapshot answers; returns counters. Commits per batch when executing."""
    stats = {"examined": 0, "filled": 0, "would_fill": 0, "missing_task": 0,
             "fetch_errors": 0, "build_errors": 0, "skipped_concurrent": 0}
    tasks: Dict[str, Any] = {}          # task_id -> task | None (missing) | _MISSING sentinel for error
    last_id: Optional[Any] = None

    def fetch(task_id: str):
        if task_id in tasks:
            return tasks[task_id]
        try:
            tasks[task_id] = task_repo.get_by_id(task_id)   # None == 404
        except Exception as exc:
            log.warning("fetch failed for %s: %s", task_id, exc)
            tasks[task_id] = _MISSING
        return tasks[task_id]

    while True:
        q = db.query(DiagAnswer.id, DiagAnswer.session_id, DiagAnswer.task_id).filter(_no_snapshot())
        if last_id is not None:
            q = q.filter(DiagAnswer.id > last_id)
        take = batch_size
        if limit:
            take = min(take, limit - stats["examined"])
            if take <= 0:
                break
        rows = q.order_by(DiagAnswer.id).limit(take).all()
        if not rows:
            break
        for answer_id, session_id, task_id in rows:
            last_id = answer_id
            stats["examined"] += 1
            task = fetch(task_id)
            if task is _MISSING:
                stats["fetch_errors"] += 1
                continue
            if task is None:
                stats["missing_task"] += 1
                continue
            try:
                snapshot = build_snapshot(task, session_id)
            except Exception as exc:
                log.warning("cannot build snapshot for answer %s task %s: %s", answer_id, task_id, exc)
                stats["build_errors"] += 1
                continue
            if not execute:
                stats["would_fill"] += 1
                continue
            result = db.execute(
                update(DiagAnswer)
                .where(DiagAnswer.id == answer_id, _no_snapshot())
                .values(task_snapshot=snapshot)
            )
            if result.rowcount:
                stats["filled"] += 1
            else:
                stats["skipped_concurrent"] += 1
        if execute:
            db.commit()
        else:
            db.rollback()
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backfill diag_answers.task_snapshot (dry-run by default)")
    parser.add_argument("--execute", action="store_true", help="write snapshots (default: dry-run, counts only)")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--limit", type=int, default=0, help="max NULL rows to examine (0 = all)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from src.core.database import SessionLocal
    from src.repositories.knowledge_repo import TaskRepository

    db = SessionLocal()
    try:
        total_null = db.query(func.count(DiagAnswer.id)).filter(_no_snapshot()).scalar()
        print(f"mode={'EXECUTE' if args.execute else 'DRY-RUN'} null_snapshots={total_null}")
        stats = run(db, TaskRepository(), execute=args.execute,
                    batch_size=args.batch_size, limit=args.limit)
        print(" ".join(f"{k}={v}" for k, v in stats.items()))
        remaining = db.query(func.count(DiagAnswer.id)).filter(_no_snapshot()).scalar()
        print(f"remaining_null={remaining}")
        return 1 if (stats["fetch_errors"] or stats["build_errors"]) else 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
