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
from datetime import date
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
        prev_g = max(7, grade - 2)
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


def _validate_ai_output(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate only the AI-generated fields."""
    errors: List[str] = []
    overall = data.get("overall", {})
    if overall.get("status") not in VALID_STATUS:
        errors.append(f"overall.status invalid: {overall.get('status')!r}")
    if not overall.get("student_summary"):
        errors.append("overall.student_summary is missing or empty")
    if not isinstance(data.get("action_plan"), list):
        errors.append("action_plan must be a list")
    full_text = json.dumps(data, ensure_ascii=False).lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in full_text:
            errors.append(f"Forbidden phrase: {phrase!r}")
    return len(errors) == 0, errors


# ── Deterministic data builders ───────────────────────────────────────────────

def _build_error_patterns(
    answers_orm: list,
    skill_map: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    """
    Build error_patterns from DiagAnswer records — no AI needed.
    Produces one entry for every wrong DiagAnswer, preserving chronological
    order. A diagnostic has a bounded number of questions, so hiding errors
    through skill de-duplication would make the error journal incomplete.
    Enriches each entry with question_text, correct_answer, and real distractor_explanation
    fetched from content-service.
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

        try:
            from src.clients import content_client
            resp = content_client.get(f"/api/v1/content/tasks/{a.task_id}")
            if resp.status_code == 200:
                task_data = resp.json()
                raw_qt = (task_data.get("question_text") or "").strip()
                raw_ql = (task_data.get("question_latex") or "").strip()
                # Keep source and presentation data distinct.  The client must
                # prefer question_latex, never infer quality from string length.
                question_text = raw_qt or None
                question_latex = raw_ql or None
                correct_answer = task_data.get("correct_answer") or None
                correct_answer_latex = task_data.get("correct_answer_latex") or None
                option_pairs = _task_option_pairs(
                    task_data, correct_answer, correct_answer_latex,
                )
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

                answer_type = task_data.get("answer_type") or "text"
                student_answer_latex = _student_answer_latex(raw_answer, option_pairs)

        except Exception as exc:
            log.warning("Could not enrich task %s from content-service: %s", a.task_id, exc)
            answer_type = "text"

        patterns.append({
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
    return patterns



def _build_skill_blocks(
    topic_breakdown: Dict[str, Any],
    weak_skill_ids: List[str],
    skill_map: Dict[str, Dict[str, str]],
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Return (strong_skills, weak_skills, critical_gaps) computed from IRT data.
    """
    strong, weak, critical = [], [], []

    for tid, info in topic_breakdown.items():
        alpha = float(info.get("alpha", 0))
        pct = int(max(0, min(100, (0.5 + alpha / 4.0) * 100)))
        level = info.get("level", "learning")
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
                "priority":        0,  # will be sorted
            })
        elif pct < _THRESHOLD_WEAK_HI or is_flagged_weak:
            status = "gap" if pct < 40 else ("unstable" if pct < 55 else "developing")
            weak.append({
                "skill_id":        tid,
                "skill_name_ru":   name,
                "mastery_percent": pct,
                "status":          status,
            })

    # Sort and assign priorities
    critical.sort(key=lambda x: x["mastery_percent"])
    for i, g in enumerate(critical, 1):
        g["priority"] = i

    strong.sort(key=lambda x: -x["mastery_percent"])
    weak.sort(key=lambda x: x["mastery_percent"])

    return strong, weak, critical


# ── AI prompt (minimal, focused) ─────────────────────────────────────────────

_AI_SCHEMA = """{
  "overall": {
    "score_percent": <int скопируй из данных>,
    "status": "<above_level|on_level|partial_gap|below_level|critical>",
    "status_label_ru": "<строка — название уровня>",
    "student_summary": "<4-5 предложений ОТ ЛИЦА ПЕДАГОГА ДЛЯ АДМИНИСТРАТОРА. ПРАВИЛА: (1) НИ ОДНОГО процента и названия темы — это уже видно в отчёте ниже. (2) Оцени реальный академический уровень как КЛАСС (например: уровень середины 8 класса, начало 9 класса). (3) Опиши типичные ошибки качественно — в чём конкретно слабость. (4) Дай рекомендацию по группе — куда зачислить. (5) Тон: профессиональная оценка учителя, не сухая статистика. ПРИМЕР СТИЛЯ: 'Ученик 10 класса демонстрирует слабое владение математикой. Систематически допускает ошибки при анализе функций и решении уравнений, что указывает на пробелы в базовых понятиях. Реальный уровень знаний соответствует середине 8 класса. Рекомендуется зачислить в группу начала 8 класса с дальнейшей проработкой пропущенных тем.'>"
  },
  "action_plan": [
    {
      "priority": <int начиная с 1>,
      "skill_name_ru": "<полное название навыка>",
      "action_title": "<заголовок MAX 8 слов>",
      "full_description": "<3-5 предложений: что именно отрабатывать, какие типы задач, на какие правила обратить внимание, как проверить усвоение>",
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
    student_name: str,
    test_code: str,
    validation_errors: Optional[List[str]] = None,
) -> str:
    retry = ""
    if validation_errors:
        retry = "\n⚠️ ПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА. ИСПРАВЬ:\n" + "\n".join(f"  • {e}" for e in validation_errors) + "\n"

    return f"""Ты — аналитический модуль платформы ALGO. Аудитория: АДМИНИСТРАТОР учебного центра.
{retry}
ПРАВИЛА:
1. Ответ — ТОЛЬКО валидный JSON. Без текста до/после. Без ```.
2. overall.status — СКОПИРУЙ ТОЧНО: "{computed_status}" (уже вычислено алгоритмом, не меняй).
3. student_summary — ОТ ЛИЦА ПЕДАГОГА ДЛЯ АДМИНИСТРАТОРА (4-5 предложений):
   • НИ ОДНОГО процента и названий тем (они уже есть в отчёте).
   • РЕАЛЬНЫЙ УРОВЕНЬ: {class_equivalent}. Оцени уровень ученика именно так (например, "уровень середины 8 класса").
   • Опиши характер ошибок (в чем именно слабость ученика).
   • Дай прямую рекомендацию по зачислению в группу.
4. action_plan — только для навыков с пробелами. Конкретно: что делать, сколько задач, какой тип.
ЗАПРЕЩЕНО: markdown внутри строк, "уважаемые родители", "потенциал".

ДАННЫЕ УЧЕНИКА:
Ученик: {student_name} | Класс: {grade_level} | Тест: {test_code}
Результат: {score_pct}% ({correct} верных из {total})
Реальный уровень знаний (по IRT-анализу): {class_equivalent}
IRT-статус: {computed_status}

НАВЫКИ (Из IRT-анализа):
{topics_block}

Неверные ответы (контекст для action_plan):
{wrong_block}

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
    student_name: str = "Ученик",
    test_code: str = "",
) -> Optional[DiagReport]:
    """
    Creates DiagReport with hybrid JSON:
      - AI generates: student_summary + action_plan
      - Python generates: error_patterns, weak_skills, strong_skills, critical_gaps
    Never raises — fire-and-forget.
    """
    from src.models.diag_models import DiagAnswer

    report_repo = DiagReportRepository(db)
    existing = report_repo.get_by_session(session_id)
    if existing and existing.report_json:
        log.info("Report already exists for session %s", session_id)
        return existing

    th = float(theta or 0.0)
    se = float(theta_se or 1.0)
    ci_lo = round(th - 2 * se, 4)
    ci_hi = round(th + 2 * se, 4)

    try:
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
        error_patterns = _build_error_patterns(answers_orm, skill_map)
        strong_skills, weak_skills_block, critical_gaps = _build_skill_blocks(
            topic_breakdown, weak_skills, skill_map
        )

        # ── Score stats ───────────────────────────────────────────────────────
        correct = sum(1 for a in answers_orm if float(a.outcome or 0) >= 1.0)
        total = max(items_total, len(answers_orm), 1)
        score_pct = int(round(correct / total * 100))
        # ── Status — computed deterministically from theta AND score_pct (never from AI) ────────
        computed_status    = _compute_overall_status(theta, score_pct)
        computed_label_ru  = _STATUS_LABEL_RU[computed_status]
        class_equivalent   = _compute_class_equivalent(theta, score_pct, grade_level)
        log.info("Computed status=%s (score=%d%%, theta=%.2f, class_eq=%s)", computed_status, score_pct, theta, class_equivalent)

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
        ai_data: Optional[Dict[str, Any]] = None
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
                student_name=student_name,
                test_code=test_code,
                validation_errors=last_errors if attempt > 1 else None,
            )
            raw = call_gemini(prompt, temperature=0.3, max_tokens=2000)
            if not raw:
                log.warning("Attempt %d: empty AI response", attempt)
                continue

            parsed = _extract_json(raw)
            if not parsed:
                last_errors = ["Response is not valid JSON"]
                log.warning("Attempt %d: JSON parse failed", attempt)
                continue

            is_valid, errors = _validate_ai_output(parsed)
            if is_valid:
                ai_data = parsed
                log.info("Attempt %d: AI output valid", attempt)
                break
            else:
                last_errors = errors
                log.warning("Attempt %d: validation errors: %s", attempt, errors[:3])

        if not ai_data:
            log.error("AI generation failed for session %s. Saving with computed data only.", session_id)

        # ── Merge AI + computed data ──────────────────────────────────────────
        overall_block = (ai_data or {}).get("overall", {})
        report_json: Dict[str, Any] = {
            "report_meta": {
                "session_id":       str(session_id),
                "student_name":     student_name,
                "class_level":      grade_level,
                "test_code":        test_code,
                "error_patterns_version": ERROR_PATTERNS_VERSION,
                "date":             date.today().isoformat(),
                "total_questions":  total,
                "questions_correct": correct,
                "score_percent":    score_pct,
            },
            "overall": {
                "score_percent":    score_pct,     # always from data
                "status":           computed_status,   # always from theta
                "status_label_ru":  computed_label_ru, # always from theta
                "student_summary":  overall_block.get("student_summary"),
                "class_equivalent": class_equivalent,  # for reference
                "confidence_of_diagnosis": round(max(0.0, 1.0 - float(theta_se)), 2),
            },
            # ── Computed from data (no AI) ──
            "strong_skills":   strong_skills,
            "weak_skills":     weak_skills_block,
            "critical_gaps":   critical_gaps,
            "error_patterns":  error_patterns,
            # ── AI-generated ──
            "action_plan":     (ai_data or {}).get("action_plan", []),
        }

    except Exception as exc:
        log.error("Report generation error for session %s: %s", session_id, exc, exc_info=True)
        report_json = None

    # ── Persist ───────────────────────────────────────────────────────────────
    try:
        if existing:
            existing.report_json = report_json
            existing.narrative_generated = report_json is not None
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
            narrative_generated=report_json is not None,
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
    """
    Architectural Live Task Enrichment:
    Dynamically re-fetch latest task details from content-service for each item
    in error_patterns so reports always reflect current Content DB task text & LaTeX.
    """
    if not patterns:
        return patterns

    try:
        from src.clients import content_client
        for ep in patterns:
            task_id = ep.get("task_id")
            if not task_id:
                continue
            resp = content_client.get(f"/api/v1/content/tasks/{task_id}")
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
                    ep["correct_answer_latex"] = ca_l or None

                matched = _find_matching_distractor(
                    task_data.get("distractor_meta") or [], ep.get("student_answer"),
                )
                if matched:
                    ep["distractor_explanation"] = _distractor_explanation(matched)
                    ep["distractor_explanation_latex"] = _distractor_explanation_latex(matched)

                option_pairs = _task_option_pairs(
                    task_data, ep.get("correct_answer"), ep.get("correct_answer_latex"),
                )
                if len(option_pairs) >= 2:
                    ep["answer_options"] = [value for value, _ in option_pairs]
                    ep["answer_options_latex"] = [latex for _, latex in option_pairs]
                else:
                    ep["answer_options"] = []
                    ep["answer_options_latex"] = []
                ep["student_answer_latex"] = _student_answer_latex(
                    ep.get("student_answer"), option_pairs,
                )
    except Exception as exc:
        log.warning("Could not live-enrich error patterns: %s", exc)

    return patterns
