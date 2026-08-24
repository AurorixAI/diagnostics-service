"""
Diagnostic Service — Rehydrate DiagReport.report_json records from Content DB.

Re-queries content-service for every task_id in error_patterns across all
DiagReport.report_json records in PostgreSQL and commits updated task fields.
"""
from __future__ import annotations

import logging
import os
import sys
import re
import urllib.parse
import requests
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from src.models.diag_models import DiagReport

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL") or "postgresql://algo:algo_password@localhost:5433/algo_diagnostic"
CONTENT_SERVICE_URL = os.getenv("CONTENT_SERVICE_URL") or "http://localhost:8004"


def canonical_answer_key(val: str | None) -> str:
    if not val:
        return ""
    s = str(val).strip()
    # 1. Strip outer and inline LaTeX math delimiters
    s = s.replace("$$", "").replace("$", "")
    # 2. Normalize mathematical minuses and dashes (U+2212, U+2013, U+2014) to standard hyphen
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    
    # 3. Strip structural modifiers FIRST (\left, \right, \displaystyle, \limits, \text{...})
    s = re.sub(r"\\?(?:left|right|displaystyle|limits)\b", "", s)
    s = re.sub(r"\\?text\s*\{([^{}]*)\}", r"\1", s)
    
    # 4. Roots: \sqrt{x} -> sqrt(x)
    while re.search(r"\\?sqrt\s*\{([^{}]+)\}", s):
        s = re.sub(r"\\?sqrt\s*\{([^{}]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\?sqrt", "sqrt", s).replace("√", "sqrt")
    
    # 5. Fractions: recursively resolve \frac{num}{den} and \dfrac{num}{den}
    while re.search(r"\\?(?:dfrac|frac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}", s):
        s = re.sub(r"\\?(?:dfrac|frac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", s)
    s = re.sub(r"\\?(?:dfrac|frac)\b", "/", s)
    
    # 6. Inequalities, approximations, set operations, and relations
    s = re.sub(r"\\?(?:approx|thickapprox|sim|simeq)\b|≈|~", "≈", s)
    s = re.sub(r"\\?(?:Delta|delta)\b|Δ|δ", "Δ", s)
    s = re.sub(r"\\?(?:prime)\b|'", "'", s)
    s = re.sub(r"\\?(?:leq|le)\b|≤", "<=", s)
    s = re.sub(r"\\?(?:geq|ge)\b|≥", ">=", s)
    s = re.sub(r"\\?(?:neq|ne)\b|≠", "!=", s)
    s = re.sub(r"\\?notin\b|∉", "!in", s)
    s = re.sub(r"\\?(?:setminus|backslash)\b|\\", "\\\\", s)
    s = re.sub(r"\\?in\b|∈", "in", s)
    s = re.sub(r"\\?infty\b|∞", "inf", s)
    s = re.sub(r"\\?cup\b|∪", "U", s)
    s = re.sub(r"\\?cap\b|∩", "cap", s)
    s = re.sub(r"\\?(?:cdot|times)\b|\*|·", "", s)
    s = re.sub(r"\\?mathbb\{R\}|\\?mathbb\s+R|ℝ", "R", s)
    s = re.sub(r"\\?mathbb\{Z\}|\\?mathbb\s+Z|ℤ", "Z", s)
    s = re.sub(r"\\?mathbb\{Q\}|\\?mathbb\s+Q|ℚ", "Q", s)
    s = re.sub(r"\\?mathbb\{N\}|\\?mathbb\s+N|ℕ", "N", s)
    s = re.sub(r"\\?pi\b|π", "pi", s)
    s = re.sub(r"\^?\\?circ\b|°", "", s)
    s = s.replace("{,}", ".").replace(",", ".")
    
    # 7. Strip remaining latex command backslashes, curly braces, and whitespace
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def are_answers_equivalent(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    ka = canonical_answer_key(a)
    kb = canonical_answer_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    strip_parens = lambda x: re.sub(r"[()]", "", x)
    return strip_parens(ka) == strip_parens(kb)


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

                encoded_task_id = urllib.parse.quote(str(task_id), safe="")
                resp = _MockContentClient.get(f"/api/v1/content/tasks/{encoded_task_id}")
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
                    student_ans = (ep.get("student_answer") or "").strip()
                    if student_ans:
                        for dm in distractor_meta:
                            if isinstance(dm, dict):
                                v_val = str(dm.get("value") or "").strip()
                                v_lat = str(dm.get("value_latex") or "").strip()
                                if are_answers_equivalent(student_ans, v_val) or are_answers_equivalent(student_ans, v_lat):
                                    ep["distractor_explanation"] = dm.get("explanation") or dm.get("error_logic") or None
                                    break

                    task_opts = task_data.get("answer_options")
                    task_opts_l = task_data.get("answer_options_latex")
                    if task_opts and len(task_opts) > 1:
                        ep["answer_options"] = task_opts
                        ep["answer_options_latex"] = task_opts_l or task_opts
                    else:
                        raw_options = [ca or ''] if ca else []
                        latex_options = [ca_l or ca or ''] if (ca_l or ca) else []
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
            flag_modified(r, "report_json")
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
