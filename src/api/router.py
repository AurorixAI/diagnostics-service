"""
Diagnostic Service — HTTP Router (thin layer, no business logic)

Endpoints:
  POST  /api/v1/diagnostic/sessions              - Create session
  POST  /api/v1/diagnostic/sessions/{id}/answer  - Submit answer
  GET   /api/v1/diagnostic/sessions/{id}/report  - Get final report
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.exceptions import DiagnosticError, SessionExpiredError, GradeNotConfiguredError
from src.domain.session_service import SessionService
from src.schemas.diag_schemas import (
    AnswerResult,
    CreateSessionRequest,
    CreateSessionResponse,
    SubmitAnswerRequest,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostic", tags=["Diagnostic"])


def _service(db: Session = Depends(get_db)) -> SessionService:
    return SessionService(db)


@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
def create_session(
    body: CreateSessionRequest,
    service: SessionService = Depends(_service),
):
    """Initialize a new diagnostic session. Returns session_id + first task."""
    try:
        session_id, first_task = service.create_session(
            student_id=body.student_id,
            grade_level=body.grade_level,
            invite_code=body.invite_code,
            prior_theta=body.prior_theta,
        )
        return CreateSessionResponse(session_id=session_id, first_task=first_task)
    except GradeNotConfiguredError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message})
    except DiagnosticError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message})
    except Exception as exc:
        log.error("create_session error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error creating session")


@router.post("/sessions/{session_id}/answer", response_model=AnswerResult)
def submit_answer(
    session_id: uuid.UUID,
    body: SubmitAnswerRequest,
    service: SessionService = Depends(_service),
):
    """Submit answer to current task. Returns result and next task (if any)."""
    try:
        return service.submit_answer(
            session_id=session_id,
            task_id=body.task_id,
            student_answer=body.student_answer,
            time_ms=body.time_ms,
        )
    except SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail={"code": exc.code, "message": exc.message})
    except DiagnosticError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message})
    except Exception as exc:
        log.error("submit_answer error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error processing answer")


@router.get("/sessions/{session_id}/report")
def get_report(
    session_id: uuid.UUID,
    service: SessionService = Depends(_service),
):
    """Get diagnostic report for a completed session."""
    try:
        return service.get_report_data(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.error("get_report error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error fetching report")
