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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.access import (
    DiagnosticActor,
    require_diagnostic_staff,
    require_student_report_access,
)
from src.models.diag_models import DiagAnswer, DiagReport, DiagSession
from src.repositories.knowledge_repo import KnowledgeRepository
from src.domain.report_generator import REPORT_SCHEMA_VERSION
from src.domain.level_policy import (
    CATEGORY_LABEL_RU,
    classify,
    count_solved,
    is_correct,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ── helpers ────────────────────────────────────────────────────────────────────

# Legacy four-value mastery vocabulary of the group overview, now derived from
# the single level policy (previously its own theta cut-offs 1.5 / 0 / -1).
_LEVEL_STATUS_TO_MASTERY = {
    "above": "mastered",
    "on_level": "learning",
    "partial_gap": "struggling",
    "below": "gap",
    "critical": "gap",
}


def _theta_to_status(theta: Optional[float], se: Optional[float] = None, grade: int = 0) -> str:
    if theta is None:
        return "no_data"
    return _LEVEL_STATUS_TO_MASTERY[classify(theta, se, grade)["status"]]


def _level_fields(session) -> dict:
    """Level fields of a completed session, from the one policy."""
    theta = float(session.theta) if session is not None and session.theta is not None else None
    se = float(session.theta_se) if session is not None and session.theta_se is not None else None
    level = classify(theta, se, session.grade_level if session is not None else 0)
    return {
        "category": level["category"] or (session.overall_level if session is not None else None),
        "level_status": level["status"],
        "level_provisional": level["provisional"],
    }


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
async def student_skill_map(
    student_id: str,
    db: Session = Depends(get_db),
    actor: DiagnosticActor = Depends(require_diagnostic_staff),
):
    """
    Per-topic mastery карта ученика из последней завершённой диагностики.
    topic_breakdown: {topic_id: {alpha, level}}
    """
    await require_student_report_access(actor, student_id)
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
        if is_correct(a.outcome):
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
        "overall_level": CATEGORY_LABEL_RU.get(session.overall_level or "", session.overall_level),
        **{k: v for k, v in _level_fields(session).items() if k != "category"},
        "diagnosed_at": session.completed_at.isoformat() if session.completed_at else None,
        "total_topics": len(skills),
        **counts,
        "skills": sorted(skills, key=lambda x: (x["level"] != "gap", x["mastery_pct"])),
    }


# ── 2. STUDENT TIMELINE ────────────────────────────────────────────────────────

@router.get("/students/{student_id}/timeline")
async def student_timeline(
    student_id: str,
    db: Session = Depends(get_db),
    actor: DiagnosticActor = Depends(require_diagnostic_staff),
):
    """Динамика θ ученика — все завершённые сессии по времени."""
    await require_student_report_access(actor, student_id)
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
            **({k: v for k, v in _level_fields(s).items() if k != "category"} if s.theta is not None else {}),
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
async def student_report(
    student_id: str,
    session_id: Optional[str] = Query(None, description="Exact diagnostic session for this report"),
    db: Session = Depends(get_db),
    actor: DiagnosticActor = Depends(require_diagnostic_staff),
):
    import uuid

    try:
        sid_uuid = uuid.UUID(student_id)
    except Exception:
        sid_uuid = None

    if not sid_uuid:
        raise HTTPException(status_code=404, detail="Ученик не найден")

    exact_session_id = None
    if session_id:
        try:
            exact_session_id = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Некорректный идентификатор сессии")

    if exact_session_id:
        session = (
            db.query(DiagSession)
            .filter(
                DiagSession.id == exact_session_id,
                DiagSession.student_id == sid_uuid,
                DiagSession.phase == "completed",
            )
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Отчёт этой диагностики не найден")
    else:
        session = (
            db.query(DiagSession)
            .filter(
                DiagSession.student_id == sid_uuid,
                DiagSession.phase == "completed",
            )
            .order_by(desc(DiagSession.completed_at))
            .first()
        )

    if session:
        await require_student_report_access(actor, str(session.student_id))
    else:
        await require_student_report_access(actor, str(sid_uuid))

    # DiagReport by student_id, session_id, or session.id
    report = None
    if session:
        report = (
            db.query(DiagReport)
            .filter(DiagReport.session_id == session.id)
            .first()
        )
    if not report and not exact_session_id:
        report = (
            db.query(DiagReport)
            .filter(DiagReport.student_id == sid_uuid)
            .order_by(desc(DiagReport.generated_at))
            .first()
        )

    if not report and not session:
        return {"report": None}

    # A GET must remain read-only. Historically, merely opening this page
    # could transmit a completed historic diagnostic to the narrative model.
    # New diagnostics are queued at completion; historic rebuilds are an
    # explicit, auditable operation.

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

    # Category labels come from the single level policy (no local dictionary).
    _LEVEL_RU_MAP = CATEGORY_LABEL_RU

    # Build confidence interval from theta_se if available
    theta_val = float(session.theta) if session and session.theta is not None else None
    theta_se = float(session.theta_se) if session and session.theta_se is not None else 0.5
    confidence_interval = (
        [round(theta_val - 1.96 * theta_se, 3), round(theta_val + 1.96 * theta_se, 3)]
        if theta_val is not None
        else None
    )

    # "Solved N of M": adaptive-test answers only, with the one is_correct rule
    # (same numbers as report_json.level and the auth completion payload).
    accuracy_val = None
    correct_count = 0
    measured_total = 0
    if session:
        counts = count_solved(
            db.query(DiagAnswer).filter(DiagAnswer.session_id == session.id).all()
        )
        correct_count, measured_total = counts["solved"], counts["total"]
        if measured_total:
            accuracy_val = round(float(correct_count) / float(measured_total), 4)

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

    hierarchical_tree = _build_hierarchical_tree(session, db, knowledge_repo)
    trajectory = _build_diagnostic_trajectory(session, db, knowledge_repo)

    out_report_json = report.report_json if report else None
    if isinstance(out_report_json, dict):
        # Reports older than schema 5 still hold retired claims (O4): never expose them.
        from src.domain.report_generator import strip_retired_report_fields
        out_report_json = strip_retired_report_fields(out_report_json)
    if out_report_json and isinstance(out_report_json, dict) and "error_patterns" in out_report_json:
        try:
            from src.domain.report_generator import refresh_error_patterns_live
            out_report_json = dict(out_report_json)
            out_report_json["error_patterns"] = refresh_error_patterns_live(out_report_json["error_patterns"])
        except Exception as exc:
            log.warning("Could not enrich report_json live: %s", exc)

    return {
        # ── Structured JSON report (v2) ─────────────────────────────────────
        "session_id": str(session.id) if session else (str(report.session_id) if report else None),
        "report_json":    out_report_json,
        # Observable lifecycle for staff UI. This endpoint never starts work:
        # a report is queued only when a new diagnostic is completed or when a
        # staff member explicitly requests a historical rebuild.
        "report_generation": {
            "status": report.generation_status if report else "pending",
            "stage": report.generation_stage if report else "queued",
            "attempts": int(report.generation_attempts or 0) if report else 0,
            "is_current_schema": bool(
                report
                and report.report_json
                and report.report_schema_version >= REPORT_SCHEMA_VERSION
                and report.generation_status == "ready"
            ),
        },
        # ── Core report fields ──────────────────────────────────────────────
        "grade_level":    (report.grade_level if report else None) or (session.grade_level if session else None),
        "overall_level":  _LEVEL_RU_MAP.get(overall_level_key or "", overall_level_key),
        "narrative_ru":   report.narrative_ru if report else None,
        "generated_at":   report.generated_at.isoformat() if report and report.generated_at else None,
        # ── IRT fields (from DiagSession) ───────────────────────────────────
        "overall_theta":  theta_val,
        "accuracy":       accuracy_val,
        "confidence_interval": confidence_interval,
        "items_total":    session.items_answered if session else None,
        "correct_answers": correct_count,
        "solved": correct_count,
        "total": measured_total,
        "level": _level_fields(session) if session else None,
        # ── Topic breakdown ─────────────────────────────────────────────────
        "topic_breakdown": enriched_breakdown,
        "hierarchical_tree": hierarchical_tree,
        "trajectory": trajectory,
        # ── Weak skills ─────────────────────────────────────────────────────
        "weak_topics":   weak_names,
        "weak_skills":   weak_skill_ids,
        "skill_names":   skill_names,
        "distractor_errors": [
            ep for ep in (out_report_json.get("error_patterns", []) if isinstance(out_report_json, dict) else [])
            if isinstance(ep, dict) and ep.get("eval_category") == "distractor"
        ],
    }


def _build_hierarchical_tree(session: Optional[DiagSession], db: Session, knowledge_repo: KnowledgeRepository) -> list[dict]:
    """Build 3-level tree (Topic L2 -> Subtopic L3 -> Skill L4) from DiagAnswers in session."""
    if not session:
        return []

    answers = (
        db.query(DiagAnswer)
        .filter(DiagAnswer.session_id == session.id)
        .order_by(DiagAnswer.answered_at)
        .all()
    )

    tree_map: dict[str, dict] = {}
    for a in answers:
        if not a.skill_id:
            continue
        skill_node = knowledge_repo.get_by_id(a.skill_id)
        if not skill_node:
            continue

        subtopic_id = getattr(skill_node, "parent_id", "other") or "other"
        subtopic_node = knowledge_repo.get_by_id(subtopic_id) if subtopic_id != "other" else None

        topic_id = getattr(subtopic_node, "parent_id", "other") if subtopic_node else "other"
        topic_node = knowledge_repo.get_by_id(topic_id) if topic_id != "other" else None

        t_name = getattr(topic_node, "name_ru", getattr(topic_node, "name", topic_id)) if topic_node else topic_id
        t_grade = getattr(topic_node, "class_level_start", getattr(session, "grade_level", 10)) if topic_node else getattr(session, "grade_level", 10)

        sub_name = getattr(subtopic_node, "name_ru", getattr(subtopic_node, "name", subtopic_id)) if subtopic_node else subtopic_id
        sub_grade = getattr(subtopic_node, "class_level_start", t_grade) if subtopic_node else t_grade

        sk_name = getattr(skill_node, "name_ru", getattr(skill_node, "name", a.skill_id))
        sk_grade = getattr(skill_node, "class_level_start", sub_grade)

        if topic_id not in tree_map:
            tree_map[topic_id] = {
                "id": topic_id,
                "name": t_name,
                "grade_level": t_grade,
                "subtopics": {},
            }
        if subtopic_id not in tree_map[topic_id]["subtopics"]:
            tree_map[topic_id]["subtopics"][subtopic_id] = {
                "id": subtopic_id,
                "name": sub_name,
                "grade_level": sub_grade,
                "skills": {},
            }

        sub_skills = tree_map[topic_id]["subtopics"][subtopic_id]["skills"]
        if a.skill_id not in sub_skills:
            sub_skills[a.skill_id] = {
                "id": a.skill_id,
                "name": sk_name,
                "grade_level": sk_grade,
                "outcomes": [],
                "is_deep_scan": False,
            }
        sub_skills[a.skill_id]["outcomes"].append(float(a.outcome))
        if a.is_deep_scan:
            sub_skills[a.skill_id]["is_deep_scan"] = True

    hierarchical_tree = []
    for tid, tdata in tree_map.items():
        subtopics_list = []
        topic_outcomes = []

        for subid, subdata in tdata["subtopics"].items():
            skills_list = []
            sub_outcomes = []
            for sk_id, sk_data in subdata["skills"].items():
                sk_avg = sum(sk_data["outcomes"]) / len(sk_data["outcomes"]) if sk_data["outcomes"] else 0.0
                sub_outcomes.extend(sk_data["outcomes"])
                topic_outcomes.extend(sk_data["outcomes"])
                sk_status = "mastered" if sk_avg >= 0.8 else ("learning" if sk_avg >= 0.5 else "gap")
                skills_list.append({
                    "id": sk_id,
                    "name": sk_data["name"],
                    "grade_level": sk_data["grade_level"],
                    "outcome": sk_avg,
                    "mastery_pct": round(sk_avg * 100, 1),
                    "status": sk_status,
                    "is_deep_scan": sk_data["is_deep_scan"],
                })

            sub_avg = sum(sub_outcomes) / len(sub_outcomes) if sub_outcomes else 0.0
            sub_status = "mastered" if sub_avg >= 0.8 else ("learning" if sub_avg >= 0.5 else "gap")
            subtopics_list.append({
                "id": subid,
                "name": subdata["name"],
                "grade_level": subdata["grade_level"],
                "mastery_pct": round(sub_avg * 100, 1),
                "status": sub_status,
                "skills": skills_list,
            })

        t_avg = sum(topic_outcomes) / len(topic_outcomes) if topic_outcomes else 0.0
        t_mastery_pct = round(t_avg * 100, 1)

        hierarchical_tree.append({
            "id": tid,
            "name": tdata["name"],
            "grade_level": tdata["grade_level"],
            "mastery_pct": t_mastery_pct,
            "subtopics": subtopics_list,
        })

    return hierarchical_tree


def _build_diagnostic_trajectory(session: Optional[DiagSession], db: Session, knowledge_repo: KnowledgeRepository) -> list[dict]:
    """Build step-by-step diagnostic trajectory timeline (Questions 1..N) from DiagAnswers."""
    if not session:
        return []

    answers = (
        db.query(DiagAnswer)
        .filter(DiagAnswer.session_id == session.id)
        .order_by(DiagAnswer.answered_at)
        .all()
    )

    trajectory = []
    for i, a in enumerate(answers, 1):
        skill_node = knowledge_repo.get_by_id(a.skill_id) if a.skill_id else None
        sk_name = getattr(skill_node, "name_ru", getattr(skill_node, "name", a.skill_id)) if skill_node else (a.skill_id or f"Вопрос {i}")
        sk_grade = getattr(skill_node, "class_level_start", getattr(session, "grade_level", 10)) if skill_node else getattr(session, "grade_level", 10)

        subtopic_id = getattr(skill_node, "parent_id", None) if skill_node else None
        subtopic_node = knowledge_repo.get_by_id(subtopic_id) if subtopic_id else None
        topic_id = getattr(subtopic_node, "parent_id", None) if subtopic_node else None
        topic_node = knowledge_repo.get_by_id(topic_id) if topic_id else None

        t_name = getattr(topic_node, "name_ru", getattr(topic_node, "name", "")) if topic_node else ""

        trajectory.append({
            "step": i,
            "task_id": a.task_id,
            "skill_id": a.skill_id,
            "skill_name": sk_name,
            "topic_name": t_name,
            "grade_level": sk_grade,
            "outcome": float(a.outcome),
            "is_correct": is_correct(a.outcome),
            "theta_after": round(float(a.theta_after), 2) if a.theta_after is not None else 0.0,
            "is_deep_scan": a.is_deep_scan,
        })

    return trajectory




# ── 4. GROUP OVERVIEW ──────────────────────────────────────────────────────────

@router.get("/groups/overview")
async def group_overview(
    student_ids: List[str] = Query(..., description="Список student_id группы"),
    db: Session = Depends(get_db),
    actor: DiagnosticActor = Depends(require_diagnostic_staff),
):
    """
    Обзор группы — принимает список student_ids от фронта/монолита.
    Возвращает: avg_theta, распределение уровней, данные по каждому ученику.
    """
    students_data = []
    thetas = []
    level_counts = {"mastered": 0, "learning": 0, "struggling": 0, "gap": 0, "no_data": 0}

    for sid in student_ids:
        await require_student_report_access(actor, sid)
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
        status = _theta_to_status(theta, float(session.theta_se) if session and session.theta_se is not None else None, session.grade_level if session else 0)

        if theta is not None:
            thetas.append(theta)

        level_key = status if status in level_counts else "no_data"
        level_counts[level_key] += 1

        students_data.append({
            "student_id": sid,
            "theta": theta,
            "overall_level": session.overall_level if session else None,
            "status": status,
            **(_level_fields(session) if session and theta is not None else {}),
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
async def group_skill_heatmap(
    student_ids: List[str] = Query(..., description="Список student_id группы"),
    db: Session = Depends(get_db),
    actor: DiagnosticActor = Depends(require_diagnostic_staff),
):
    """
    Тепловая карта навыков группы (students × topics).
    Данные из последней сессии каждого ученика.
    """
    all_topics: set = set()
    student_breakdowns: dict = {}

    for sid in student_ids:
        await require_student_report_access(actor, sid)
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
async def org_live_queue(
    hours: int = Query(24, ge=1, le=168, description="Период в часах"),
    db: Session = Depends(get_db),
    actor: DiagnosticActor = Depends(require_diagnostic_staff),
):
    """
    Живая очередь диагностик за последние N часов.
    Активные (in-progress) + завершённые.
    """
    # Legacy diagnostic sessions do not yet persist org_id. Returning a global
    # queue would cross organisation boundaries, so this route is deliberately
    # disabled until the organisation-key migration is completed.
    raise HTTPException(
        status_code=409,
        detail="Очередь диагностик временно недоступна до миграции tenant-изоляции",
    )

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
async def org_stats(
    db: Session = Depends(get_db),
    actor: DiagnosticActor = Depends(require_diagnostic_staff),
):
    """Общая статистика: всего сессий, завершённых, средний theta."""
    raise HTTPException(
        status_code=409,
        detail="Статистика организации временно недоступна до миграции tenant-изоляции",
    )
