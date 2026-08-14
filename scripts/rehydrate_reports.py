"""
Diagnostic Service — Rehydrate DiagReport.report_json records from Content DB.

Re-queries content-service for every task_id in error_patterns across all
DiagReport.report_json records in PostgreSQL and commits updated task fields.
"""
from __future__ import annotations

import logging
import os
import sys
import requests
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.diag_models import DiagReport

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL") or "postgresql://algo:algo_password@localhost:5433/algo_diagnostic"
CONTENT_SERVICE_URL = os.getenv("CONTENT_SERVICE_URL") or "http://localhost:8004"


class _MockContentClient:
    @staticmethod
    def get(endpoint: str):
        url = f"{CONTENT_SERVICE_URL.rstrip('/')}{endpoint}"
        try:
            return requests.get(url, timeout=10)
        except Exception as exc:
            log.warning("HTTP get error to %s: %s", url, exc)
            class MockResp:
                status_code = 500
            return MockResp()


def rehydrate_all_reports() -> None:
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        reports = db.query(DiagReport).all()
        log.info("Found %d reports in diag_reports table.", len(reports))
        updated_count = 0

        for r in reports:
            if not r.report_json or not isinstance(r.report_json, dict):
                continue
            error_patterns = r.report_json.get("error_patterns")
            if not error_patterns or not isinstance(error_patterns, list):
                continue

            new_eps = []
            for ep in error_patterns:
                task_id = ep.get("task_id")
                if not task_id:
                    new_eps.append(ep)
                    continue

                resp = _MockContentClient.get(f"/api/v1/content/tasks/{task_id}")
                if resp.status_code == 200:
                    task_data = resp.json()
                    raw_qt = (task_data.get("question_text") or "").strip()
                    raw_ql = (task_data.get("question_latex") or "").strip()
                    if raw_qt or raw_ql:
                        ep["question_text"] = raw_qt or None
                        ep["question_latex"] = raw_ql or None

                    ca = task_data.get("correct_answer")
                    ca_l = task_data.get("correct_answer_latex")
                    if ca or ca_l:
                        ep["correct_answer"] = ca or None
                        ep["correct_answer_latex"] = ca_l or ca or None

                    distractor_meta = task_data.get("distractor_meta") or []
                    student_ans = (ep.get("student_answer") or "").strip().lower()
                    if student_ans:
                        for dm in distractor_meta:
                            if isinstance(dm, dict):
                                v_val = str(dm.get("value") or "").strip().lower()
                                v_lat = str(dm.get("value_latex") or "").strip().lower()
                                if student_ans == v_val or student_ans == v_lat:
                                    ep["distractor_explanation"] = dm.get("explanation") or dm.get("error_logic") or None
                                    break

                    raw_options = [ca or '']
                    latex_options = [ca_l or ca or '']
                    for dm in distractor_meta:
                        if isinstance(dm, dict):
                            v_val = dm.get("value") or ""
                            v_lat = dm.get("value_latex") or v_val
                            if v_val and v_val not in raw_options:
                                raw_options.append(v_val)
                                latex_options.append(v_lat)

                    if len(raw_options) > 1:
                        ep["answer_options"] = raw_options
                        ep["answer_options_latex"] = latex_options

                new_eps.append(ep)

            report_data = dict(r.report_json)
            report_data["error_patterns"] = new_eps
            r.report_json = report_data
            updated_count += 1

        db.commit()
        log.info("Successfully rehydrated %d report(s) in PostgreSQL database.", updated_count)

    except Exception as exc:
        log.error("Failed to rehydrate reports: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()



if __name__ == "__main__":
    rehydrate_all_reports()
