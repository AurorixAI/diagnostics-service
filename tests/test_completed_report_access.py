"""Regression coverage for report access during auth-service callback lag."""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from src.api import router as diagnostic_router


class _Query:
    def __init__(self, session):
        self._session = session

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._session


class _Db:
    def __init__(self, session):
        self._session = session

    def query(self, *_args, **_kwargs):
        return _Query(self._session)


class _Service:
    def __init__(self, expected_id):
        self.expected_id = expected_id

    def get_report_data(self, session_id):
        assert session_id == self.expected_id
        return {"session_id": str(session_id), "report_generation": {"status": "pending"}}


@pytest.mark.parametrize("invite_status", ["confirmed", "in_progress", "completed", "expired"])
def test_completed_session_report_is_available_during_auth_projection_lag(monkeypatch, invite_status):
    """A completed local session must not fail while callback status catches up."""
    session_id = uuid.uuid4()
    invite_code = "TEST-CAPABILITY-CODE"
    db_session = SimpleNamespace(
        id=session_id,
        invite_code=invite_code,
        student_id=uuid.uuid4(),
        grade_level=9,
        phase="completed",
    )
    observed: dict[str, object] = {}

    async def _capability(code, **kwargs):
        observed["code"] = code
        observed.update(kwargs)
        return {"status": invite_status}

    monkeypatch.setattr(diagnostic_router, "validate_invite_capability", _capability)

    result = asyncio.run(
        diagnostic_router.get_report(
            request=SimpleNamespace(headers={}, client=SimpleNamespace(host="203.0.113.5")),
            session_id=session_id,
            service=_Service(session_id),
            db=_Db(db_session),
            invite_header=invite_code,
            invite_query=None,
        )
    )

    assert result["session_id"] == str(session_id)
    assert observed["code"] == invite_code
    assert observed["student_id"] == str(db_session.student_id)
    assert observed["grade_level"] == 9
    assert observed["allowed_statuses"] == {"confirmed", "in_progress", "completed", "expired"}
    assert observed["enforce_expiry"] is False
