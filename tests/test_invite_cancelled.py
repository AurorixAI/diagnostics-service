"""ROADMAP #89: an invite that the centre CANCELLED (the student was archived) is unusable on every public path.

auth-service owns the public invite and answers its projection with status ``cancelled``.  diagnostic-service
must answer like it does for an expired code - the same HTTP class (410) - with the text «Приглашение отменено»
and its own machine code, whichever statuses the endpoint accepts.  It is a state a legitimate student can meet,
not a guess: it must not eat the brute-force budget of the address.
"""
from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import access  # noqa: E402
from src.core.abuse_limit import FAILS_PER_MINUTE, GUESS_CODES  # noqa: E402

from tests.test_invite_rate_limit import (  # noqa: E402,F401  (fixtures and helpers)
    GRADE, _invite, active, api, code_of, create, resolve, student_of,
)

MESSAGE = "Приглашение отменено"

# Every set of statuses a router endpoint passes to the check (src/api/router.py), plus «no restriction».
ALLOWED_SETS = [
    {"confirmed"},
    {"confirmed", "in_progress"},
    {"confirmed", "in_progress", "completed", "expired"},
    None,
]


def _detail(exc: HTTPException) -> dict:
    return exc.detail


@pytest.mark.parametrize("allowed", ALLOWED_SETS)
def test_validate_invite_state_refuses_a_cancelled_invite_like_an_expired_one(allowed):
    cancelled = {"status": "cancelled", "expires_at": None}
    with pytest.raises(HTTPException) as cancelled_exc:
        access.validate_invite_state(cancelled, allowed_statuses=allowed)
    assert cancelled_exc.value.status_code == 410
    assert _detail(cancelled_exc.value) == {
        "code": "INVITE_CANCELLED", "message": MESSAGE, "action": "contact_center",
    }
    # the expired one is the same HTTP class
    if allowed is not None:
        with pytest.raises(HTTPException) as expired_exc:
            access.validate_invite_state({"status": "expired", "expires_at": None}, allowed_statuses={"confirmed"})
        assert expired_exc.value.status_code == cancelled_exc.value.status_code == 410


def test_cancelled_is_not_a_guess_and_other_statuses_keep_their_answers():
    assert "INVITE_CANCELLED" not in GUESS_CODES
    with pytest.raises(HTTPException) as exc:
        access.validate_invite_state({"status": "pending"}, allowed_statuses={"confirmed"})
    assert exc.value.status_code == 409 and _detail(exc.value)["code"] == "INVITE_NOT_AVAILABLE"
    access.validate_invite_state({"status": "confirmed", "expires_at": None}, allowed_statuses={"confirmed"})


def test_capability_check_refuses_a_cancelled_projection_for_every_allowed_set(api):
    code = code_of(1)
    api.invites[code]["status"] = "cancelled"
    for allowed in ALLOWED_SETS:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(access.validate_invite_capability(code, allowed_statuses=allowed))
        assert exc.value.status_code == 410 and _detail(exc.value)["code"] == "INVITE_CANCELLED"


def test_every_public_entry_answers_410_for_a_cancelled_code(api):
    code, student = code_of(2), student_of(2)
    api.invites[code]["status"] = "cancelled"
    for response in (create(api, code, student), active(api, code), resolve(api, code)):
        assert response.status_code == 410, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "INVITE_CANCELLED" and detail["message"] == MESSAGE
        assert detail["action"] == "contact_center"


def test_cancelled_codes_do_not_eat_the_guess_budget_of_the_address(api):
    # More lookups of DIFFERENT cancelled codes than the failed-lookup budget of one address (each code once, so
    # the per-code volume cap stays out of the picture).
    for i in range(FAILS_PER_MINUTE.count + 5):
        code = f"CNC{i:05d}"
        api.invites[code] = _invite(100 + i, "cancelled")
        assert resolve(api, code).status_code == 410
    # a student behind the same address still gets in with a valid code
    assert create(api, code_of(4), student_of(4)).status_code == 201


# ── «начатую диагностику дать закончить»: a session that started BEFORE the cancellation ─────────────────────────

CANCEL_AT = "2026-10-17T10:00:00"
CANCELLED_BY_ARCHIVE = {"status": "cancelled", "cancel_reason": "student_archived", "cancelled_at": CANCEL_AT, "expires_at": None}


@pytest.mark.parametrize("started, expected", [
    ("2026-10-17T09:59:59", True),                       # before: finishes
    ("2026-10-17T10:00:00", False),                      # at the very moment: no
    ("2026-10-17T10:00:01", False),                      # after: no
    (None, False),                                       # no session at all
    ("not a date", False),
])
def test_only_a_session_that_started_before_the_cancellation_counts(started, expected):
    assert access.session_predates_cancellation(CANCELLED_BY_ARCHIVE, started) is expected
    assert access.session_predates_cancellation(CANCELLED_BY_ARCHIVE, lambda: started) is expected   # looked up lazily


def test_the_reason_and_the_date_must_both_be_there():
    started = "2026-10-17T09:00:00"
    assert access.session_predates_cancellation({**CANCELLED_BY_ARCHIVE, "cancel_reason": "x"}, started) is False
    assert access.session_predates_cancellation({**CANCELLED_BY_ARCHIVE, "cancelled_at": None}, started) is False
    assert access.session_predates_cancellation({**CANCELLED_BY_ARCHIVE, "status": "confirmed"}, started) is False


@pytest.mark.parametrize("allowed", [{"confirmed", "in_progress"}, {"confirmed", "in_progress", "completed", "expired"}])
def test_a_running_session_of_a_cancelled_invite_passes_where_in_progress_does(allowed):
    from datetime import datetime
    access.validate_invite_state(CANCELLED_BY_ARCHIVE, allowed_statuses=allowed, session_started_at=datetime(2026, 10, 17, 9, 0))
    with pytest.raises(HTTPException) as exc:                      # but not where only a NEW attempt is welcome
        access.validate_invite_state(CANCELLED_BY_ARCHIVE, allowed_statuses={"confirmed"}, session_started_at="2026-10-17T09:00:00")
    assert exc.value.status_code == 409 and _detail(exc.value)["code"] == "INVITE_NOT_AVAILABLE"
    with pytest.raises(HTTPException) as exc:
        access.validate_invite_state(CANCELLED_BY_ARCHIVE, allowed_statuses=allowed, session_started_at="2026-10-17T10:00:00")
    assert exc.value.status_code == 410 and _detail(exc.value)["code"] == "INVITE_CANCELLED"


def test_the_capability_check_returns_the_projection_of_a_running_session_as_in_progress(api):
    code = code_of(5)
    api.invites[code].update(CANCELLED_BY_ARCHIVE, expires_at=api.invites[code]["expires_at"])
    admitted = asyncio.run(access.validate_invite_capability(
        code, allowed_statuses={"confirmed", "in_progress"}, session_started_at="2026-10-17T09:00:00"))
    assert admitted["status"] == "in_progress"
    # the caller's own second check (as the answer endpoint does) agrees with it
    access.validate_invite_state(admitted, allowed_statuses={"confirmed", "in_progress"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(access.validate_invite_capability(code, allowed_statuses={"confirmed", "in_progress"}))
    assert exc.value.status_code == 410


def test_the_active_session_endpoint_resumes_a_session_that_predates_the_cancellation(api):
    from datetime import datetime
    code = code_of(6)
    api.invites[code].update(CANCELLED_BY_ARCHIVE, expires_at=api.invites[code]["expires_at"])

    class Service:
        def __init__(self, started):
            self.session_repo = SimpleNamespace(
                get_by_invite_code=lambda c: SimpleNamespace(created_at=started) if started else None)

        def get_active_session(self, c):
            return None                                           # (404 below = it got past the invite check)

    from src.api import router as diag_router
    for started, status_code in ((datetime(2026, 10, 17, 9, 0), 404), (datetime(2026, 10, 17, 11, 0), 410), (None, 410)):
        api.app.dependency_overrides[diag_router._service] = lambda s=started: Service(s)
        response = active(api, code)
        assert response.status_code == status_code, (started, response.text)
        if status_code == 410:
            assert response.json()["detail"]["code"] == "INVITE_CANCELLED"


def test_the_start_callback_carries_the_moment_the_session_started(monkeypatch):
    from src.core import auth_client

    sent = []

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def post(self, url, json=None, headers=None):
            sent.append((url.rsplit("/", 1)[1], json))
            return httpx.Response(200)

    monkeypatch.setattr(auth_client.httpx, "Client", Client)
    monkeypatch.setattr(auth_client, "_internal_headers", lambda: {"X-Internal-Service-Token": "t"})
    assert auth_client.notify_start("CODE", "S1", "2026-10-17T09:00:00") is True
    assert auth_client.notify_start("CODE", "S1") is True
    assert auth_client.notify_complete("CODE", "S1", {"session_started_at": "2026-10-17T09:00:00", "final_theta": 0.1}) is True
    assert sent[0] == ("start", {"session_id": "S1", "session_started_at": "2026-10-17T09:00:00"})
    assert sent[1] == ("start", {"session_id": "S1"})                      # an older caller: the body is unchanged
    assert sent[2] == ("start", {"session_id": "S1", "session_started_at": "2026-10-17T09:00:00"})   # the repair start of a completion
    assert sent[3][0] == "complete" and sent[3][1]["session_started_at"] == "2026-10-17T09:00:00"
