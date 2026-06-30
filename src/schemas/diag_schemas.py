"""Diagnostic Service — Pydantic v2 request/response schemas"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Requests ──────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    student_id: uuid.UUID
    grade_level: int = Field(..., ge=5, le=11)
    invite_code: Optional[str] = None
    prior_theta: float = Field(default=0.0, ge=-4.0, le=4.0)


class SubmitAnswerRequest(BaseModel):
    task_id: str
    student_answer: str
    time_ms: Optional[int] = Field(default=None, ge=0)


# ── Task presentation ─────────────────────────────────────────────────────

class TaskOut(BaseModel):
    task_id: str
    skill_id: str
    topic_id: str
    question_text: str
    question_latex: Optional[str] = None
    answer_type: str
    answer_options: Optional[List[Any]] = None
    answer_options_latex: Optional[List[str]] = None
    # Navigation context (used by frontend progress bar)
    phase: str
    items_answered: int
    items_max: int
    is_deep_scan: bool = False


class AnswerResult(BaseModel):
    is_correct: bool
    outcome: float          # 0.0 | 0.5 | 1.0
    eval_category: str      # correct | distractor | wrong | idk
    theta: float
    se: float
    next_task: Optional[TaskOut] = None
    session_completed: bool = False


# ── Session ───────────────────────────────────────────────────────────────

class CreateSessionResponse(BaseModel):
    session_id: uuid.UUID
    first_task: TaskOut


# ── Report ────────────────────────────────────────────────────────────────

class TopicBreakdownItem(BaseModel):
    topic_id: str
    alpha: float
    level: str      # below_grade | at_grade | above_grade


class DiagnosticReportOut(BaseModel):
    session_id: uuid.UUID
    student_id: uuid.UUID
    grade_level: int
    overall_theta: float
    overall_level: str
    confidence_interval: List[float]    # [lo, hi]
    topic_breakdown: Dict[str, Any]
    weak_skills: List[str]
    recommended_start: Optional[str]
    items_total: int


# ── Health ────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: str
