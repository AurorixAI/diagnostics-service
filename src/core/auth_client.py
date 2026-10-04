"""
Auth Service client — notifies algo-auth of diagnostic invite state changes.
Fire-and-forget: errors are logged but never raised (don't break the CAT flow).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from src.core.config import get_settings

log = logging.getLogger(__name__)


def _base_url() -> str:
    return get_settings().auth_service_url.rstrip("/")


def _internal_headers() -> dict[str, str]:
    token = get_settings().internal_service_token
    if not token:
        raise RuntimeError("INTERNAL_SERVICE_TOKEN is not configured")
    return {"X-Internal-Service-Token": token}


def notify_start(invite_code: str, session_id: str) -> bool:
    """
    Mark diagnostic invite as in_progress and link cat_session_id.
    Calls POST /api/v1/internal/diagnostic/{code}/start
    """
    if not invite_code:
        return True
    url = f"{_base_url()}/api/v1/internal/diagnostic/{invite_code}/start"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                url,
                json={"session_id": session_id},
                headers=_internal_headers(),
            )
            if resp.status_code not in (200, 204):
                log.warning(
                    "diagnostic_auth_start_failed session_id=%s status=%s",
                    session_id,
                    resp.status_code,
                )
                return False
            return True
    except Exception as exc:
        log.warning("diagnostic_auth_start_failed session_id=%s error_type=%s", session_id, type(exc).__name__)
        return False


def notify_complete(
    invite_code: str,
    session_id: str,
    result_data: Dict[str, Any],
) -> bool:
    """
    Mark diagnostic invite as completed and save result to StudentDiagnosticResult.
    Calls POST /api/v1/internal/diagnostic/{code}/complete
    """
    if not invite_code:
        return True
    # Repair a transient start-callback failure before completing the exact
    # same session.  start is idempotent only for this session_id.
    notify_start(invite_code, session_id)
    url = f"{_base_url()}/api/v1/internal/diagnostic/{invite_code}/complete"
    payload = {"session_id": session_id, **result_data}
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload, headers=_internal_headers())
            if resp.status_code not in (200, 204):
                log.warning(
                    "diagnostic_auth_completion_failed session_id=%s status=%s",
                    session_id,
                    resp.status_code,
                )
                return False
            return True
    except Exception as exc:
        log.warning("diagnostic_auth_completion_failed session_id=%s error_type=%s", session_id, type(exc).__name__)
        return False
