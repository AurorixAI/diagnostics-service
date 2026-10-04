"""Access controls for diagnostic reports and public invite capabilities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AbstractSet, Mapping, Optional

import httpx
from fastapi import HTTPException, Request, status

from src.core.config import get_settings


_STAFF_ROLES = {"owner", "admin", "teacher"}


def invite_error(http_status: int, code: str, message: str, action: str) -> HTTPException:
    return HTTPException(http_status, {"code": code, "message": message, "action": action})


def validate_invite_state(
    invite: dict,
    *,
    allowed_statuses: Optional[AbstractSet[str]] = None,
    enforce_expiry: bool = True,
) -> None:
    """Check a fetched projection without making a second auth-service request."""
    invite_status = str(invite.get("status") or "")
    if allowed_statuses is not None and invite_status not in allowed_statuses:
        if invite_status == "expired":
            raise invite_error(410, "INVITE_EXPIRED", "Срок действия приглашения истёк.", "contact_center")
        raise invite_error(409, "INVITE_NOT_AVAILABLE", "Приглашение не принимает новые ответы.", "check_session")
    expires_raw = invite.get("expires_at")
    if enforce_expiry and expires_raw and invite_status != "completed":
        try:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            raise invite_error(503, "INVALID_INVITE_EXPIRY", "Не удалось проверить срок действия приглашения.", "retry")
        if expires_at <= datetime.now(timezone.utc):
            raise invite_error(410, "INVITE_EXPIRED", "Срок действия приглашения истёк.", "contact_center")


@dataclass(frozen=True)
class DiagnosticActor:
    user_id: str
    org_id: str
    role: str
    auth_headers: Mapping[str, str]


def _forward_auth_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    if cookie := request.headers.get("cookie"):
        headers["cookie"] = cookie
    if authorization := request.headers.get("authorization"):
        headers["authorization"] = authorization
    return headers


async def require_diagnostic_staff(request: Request) -> DiagnosticActor:
    """Resolve staff authority at auth-service; never fail open."""
    headers = _forward_auth_headers(request)
    if not headers:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется аутентификация")
    base = get_settings().auth_service_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base}/api/v1/auth/me", headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Сервис авторизации временно недоступен") from exc
    if response.status_code in {401, 403}:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется действующая авторизация")
    if response.status_code != 200:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Не удалось проверить доступ")
    data = response.json()
    role = data.get("org_role") or data.get("role")
    user_id = data.get("id")
    org_id = data.get("default_org_id")
    if not user_id or not org_id or role not in _STAFF_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для просмотра диагностик")
    return DiagnosticActor(str(user_id), str(org_id), str(role), headers)


async def require_student_report_access(actor: DiagnosticActor, student_id: str) -> None:
    """Delegate organisation and teacher-group scoping to auth-service."""
    base = get_settings().auth_service_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{base}/api/v1/auth/org/students/{student_id}/profile",
                headers=dict(actor.auth_headers),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Не удалось проверить доступ к ученику") from exc
    if response.status_code in {401, 403, 404}:
        # Do not reveal whether a student exists outside the actor's scope.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к диагностике этого ученика")
    if response.status_code != 200:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Не удалось проверить доступ к ученику")


async def validate_invite_capability(
    invite_code: Optional[str],
    *,
    student_id: Optional[str] = None,
    grade_level: Optional[int] = None,
    allowed_statuses: Optional[AbstractSet[str]] = None,
    enforce_expiry: bool = True,
) -> dict:
    """Validate a public invite against its complete server-side lifecycle.

    The code is a capability, but it is valid only in the expected lifecycle
    state.  This prevents a completed or expired code from starting a second
    session through a direct API call.
    """
    if not invite_code:
        raise invite_error(403, "INVITE_REQUIRED", "Требуется код приглашения на диагностику.", "contact_center")
    base = get_settings().auth_service_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base}/api/v1/auth/diagnostic/{invite_code}")
    except httpx.HTTPError as exc:
        raise invite_error(503, "INVITE_CHECK_UNAVAILABLE", "Не удалось проверить приглашение.", "retry") from exc
    if response.status_code == 404:
        raise invite_error(403, "INVITE_INVALID", "Недействительное приглашение на диагностику.", "contact_center")
    if response.status_code != 200:
        raise invite_error(503, "INVITE_CHECK_UNAVAILABLE", "Не удалось проверить приглашение.", "retry")
    try:
        invite = response.json()
        if not isinstance(invite, dict):
            raise ValueError("Invalid invite projection")
    except ValueError as exc:
        raise invite_error(503, "INVITE_CHECK_UNAVAILABLE", "Не удалось проверить приглашение.", "retry") from exc
    if student_id and str(invite.get("student_id") or "") != str(student_id):
        raise invite_error(403, "INVITE_STUDENT_MISMATCH", "Нет доступа к этой диагностике.", "contact_center")
    if grade_level is not None and invite.get("class_level") != grade_level:
        raise invite_error(403, "INVITE_GRADE_MISMATCH", "Класс не соответствует приглашению.", "contact_center")
    validate_invite_state(invite, allowed_statuses=allowed_statuses, enforce_expiry=enforce_expiry)
    return invite
