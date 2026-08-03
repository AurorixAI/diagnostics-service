"""
Diagnostic Service — Analytics Router

Reads from algo-postgres-diag (diag_sessions, diag_answers, diag_reports).
No dependency on monolith DB.

Endpoints:
  GET /analytics/students/{student_id}/skill-map     — per-topic mastery from latest session
  GET /analytics/students/{student_id}/timeline      — all sessions over time
  GET /analytics/students/{student_id}/report        — latest diag_report
  GET /analytics/groups/overview                     — aggregate for list of student_ids
  GET /analytics/org/live-queue                      — active/recent sessions (last 24h)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.models.diag_models import DiagAnswer, DiagReport, DiagSession
from src.repositories.knowledge_repo import KnowledgeRepository

log = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ── helpers ────────────────────────────────────────────────────────────────────

def _theta_to_status(theta: Optional[float]) -> str:
    if theta is None:
        return "no_data"
    if theta >= 1.5:
        return "mastered"
    if theta >= 0.0:
        return "learning"
    if theta >= -1.0:
        return "struggling"
    return "gap"


def _alpha_to_status(alpha: float) -> str:
    if alpha >= 0.4:
        return "mastered"
    if alpha >= -0.2:
        return "learning"
    if alpha >= -0.8:
        return "struggling"
    return "gap"


# ── 1. STUDENT SKILL MAP ───────────────────────────────────────────────────────

@router.get("/students/{student_id}/skill-map")
def student_skill_map(
    student_id: str,
    db: Session = Depends(get_db),
):
    """
    Per-topic mastery карта ученика из последней завершённой диагностики.
    topic_breakdown: {topic_id: {alpha, level}}
    """
    session = (
        db.query(DiagSession)
        .filter(
            DiagSession.student_id == student_id,
            DiagSession.phase == "completed",
        )
        .order_by(desc(DiagSession.completed_at))
        .first()
    )

    if not session:
        return {
            "student_id": student_id,
            "total_topics": 0,
            "mastered": 0,
            "learning": 0,
            "struggling": 0,
            "gaps": 0,
            "skills": [],
        }

    # Query actual L4 atomic skills tested in this session from DiagAnswer
    answers = (
        db.query(DiagAnswer)
        .filter(DiagAnswer.session_id == session.id)
        .order_by(DiagAnswer.answered_at)
        .all()
    )

    confirmed_gaps = set(session.weak_skills or [])

    # Aggregate outcomes by L4 skill_id
    skill_stats: dict[str, dict] = {}
    for a in answers:
        if not a.skill_id:
            continue
        if a.skill_id not in skill_stats:
            skill_stats[a.skill_id] = {"total": 0, "correct": 0, "outcomes": []}
        skill_stats[a.skill_id]["total"] += 1
        skill_stats[a.skill_id]["outcomes"].append(float(a.outcome))
        if a.outcome >= 1.0:
            skill_stats[a.skill_id]["correct"] += 1

    knowledge_repo = KnowledgeRepository()

    _LEVEL_RU_MAP = {
        "mastered":   "Отличное владение",
        "learning":   "Хорошее понимание",
        "struggling": "Есть затруднения",
        "gap":        "Пробел",
    }

    skills = []
    counts = {"mastered": 0, "learning": 0, "struggling": 0, "gap": 0}

    for skill_id, stats in skill_stats.items():
        outcomes = stats["outcomes"]
        avg_outcome = sum(outcomes) / len(outcomes) if outcomes else 0.0

        if skill_id in confirmed_gaps or avg_outcome < 0.5:
            status = "gap"
            front_level = "gap"
            mastery = round(min(0.4, avg_outcome), 4)
        elif avg_outcome >= 0.8:
            status = "mastered"
            front_level = "strong"
            mastery = round(max(0.75, avg_outcome), 4)
        else:
            status = "learning"
            front_level = "medium"
            mastery = round(avg_outcome, 4)

        if status in counts:
            counts[status] += 1

        try:
            node = knowledge_repo.get_by_id(skill_id)
            name_str = getattr(node, "name_ru", getattr(node, "name", skill_id)) if node else skill_id
        except Exception:
            name_str = skill_id

        skills.append({
            "skill_id": skill_id,
            "skill_name": name_str,
            "name": name_str,
            "status": _LEVEL_RU_MAP.get(status, status),
            "mastery": mastery,
            "mastery_pct": round(mastery * 100, 1),
            "level": front_level,
        })

    return {
        "grade_level": session.grade_level,
        "overall_level": _LEVEL_RU_MAP.get(session.overall_level or "", session.overall_level),
        "diagnosed_at": session.completed_at.isoformat() if session.completed_at else None,
        "total_topics": len(skills),
        **counts,
        "skills": sorted(skills, key=lambda x: (x["level"] != "gap", x["mastery_pct"])),
    }


# ── 2. STUDENT TIMELINE ────────────────────────────────────────────────────────

@router.get("/students/{student_id}/timeline")
def student_timeline(
    student_id: str,
    db: Session = Depends(get_db),
):
    """Динамика θ ученика — все завершённые сессии по времени."""
    sessions = (
        db.query(DiagSession)
        .filter(
            DiagSession.student_id == student_id,
            DiagSession.phase == "completed",
        )
        .order_by(DiagSession.completed_at)
        .all()
    )

    timeline = []
    for s in sessions:
        theta = float(s.theta) if s.theta else None
        timeline.append({
            "session_id": str(s.id),
            "date": s.completed_at.isoformat() if s.completed_at else None,
            "theta": theta,
            "se": float(s.theta_se) if s.theta_se else None,
            "items_answered": s.items_answered,
            "overall_level": s.overall_level,
            "grade_level": s.grade_level,
            "weak_skills_count": len(s.weak_skills or []),
        })

    thetas = [t["theta"] for t in timeline if t["theta"] is not None]
    trend = "stable"
    if len(thetas) >= 2:
        if thetas[-1] > thetas[0] + 0.3:
            trend = "improving"
        elif thetas[-1] < thetas[0] - 0.3:
            trend = "declining"

    return {
        "student_id": student_id,
        "total_sessions": len(timeline),
        "trend": trend,
        "latest_theta": thetas[-1] if thetas else None,
        "timeline": timeline,
    }


# ── 3. STUDENT REPORT ──────────────────────────────────────────────────────────

@router.get("/students/{student_id}/report")
def student_report(
    student_id: str,
    db: Session = Depends(get_db),
):
    """Последний diag_report ученика + данные из DiagSession."""
    report = (
        db.query(DiagReport)
        .filter(DiagReport.student_id == student_id)
        .order_by(desc(DiagReport.generated_at))
        .first()
    )

    # Latest completed session — needed for theta, accuracy, topic_breakdown
    session = (
        db.query(DiagSession)
        .filter(
            DiagSession.student_id == student_id,
            DiagSession.phase == "completed",
        )
        .order_by(desc(DiagSession.completed_at))
        .first()
    )

    if not report and not session:
        return {"report": None}

    # Resolve human-readable names for weak skills
    knowledge_repo = KnowledgeRepository()
    weak_skill_ids: list = (report.weak_skills if report else None) or (session.weak_skills if session else None) or []
    weak_names: list[str] = []
    skill_names: dict[str, str] = {}
    for sid in weak_skill_ids:
        try:
            node = knowledge_repo.get_by_id(sid)
            name = node.name if node and hasattr(node, "name") else sid
        except Exception:
            name = sid
        weak_names.append(name)
        skill_names[sid] = name

    _LEVEL_RU_MAP = {
        "mastered":    "Отличное владение",
        "learning":    "Хорошее понимание",
        "struggling":  "Есть затруднения",
        "gap":         "Пробел в знаниях",
        "below_grade": "Ниже уровня класса",
        "at_grade":    "Соответствует программе",
        "above_grade": "Выше уровня класса",
    }

    # Build confidence interval from theta_se if available
    theta_val = float(session.theta) if session and session.theta is not None else None
    theta_se = float(session.theta_se) if session and session.theta_se is not None else 0.5
    confidence_interval = (
        [round(theta_val - 1.96 * theta_se, 3), round(theta_val + 1.96 * theta_se, 3)]
        if theta_val is not None
        else None
    )

    # Calculate accuracy and correct count from diag_answers
    accuracy_val = None
    correct_count = 0
    if session:
        ans_stats = (
            db.query(
                func.count(DiagAnswer.id).label("total"),
                func.sum(DiagAnswer.outcome).label("correct")
            )
            .filter(DiagAnswer.session_id == session.id)
            .first()
        )
        if ans_stats and ans_stats.total and ans_stats.total > 0:
            correct_count = int(ans_stats.correct or 0)
            accuracy_val = round(float(correct_count) / float(ans_stats.total), 4)

    overall_level_key = (report.overall_level if report else None) or (session.overall_level if session else None)

    # Enrich topic_breakdown with human-readable names (name_ru) and mastery [0, 1]
    raw_breakdown = session.topic_breakdown if session else {}
    enriched_breakdown = {}
    for tid, info in raw_breakdown.items():
        info_copy = dict(info)
        try:
            node = knowledge_repo.get_by_id(tid)
            name = getattr(node, "name_ru", getattr(node, "name", tid)) if node else tid
        except Exception:
            name = tid
        alpha = float(info.get("alpha", 0.0))
        mastery = round(max(0.0, min(1.0, 0.5 + alpha / 4.0)), 4)
        info_copy["name_ru"] = name
        info_copy["name"] = name
        info_copy["mastery"] = mastery
        info_copy["mastery_pct"] = round(mastery * 100, 1)
        enriched_breakdown[tid] = info_copy

    return {
        # Core report fields
        "grade_level":    (report.grade_level if report else None) or (session.grade_level if session else None),
        "overall_level":  _LEVEL_RU_MAP.get(overall_level_key or "", overall_level_key),
        "narrative_ru":   report.narrative_ru if report else None,
        "generated_at":   report.generated_at.isoformat() if report and report.generated_at else None,
        # IRT fields (from DiagSession)
        "overall_theta":  theta_val,
        "accuracy":       accuracy_val,
        "confidence_interval": confidence_interval,
        "items_total":    session.items_answered if session else None,
        "correct_answers": correct_count,
        # Topic breakdown — {topic_id: {alpha, level, name_ru, name}}
        "topic_breakdown": enriched_breakdown,
        # Weak skills
        "weak_topics":   weak_names,           # human-readable list
        "weak_skills":   weak_skill_ids,        # raw IDs (for frontend mapping)
        "skill_names":   skill_names,           # id → name map
        # Distractor errors (not yet populated per-report — empty list safe default)
        "distractor_errors": [],
    }


# ── 4. GROUP OVERVIEW ──────────────────────────────────────────────────────────

@router.get("/groups/overview")
def group_overview(
    student_ids: List[str] = Query(..., description="Список student_id группы"),
    db: Session = Depends(get_db),
):
    """
    Обзор группы — принимает список student_ids от фронта/монолита.
    Возвращает: avg_theta, распределение уровней, данные по каждому ученику.
    """
    students_data = []
    thetas = []
    level_counts = {"mastered": 0, "learning": 0, "struggling": 0, "gap": 0, "no_data": 0}

    for sid in student_ids:
        session = (
            db.query(DiagSession)
            .filter(
                DiagSession.student_id == sid,
                DiagSession.phase == "completed",
            )
            .order_by(desc(DiagSession.completed_at))
            .first()
        )

        theta = float(session.theta) if session and session.theta else None
        status = _theta_to_status(theta)

        if theta is not None:
            thetas.append(theta)

        level_key = status if status in level_counts else "no_data"
        level_counts[level_key] += 1

        students_data.append({
            "student_id": sid,
            "theta": theta,
            "overall_level": session.overall_level if session else None,
            "status": status,
            "grade_level": session.grade_level if session else None,
            "diagnosed_at": session.completed_at.isoformat() if session and session.completed_at else None,
            "weak_skills_count": len(session.weak_skills or []) if session else 0,
        })

    avg_theta = round(sum(thetas) / len(thetas), 3) if thetas else None

    return {
        "student_count": len(student_ids),
        "avg_theta": avg_theta,
        "level_distribution": level_counts,
        "students": sorted(students_data, key=lambda x: (x["theta"] or -99)),
    }


# ── 5. GROUP SKILL HEATMAP ─────────────────────────────────────────────────────

@router.get("/groups/heatmap")
def group_skill_heatmap(
    student_ids: List[str] = Query(..., description="Список student_id группы"),
    db: Session = Depends(get_db),
):
    """
    Тепловая карта навыков группы (students × topics).
    Данные из последней сессии каждого ученика.
    """
    all_topics: set = set()
    student_breakdowns: dict = {}

    for sid in student_ids:
        session = (
            db.query(DiagSession)
            .filter(
                DiagSession.student_id == sid,
                DiagSession.phase == "completed",
            )
            .order_by(desc(DiagSession.completed_at))
            .first()
        )

        breakdown = session.topic_breakdown or {} if session else {}
        weak = set(session.weak_skills or []) if session else set()

        student_breakdowns[sid] = {"breakdown": breakdown, "weak": weak}
        all_topics.update(breakdown.keys())

    all_topics_sorted = sorted(all_topics)

    heatmap = []
    for sid in student_ids:
        info = student_breakdowns[sid]
        row = {"student_id": sid, "skills": {}}
        for topic_id in all_topics_sorted:
            if topic_id in info["breakdown"]:
                alpha = float(info["breakdown"][topic_id].get("alpha", 0.0))
                status = _alpha_to_status(alpha)
                if topic_id in info["weak"]:
                    status = "gap"
                row["skills"][topic_id] = {
                    "mastery": round(max(0.0, min(1.0, 0.5 + alpha / 4.0)), 4),
                    "status": status,
                }
        heatmap.append(row)

    # Per-topic group averages
    topic_averages = {}
    for topic_id in all_topics_sorted:
        values = []
        for sid in student_ids:
            bd = student_breakdowns[sid]["breakdown"]
            if topic_id in bd:
                alpha = float(bd[topic_id].get("alpha", 0.0))
                values.append(max(0.0, min(1.0, 0.5 + alpha / 4.0)))
        topic_averages[topic_id] = round(sum(values) / len(values), 3) if values else 0.0

    return {
        "topics": all_topics_sorted,
        "topic_averages": topic_averages,
        "heatmap": heatmap,
    }


# ── 6. ORG LIVE QUEUE ──────────────────────────────────────────────────────────

@router.get("/org/live-queue")
def org_live_queue(
    hours: int = Query(24, ge=1, le=168, description="Период в часах"),
    db: Session = Depends(get_db),
):
    """
    Живая очередь диагностик за последние N часов.
    Активные (in-progress) + завершённые.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Active sessions (not completed, created recently)
    active = (
        db.query(DiagSession)
        .filter(
            DiagSession.phase != "completed",
            DiagSession.created_at >= since,
        )
        .order_by(desc(DiagSession.created_at))
        .all()
    )

    # Completed in window
    completed = (
        db.query(DiagSession)
        .filter(
            DiagSession.phase == "completed",
            DiagSession.completed_at >= since,
        )
        .order_by(desc(DiagSession.completed_at))
        .limit(100)
        .all()
    )

    def _fmt(s: DiagSession, status: str) -> dict:
        return {
            "session_id": str(s.id),
            "student_id": str(s.student_id),
            "invite_code": s.invite_code,
            "grade_level": s.grade_level,
            "status": status,
            "phase": s.phase,
            "items_answered": s.items_answered,
            "theta": float(s.theta) if s.theta else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }

    return {
        "period_hours": hours,
        "active_count": len(active),
        "completed_count": len(completed),
        "active": [_fmt(s, "in_progress") for s in active],
        "completed": [_fmt(s, "completed") for s in completed],
    }


# ── 7. ORG STATS ───────────────────────────────────────────────────────────────

@router.get("/org/stats")
def org_stats(
    db: Session = Depends(get_db),
):
    """Общая статистика: всего сессий, завершённых, средний theta."""
    total = db.query(func.count(DiagSession.id)).scalar()
    completed = db.query(func.count(DiagSession.id)).filter(DiagSession.phase == "completed").scalar()
    avg_theta = db.query(func.avg(DiagSession.theta)).filter(DiagSession.phase == "completed").scalar()

    return {
        "total_sessions": total,
        "completed_sessions": completed,
        "avg_theta": round(float(avg_theta), 3) if avg_theta else None,
    }
