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


def notify_start(invite_code: str, session_id: str) -> None:
    """
    Mark diagnostic invite as in_progress and link cat_session_id.
    Calls POST /api/v1/internal/diagnostic/{code}/start
    """
    if not invite_code:
        return
    url = f"{_base_url()}/api/v1/internal/diagnostic/{invite_code}/start"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json={"session_id": session_id})
            if resp.status_code not in (200, 204):
                log.warning(
                    "notify_start: auth-service returned %s for code=%s",
                    resp.status_code,
                    invite_code,
                )
    except Exception as exc:
        log.warning("notify_start failed (fire-and-forget): %s", exc)


def notify_complete(
    invite_code: str,
    session_id: str,
    result_data: Dict[str, Any],
) -> None:
    """
    Mark diagnostic invite as completed and save result to StudentDiagnosticResult.
    Calls POST /api/v1/internal/diagnostic/{code}/complete
    """
    if not invite_code:
        return
    url = f"{_base_url()}/api/v1/internal/diagnostic/{invite_code}/complete"
    payload = {"session_id": session_id, **result_data}
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code not in (200, 204):
                log.warning(
                    "notify_complete: auth-service returned %s for code=%s",
                    resp.status_code,
                    invite_code,
                )
    except Exception as exc:
        log.warning("notify_complete failed (fire-and-forget): %s", exc)
