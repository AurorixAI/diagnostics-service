"""
Diagnostic Service — Report Generator (v3)

Architecture:
  ┌─ Python (deterministic) ─────────────────────────────────────────┐
  │  error_patterns  — built from DiagAnswer records                 │
  │  weak_skills     — topic_breakdown AND >=1 wrong attempt (N02)   │
  │  strong_skills   — built from topic_breakdown (mastery ≥ 70%)    │
  │  critical_gaps   — built from topic_breakdown (mastery < 35%)    │
  └───────────────────────────────────────────────────────────────────┘
  ┌─ Azure OpenAI (generative) ───────────────────────────────────────┐
  │  overall.student_summary — 3-5 sentence admin paragraph          │
  │  action_plan[]            — full text per weak skill             │
  └───────────────────────────────────────────────────────────────────┘

Fire-and-forget: errors are logged, never raised.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.core.gemini_client import call_gemini
from src.models.diag_models import DiagReport
from src.repositories.diag_repo import DiagReportRepository
from src.repositories.knowledge_repo import KnowledgeRepository
from .answer_value import answer_value_key
from .level_policy import (
    LEGACY_STATUS,
    STATUS_LABEL_RU,
    build_level,
    count_solved,
    is_correct,
)

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_STATUS = {"above_level", "on_level", "partial_gap", "below_level", "critical"}
FORBIDDEN_PHRASES = [
    "уважаемые родители", "к сожалению", "к счастью",
    "хотелось бы отметить", "демонстрирует высокий потенциал",
    "порекомендуйте ребёнку",
]

_LEVEL_RU = {
    "mastered":    "Отличное владение",
    "learning":    "Хорошее понимание",
    "struggling":  "Есть затруднения",
    "gap":         "Пробел в знаниях",
    "below_grade": "Ниже уровня класса",
    "at_grade":    "Соответствует уровню",
    "above_grade": "Выше уровня класса",
}

_STATUS_MAP = {
    "above_grade": "above_level",
    "at_grade":    "on_level",
    "below_grade": "below_level",
}

# Thresholds for deterministic classification
_THRESHOLD_STRONG   = 70   # mastery % ≥ this → strong skill
_THRESHOLD_WEAK_HI  = 65   # mastery % < this → weak skill (upper bound)
_THRESHOLD_CRITICAL = 35   # mastery % < this → critical gap
ERROR_PATTERNS_VERSION = 4
# A report is a derived view of append-only answers.  This independent version
# lets us upgrade its structure without pretending that an old error journal is
# fully current just because its journal version still matches.
# 4 (N02): one level policy (``level`` object), evidence-gated weak topics on L2,
# Deep Scan chains from the stored origin link.
REPORT_SCHEMA_VERSION = 4


def _distractor_value(distractor: Any) -> str:
    """Canonical option value, supporting legacy storage without rewriting it."""
    if not isinstance(distractor, dict):
        return ""
    return str(
        distractor.get("value") or distractor.get("text") or distractor.get("content") or ""
    ).strip()


def _distractor_value_latex(distractor: Any, fallback: str) -> str:
    if not isinstance(distractor, dict):
        return fallback
    return str(
        distractor.get("value_latex")
        or distractor.get("text_latex")
        or distractor.get("content_latex")
        or fallback
    ).strip()


def _distractor_explanation(distractor: Any) -> Optional[str]:
    if not isinstance(distractor, dict):
        return None
    # explanation is a legacy mirror of error_logic. Prefer the latter, which
    # is the concrete pedagogical mistake used by the distractor pipeline.
    value = distractor.get("error_logic") or distractor.get("explanation")
    return str(value).strip() or None if value is not None else None


def _distractor_explanation_latex(distractor: Any) -> Optional[str]:
    if not isinstance(distractor, dict):
        return None
    value = distractor.get("error_logic_latex") or distractor.get("explanation_latex")
    return str(value).strip() or None if value is not None else None


def _find_matching_distractor(distractors: Any, student_answer: object) -> Optional[Dict[str, Any]]:
    """Find an exact stored distractor without changing historical answer facts.

    Older diagnostic attempts can have ``eval_category='wrong'`` even when the
    submitted value is exactly a distractor (for example, when the value had
    outer LaTeX delimiters).  A report may safely enrich such an entry with an
    explanation only after an exact canonical-value match; it must not infer a
    misconception from a merely incorrect answer.
    """
    answer_key = answer_value_key(student_answer)
    if not answer_key or not isinstance(distractors, list):
        return None
    for distractor in distractors:
        if answer_value_key(_distractor_value(distractor)) == answer_key:
            return distractor if isinstance(distractor, dict) else None
    return None


def _option_value(option: Any) -> str:
    if isinstance(option, dict):
        return str(option.get("value") or option.get("text") or option.get("content") or "").strip()
    return str(option or "").strip()


def _option_latex(option: Any, parallel_latex: Any, index: int, fallback: str) -> str:
    """Return explicitly stored display text without transforming its meaning."""
    if isinstance(parallel_latex, list) and index < len(parallel_latex):
        value = str(parallel_latex[index] or "").strip()
        if value:
            return value
    if isinstance(option, dict):
        value = str(
            option.get("value_latex")
            or option.get("text_latex")
            or option.get("content_latex")
            or option.get("latex")
            or ""
        ).strip()
        if value:
            return value
    return fallback


def _task_option_pairs(task_data: Dict[str, Any], correct_answer: Optional[str], correct_latex: Optional[str]) -> List[Tuple[str, str]]:
    """Build report choices from the stored UI list, then distractors as fallback."""
    explainable_pairs: List[Tuple[str, str]] = []
    if correct_answer:
        explainable_pairs.append((str(correct_answer), str(correct_latex or correct_answer)))
    for distractor in task_data.get("distractor_meta") or []:
        value = _distractor_value(distractor)
        if value and not any(answer_value_key(value) == answer_value_key(existing) for existing, _ in explainable_pairs):
            explainable_pairs.append((value, _distractor_value_latex(distractor, value)))
    stored = task_data.get("answer_options")
    parallel_latex = task_data.get("answer_options_latex")
    if isinstance(stored, list) and stored:
        distractor_latex = {
            answer_value_key(_distractor_value(distractor)): _distractor_value_latex(
                distractor, _distractor_value(distractor),
            )
            for distractor in task_data.get("distractor_meta") or []
            if _distractor_value(distractor)
        }
        pairs = []
        for index, option in enumerate(stored):
            value = _option_value(option)
            if value:
                display = _option_latex(option, parallel_latex, index, "")
                if not display and answer_value_key(value) == answer_value_key(correct_answer or ""):
                    display = str(correct_latex or value)
                if not display:
                    display = distractor_latex.get(answer_value_key(value), value)
                pairs.append((value, display))
        correct_key = answer_value_key(correct_answer or "")
        has_correct = any(answer_value_key(value) == correct_key for value, _ in pairs)
        if len(pairs) >= 2 and correct_answer and correct_key and not has_correct:
            pairs.append((str(correct_answer), str(correct_latex or correct_answer)))
        if len(pairs) >= 2:
            return pairs

    return explainable_pairs


def _student_answer_latex(student_answer: Optional[str], option_pairs: List[Tuple[str, str]]) -> Optional[str]:
    """Only map a student answer to already stored display content, never LLM-rewrite it."""
    key = answer_value_key(student_answer or "")
    if not key:
        return None
    for value, display in option_pairs:
        if answer_value_key(value) == key:
            return display or value
    return None


def _legacy_overall(level: Dict[str, Any]) -> Tuple[str, str, str]:
    """(status code, label, class_equivalent) in the pre-N02 report field format.

    The front end reads ``overall.status`` (above_level | on_level | partial_gap |
    below_level | critical), ``overall.status_label_ru`` and
    ``overall.class_equivalent``; they are filled from ``level_policy``.
    """
    status = level.get("status") or "on_level"
    return (
        LEGACY_STATUS.get(status, "on_level"),
        STATUS_LABEL_RU.get(status, STATUS_LABEL_RU["on_level"]),
        level.get("class_equivalent") or "",
    )


# ── Name resolver ─────────────────────────────────────────────────────────────

def _resolve_skill(
    sid: str, repo: KnowledgeRepository, failures: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Return {name_ru, example_task, description} for a skill ID.

    A transport failure (not a 404) is recorded in ``failures`` so that the
    caller can tell a degraded report (ids instead of names) from a complete one.
    """
    try:
        node = repo.get_by_id(sid)
        if node:
            return {
                "name_ru":     getattr(node, "name_ru", sid) or sid,
                "example":     (getattr(node, "example_task", "") or
                                getattr(node, "description", "") or ""),
            }
    except Exception:
        if failures is not None:
            failures.append(sid)
    return {"name_ru": sid, "example": ""}


# ── JSON utilities ────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """Strip markdown fences and parse JSON."""
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    cleaned = re.sub(r"//[^\n]*", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None


def _validate_ai_output(
    data: Dict[str, Any],
    *,
    computed_status: str,
    score_pct: int,
    allowed_plan_skills: Dict[str, str],
) -> Tuple[bool, List[str]]:
    """Validate narrative output against deterministic report evidence."""
    errors: List[str] = []
    overall = data.get("overall", {})
    if overall.get("status") != computed_status:
        errors.append("overall.status does not match deterministic status")
    if overall.get("score_percent") != score_pct:
        errors.append("overall.score_percent does not match source answers")
    if not overall.get("student_summary"):
        errors.append("overall.student_summary is missing or empty")
    plan = data.get("action_plan")
    if not isinstance(plan, list):
        errors.append("action_plan must be a list")
    else:
        expected_max = min(5, len(allowed_plan_skills))
        expected_min = min(3, expected_max)
        if not expected_min <= len(plan) <= expected_max:
            errors.append(f"action_plan must contain {expected_min}–{expected_max} evidence-backed items")
        seen_skill_ids = set()
        priorities = []
        for item in plan:
            if not isinstance(item, dict):
                errors.append("action_plan contains a non-object item")
                continue
            skill_id = str(item.get("skill_id") or "")
            if skill_id not in allowed_plan_skills:
                errors.append(f"action_plan skill_id is not evidence-backed: {skill_id!r}")
            elif item.get("skill_name_ru") != allowed_plan_skills[skill_id]:
                errors.append(f"action_plan skill name does not match {skill_id!r}")
            if skill_id in seen_skill_ids:
                errors.append(f"action_plan repeats skill {skill_id!r}")
            seen_skill_ids.add(skill_id)
            priorities.append(item.get("priority"))
            if not str(item.get("action_title") or "").strip():
                errors.append("action_plan action_title is missing")
            if not str(item.get("full_description") or "").strip():
                errors.append("action_plan full_description is missing")
        if priorities and sorted(priorities) != list(range(1, len(plan) + 1)):
            errors.append("action_plan priorities must be consecutive from 1")
    full_text = json.dumps(data, ensure_ascii=False).lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in full_text:
            errors.append(f"Forbidden phrase: {phrase!r}")
    return len(errors) == 0, errors


# ── Deterministic data builders ───────────────────────────────────────────────

def _load_task_context(answer) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return (task_data, source) for one answer.

    source is "snapshot" when the exact issued task was recorded with the answer;
    "live_bank" when there is no snapshot (answer predates snapshots and was not
    backfilled) and the task is read from content-service; "unavailable" when
    neither source can supply it.  Snapshot errors propagate to the caller.
    """
    from src.domain.task_evidence import read_task
    snapshot = getattr(answer, 'task_snapshot', None)
    task_data = read_task(snapshot, answer.task_id)
    if task_data is not None:
        pairs = list(zip(task_data.get('display_options') or [],
                         list(task_data.get('display_options_latex') or []) + [''] * len(task_data.get('display_options') or [])))
        task_data['_option_pairs'] = pairs
        task_data['_answer_type'] = task_data.get('display_answer_type') or 'text'
        return task_data, 'snapshot'
    try:
        from src.clients import content_client
        resp = content_client.get_task(answer.task_id)
        if resp.status_code == 200:
            task_data = resp.json()
            task_data['_option_pairs'] = _task_option_pairs(
                task_data, task_data.get('correct_answer'), task_data.get('correct_answer_latex'),
            )
            task_data['_answer_type'] = task_data.get('answer_type') or 'text'
            return task_data, 'live_bank'
    except Exception as exc:
        log.warning("Could not read task %s from content-service: %s", answer.task_id, exc)
    return None, 'unavailable'


def _build_error_patterns(
    answers_orm: list,
    skill_map: Dict[str, Dict[str, str]],
    previous_patterns: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Build error_patterns from DiagAnswer records — no AI needed.
    Produces one entry for every wrong DiagAnswer, preserving chronological
    order. A diagnostic has a bounded number of questions, so hiding errors
    through skill de-duplication would make the error journal incomplete.
    Uses evaluated task evidence. A legacy report may retain its recorded
    context, but today's live bank is never presented as historical evidence.
    """
    wrong = [a for a in answers_orm if not is_correct(a.outcome)]

    selected = sorted(
        wrong,
        key=lambda a: (
            getattr(a, "answered_at", None)
            or getattr(a, "created_at", None)
            or getattr(a, "id", 0)
        ),
    )

    patterns = []
    for a in selected:
        info = skill_map.get(a.skill_id, {})
        skill_name_ru = info.get("name_ru") or a.skill_id
        raw_answer = (a.student_answer or "").strip()
        # Sanitize internal markers → None so frontend renders "—"
        if raw_answer in ("x_wrong_x", "wrong", ""):
            raw_answer = None

        # ── Enrich from content-service ─────────────────────────────────────
        question_text: Optional[str] = None
        question_latex: Optional[str] = None
        correct_answer: Optional[str] = None
        correct_answer_latex: Optional[str] = None
        distractor_explanation: Optional[str] = None
        distractor_explanation_latex: Optional[str] = None
        student_answer_latex: Optional[str] = None
        answer_options: List[str] = []
        answer_options_latex: List[str] = []
        answer_type = "text"

        context_source = "unavailable"
        try:
            task_data, context_source = _load_task_context(a)
            if task_data is not None:
                raw_qt = (task_data.get("question_text") or "").strip()
                raw_ql = (task_data.get("question_latex") or "").strip()
                # Keep source and presentation data distinct.  The client must
                # prefer question_latex, never infer quality from string length.
                question_text = raw_qt or None
                question_latex = raw_ql or None
                correct_answer = task_data.get("correct_answer") or None
                correct_answer_latex = task_data.get("correct_answer_latex") or None
                option_pairs = task_data["_option_pairs"]
                if len(option_pairs) >= 2:
                    answer_options = [value for value, _ in option_pairs]
                    answer_options_latex = [latex for _, latex in option_pairs]
                else:
                    answer_options = []
                    answer_options_latex = []

                # Do not trust a historic category as the sole source of truth:
                # an exact match is sufficient and cannot misattribute an error.
                matched = _find_matching_distractor(
                    task_data.get("distractor_meta") or [], raw_answer,
                )
                if matched:
                    distractor_explanation = _distractor_explanation(matched)
                    distractor_explanation_latex = _distractor_explanation_latex(matched)

                answer_type = task_data["_answer_type"]
                student_answer_latex = _student_answer_latex(raw_answer, option_pairs)

        except Exception as exc:
            log.warning("Could not read task context for %s: %s", a.task_id, exc)
            answer_type = "text"
            context_source = "unavailable"

        patterns.append({
            "answer_id":               str(a.id),
            "content_provenance":      (getattr(a, 'task_snapshot', None) or {}).get('provenance', 'unavailable'),
            "context_source":          context_source,
            "task_id":                 a.task_id,
            "skill_id":                a.skill_id,
            "skill_name_ru":           skill_name_ru,
            "question_text":           question_text,
            "question_latex":          question_latex,
            "answer_type":             answer_type,
            "answer_options":          answer_options,
            "answer_options_latex":    answer_options_latex,
            "eval_category":           a.eval_category,
            "student_answer":          raw_answer,
            "student_answer_latex":    student_answer_latex,
            "correct_answer":          correct_answer,
            "correct_answer_latex":    correct_answer_latex,
            "distractor_explanation":  distractor_explanation,
            "distractor_explanation_latex": distractor_explanation_latex,
        })
        if context_source == 'unavailable' and getattr(a, 'task_snapshot', None) is None and previous_patterns:
            # Older reports have no answer UUID. Match them only if task/answer
            # is unique; never attribute another answer's context to this row.
            matches = [p for p in previous_patterns if (
                p.get('answer_id') == str(a.id) if p.get('answer_id') else
                p.get('task_id') == a.task_id and p.get('student_answer') == raw_answer
            )]
            if len(matches) == 1:
                from copy import deepcopy
                cached = deepcopy(matches[0])
                for field in ('question_text', 'question_latex', 'answer_type', 'answer_options',
                              'answer_options_latex', 'correct_answer', 'correct_answer_latex',
                              'student_answer_latex', 'distractor_explanation',
                              'distractor_explanation_latex'):
                    if field in cached:
                        patterns[-1][field] = cached[field]
                patterns[-1]['content_provenance'] = 'legacy_report_context'
                patterns[-1]['context_source'] = 'previous_report'
    return patterns



def _extract_grade_from_id(sid: Optional[str]) -> Optional[int]:
    """Extract grade number (5..11) from skill ID or topic ID."""
    if not sid:
        return None
    m = re.search(r"\bG(\d+)_", str(sid)) or re.search(r"grade_?(\d+)", str(sid), re.I)
    if m:
        try:
            g = int(m.group(1))
            if 1 <= g <= 11:
                return g
        except Exception:
            pass
    return None


def _build_cognitive_error_types(error_patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Cluster student errors by cognitive failure mechanisms and distractor patterns.
    """
    clusters = {
        "signs_and_powers": {
            "category": "signs_and_powers",
            "title": "Знаки, степени и свойства корней",
            "description": "Ошибки при возведении отрицательных чисел в степени, путаница знака основания и свойств корней",
            "keywords": ["степен", "корен", "знак", "отрицательн", "(-1)^2", "квадрат"],
            "items": [],
        },
        "algebraic_transforms": {
            "category": "algebraic_transforms",
            "title": "Алгебраические преобразования и скобки",
            "description": "Нарушение распределительного закона, пропуск множителей при раскрытии скобок и ошибки приведения подобных",
            "keywords": ["скобок", "подобн", "раскрыт", "множител", "распределительн", "слагаем", "2(x+7)", "9y"],
            "items": [],
        },
        "fractions_and_rationals": {
            "category": "fractions_and_rationals",
            "title": "Рациональные выражения и дроби",
            "description": "Сложение дробей с разными знаменателями, сокращение слагаемых вместо множителей",
            "keywords": ["дроб", "знаменател", "числител", "сокращен", "рациональн"],
            "items": [],
        },
        "equations_and_logic": {
            "category": "equations_and_logic",
            "title": "Логика уравнений и неравенств",
            "description": "Ошибки в переносе слагаемых, подстановке корней и анализе условий",
            "keywords": ["уравнен", "неравенств", "корен", "подстановк", "интервал", "модул"],
            "items": [],
        },
    }

    uncategorized: List[Dict[str, Any]] = []

    for ep in error_patterns:
        expl = (ep.get("distractor_explanation") or "").lower()
        name = (ep.get("skill_name_ru") or "").lower()
        ans = (ep.get("student_answer") or "").lower()
        text_corpus = f"{expl} {name} {ans}"

        matched_key = None
        for key, conf in clusters.items():
            if any(kw in text_corpus for kw in conf["keywords"]):
                matched_key = key
                break

        item_summary = {
            "task_id": ep.get("task_id"),
            "skill_id": ep.get("skill_id"),
            "skill_name_ru": ep.get("skill_name_ru"),
            "question_text": ep.get("question_text"),
            "question_latex": ep.get("question_latex"),
            "student_answer": ep.get("student_answer"),
            "student_answer_latex": ep.get("student_answer_latex"),
            "correct_answer": ep.get("correct_answer"),
            "correct_answer_latex": ep.get("correct_answer_latex"),
            "distractor_explanation": ep.get("distractor_explanation"),
        }

        if matched_key:
            clusters[matched_key]["items"].append(item_summary)
        else:
            uncategorized.append(item_summary)

    result = []
    for key, conf in clusters.items():
        if conf["items"]:
            result.append({
                "category": conf["category"],
                "title": conf["title"],
                "description": conf["description"],
                "count": len(conf["items"]),
                "examples": conf["items"][:3],
            })

    if uncategorized:
        result.append({
            "category": "other_errors",
            "title": "Прочие предметные затруднения",
            "description": "Ошибки в вычислениях и формулировках условий",
            "count": len(uncategorized),
            "examples": uncategorized[:3],
        })

    result.sort(key=lambda x: -x["count"])
    return result


def _ordered_answers(answers_orm: list) -> list:
    """Chronological order (answered_at, id) when every row has a timestamp.

    Rows without timestamps (unit tests, partial legacy rows) keep the order the
    caller supplied.  Generation queries ORDER BY answered_at, id as well.
    """
    items = list(answers_orm)
    if items and all(getattr(a, "answered_at", None) is not None for a in items):
        return sorted(items, key=lambda a: (a.answered_at, str(getattr(a, "id", ""))))
    return items


def _chain_step(a, skill_map, ep_by_task, grade_level) -> Dict[str, Any]:
    sid = a.skill_id or ""
    g = _extract_grade_from_id(sid) or grade_level
    name = skill_map.get(sid, {}).get("name_ru") or sid
    ep = ep_by_task.get(a.task_id, {})
    step_data = {
        "task_id": a.task_id,
        "skill_id": sid,
        "skill_name_ru": name,
        "grade": g,
        "phase": a.phase,
        "is_deep_scan": bool(a.is_deep_scan),
        "deep_scan_step": getattr(a, "deep_scan_step", None),
        "outcome": float(a.outcome or 0),
        "eval_category": a.eval_category,
        "question_text": ep.get("question_text"),
        "question_latex": ep.get("question_latex"),
        "student_answer": ep.get("student_answer") or (a.student_answer if a.student_answer not in ("x_wrong_x", "wrong") else "—"),
        "student_answer_latex": ep.get("student_answer_latex"),
        "correct_answer": ep.get("correct_answer"),
        "correct_answer_latex": ep.get("correct_answer_latex"),
        "distractor_explanation": ep.get("distractor_explanation"),
    }
    if not ep and a.task_id:
        try:
            t_data, _src = _load_task_context(a)
            if t_data is not None:
                step_data["question_text"] = t_data.get("question_text")
                step_data["question_latex"] = t_data.get("question_latex")
                step_data["correct_answer"] = t_data.get("correct_answer")
                step_data["correct_answer_latex"] = t_data.get("correct_answer_latex")
        except Exception:
            pass
    return step_data


def _reconstruct_root_cause_chains(
    answers_orm: list,
    skill_map: Dict[str, Dict[str, str]],
    error_patterns: List[Dict[str, Any]],
    grade_level: int,
) -> List[Dict[str, Any]]:
    """
    Reconstruct Deep Scan prerequisite descent trajectories from session answers.
    Identifies:
      - Trigger topic in current grade
      - Prerequisite steps (any grade, including the same grade)
      - Breakpoint (the deepest failed prerequisite)
      - Anchor (where student answered correctly on lower grade foundation)

    Answers carrying ``deep_scan_origin_skill_id`` (recorded since migration 010)
    are grouped by that stored link and ordered by ``deep_scan_step``; the result
    does not depend on the order of the input rows.  Older deep-scan answers
    without the link keep the previous inference (a run of consecutive deep-scan
    answers is attached to the preceding wrong navigation answer).
    """
    ep_by_task = {ep.get("task_id"): ep for ep in error_patterns if ep.get("task_id")}
    ordered = _ordered_answers(answers_orm)
    has_timestamps = bool(ordered) and all(
        getattr(a, "answered_at", None) is not None for a in ordered
    )

    def step(a) -> Dict[str, Any]:
        return _chain_step(a, skill_map, ep_by_task, grade_level)

    chains: List[Dict[str, Any]] = []

    # ── A. chains from the stored origin link ────────────────────────────────
    linked = [
        a for a in ordered
        if a.is_deep_scan and getattr(a, "deep_scan_origin_skill_id", None)
    ]
    groups: Dict[str, List[list]] = {}
    for a in linked:
        origin = a.deep_scan_origin_skill_id
        scans = groups.setdefault(origin, [])
        a_step = getattr(a, "deep_scan_step", None)
        last_step = getattr(scans[-1][-1], "deep_scan_step", None) if scans else None
        # The same skill can start a second scan; steps then restart from 1.
        restarted = (
            has_timestamps and scans and a_step is not None and last_step is not None
            and a_step <= last_step
        )
        if not scans or restarted:
            scans.append([a])
        else:
            scans[-1].append(a)
    for origin, scans in groups.items():
        trigger_pool = [
            x for x in ordered
            if not x.is_deep_scan and (x.skill_id or "") == origin
            and not is_correct(x.outcome)
        ]
        for scan_answers in scans:
            scan_answers = sorted(
                scan_answers,
                key=lambda x: (getattr(x, "deep_scan_step", None) is None,
                               getattr(x, "deep_scan_step", None) or 0),
            )
            if trigger_pool:
                source = step(trigger_pool[-1])
                source["is_scan_origin"] = True
            else:
                # The failing skill was aggregated by the navigator; there is no
                # single wrong item to show.  Keep the fact, not an invented item.
                grade = _extract_grade_from_id(origin) or grade_level
                source = {
                    "task_id": None, "skill_id": origin,
                    "skill_name_ru": skill_map.get(origin, {}).get("name_ru") or origin,
                    "grade": grade, "phase": "navigation", "is_deep_scan": False,
                    "deep_scan_step": None, "outcome": 0.0, "eval_category": None,
                    "question_text": None, "question_latex": None, "student_answer": "—",
                    "student_answer_latex": None, "correct_answer": None,
                    "correct_answer_latex": None, "distractor_explanation": None,
                    "is_scan_origin": True,
                }
            chain = _finalize_chain([source] + [step(x) for x in scan_answers], grade_level)
            chain["evidence_source"] = "stored_link"
            chains.append(chain)

    # ── B. legacy answers without a link: previous inference ─────────────────
    current_chain_steps: List[Dict[str, Any]] = []
    last_nav_wrong: Optional[Dict[str, Any]] = None
    for a in ordered:
        if a.is_deep_scan and getattr(a, "deep_scan_origin_skill_id", None):
            continue  # already handled through its stored link
        step_data = step(a)
        if not a.is_deep_scan:
            if current_chain_steps:
                chains.append(_finalize_chain(current_chain_steps, grade_level))
                chains[-1]["evidence_source"] = "inferred"
                current_chain_steps = []
            if not is_correct(a.outcome):
                last_nav_wrong = step_data
        else:
            if not current_chain_steps and last_nav_wrong:
                current_chain_steps.append(last_nav_wrong)
            current_chain_steps.append(step_data)
    if current_chain_steps:
        chains.append(_finalize_chain(current_chain_steps, grade_level))
        chains[-1]["evidence_source"] = "inferred"

    # Only genuine Deep Scan trajectories with a failed prerequisite are shown.
    # A normal wrong answer establishes an observed gap, not a causal chain.
    # A prerequisite of the SAME grade is a valid link (it used to be dropped).
    seen_keys = set()
    unique_chains = []
    for ch in chains:
        if not ch.get("has_prerequisite_gap"):
            continue
        key = (ch.get("source_skill_id"), ch.get("root_gap_skill_id"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_chains.append(ch)

    # Sort critical first, then deepest grade descent; ids make ties stable.
    unique_chains.sort(key=lambda c: (
        0 if c.get("severity") == "critical" else 1 if c.get("severity") == "warning" else 2,
        c.get("root_gap_grade", 99),
        str(c.get("source_skill_id")), str(c.get("root_gap_skill_id")),
    ))

    return unique_chains

def _clean_explanation_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = str(text)
    t = t.replace(r"\$", "$")
    t = re.sub(r"\$-\$", "—", t)
    t = re.sub(r"\$\s*-\s*\$", "—", t)
    t = re.sub(r"\$\s*\+", "+", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _finalize_chain(steps: List[Dict[str, Any]], grade_level: int) -> Dict[str, Any]:
    """Synthesize a single prerequisite chain into source, breakpoint, and anchor.

    The breakpoint is the deepest FAILED Deep Scan step: the lowest grade, and on
    equal grades the one reached last (furthest from the source).  A same-grade
    prerequisite is therefore a legitimate breakpoint.  When no deep-scan step
    failed, the chain has no prerequisite gap and is not reported as a cause.
    """
    source = steps[0] if steps else {}
    passed_steps = [s for s in steps if is_correct(s["outcome"])]
    deep_failed = [
        (i, s) for i, s in enumerate(steps)
        if s.get("is_deep_scan") and not is_correct(s["outcome"])
        and s.get("skill_id") != source.get("skill_id")
    ]
    has_gap = bool(deep_failed)
    if has_gap:
        root_gap = min(deep_failed, key=lambda pair: (pair[1]["grade"], -pair[0]))[1]
    else:
        root_gap = source

    passed_steps_sorted = sorted(passed_steps, key=lambda s: s["grade"])
    anchor = passed_steps_sorted[0] if passed_steps_sorted else None

    # Clean explanation texts
    root_expl = _clean_explanation_text(root_gap.get("distractor_explanation"))
    for s in steps:
        s["distractor_explanation"] = _clean_explanation_text(s.get("distractor_explanation"))

    if root_gap["grade"] <= max(1, grade_level - 2):
        severity = "critical"
    elif root_gap["grade"] < grade_level:
        severity = "warning"
    else:
        severity = "local_gap"

    return {
        "source_grade": source.get("grade", grade_level),
        "source_skill_id": source.get("skill_id"),
        "source_skill_name": source.get("skill_name_ru"),
        "root_gap_grade": root_gap.get("grade"),
        "root_gap_skill_id": root_gap.get("skill_id"),
        "root_gap_skill_name": root_gap.get("skill_name_ru"),
        "root_gap_explanation": root_expl,
        "anchor_grade": anchor.get("grade") if anchor else None,
        "anchor_skill_id": anchor.get("skill_id") if anchor else None,
        "anchor_skill_name": anchor.get("skill_name_ru") if anchor else None,
        "severity": severity,
        "has_prerequisite_gap": has_gap,
        "steps_count": len(steps),
        "steps": steps,
    }


def _build_diagnostic_boundary(
    answers_orm: list,
    skill_map: Dict[str, Dict[str, str]],
    grade_level: int,
    chains: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute a boundary while preserving the strength of its evidence.

    A true breakpoint may be labelled a root prerequisite only after a Deep
    Scan trajectory reaches it.  Without that trajectory the report still
    presents the most important observed gap and a useful remediation start,
    but does not overstate causality.
    """
    correct_by_grade: Dict[int, List[str]] = {}
    wrong_by_grade: Dict[int, List[str]] = {}

    for a in answers_orm:
        sid = a.skill_id or ""
        g = _extract_grade_from_id(sid) or grade_level
        name = skill_map.get(sid, {}).get("name_ru") or sid
        if is_correct(a.outcome):
            correct_by_grade.setdefault(g, []).append(name)
        else:
            wrong_by_grade.setdefault(g, []).append(name)

    chain_anchors = [
        (ch.get("anchor_grade"), ch.get("anchor_skill_name"))
        for ch in chains if ch.get("anchor_grade") and ch.get("anchor_skill_name")
    ]
    if chain_anchors:
        anchor_grade = min(int(g) for g, _ in chain_anchors)
        anchor_skills = list(dict.fromkeys(
            name for g, name in chain_anchors if int(g) == anchor_grade
        ))[:3]
    else:
        anchor_grade = min(correct_by_grade.keys()) if correct_by_grade else max(1, grade_level - 2)
        anchor_skills = list(dict.fromkeys(correct_by_grade.get(anchor_grade, [])))[:3]

    if chains:
        breakpoint_grade = min(int(ch.get("root_gap_grade") or grade_level) for ch in chains)
        breakpoint_skills = list(dict.fromkeys(
            ch.get("root_gap_skill_name")
            for ch in chains
            if int(ch.get("root_gap_grade") or grade_level) == breakpoint_grade
            and ch.get("root_gap_skill_name")
        ))[:3]
        evidence_status = "confirmed"
    else:
        breakpoint_grade = min(wrong_by_grade.keys()) if wrong_by_grade else grade_level
        breakpoint_skills = list(dict.fromkeys(wrong_by_grade.get(breakpoint_grade, [])))[:3]
        evidence_status = "observed"

    blocked_skills = list(dict.fromkeys(wrong_by_grade.get(grade_level, [])))[:4]

    return {
        "anchor_level": f"{anchor_grade} класс" if anchor_skills else "базовый уровень",
        "anchor_skills": anchor_skills,
        "breakpoint_level": f"{breakpoint_grade} класс" if breakpoint_skills else f"{grade_level} класс",
        "breakpoint_skills": breakpoint_skills,
        "breakpoint_evidence": evidence_status,
        "blocked_level": f"{grade_level} класс",
        "blocked_skills": blocked_skills,
    }


class _L2Resolver:
    """``skill_id -> L2 topic id`` through the knowledge hierarchy.

    An L4 skill (or L3 paragraph) resolves to its L2 ancestor, an L2 to itself;
    anything that cannot be resolved (missing node) gives ``None`` so that no
    unverified parent is ever invented.  Results are cached.

    When content-service is unreachable the lookup is *degraded*: a skill id that
    is itself a key of ``topic_breakdown`` is its own L2 (L2 ids are exactly those
    keys); other ids stay unresolved.  ``degraded`` tells the report generator
    that the result must not be stamped as a current report.
    """

    def __init__(self, repo: Any, own_topic_ids: Any = ()) -> None:
        self._repo = repo
        self._own = set(own_topic_ids or ())
        self._cache: Dict[str, Optional[str]] = {}
        self.degraded = False

    def __call__(self, skill_id: str) -> Optional[str]:
        sid = str(skill_id or "")
        if not sid:
            return None
        if sid in self._cache:
            return self._cache[sid]
        result: Optional[str] = None
        try:
            node = self._repo.get_by_id(sid)
            hops = 0
            while node is not None and hops < 5:
                if getattr(node, "level", None) == "L2":
                    result = getattr(node, "id", sid)
                    break
                parent = getattr(node, "parent_id", None)
                if not parent:
                    break
                node = self._repo.get_by_id(parent)
                hops += 1
        except Exception as exc:
            log.warning("Could not resolve L2 parent of %s: %s", sid, exc)
            self.degraded = True
            result = sid if sid in self._own else None
        self._cache[sid] = result
        return result


def _make_l2_resolver(repo: Any, own_topic_ids: Any = ()) -> _L2Resolver:
    return _L2Resolver(repo, own_topic_ids)


def _topic_evidence(topic_id: str, info: Dict[str, Any], answers: List[Any]) -> Tuple[int, int]:
    """(observations, wrong_attempts) of an L2 topic from the answer journal.

    ``observations`` prefers the AlphaTracker count stored with the topic
    breakdown (every answer updates it); older sessions fall back to counting
    the journal, which is the same quantity.
    """
    mine = [a for a in answers if getattr(a, "topic_id", None) == topic_id]
    wrong = sum(1 for a in mine if not is_correct(getattr(a, "outcome", None)))
    stored = info.get("observations")
    observations = int(stored) if isinstance(stored, (int, float)) else len(mine)
    return observations, wrong


def _build_skill_blocks(
    topic_breakdown: Dict[str, Any],
    weak_skill_ids: List[str],
    skill_map: Dict[str, Dict[str, str]],
    answers: Optional[List[Any]] = None,
    *,
    l2_of: Optional[Callable[[str], Optional[str]]] = None,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Return (strong_skills, weak_skills, critical_gaps) at the L2 topic level.

    A topic is WEAK only with evidence:
      * at least one incorrect attempt in the topic, AND
      * (>= 2 observations with low mastery (< 65%)  OR  a gap confirmed by Deep Scan).
    A topic with only correct answers is never weak, whatever its alpha is (alpha
    starts at 0 and grows slowly: one correct answer is 55%).

    ``weak_skill_ids`` are the Deep Scan confirmed gaps (L4 skill ids, sometimes
    L2).  Each is mapped to its parent L2 topic through ``l2_of`` and shown as a
    detail of that topic; a topic and its skills never appear as separate items.
    """
    strong, weak, critical = [], [], []
    answers = list(answers or [])
    resolve = l2_of or (lambda sid: sid if sid in topic_breakdown else None)

    confirmed: Dict[str, List[str]] = {}
    for skill_id in dict.fromkeys(weak_skill_ids or []):
        topic = resolve(skill_id)
        if topic:
            details = confirmed.setdefault(topic, [])
            if skill_id != topic and skill_id not in details:
                details.append(skill_id)

    for tid, info in topic_breakdown.items():
        alpha = float(info.get("alpha", 0))
        pct = int(max(0, min(100, (0.5 + alpha / 4.0) * 100)))
        name = skill_map.get(tid, {}).get("name_ru", tid)
        observations, wrong_attempts = _topic_evidence(tid, info, answers)
        is_confirmed = tid in confirmed
        is_weak = wrong_attempts >= 1 and (
            (observations >= 2 and pct < _THRESHOLD_WEAK_HI) or is_confirmed
        )

        if not is_weak:
            if pct >= _THRESHOLD_STRONG:
                strong.append({
                    "skill_id":      tid,
                    "skill_name_ru": name,
                    "mastery_percent": pct,
                })
            continue

        evidence = {
            "observations": observations,
            "wrong_attempts": wrong_attempts,
            "confirmed_by_deep_scan": is_confirmed,
            "detail_skills": [
                {"skill_id": d, "skill_name_ru": skill_map.get(d, {}).get("name_ru", d)}
                for d in confirmed.get(tid, [])
            ],
        }
        if pct < _THRESHOLD_CRITICAL:
            critical.append({
                "skill_id":        tid,
                "skill_name_ru":   name,
                "mastery_percent": pct,
                "priority":        0,
                **evidence,
            })
        else:
            status = "gap" if pct < 40 else ("unstable" if pct < 55 else "developing")
            weak.append({
                "skill_id":        tid,
                "skill_name_ru":   name,
                "mastery_percent": pct,
                "status":          status,
                **evidence,
            })

    critical.sort(key=lambda x: (x["mastery_percent"], x["skill_id"]))
    for i, g in enumerate(critical, 1):
        g["priority"] = i

    strong.sort(key=lambda x: (-x["mastery_percent"], x["skill_id"]))
    weak.sort(key=lambda x: (x["mastery_percent"], x["skill_id"]))
    return strong, weak, critical


def _build_plan_candidates(
    chains: List[Dict[str, Any]],
    critical_gaps: List[Dict[str, Any]],
    weak_skills: List[Dict[str, Any]],
    error_patterns: List[Dict[str, Any]],
    *,
    l2_of: Optional[Callable[[str], Optional[str]]] = None,
) -> List[Dict[str, Any]]:
    """Return up to five ordered, evidence-backed correction targets.

    The model may improve pedagogical wording but cannot add its own topics.
    This keeps the plan compact and anchored in either a confirmed prerequisite
    or an observed error / measured weak skill.

    Parent/child pairs are not duplicated: an L4 skill whose L2 topic is already
    a candidate becomes a ``details`` entry of that topic; an L2 topic arriving
    after one of its (more specific) L4 candidates is only noted on that item.
    """
    candidates: List[Dict[str, Any]] = []
    by_id: Dict[str, Dict[str, Any]] = {}
    parent_of: Dict[str, Optional[str]] = {}

    def parent(sid: str) -> Optional[str]:
        if sid not in parent_of:
            parent_of[sid] = l2_of(sid) if l2_of else None
        return parent_of[sid]

    def add(skill_id: Any, name: Any, evidence: str, details: Optional[List[Dict[str, str]]] = None) -> None:
        sid = str(skill_id or "").strip()
        title = str(name or "").strip()
        if not sid or not title or sid in by_id:
            return
        topic = parent(sid)
        if topic and topic != sid and topic in by_id:
            known = by_id[topic].setdefault("details", [])
            if all(d.get("skill_id") != sid for d in known):
                known.append({"skill_id": sid, "skill_name_ru": title})
            return
        if topic == sid:
            child = next((c for c in candidates if parent(c["skill_id"]) == sid), None)
            if child is not None:
                child["parent_topic_id"] = sid
                child["parent_topic_name_ru"] = title
                return
        if len(candidates) >= 5:
            return
        item: Dict[str, Any] = {"skill_id": sid, "skill_name_ru": title, "evidence": evidence}
        if details:
            item["details"] = [d for d in details if d.get("skill_id") != sid]
        candidates.append(item)
        by_id[sid] = item

    for chain in chains:
        add(chain.get("root_gap_skill_id"), chain.get("root_gap_skill_name"), "confirmed_prerequisite")
    for item in critical_gaps:
        add(item.get("skill_id"), item.get("skill_name_ru"), "measured_critical_gap", item.get("detail_skills"))
    for item in weak_skills:
        add(item.get("skill_id"), item.get("skill_name_ru"), "measured_weak_skill", item.get("detail_skills"))
    for item in error_patterns:
        add(item.get("skill_id"), item.get("skill_name_ru"), "observed_error")
    return candidates


def _build_fallback_action_plan(candidates: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """A usable, evidence-backed plan when the narrative provider is unavailable."""
    plan = []
    for priority, candidate in enumerate(candidates, 1):
        name = candidate["skill_name_ru"]
        evidence = candidate["evidence"]
        qualifier = (
            "Это подтверждённый пререквизит, поэтому с него следует начать коррекцию."
            if evidence == "confirmed_prerequisite"
            else "Затруднение зафиксировано в диагностике и требует целевой отработки."
        )
        plan.append({
            "priority": priority,
            "skill_id": candidate["skill_id"],
            "skill_name_ru": name,
            "action_title": f"Отработать: {name}",
            "full_description": (
                f"Сначала восстановить базовый алгоритм навыка «{name}» на коротких примерах. "
                f"Затем проверить применение правила в задачах с новым контекстом. {qualifier}"
            ),
            "estimated_hours": 2,
            "source": "deterministic_fallback",
        })
    return plan


def _build_deterministic_summary(
    *,
    class_equivalent: str,
    grade_level: int,
    score_pct: int,
    boundary: Dict[str, Any],
    chains: List[Dict[str, Any]],
    strong_skills: List[Dict[str, Any]],
    deep_scan_run: bool = False,
    solved: Optional[int] = None,
    total: Optional[int] = None,
    provisional: bool = False,
) -> str:
    """Safe fallback conclusion that never invents a causal explanation."""
    root = chains[0].get("root_gap_skill_name") if chains else None
    observed = ", ".join(boundary.get("breakpoint_skills") or [])
    anchors = ", ".join(item.get("skill_name_ru", "") for item in strong_skills[:2] if item.get("skill_name_ru"))
    if root:
        evidence_sentence = f"Deep Scan подтвердил первопричину: «{root}»."
    elif observed and deep_scan_run:
        evidence_sentence = (
            f"Зафиксированы ключевые затруднения: {observed}; "
            "углублённая проверка не подтвердила единую первопричину."
        )
    elif observed:
        evidence_sentence = f"Зафиксированы ключевые затруднения: {observed}; причинная цепочка не заявляется без Deep Scan."
    else:
        evidence_sentence = "В выполненных заданиях затруднения не зафиксированы."
    anchors_sentence = f"Опорные навыки: {anchors}." if anchors else "Устойчивые опорные навыки требуют дальнейшего наблюдения."
    result = (
        f"Решено {solved} из {total} заданий адаптивного теста"
        if solved is not None and total is not None else f"Результат — {score_pct}%"
    )
    provisional_sentence = (
        " Оценка предварительная: точность измерения пока ограничена." if provisional else ""
    )
    return (
        f"{result}; уровень по результатам измерения соответствует {class_equivalent} при заявленном {grade_level} классе.{provisional_sentence} "
        f"{evidence_sentence} {anchors_sentence} "
        + ("Коррекцию следует начать с первого пункта индивидуального плана и подтвердить перенос навыка на новой задаче."
           if root or observed else "Рекомендуется развивать опорные навыки на задачах с новым контекстом.")
    )


# ── AI prompt ─────────────────────────────────────────────────────────────────

_AI_SCHEMA = """{
  "overall": {
    "score_percent": <int скопируй из данных>,
    "status": "<above_level|on_level|partial_gap|below_level|critical>",
    "status_label_ru": "<строка — название уровня>",
    "student_summary": "<МЕТОДИЧЕСКОЕ ЗАКЛЮЧЕНИЕ ПЕДАГОГА-ДИАГНОСТА (4-6 связных предложений для администратора учебного центра и преподавателя). ТРЕБОВАНИЯ: (1) Назови реальный академический уровень ({class_equivalent}) относительно тестируемого {grade_level} класса. (2) Объясни МЕХАНИКУ СБОЯ (Root-Cause): укажи, какой именно базовый дефицит в младших классах (6-7 классы) разрушает усвоение программы {grade_level} класса с опорой на цепочки Deep Scan. (3) Опиши КОГНИТИВНЫЙ ПРОФИЛЬ ОШИБОК по зафиксированным дистракторам (знаки четных степеней, скобки, распределительный закон). (4) Укажи ТОЧКИ ОПОРЫ (что ученик решает стабильно). (5) Дай прямую методическую рекомендацию по стартовой теме коррекции и группе зачисления. СТИЛЬ: профессиональный, экспертный, фактологический, без общих фраз и без сухой статистики.>"
  },
  "action_plan": [
    {
      "priority": <int начиная с 1>,
      "skill_id": "<ТОЛЬКО идентификатор из списка ДОПУСТИМЫХ ЦЕЛЕЙ>",
      "skill_name_ru": "<ТОЧНОЕ название из списка ДОПУСТИМЫХ ЦЕЛЕЙ>",
      "action_title": "<заголовок MAX 8 слов>",
      "full_description": "<3-5 предложений: что именно отрабатывать, какие типы задач, на какие правила обратить внимание, как проверить усвоение. НЕ добавляй в конце текст про количество часов, так как часы указываются отдельно в estimated_hours>",
      "estimated_hours": <int>
    }
  ]
}"""


def _build_prompt(
    *,
    grade_level: int,
    overall_level: str,
    score_pct: int,
    correct: int,
    total: int,
    computed_status: str,
    class_equivalent: str,
    topics_block: str,
    wrong_block: str,
    chains_block: str,
    boundary_block: str,
    cognitive_block: str,
    anchor_block: str,
    plan_candidates_block: str,
    plan_min_items: int,
    plan_max_items: int,
    root_cause_confirmed: bool,
    student_name: str,
    test_code: str,
    validation_errors: Optional[List[str]] = None,
) -> str:
    retry = ""
    if validation_errors:
        retry = "\n⚠️ ПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА. ИСПРАВЬ:\n" + "\n".join(f"  • {e}" for e in validation_errors) + "\n"

    return f"""Ты — старший методист и аналитический модуль платформы адаптивной диагностики ALGO.
Аудитория отчёта: Администратор учебного центра, методист и преподаватель математики.
{retry}
ПРАВИЛА:
1. Ответ — ТОЛЬКО валидный JSON. Без markdown-обёрток, без текста до/после.
2. overall.status — СКОПИРУЙ ТОЧНО: "{computed_status}" (уже вычислено алгоритмом).
3. student_summary — ЭКСПЕРТНОЕ ПЕДАГОГИЧЕСКОЕ ЗАКЛЮЧЕНИЕ (4-6 предложений):
   • Сформулируй реальный академический уровень: {class_equivalent}.
   • {'Объясни только подтверждённую Deep Scan первопричину.' if root_cause_confirmed else 'Не называй наблюдаемый дефицит «первопричиной»: опиши его как ключевое зафиксированное затруднение.'}
   • Разбери когнитивные паттерны мышления ученика по дистракторам.
   • Опиши опорные навыки (базовые темы, решенные верно).
   • Дай четкую рекомендацию: с какой конкретной темы начать коррекцию и в какую группу определить ученика.
4. action_plan — от {plan_min_items} до {plan_max_items} приоритетных шагов. Используй ТОЛЬКО цели из списка ниже, не добавляй темы от себя.

ДАННЫЕ АДАПТИВНОЙ ДИАГНОСТИКИ:
Ученик: {student_name} | Заявленный класс: {grade_level} | Код теста: {test_code}
Решено: {correct} из {total} заданий адаптивного теста ({score_pct}%; это факт о выданном наборе, уровень определён по θ, а не по этому проценту)
Реальный уровень (IRT): {class_equivalent} | Статус: {computed_status}

АКАДЕМИЧЕСКАЯ ГРАНИЦА ЗНАНИЙ:
{boundary_block}

ТОЧКИ ОПОРЫ (Решено верно):
{anchor_block}

ЦЕПОЧКИ ДИАГНОСТИЧЕСКОГО СПУСКА (DEEP SCAN — Поиск первопричин):
{chains_block}

КОГНИТИВНЫЕ ПАТТЕРНЫ ОШИБОК (По дистракторам):
{cognitive_block}

ДЕТАЛИЗАЦИЯ НЕВЕРНЫХ ОТВЕТОВ:
{wrong_block}

ДОПУСТИМЫЕ ЦЕЛИ ПЛАНА (порядок уже отражает приоритет):
{plan_candidates_block}

ВЕРНИ ТОЛЬКО JSON:
{_AI_SCHEMA}"""


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_and_save_report(
    db: Session,
    *,
    session_id: uuid.UUID,
    student_id: uuid.UUID,
    grade_level: int,
    theta: float,
    theta_se: float,
    overall_level: str,
    topic_breakdown: Dict[str, Any],
    weak_skills: List[str],
    items_total: int,
    stop_reason: Optional[str] = None,
    items_max: Optional[int] = None,
    covered_section_ids: Optional[List[str]] = None,
    deep_scan_incomplete: bool = False,
    classification_confidence: Optional[float] = None,
    student_name: str = "Ученик",
    test_code: str = "",
    force: bool = False,
    skip_narrative: bool = False,
) -> Optional[DiagReport]:
    """
    Creates DiagReport with hybrid JSON:
      - AI generates: student_summary + action_plan
      - Python generates: error_patterns, weak_skills, strong_skills, critical_gaps
    Raw answers are never modified.  ``force`` only rebuilds this derived
    report when its schema is stale or a durable retry explicitly claims it.
    """
    from src.models.diag_models import DiagAnswer

    report_repo = DiagReportRepository(db)
    existing = report_repo.get_by_session(session_id)
    # Persistence below must also be safe when evidence collection fails before
    # the narrative call is reached.
    ai_data: Optional[Dict[str, Any]] = None
    if (
        existing
        and existing.report_json
        and existing.report_schema_version >= REPORT_SCHEMA_VERSION
        and not force
    ):
        log.info("Report already exists for session %s", session_id)
        return existing

    th = float(theta or 0.0)
    se = float(theta_se or 1.0)
    ci_lo = round(th - 2 * se, 4)
    ci_hi = round(th + 2 * se, 4)

    try:
        if existing:
            existing.generation_stage = "collecting_evidence"
            existing.generation_error = None
            # A flush is invisible to the status endpoint. Persist the stage
            # before potentially slow content enrichment begins.
            db.commit()

        # ── Fetch answers ─────────────────────────────────────────────────────
        answers_orm = (
            db.query(DiagAnswer)
            .filter(DiagAnswer.session_id == session_id)
            .order_by(DiagAnswer.answered_at, DiagAnswer.id)
            .all()
        )

        # ── Resolve skill names + examples ────────────────────────────────────
        repo = KnowledgeRepository()
        all_ids = list(dict.fromkeys(
            list(topic_breakdown.keys())
            + [a.skill_id for a in answers_orm if a.skill_id]
            + list(weak_skills or [])
        ))
        name_failures: List[str] = []
        skill_map: Dict[str, Dict[str, str]] = {
            sid: _resolve_skill(sid, repo, name_failures) for sid in all_ids
        }

        # ── Deterministic blocks (no AI) ──────────────────────────────────────
        previous_patterns = (existing.report_json or {}).get('error_patterns', []) if existing else []
        error_patterns = _build_error_patterns(answers_orm, skill_map, previous_patterns)
        l2_of = _make_l2_resolver(repo, topic_breakdown.keys())
        strong_skills, weak_skills_block, critical_gaps = _build_skill_blocks(
            topic_breakdown, weak_skills, skill_map, answers_orm, l2_of=l2_of,
        )

        # ── Score stats: "solved N of M" over adaptive-test items only ────────
        # Deep Scan answers probe prerequisites; they are not part of the measured
        # set and do not enter the level.  One rule (level_policy.is_correct).
        # The append-only answer journal is authoritative.  ``items_total`` is
        # retained only as a zero-answer fallback for an interrupted legacy run.
        counts = count_solved(answers_orm)
        correct = counts["solved"]
        total = counts["total"] or (0 if answers_orm else max(int(items_total or 0), 1))
        score_pct = int(round(correct / total * 100)) if total else 0
        prerequisite_answers = [a for a in answers_orm if a.is_deep_scan]
        deep_scan_run = bool(prerequisite_answers)
        # ── Level — only from theta/se (never from %-correct, never from AI) ──
        level = build_level(th, se, grade_level, solved=correct, total=total)
        computed_status, computed_label_ru, class_equivalent = _legacy_overall(level)
        log.info("Computed level=%s status=%s (solved=%d/%d, theta=%.2f, class_eq=%s, provisional=%s)",
                 level["category"], computed_status, correct, total, th, class_equivalent, level["provisional"])

        # ── Advanced Diagnostic Data Blocks ───────────────────────────────────
        root_cause_chains = _reconstruct_root_cause_chains(answers_orm, skill_map, error_patterns, grade_level)
        diagnostic_boundary = _build_diagnostic_boundary(answers_orm, skill_map, grade_level, root_cause_chains)
        cognitive_error_types = _build_cognitive_error_types(error_patterns)
        plan_candidates = _build_plan_candidates(
            root_cause_chains, critical_gaps, weak_skills_block, error_patterns, l2_of=l2_of,
        )
        allowed_plan_skills = {
            item["skill_id"]: item["skill_name_ru"] for item in plan_candidates
        }
        plan_candidates_block = "\n".join(
            f"  {index}. {item['skill_id']} — {item['skill_name_ru']} ({item['evidence']})"
            for index, item in enumerate(plan_candidates, 1)
        ) or "  (коррекционный план не требуется: нет зафиксированных ошибок)"

        # ── Boundary & Anchor blocks for prompt ───────────────────────────────
        boundary_lines = [
            f"  • Опорная база (что решено верно): {diagnostic_boundary['anchor_level']} — {', '.join(diagnostic_boundary['anchor_skills']) or 'базовые вычисления'}",
            f"  • {'Подтверждённая точка слома' if diagnostic_boundary['breakpoint_evidence'] == 'confirmed' else 'Ключевой наблюдаемый дефицит'}: {diagnostic_boundary['breakpoint_level']} — {', '.join(diagnostic_boundary['breakpoint_skills']) or 'не выявлен'}",
            f"  • Заблокированные темы текущего класса: {diagnostic_boundary['blocked_level']} — {', '.join(diagnostic_boundary['blocked_skills']) or 'нет'}",
        ]
        boundary_block = "\n".join(boundary_lines)

        anchor_lines = [
            f"  • {s['skill_name_ru']} (Класс {s['grade']}): верный ответ"
            for ch in root_cause_chains for s in ch.get("steps", []) if is_correct(s.get("outcome"))
        ]
        if not anchor_lines:
            anchor_lines = [f"  • {name}" for name in diagnostic_boundary.get("anchor_skills", [])]
        anchor_block = "\n".join(dict.fromkeys(anchor_lines)) or "  (базовый уровень не подтверждён)"

        # ── Chains block for prompt ───────────────────────────────────────────
        chain_lines = []
        for i, ch in enumerate(root_cause_chains, 1):
            expl = ch.get("root_gap_explanation") or "ошибка в пререквизите"
            anc = f" -> Опора: {ch['anchor_skill_name']} ({ch['anchor_grade']} кл)" if ch.get("anchor_skill_name") else " -> Опора на данном уровне не зафиксирована"
            chain_lines.append(
                f"  [{i}] Исходная тема ({ch['source_grade']} кл): {ch['source_skill_name']} "
                f"-> Сбой в пререквизите ({ch['root_gap_grade']} кл): {ch['root_gap_skill_name']} "
                f"(Суть ошибки: {expl}){anc}"
            )
        chains_block = "\n".join(chain_lines) or (
            "  (углублённая проверка не подтвердила единую первопричину)"
            if deep_scan_run else "  (спуск не потребовался)"
        )

        # ── Cognitive error patterns for prompt ───────────────────────────────
        cog_lines = []
        for cg in cognitive_error_types:
            ex_strs = []
            for ex in cg.get("examples", [])[:2]:
                ans_str = ex.get("student_answer") or "—"
                d_exp = ex.get("distractor_explanation")
                ex_strs.append(f"{ex['skill_name_ru']} (ответ: {repr(ans_str)}{f' — {d_exp}' if d_exp else ''})")
            cog_lines.append(f"  • {cg['title']} ({cg['count']} ошибок): {'; '.join(ex_strs)}")
        cognitive_block = "\n".join(cog_lines) or "  (нет выраженных когнитивных паттернов)"

        # ── Topics block for prompt ───────────────────────────────────────────
        topic_lines = []
        weak_ids = {item["skill_id"] for item in weak_skills_block + critical_gaps}
        for tid, info in topic_breakdown.items():
            alpha = float(info.get("alpha", 0))
            pct = int(max(0, min(100, (0.5 + alpha / 4.0) * 100)))
            name = skill_map.get(tid, {}).get("name_ru", tid)
            flag = " ⚠️" if tid in weak_ids else ""
            topic_lines.append(f"  {name}: {pct}%{flag}")
        topics_block = "\n".join(topic_lines) or "  (нет данных)"

        # ── Wrong answers block for prompt (max 8, unique skills) ────────────
        wrong_answers = [a for a in answers_orm if not is_correct(a.outcome)]
        seen: set = set()
        selected_wrong = []
        for a in wrong_answers:
            if a.skill_id not in seen and len(selected_wrong) < 8:
                seen.add(a.skill_id)
                selected_wrong.append(a)

        wrong_lines = []
        for i, a in enumerate(selected_wrong, 1):
            name = skill_map.get(a.skill_id, {}).get("name_ru", a.skill_id)
            ans = (a.student_answer or "").strip()
            if ans in ("x_wrong_x", "wrong", ""):
                ans = "—"
            wrong_lines.append(f"  [{i}] {name}: ответ={repr(ans)}, категория={a.eval_category}")
        wrong_block = "\n".join(wrong_lines) or "  (нет неверных ответов)"

        # ── AI generation (retry x2) ──────────────────────────────────────────
        if existing:
            existing.generation_stage = "writing_methodical_conclusion"
            db.commit()
        last_errors: List[str] = []

        # ``skip_narrative``: deterministic backfills never call the paid model.
        for attempt in range(1, 1 if skip_narrative else 3):
            prompt = _build_prompt(
                grade_level=grade_level,
                overall_level=overall_level,
                score_pct=score_pct,
                correct=correct,
                total=total,
                computed_status=computed_status,
                class_equivalent=class_equivalent,
                topics_block=topics_block,
                wrong_block=wrong_block,
                chains_block=chains_block,
                boundary_block=boundary_block,
                cognitive_block=cognitive_block,
                anchor_block=anchor_block,
                plan_candidates_block=plan_candidates_block,
                plan_min_items=min(3, len(plan_candidates)),
                plan_max_items=min(5, len(plan_candidates)),
                root_cause_confirmed=bool(root_cause_chains),
                student_name=student_name,
                test_code=test_code,
                validation_errors=last_errors if attempt > 1 else None,
            )
            raw = call_gemini(prompt, temperature=0.3, max_tokens=2500)
            if not raw:
                log.warning("Attempt %d: empty AI response", attempt)
                continue

            parsed = _extract_json(raw)
            if not parsed:
                last_errors = ["Response is not valid JSON"]
                log.warning("Attempt %d: JSON parse failed", attempt)
                continue

            is_valid, errors = _validate_ai_output(
                parsed,
                computed_status=computed_status,
                score_pct=score_pct,
                allowed_plan_skills=allowed_plan_skills,
            )
            if is_valid:
                ai_data = parsed
                log.info("Attempt %d: AI output valid", attempt)
                break
            else:
                last_errors = errors
                log.warning("Attempt %d: validation errors: %s", attempt, errors[:3])

        if not ai_data and not skip_narrative:
            log.warning("AI generation unavailable for session %s; using deterministic report wording.", session_id)

        # ── Reliability Calculation (rho = 1 - SE^2) ──────────────────────────
        reliability = round(max(0.0, min(0.99, 1.0 - (float(theta_se) ** 2))), 2)

        # ── Clean action plan descriptions ──────────────────────────────────
        action_plan_cleaned = []
        for item in (ai_data or {}).get("action_plan", _build_fallback_action_plan(plan_candidates)):
            if isinstance(item, dict):
                raw_desc = str(item.get("full_description") or "").strip()
                cleaned_desc = re.sub(
                    r"(?:[\.\s,;–—-]*)?(?:Рекомендуем(?:ое|ый)?\s+(?:количество\s+часов|время|объем)|Время\s+на\s+отработку|Примерное\s+время)\s*:\s*\d+\s*(?:часов|часа|час|ч)?\.?$",
                    "",
                    raw_desc,
                    flags=re.IGNORECASE,
                ).strip()
                item_copy = dict(item)
                item_copy["full_description"] = cleaned_desc
                action_plan_cleaned.append(item_copy)

        # ── Merge AI + computed data ──────────────────────────────────────────
        overall_block = (ai_data or {}).get("overall", {})
        deterministic_summary = _build_deterministic_summary(
            class_equivalent=class_equivalent,
            grade_level=grade_level,
            score_pct=score_pct,
            boundary=diagnostic_boundary,
            chains=root_cause_chains,
            strong_skills=strong_skills,
            deep_scan_run=deep_scan_run,
            solved=correct,
            total=total,
            provisional=level["provisional"],
        )
        # Content-service lookups that failed (transport, not "not found") make the
        # parent-topic mapping / names incomplete.  Such a report is usable but is
        # never stamped as current (see the persist step).
        degraded_reasons: List[str] = []
        if l2_of.degraded:
            degraded_reasons.append("knowledge_hierarchy")
        if name_failures:
            degraded_reasons.append("skill_names")
        report_json: Dict[str, Any] = {
            "report_meta": {
                "degraded": degraded_reasons,
                "session_id":       str(session_id),
                "student_name":     student_name,
                "class_level":      grade_level,
                "test_code":        test_code,
                "error_patterns_version": ERROR_PATTERNS_VERSION,
                "report_schema_version": REPORT_SCHEMA_VERSION,
                "date":             date.today().isoformat(),
                # "solved N of M": adaptive-test items only (same as level.*).
                "total_questions":  total,
                "questions_correct": correct,
                "score_percent":    score_pct,
                "stop_reason": stop_reason or "unknown",
                "precision_reached": stop_reason == "precision_reached",
                "level_classification_reached": stop_reason == "classification_confident",
                "classification_confidence": classification_confidence,
                "measurement_questions": total,
                "prerequisite_questions": len(prerequisite_answers),
                "prerequisite_correct": sum(is_correct(a.outcome) for a in prerequisite_answers),
                "items_max": items_max,
                "covered_section_ids": covered_section_ids or [],
                "deep_scan_incomplete": deep_scan_incomplete,
                "narrative_status": "ready" if ai_data else "deterministic_fallback",
            },
            "overall": {
                "score_percent":    score_pct,     # always from data
                "status":           computed_status,   # legacy code, from level_policy
                "status_label_ru":  computed_label_ru, # from level_policy
                "student_summary":  overall_block.get("student_summary") or deterministic_summary,
                "class_equivalent": class_equivalent,  # from level_policy
                "category":         level["category"],
                "provisional":      level["provisional"],
                "confidence_of_diagnosis": reliability,
            },
            # The single level object (N02).  The legacy ``overall`` fields above
            # are filled from it.
            "level": level,
            # ── Diagnostic Anatomy & Root Cause (New) ──
            "diagnostic_boundary":   diagnostic_boundary,
            "root_cause_chains":     root_cause_chains,
            "cognitive_error_types": cognitive_error_types,
            # ── Computed from data (no AI) ──
            "strong_skills":   strong_skills,
            "weak_skills":     weak_skills_block,
            "critical_gaps":   critical_gaps,
            "error_patterns":  error_patterns,
            # ── AI-generated ──
            "action_plan":     action_plan_cleaned,
        }

    except Exception as exc:
        log.error("Report generation error for session %s: %s", session_id, exc, exc_info=True)
        if existing:
            existing.generation_status = "failed"
            existing.generation_stage = "failed"
            existing.generation_error = str(exc)[:1000]
            existing.generation_completed_at = datetime.now(timezone.utc)
            db.commit()
            return existing
        report_json = None

    # ── Persist ───────────────────────────────────────────────────────────────
    # A degraded report (content-service was unreachable) is not current.  While
    # retries remain it is NOT written: the job is returned to the durable queue
    # through the normal failure path (report_jobs re-queues failed jobs up to
    # MAX_GENERATION_ATTEMPTS).  On the last attempt the degraded content is
    # kept for display but stays schema 0 / failed, so it is picked up again by
    # scripts/regenerate_reports.py once content-service is back.
    degraded = bool(report_json and report_json["report_meta"].get("degraded"))
    if degraded:
        from src.domain.report_jobs import MAX_GENERATION_ATTEMPTS
        retries_left = bool(existing) and int(existing.generation_attempts or 0) < MAX_GENERATION_ATTEMPTS
        message = ("content-service unavailable (%s); report not marked current"
                   % ", ".join(report_json["report_meta"]["degraded"]))
        log.warning("Degraded report for session %s: %s", session_id, message)
        if retries_left:
            existing.generation_status = "failed"
            existing.generation_stage = "failed"
            existing.generation_error = message
            existing.generation_completed_at = datetime.now(timezone.utc)
            db.commit()
            return existing
    try:
        if existing:
            existing.report_json = report_json
            existing.narrative_generated = bool(ai_data)
            current = bool(report_json) and not degraded
            existing.report_schema_version = REPORT_SCHEMA_VERSION if current else 0
            existing.generation_status = "ready" if current else "failed"
            existing.generation_stage = "ready" if current else "failed"
            existing.generation_error = (
                None if current else (message if degraded else "Report data could not be built")
            )
            existing.generation_completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            return existing

        current = bool(report_json) and not degraded
        report = DiagReport(
            session_id=session_id,
            student_id=student_id,
            grade_level=grade_level,
            overall_theta=theta,
            overall_level=overall_level,
            confidence_interval_lo=ci_lo,
            confidence_interval_hi=ci_hi,
            topic_breakdown=topic_breakdown,
            weak_skills=weak_skills,
            recommended_start=weak_skills[0] if weak_skills else None,
            report_json=report_json,
            narrative_ru=None,
            narrative_generated=bool(ai_data),
            report_schema_version=REPORT_SCHEMA_VERSION if current else 0,
            generation_status="ready" if current else "failed",
            generation_stage="ready" if current else "failed",
            generation_error=None if current else (message if degraded else "Report data could not be built"),
            generation_started_at=datetime.now(timezone.utc),
            generation_completed_at=datetime.now(timezone.utc),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        log.info("DiagReport saved for session %s", session_id)
        return report

    except Exception as exc:
        log.error("Failed to save DiagReport for session %s: %s", session_id, exc)
        db.rollback()
        return None


def refresh_error_patterns_live(patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compatibility entry point: preserve recorded context without bank GETs.

    Legacy cached context is not promoted to an issued-content snapshot. A
    deep copy also prevents a read endpoint from mutating persistent report JSON.
    """
    from copy import deepcopy
    return deepcopy(patterns)
