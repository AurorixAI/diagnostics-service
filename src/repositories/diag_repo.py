"""
Diagnostic Service — Repositories for owned tables:
  DiagSessionRepository
  DiagAnswerRepository
  DiagReportRepository
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.diag_models import DiagAnswer, DiagReport, DiagSession
from src.repositories.base import BaseRepository


class DiagSessionRepository(BaseRepository[DiagSession]):
    model = DiagSession

    def get_fresh(self, session_id: uuid.UUID, *, for_update: bool = False) -> Optional[DiagSession]:
        # The router may have loaded this row before another request completed.
        statement = select(DiagSession).where(DiagSession.id == session_id).execution_options(populate_existing=True)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def get_active(self, session_id: uuid.UUID) -> Optional[DiagSession]:
        return self.session.scalar(
            select(DiagSession).where(
                DiagSession.id == session_id,
                DiagSession.phase != "completed",
            )
        )

    def get_by_invite_code(
        self,
        code: str,
        *,
        unfinished_only: bool = False,
    ) -> Optional[DiagSession]:
        statement = select(DiagSession).where(DiagSession.invite_code == code)
        if unfinished_only:
            statement = statement.where(DiagSession.phase != "completed")
        return self.session.scalar(statement.order_by(DiagSession.created_at.desc()))

    def get_student_history(
        self, student_id: uuid.UUID, limit: int = 10
    ) -> List[DiagSession]:
        from sqlalchemy import desc

        return list(
            self.session.scalars(
                select(DiagSession)
                .where(DiagSession.student_id == student_id)
                .order_by(desc(DiagSession.created_at))
                .limit(limit)
            )
        )

    def mark_completed(
        self,
        session: DiagSession,
        *,
        theta: float,
        theta_se: float,
        level: str,
        weak_skills: list,
        topic_breakdown: dict,
        state_snapshot: dict,
        items_answered: int = 0,
        stop_reason: Optional[str] = None,
    ) -> DiagSession:
        session.phase = "completed"
        session.theta = theta
        session.theta_se = theta_se
        session.overall_level = level
        session.weak_skills = weak_skills
        session.topic_breakdown = topic_breakdown
        session.state_snapshot = state_snapshot
        session.items_answered = items_answered          # ← was missing, always 0
        session.stop_reason = stop_reason
        session.completed_at = datetime.utcnow()
        self.session.flush()
        return session


class DiagAnswerRepository(BaseRepository[DiagAnswer]):
    model = DiagAnswer

    def get_last_answer(self, session_id: uuid.UUID) -> Optional[DiagAnswer]:
        return self.session.scalar(
            select(DiagAnswer)
            .where(DiagAnswer.session_id == session_id)
            .order_by(DiagAnswer.answered_at.desc(), DiagAnswer.id.desc())
            .limit(1)
        )

    def get_session_answers(self, session_id: uuid.UUID) -> List[DiagAnswer]:
        return list(
            self.session.scalars(
                select(DiagAnswer)
                .where(DiagAnswer.session_id == session_id)
                .order_by(DiagAnswer.answered_at)
            )
        )

    def count_session_answers(self, session_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                select(func.count(DiagAnswer.id)).where(
                    DiagAnswer.session_id == session_id
                )
            )
            or 0
        )

    def get_total_time_ms(self, session_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                select(func.coalesce(func.sum(DiagAnswer.time_ms), 0)).where(
                    DiagAnswer.session_id == session_id
                )
            )
            or 0
        )

    def log_answer(
        self,
        *,
        session_id: uuid.UUID,
        task_id: str,
        skill_id: str,
        topic_id: str,
        subtopic_id: Optional[str],
        student_answer: str,
        time_ms: Optional[int],
        outcome: float,
        eval_category: str,
        ai_evaluated: bool,
        theta_before: float,
        theta_after: float,
        se_after: float,
        phase: str,
        is_deep_scan: bool,
        task_snapshot: Optional[dict] = None,
        deep_scan_origin_skill_id: Optional[str] = None,
        deep_scan_step: Optional[int] = None,
    ) -> DiagAnswer:
        answer = DiagAnswer(
            session_id=session_id,
            task_id=task_id,
            skill_id=skill_id,
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            student_answer=student_answer,
            time_ms=time_ms,
            outcome=outcome,
            eval_category=eval_category,
            ai_evaluated=ai_evaluated,
            theta_before=theta_before,
            theta_after=theta_after,
            se_after=se_after,
            phase=phase,
            is_deep_scan=is_deep_scan,
            task_snapshot=task_snapshot,
            deep_scan_origin_skill_id=deep_scan_origin_skill_id,
            deep_scan_step=deep_scan_step,
        )
        return self.add(answer)


class DiagReportRepository(BaseRepository[DiagReport]):
    model = DiagReport

    def get_by_session(self, session_id: uuid.UUID) -> Optional[DiagReport]:
        return self.session.scalar(
            select(DiagReport).where(DiagReport.session_id == session_id)
        )

    def get_student_reports(
        self, student_id: uuid.UUID, limit: int = 5
    ) -> List[DiagReport]:
        from sqlalchemy import desc

        return list(
            self.session.scalars(
                select(DiagReport)
                .where(DiagReport.student_id == student_id)
                .order_by(desc(DiagReport.generated_at))
                .limit(limit)
            )
        )
