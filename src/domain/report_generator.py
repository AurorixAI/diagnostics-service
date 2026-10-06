"""
Diagnostic Service — Report Generator (v3)

Architecture:
  ┌─ Python (deterministic) ─────────────────────────────────────────┐
  │  error_patterns  — built from DiagAnswer records                 │
  │  weak_skills     — built from topic_breakdown (mastery 35–65%)   │
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
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.core.gemini_client import call_gemini
from src.models.diag_models import DiagReport
from src.repositories.diag_repo import DiagReportRepository
from src.repositories.knowledge_repo import KnowledgeRepository
from .answer_value import answer_value_key

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
REPORT_SCHEMA_VERSION = 3


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


def _compute_overall_status(theta: float, score_pct: int) -> str:
    """
    Compute overall status deterministically from IRT theta score AND empirical accuracy (score_pct).
    Ensures logical consistency: low accuracy (<45%) can NEVER be labeled 'on_level' or 'above_level'.
    """
    if score_pct < 25 or theta < -1.4:
        return "critical"
    if score_pct < 45 or theta < -0.6:
        return "below_level"
    if score_pct < 65 or theta < 0.1:
        return "partial_gap"

    # For score_pct >= 65%:
    if score_pct >= 80 and theta >= 1.2:
        return "above_level"
    elif theta >= 0.2:
        return "on_level"
    else:
        return "partial_gap"


_STATUS_LABEL_RU = {
    "above_level": "Выше уровня класса",
    "on_level":    "Соответствует уровню",
    "partial_gap": "Частичные пробелы",
    "below_level": "Ниже уровня класса",
    "critical":    "Критическое отставание",
}


def _compute_class_equivalent(theta: float, score_pct: int, grade: int) -> str:
    """
    Return a human-readable class level equivalent combining IRT theta and empirical accuracy.
    """
    if score_pct < 25 or theta < -1.4:
        prev_g = max(1, grade - 2)
        return f"начало {prev_g} класса"
    elif score_pct < 45 or theta < -0.6:
        return f"середина {grade - 1} класса"
    elif score_pct < 65 or theta < 0.1:
        return f"конец {grade - 1} класса"
    elif score_pct < 80 or theta < 0.7:
        return f"начало {grade} класса"
    elif theta < 1.5:
        return f"середина {grade} класса"
    else:
        return f"начало {grade + 1} класса"


# ── Name resolver ─────────────────────────────────────────────────────────────

def _resolve_skill(sid: str, repo: KnowledgeRepository) -> Dict[str, str]:
    """Return {name_ru, example_task, description} for a skill ID."""
    try:
        node = repo.get_by_id(sid)
        if node:
            return {
                "name_ru":     getattr(node, "name_ru", sid) or sid,
                "example":     (getattr(node, "example_task", "") or
                                getattr(node, "description", "") or ""),
            }
    except Exception:
        pass
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
    wrong = [a for a in answers_orm if float(a.outcome or 0) < 1.0]

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
      - Prerequisite steps in lower grades
      - Breakpoint (where fundamental misconception happened)
      - Anchor (where student answered correctly on lower grade foundation)
    """
    ep_by_task = {ep.get("task_id"): ep for ep in error_patterns if ep.get("task_id")}

    chains: List[Dict[str, Any]] = []
    current_chain_steps: List[Dict[str, Any]] = []
    last_nav_wrong: Optional[Dict[str, Any]] = None

    for a in answers_orm:
        sid = a.skill_id or ""
        g = _extract_grade_from_id(sid) or grade_level
        is_correct = float(a.outcome or 0) >= 1.0
        name = skill_map.get(sid, {}).get("name_ru") or sid
        ep = ep_by_task.get(a.task_id, {})

        step_data = {
            "task_id": a.task_id,
            "skill_id": sid,
            "skill_name_ru": name,
            "grade": g,
            "phase": a.phase,
            "is_deep_scan": bool(a.is_deep_scan),
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

        if not a.is_deep_scan:
            if current_chain_steps:
                chains.append(_finalize_chain(current_chain_steps, grade_level))
                current_chain_steps = []
            if not is_correct:
                last_nav_wrong = step_data
        else:
            if not current_chain_steps and last_nav_wrong:
                current_chain_steps.append(last_nav_wrong)
            current_chain_steps.append(step_data)

    if current_chain_steps:
        chains.append(_finalize_chain(current_chain_steps, grade_level))

    seen_keys = set()
    unique_chains = []

    # Only genuine Deep Scan trajectories are allowed here.  A normal wrong
    # answer establishes an observed gap, not a causal prerequisite chain.
    # The previous fallback created a persuasive but methodically false
    # "primary cause" even when no prerequisite had been tested.
    # 1. Genuine prerequisite descent chains (Grade N -> Grade N-1 or N-2)
    for ch in chains:
        key = (ch.get("source_skill_id"), ch.get("root_gap_skill_id"))
        if key not in seen_keys and ch.get("root_gap_grade", grade_level) < ch.get("source_grade", grade_level):
            seen_keys.add(key)
            unique_chains.append(ch)

    # 2. Multi-step distinct chains across different skills
    for ch in chains:
        key = (ch.get("source_skill_id"), ch.get("root_gap_skill_id"))
        if key not in seen_keys and len(ch.get("steps", [])) >= 2 and ch.get("source_skill_id") != ch.get("root_gap_skill_id"):
            seen_keys.add(key)
            unique_chains.append(ch)

    # Sort critical first, then deepest grade descent
    unique_chains.sort(key=lambda c: (
        0 if c.get("severity") == "critical" else 1 if c.get("severity") == "warning" else 2,
        c.get("root_gap_grade", 99)
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
    """Synthesize a single prerequisite chain into source, breakpoint, and anchor."""
    source = steps[0] if steps else {}
    passed_steps = [s for s in steps if s["outcome"] >= 1.0]
    failed_steps = [s for s in steps if s["outcome"] < 1.0]

    failed_steps_sorted = sorted(failed_steps, key=lambda s: s["grade"])
    root_gap = failed_steps_sorted[0] if failed_steps_sorted else source

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
        if float(a.outcome or 0) >= 1.0:
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


def _build_skill_blocks(
    topic_breakdown: Dict[str, Any],
    weak_skill_ids: List[str],
    skill_map: Dict[str, Dict[str, str]],
    answers: Optional[List[Any]] = None,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Return (strong_skills, weak_skills, critical_gaps) computed from IRT data.
    """
    strong, weak, critical = [], [], []

    for tid, info in topic_breakdown.items():
        alpha = float(info.get("alpha", 0))
        pct = int(max(0, min(100, (0.5 + alpha / 4.0) * 100)))
        name = skill_map.get(tid, {}).get("name_ru", tid)
        is_flagged_weak = tid in weak_skill_ids

        if pct >= _THRESHOLD_STRONG and not is_flagged_weak:
            strong.append({
                "skill_id":      tid,
                "skill_name_ru": name,
                "mastery_percent": pct,
            })
        elif pct < _THRESHOLD_CRITICAL or (is_flagged_weak and pct < _THRESHOLD_CRITICAL):
            critical.append({
                "skill_id":        tid,
                "skill_name_ru":   name,
                "mastery_percent": pct,
                "priority":        0,
            })
        elif pct < _THRESHOLD_WEAK_HI or is_flagged_weak:
            status = "gap" if pct < 40 else ("unstable" if pct < 55 else "developing")
            weak.append({
                "skill_id":        tid,
                "skill_name_ru":   name,
                "mastery_percent": pct,
                "status":          status,
            })

    critical.sort(key=lambda x: x["mastery_percent"])
    for i, g in enumerate(critical, 1):
        g["priority"] = i

    strong.sort(key=lambda x: -x["mastery_percent"])
    weak.sort(key=lambda x: x["mastery_percent"])

    # Alpha starts at zero and rises gradually. A short, error-free trajectory
    # can still have a low alpha; that is not evidence of a learning deficit.
    if answers and all(float(a.outcome or 0) >= 1.0 for a in answers):
        weak, critical = [], []
    return strong, weak, critical


def _build_plan_candidates(
    chains: List[Dict[str, Any]],
    critical_gaps: List[Dict[str, Any]],
    weak_skills: List[Dict[str, Any]],
    error_patterns: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Return up to five ordered, evidence-backed correction targets.

    The model may improve pedagogical wording but cannot add its own topics.
    This keeps the plan compact and anchored in either a confirmed prerequisite
    or an observed error / measured weak skill.
    """
    candidates: List[Dict[str, str]] = []
    seen: set[str] = set()

    def add(skill_id: Any, name: Any, evidence: str) -> None:
        sid = str(skill_id or "").strip()
        title = str(name or "").strip()
        if sid and title and sid not in seen and len(candidates) < 5:
            seen.add(sid)
            candidates.append({"skill_id": sid, "skill_name_ru": title, "evidence": evidence})

    for chain in chains:
        add(chain.get("root_gap_skill_id"), chain.get("root_gap_skill_name"), "confirmed_prerequisite")
    for item in critical_gaps:
        add(item.get("skill_id"), item.get("skill_name_ru"), "measured_critical_gap")
    for item in weak_skills:
        add(item.get("skill_id"), item.get("skill_name_ru"), "measured_weak_skill")
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
) -> str:
    """Safe fallback conclusion that never invents a causal explanation."""
    root = chains[0].get("root_gap_skill_name") if chains else None
    observed = ", ".join(boundary.get("breakpoint_skills") or [])
    anchors = ", ".join(item.get("skill_name_ru", "") for item in strong_skills[:2] if item.get("skill_name_ru"))
    if root:
        evidence_sentence = f"Deep Scan подтвердил первопричину: «{root}»."
    elif observed:
        evidence_sentence = f"Зафиксированы ключевые затруднения: {observed}; причинная цепочка не заявляется без Deep Scan."
    else:
        evidence_sentence = "В выполненных заданиях затруднения не зафиксированы."
    anchors_sentence = f"Опорные навыки: {anchors}." if anchors else "Устойчивые опорные навыки требуют дальнейшего наблюдения."
    return (
        f"Результат — {score_pct}%; фактический уровень соответствует {class_equivalent} при заявленном {grade_level} классе. "
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
Результат: {score_pct}% ({correct} верных из {total} заданий)
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
            .all()
        )

        # ── Resolve skill names + examples ────────────────────────────────────
        repo = KnowledgeRepository()
        all_ids = list(dict.fromkeys(
            list(topic_breakdown.keys()) + [a.skill_id for a in answers_orm if a.skill_id]
        ))
        skill_map: Dict[str, Dict[str, str]] = {sid: _resolve_skill(sid, repo) for sid in all_ids}

        # ── Deterministic blocks (no AI) ──────────────────────────────────────
        previous_patterns = (existing.report_json or {}).get('error_patterns', []) if existing else []
        error_patterns = _build_error_patterns(answers_orm, skill_map, previous_patterns)
        strong_skills, weak_skills_block, critical_gaps = _build_skill_blocks(
            topic_breakdown, weak_skills, skill_map, answers_orm
        )

        # ── Score stats ───────────────────────────────────────────────────────
        correct = sum(1 for a in answers_orm if float(a.outcome or 0) >= 1.0)
        # The append-only answer journal is authoritative.  ``items_total`` is
        # retained only as a zero-answer fallback for an interrupted legacy run.
        total = len(answers_orm) or max(int(items_total or 0), 1)
        score_pct = int(round(correct / total * 100))
        # ── Status — computed deterministically from theta AND score_pct (never from AI) ────────
        computed_status    = _compute_overall_status(theta, score_pct)
        computed_label_ru  = _STATUS_LABEL_RU[computed_status]
        class_equivalent   = _compute_class_equivalent(theta, score_pct, grade_level)
        log.info("Computed status=%s (score=%d%%, theta=%.2f, class_eq=%s)", computed_status, score_pct, theta, class_equivalent)

        # ── Advanced Diagnostic Data Blocks ───────────────────────────────────
        root_cause_chains = _reconstruct_root_cause_chains(answers_orm, skill_map, error_patterns, grade_level)
        diagnostic_boundary = _build_diagnostic_boundary(answers_orm, skill_map, grade_level, root_cause_chains)
        cognitive_error_types = _build_cognitive_error_types(error_patterns)
        plan_candidates = _build_plan_candidates(
            root_cause_chains, critical_gaps, weak_skills_block, error_patterns,
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
            for ch in root_cause_chains for s in ch.get("steps", []) if s.get("outcome", 0) >= 1.0
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
        chains_block = "\n".join(chain_lines) or "  (спуск не потребовался)"

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
        for tid, info in topic_breakdown.items():
            alpha = float(info.get("alpha", 0))
            pct = int(max(0, min(100, (0.5 + alpha / 4.0) * 100)))
            name = skill_map.get(tid, {}).get("name_ru", tid)
            flag = " ⚠️" if tid in weak_skills else ""
            topic_lines.append(f"  {name}: {pct}%{flag}")
        topics_block = "\n".join(topic_lines) or "  (нет данных)"

        # ── Wrong answers block for prompt (max 8, unique skills) ────────────
        wrong_answers = [a for a in answers_orm if float(a.outcome or 0) < 1.0]
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

        for attempt in range(1, 3):
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

        if not ai_data:
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
        )
        report_json: Dict[str, Any] = {
            "report_meta": {
                "session_id":       str(session_id),
                "student_name":     student_name,
                "class_level":      grade_level,
                "test_code":        test_code,
                "error_patterns_version": ERROR_PATTERNS_VERSION,
                "report_schema_version": REPORT_SCHEMA_VERSION,
                "date":             date.today().isoformat(),
                "total_questions":  total,
                "questions_correct": correct,
                "score_percent":    score_pct,
                "stop_reason": stop_reason or "unknown",
                "precision_reached": stop_reason == "precision_reached",
                "level_classification_reached": stop_reason == "classification_confident",
                "classification_confidence": classification_confidence,
                "measurement_questions": sum(not a.is_deep_scan for a in answers_orm),
                "prerequisite_questions": sum(bool(a.is_deep_scan) for a in answers_orm),
                "items_max": items_max,
                "covered_section_ids": covered_section_ids or [],
                "deep_scan_incomplete": deep_scan_incomplete,
                "narrative_status": "ready" if ai_data else "deterministic_fallback",
            },
            "overall": {
                "score_percent":    score_pct,     # always from data
                "status":           computed_status,   # always from theta
                "status_label_ru":  computed_label_ru, # always from theta
                "student_summary":  overall_block.get("student_summary") or deterministic_summary,
                "class_equivalent": class_equivalent,  # for reference
                "confidence_of_diagnosis": reliability,
            },
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
    try:
        if existing:
            existing.report_json = report_json
            existing.narrative_generated = bool(ai_data)
            existing.report_schema_version = REPORT_SCHEMA_VERSION if report_json else 0
            existing.generation_status = "ready" if report_json else "failed"
            existing.generation_stage = "ready" if report_json else "failed"
            existing.generation_error = None if report_json else "Report data could not be built"
            existing.generation_completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
            return existing

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
            report_schema_version=REPORT_SCHEMA_VERSION if report_json else 0,
            generation_status="ready" if report_json else "failed",
            generation_stage="ready" if report_json else "failed",
            generation_error=None if report_json else "Report data could not be built",
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
