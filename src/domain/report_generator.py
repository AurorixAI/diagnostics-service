"""
Diagnostic Service — Report Generator

Generates a DiagReport for a completed session:
  1. Collects topic/skill names from content-service
  2. Builds a structured prompt with all diagnostic data
  3. Calls Gemini Flash to produce narrative_ru
  4. Persists DiagReport to DB

Fire-and-forget pattern: errors are logged, never raised.
Called once at session completion — ~900 tokens total, ~$0.0001 per report.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.core.gemini_client import call_gemini
from src.models.diag_models import DiagReport
from src.repositories.diag_repo import DiagReportRepository
from src.repositories.knowledge_repo import KnowledgeRepository

log = logging.getLogger(__name__)

# ── Level labels ──────────────────────────────────────────────────────────────

_LEVEL_RU = {
    "mastered":   "Отличное владение",
    "learning":   "Хорошее понимание",
    "struggling": "Есть затруднения",
    "gap":        "Пробел в знаниях",
    "below_grade":"Ниже уровня класса",
    "at_grade":   "Уровень класса",
    "above_grade":"Выше уровня класса",
}

_OVERALL_VERDICT = {
    "below_grade": "нуждается в дополнительной поддержке по ключевым темам",
    "at_grade":    "соответствует программе класса",
    "above_grade": "демонстрирует знания выше программы класса",
}


# ── Topic name resolver ───────────────────────────────────────────────────────

def _get_topic_names(topic_ids: List[str]) -> Dict[str, str]:
    """Fetch human-readable topic names from content-service. Fallback to ID."""
    repo = KnowledgeRepository()
    names: Dict[str, str] = {}
    for tid in topic_ids:
        try:
            node = repo.get_by_id(tid)
            if node and hasattr(node, "name"):
                names[tid] = node.name
            else:
                names[tid] = tid
        except Exception:
            names[tid] = tid
    return names


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    grade_level: int,
    overall_level: str,
    theta: float,
    topic_breakdown: Dict[str, Any],
    weak_skills: List[str],
    items_total: int,
    topic_names: Dict[str, str],
) -> str:
    # Сортируем темы от слабого к сильному
    sorted_topics = sorted(
        topic_breakdown.items(),
        key=lambda kv: float(kv[1].get("alpha", 0)),
    )

    topic_lines = []
    for tid, info in sorted_topics:
        alpha = float(info.get("alpha", 0))
        level = info.get("level", "learning")
        name = topic_names.get(tid, tid)
        is_weak = tid in weak_skills
        marker = " ⚠️" if is_weak else ""
        topic_lines.append(
            f"  • {name}: {_LEVEL_RU.get(level, level)} "
            f"(α={alpha:+.2f}){marker}"
        )

    topics_block = "\n".join(topic_lines) if topic_lines else "  Данные не доступны"
    overall_ru = _LEVEL_RU.get(overall_level, overall_level)
    verdict = _OVERALL_VERDICT.get(overall_level, "")
    weak_names = [topic_names.get(s, s) for s in weak_skills]
    weak_block = (
        "  • " + "\n  • ".join(weak_names) if weak_names
        else "  Слабых зон не выявлено"
    )

    return f"""Ты — педагогический аналитик платформы ALGO. Напиши профессиональный отчёт об итогах диагностики ученика.

ДАННЫЕ ДИАГНОСТИКИ:
- Класс: {grade_level}
- Пройдено заданий: {items_total}
- Общий уровень: {overall_ru} (θ = {theta:+.2f})
- Вердикт: ученик {verdict}

РАЗБИВКА ПО ТЕМАМ:
{topics_block}

ПРИОРИТЕТНЫЕ ПРОБЕЛЫ:
{weak_block}

ТРЕБОВАНИЯ К ОТЧЁТУ:
- Обратись к учителю/родителю, не к ученику
- 3–4 абзаца: (1) общий вывод, (2) сильные стороны, (3) зоны роста с конкретными темами, (4) рекомендация по дальнейшим шагам
- Деловой, но тёплый тон; без жаргона и технических терминов (не упоминай θ, α, IRT)
- Конкретные темы называй по имени, не по коду
- Если пробелов нет — акцент на развитии
- Только текст, без markdown-заголовков, без списков

Напиши отчёт на русском языке:"""


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
) -> Optional[DiagReport]:
    """
    Creates DiagReport, generates narrative with Gemini, saves to DB.
    Returns the created report, or None if anything fails.
    Never raises — fire-and-forget.
    """
    report_repo = DiagReportRepository(db)

    # Idempotent: skip if report already exists for this session
    existing = report_repo.get_by_session(session_id)
    if existing:
        log.info("Report already exists for session %s — skipping", session_id)
        return existing

    # Confidence interval (95% ≈ ±2·SE)
    ci_lo = round(theta - 2 * theta_se, 4)
    ci_hi = round(theta + 2 * theta_se, 4)

    # Recommended start = first weak skill
    recommended_start: Optional[str] = weak_skills[0] if weak_skills else None

    try:
        # Resolve human-readable topic names
        all_topic_ids = list(topic_breakdown.keys())
        topic_names = _get_topic_names(all_topic_ids)

        # Build prompt and call Gemini
        prompt = _build_prompt(
            grade_level=grade_level,
            overall_level=overall_level,
            theta=theta,
            topic_breakdown=topic_breakdown,
            weak_skills=weak_skills,
            items_total=items_total,
            topic_names=topic_names,
        )
        narrative = call_gemini(prompt, temperature=0.45, max_tokens=800)

    except Exception as exc:
        log.warning("Narrative generation failed for session %s: %s", session_id, exc)
        narrative = None

    # Create and persist report regardless of narrative success
    try:
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
            recommended_start=recommended_start,
            narrative_ru=narrative,
            narrative_generated=narrative is not None,
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        log.info(
            "DiagReport created for session %s (narrative=%s)",
            session_id,
            "yes" if narrative else "no",
        )
        return report

    except Exception as exc:
        log.error("Failed to save DiagReport for session %s: %s", session_id, exc)
        db.rollback()
        return None
