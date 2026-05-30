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

    breakdown: dict = session.topic_breakdown or {}
    weak_skills: list = session.weak_skills or []

    skills = []
    counts = {"mastered": 0, "learning": 0, "struggling": 0, "gap": 0}

    for topic_id, info in breakdown.items():
        alpha = float(info.get("alpha", 0.0))
        status = _alpha_to_status(alpha)
        if topic_id in weak_skills:
            status = "gap"
        mastery = round(max(0.0, min(1.0, 0.5 + alpha / 4.0)), 4)
        if status in counts:
            counts[status] += 1
        skills.append({
            "skill_id": topic_id,
            "mastery": mastery,
            "status": status,
            "level": info.get("level", "unknown"),
            "alpha": alpha,
        })

    return {
        "student_id": student_id,
        "session_id": str(session.id),
        "grade_level": session.grade_level,
        "overall_theta": float(session.theta) if session.theta else None,
        "overall_level": session.overall_level,
        "diagnosed_at": session.completed_at.isoformat() if session.completed_at else None,
        "total_topics": len(skills),
        **counts,
        "skills": sorted(skills, key=lambda x: x["mastery"]),
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
    """Последний diag_report ученика."""
    report = (
        db.query(DiagReport)
        .filter(DiagReport.student_id == student_id)
        .order_by(desc(DiagReport.generated_at))
        .first()
    )

    if not report:
        return {"student_id": student_id, "report": None}

    return {
        "student_id": student_id,
        "session_id": str(report.session_id),
        "grade_level": report.grade_level,
        "overall_theta": float(report.overall_theta) if report.overall_theta else None,
        "overall_level": report.overall_level,
        "confidence_interval": {
            "lo": float(report.confidence_interval_lo) if report.confidence_interval_lo else None,
            "hi": float(report.confidence_interval_hi) if report.confidence_interval_hi else None,
        },
        "topic_breakdown": report.topic_breakdown or {},
        "weak_skills": report.weak_skills or [],
        "recommended_start": report.recommended_start,
        "narrative_ru": report.narrative_ru,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
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
