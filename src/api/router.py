"""
Diagnostic Service — HTTP Router (thin layer, no business logic)

Endpoints:
  POST  /api/v1/diagnostic/sessions              - Create session
  POST  /api/v1/diagnostic/sessions/{id}/answer  - Submit answer
  GET   /api/v1/diagnostic/sessions/{id}/report  - Get final report
  GET   /api/v1/diagnostic/sessions/active        - Check active session by invite_code
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.access import invite_error, validate_invite_capability, validate_invite_state
from src.models.diag_models import DiagSession
from src.core.exceptions import (
    DiagnosticError,
    GradeNotConfiguredError,
    SessionAlreadyStartedError,
)
from src.domain.session_service import SessionService
from src.schemas.diag_schemas import (
    ActiveSessionResponse,
    AnswerResult,
    CreateSessionRequest,
    CreateSessionResponse,
    ResolvedSessionResponse,
    SubmitAnswerRequest,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostic", tags=["Diagnostic"])



def _service(db: Session = Depends(get_db)) -> SessionService:
    return SessionService(db)


def _answer_error(exc: DiagnosticError) -> HTTPException:
    messages = {
        "ANSWER_IN_PROGRESS": (409, "Ответ ещё обрабатывается. Проверяем состояние попытки.", "check_session"),
        "TASK_OUT_OF_SEQUENCE": (409, "Состояние попытки изменилось. Восстановите текущий вопрос или результат.", "check_session"),
        "SESSION_EXPIRED": (410, "Состояние диагностики больше недоступно. Обратитесь к учебному центру.", "contact_center"),
        "SESSION_NOT_FOUND": (404, "Сессия диагностики не найдена.", "contact_center"),
        "SESSION_ALREADY_STARTED": (409, "Попытка по этому приглашению уже начата. Восстановите её состояние.", "check_session"),
        "GRADE_NOT_CONFIGURED": (422, "Для этого класса пока не настроена диагностика. Обратитесь к учебному центру.", "contact_center"),
        "NO_TASKS": (503, "Не удалось получить задание. Проверьте состояние попытки.", "check_session"),
    }
    http_status, message, action = messages.get(exc.code, (400, exc.message, "retry"))
    return invite_error(http_status, exc.code, message, action)


@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    service: SessionService = Depends(_service),
):
    """Initialize a session only for the student bound to the invite code."""
    try:
        # The public code is a capability, not merely presentation metadata.
        # A direct API caller cannot substitute another student UUID or grade.
        await validate_invite_capability(
            body.invite_code,
            student_id=str(body.student_id),
            grade_level=body.grade_level,
            allowed_statuses={"confirmed"},
        )
        session_id, first_task = service.create_session(
            student_id=body.student_id,
            grade_level=body.grade_level,
            invite_code=body.invite_code,
            prior_theta=body.prior_theta,
        )
        return CreateSessionResponse(session_id=session_id, first_task=first_task)
    except GradeNotConfiguredError as exc:
        raise _answer_error(exc)
    except SessionAlreadyStartedError as exc:
        raise _answer_error(exc)
    except DiagnosticError as exc:
        raise _answer_error(exc)
    except HTTPException:
        # A deliberate 4xx (missing invite capability, wrong student, a
        # session already started) must reach the client as itself. The
        # generic handler below would relabel it 500, and the UI would
        # report a server failure instead of what the user has to do.
        raise
    except Exception as exc:
        log.error("diagnostic_start_failed error_type=%s", type(exc).__name__)
        raise invite_error(500, "SESSION_START_FAILED", "Не удалось начать диагностику. Повторите проверку состояния.", "check_session")


@router.get("/sessions/active", response_model=ActiveSessionResponse)
async def get_active_session(
    invite_code: str = Query(..., description="Diagnostic invite code"),
    service: SessionService = Depends(_service),
):
    """Check if an active (unfinished) session exists for the given invite_code.

    Called on page load by the frontend to offer 'Continue where you left off?'
    Returns 404 when no active session exists (new student or session completed/expired).
    """
    try:
        # A callback retry can leave auth-service on ``confirmed`` briefly,
        # while the diagnostic DB already owns the only valid session.  Resume
        # that session; never replace it with a fresh one.
        await validate_invite_capability(
            invite_code,
            allowed_statuses={"confirmed", "in_progress"},
        )
        result = service.get_active_session(invite_code)
        if result is None:
            raise invite_error(404, "SESSION_NOT_FOUND", "Активная попытка не найдена.", "check_session")
        session_id, items_answered, current_task, total_time_ms = result
        return ActiveSessionResponse(
            session_id=session_id,
            items_answered=items_answered,
            current_task=current_task,
            total_time_ms=total_time_ms,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("diagnostic_restore_failed error_type=%s", type(exc).__name__)
        raise invite_error(500, "SESSION_RESTORE_FAILED", "Не удалось проверить состояние попытки.", "retry")


@router.post("/sessions/{session_id}/answer", response_model=AnswerResult)
async def submit_answer(
    session_id: uuid.UUID,
    body: SubmitAnswerRequest,
    service: SessionService = Depends(_service),
    db: Session = Depends(get_db),
    invite_code: Optional[str] = Header(None, alias="X-Diagnostic-Invite-Code"),
):
    """Submit answer to current task. Returns result and next task (if any)."""
    try:
        session = db.query(DiagSession).filter(DiagSession.id == session_id).first()
        if not session or not session.invite_code:
            raise invite_error(404, "SESSION_NOT_FOUND", "Сессия диагностики не найдена.", "contact_center")
        if invite_code != session.invite_code:
            raise invite_error(403, "INVITE_SESSION_MISMATCH", "Нет доступа к этой диагностике.", "contact_center")
        invite = await validate_invite_capability(
            invite_code,
            student_id=str(session.student_id),
            grade_level=session.grade_level,
            # Terminal projections can serve the already committed final
            # answer, but can never admit a new answer or a second attempt.
            allowed_statuses={"confirmed", "in_progress", "completed", "expired"},
            enforce_expiry=False,
        )
        replay = service.get_completed_answer_result(session_id, body.task_id, body.student_answer)
        if replay is not None:
            return replay
        validate_invite_state(invite, allowed_statuses={"confirmed", "in_progress"})
        return service.submit_answer(
            session_id=session_id,
            task_id=body.task_id,
            student_answer=body.student_answer,
            time_ms=body.time_ms,
        )
    except DiagnosticError as exc:
        raise _answer_error(exc)
    except HTTPException:
        # A deliberate 4xx (missing invite capability, wrong student, a
        # session already started) must reach the client as itself. The
        # generic handler below would relabel it 500, and the UI would
        # report a server failure instead of what the user has to do.
        raise
    except Exception as exc:
        log.error("diagnostic_answer_failed session_id=%s error_type=%s", session_id, type(exc).__name__)
        raise invite_error(500, "ANSWER_FAILED", "Не удалось подтвердить отправку ответа. Проверьте состояние попытки.", "check_session")


@router.get("/sessions/by-invite", response_model=ResolvedSessionResponse)
async def resolve_session(
    invite_code: str = Query(..., min_length=1),
    service: SessionService = Depends(_service),
):
    """Restore the exact owned attempt, including a durably completed one."""
    try:
        session = service.session_repo.get_by_invite_code(invite_code)
        invite = await validate_invite_capability(
            invite_code,
            student_id=str(session.student_id) if session else None,
            grade_level=session.grade_level if session else None,
            allowed_statuses={"confirmed", "in_progress", "completed", "expired"},
            enforce_expiry=False,
        )
        if session:
            session = service.session_repo.get_fresh(session.id)
        if session and session.phase == "completed":
            return ResolvedSessionResponse(
                session_id=session.id, status="completed", items_answered=session.items_answered,
                total_time_ms=service.answer_repo.get_total_time_ms(session.id),
            )
        validate_invite_state(invite, allowed_statuses={"confirmed", "in_progress"})
        if session is None:
            raise invite_error(404, "SESSION_NOT_FOUND", "Попытка по этому приглашению ещё не начата.", "start")
        active = service.get_active_session(invite_code)
        if active is None:
            # Completion may commit while the Redis-backed resume check runs.
            session = service.session_repo.get_fresh(session.id)
            if session and session.phase == "completed":
                return ResolvedSessionResponse(
                    session_id=session.id, status="completed", items_answered=session.items_answered,
                    total_time_ms=service.answer_repo.get_total_time_ms(session.id),
                )
            raise invite_error(410, "SESSION_EXPIRED", "Состояние попытки больше недоступно. Обратитесь к учебному центру.", "contact_center")
        session_id, items_answered, current_task, total_time_ms = active
        return ResolvedSessionResponse(
            session_id=session_id, status="active", items_answered=items_answered,
            current_task=current_task, total_time_ms=total_time_ms,
        )
    except DiagnosticError as exc:
        raise _answer_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        log.error("diagnostic_restore_failed error_type=%s", type(exc).__name__)
        raise invite_error(500, "SESSION_RESTORE_FAILED", "Не удалось проверить состояние попытки. Повторите проверку.", "retry")


@router.get("/sessions/{session_id}/report")
async def get_report(
    session_id: uuid.UUID,
    service: SessionService = Depends(_service),
    db: Session = Depends(get_db),
    invite_code: str = Query(..., min_length=1),
):
    """Get diagnostic report for a completed session."""
    try:
        session = db.query(DiagSession).filter(DiagSession.id == session_id).first()
        if not session or session.invite_code != invite_code:
            raise invite_error(404, "REPORT_NOT_FOUND", "Отчёт не найден.", "contact_center")
        await validate_invite_capability(
            invite_code,
            student_id=str(session.student_id),
            grade_level=session.grade_level,
            # Completion is durable in diagnostic-service before the async
            # auth-service projection has necessarily moved the invite from
            # ``confirmed`` to ``in_progress``/``completed``.  The session
            # lookup above already binds this exact code to this exact
            # completed attempt, so allowing that narrow lag cannot expose a
            # different student's report or revive an invite for a new run.
            allowed_statuses={"confirmed", "in_progress", "completed", "expired"},
            enforce_expiry=False,
        )
        if session.phase != "completed":
            raise invite_error(409, "SESSION_NOT_COMPLETED", "Диагностика ещё не завершена.", "check_session")
        return service.get_report_data(session_id)
    except ValueError as exc:
        raise invite_error(404, "REPORT_NOT_FOUND", "Отчёт не найден.", "contact_center")
    except HTTPException:
        # A deliberate 4xx (missing invite capability, wrong student, a
        # session already started) must reach the client as itself. The
        # generic handler below would relabel it 500, and the UI would
        # report a server failure instead of what the user has to do.
        raise
    except Exception as exc:
        log.error("diagnostic_report_failed session_id=%s error_type=%s", session_id, type(exc).__name__)
        raise invite_error(500, "REPORT_FETCH_FAILED", "Ответы сохранены. Не удалось загрузить отчёт.", "retry")
