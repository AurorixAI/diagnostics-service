#!/usr/bin/env python3
"""Safely rebuild stale diagnostic error journals from append-only answers.

Default mode is dry-run.  The script derives entries exclusively from
``diag_answers.session_id`` and ``diag_answers.task_id``; it never guesses a
task by text, skill, or a fuzzy match.  ``--execute`` requires an explicit
backup directory and confirmation token before it writes report_json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.domain.report_generator import (  # noqa: E402
    ERROR_PATTERNS_VERSION,
    _build_error_patterns,
    _resolve_skill,
)
from src.core.db_timezone import utc_connect_args  # noqa: E402
from src.models.diag_models import DiagAnswer, DiagReport  # noqa: E402
from src.repositories.knowledge_repo import KnowledgeRepository  # noqa: E402


def is_stale_report(report_json: object) -> bool:
    if not isinstance(report_json, dict):
        return True
    meta = report_json.get("report_meta")
    version = meta.get("error_patterns_version") if isinstance(meta, dict) else None
    patterns = report_json.get("error_patterns")
    return not isinstance(patterns, list) or not patterns or version != ERROR_PATTERNS_VERSION


def build_patterns(db, report: DiagReport) -> list[dict]:
    answers = (
        db.query(DiagAnswer)
        .filter(DiagAnswer.session_id == report.session_id)
        .order_by(DiagAnswer.answered_at, DiagAnswer.id)
        .all()
    )
    repo = KnowledgeRepository()
    skill_map = {
        skill_id: _resolve_skill(skill_id, repo)
        for skill_id in {answer.skill_id for answer in answers if answer.skill_id}
    }
    return _build_error_patterns(answers, skill_map)


def backup_report(backup_dir: Path, report: DiagReport) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "report_id": str(report.id),
        "session_id": str(report.session_id),
        "backed_up_at": datetime.now(timezone.utc).isoformat(),
        "report_json": report.report_json,
    }
    (backup_dir / f"diag-report-{report.id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild stale diagnostic report error journals")
    parser.add_argument("--session-id", action="append", default=[], help="Restrict to one session ID (repeatable)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--execute", action="store_true", help="Persist rebuilt report_json after backup")
    parser.add_argument("--backup-dir", type=Path, help="Required with --execute")
    parser.add_argument("--confirm", help="Must equal REBUILD_ERROR_PATTERNS to permit writes")
    parser.add_argument("--content-service-url", help="Override content-service URL for a host-side local run")
    args = parser.parse_args()

    if args.execute and (args.backup_dir is None or args.confirm != "REBUILD_ERROR_PATTERNS"):
        parser.error("--execute requires --backup-dir and --confirm REBUILD_ERROR_PATTERNS")
    if args.content_service_url:
        os.environ["CONTENT_SERVICE_URL"] = args.content_service_url.rstrip("/")

    db_url = os.environ.get("DATABASE_URL") or "postgresql://algo:algo_password@127.0.0.1:5433/algo_diagnostic"
    engine = create_engine(db_url, connect_args=utc_connect_args(db_url))
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        query = db.query(DiagReport).order_by(DiagReport.generated_at)
        if args.session_id:
            query = query.filter(DiagReport.session_id.in_(args.session_id))
        reports = [report for report in query.all() if is_stale_report(report.report_json)]
        if args.limit:
            reports = reports[:args.limit]

        print(f"mode={'EXECUTE' if args.execute else 'DRY-RUN'} stale_reports={len(reports)}")
        rebuilt = 0
        for report in reports:
            patterns = build_patterns(db, report)
            wrong_count = (
                db.query(DiagAnswer)
                .filter(DiagAnswer.session_id == report.session_id, DiagAnswer.outcome < 1.0)
                .count()
            )
            print(
                f"report={report.id} session={report.session_id} "
                f"wrong_answers={wrong_count} journal_entries={len(patterns)}"
            )
            if len(patterns) != wrong_count:
                raise RuntimeError(f"Journal count mismatch for report {report.id}; refusing to write")

            if args.execute:
                backup_report(args.backup_dir, report)
                updated = dict(report.report_json or {})
                meta = dict(updated.get("report_meta") or {})
                meta["error_patterns_version"] = ERROR_PATTERNS_VERSION
                meta["error_patterns_rebuilt_at"] = datetime.now(timezone.utc).isoformat()
                updated["report_meta"] = meta
                updated["error_patterns"] = patterns
                report.report_json = updated
            rebuilt += 1

        if args.execute:
            db.commit()
        print(f"completed={rebuilt} writes={'committed' if args.execute else '0'}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
