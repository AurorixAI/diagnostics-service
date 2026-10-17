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
