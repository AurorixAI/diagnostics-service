"""N03b-1 (1, 5): the public report route (by invite code) tells only the state of the attempt; staff get the schema version.

The report holds the level, the plan and the answer keys (``correct_answer`` of every wrong answer): the invite code of a
completed attempt must not read them (a recheck may issue the same tasks again).  Staff read the report through the
analytics router, with a session cookie.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace as NS

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import analytics_router, router as diag_router
from src.core.access import require_diagnostic_staff
from src.core.database import get_db
from src.domain.report_generator import REPORT_SCHEMA_VERSION
from src.domain.session_service import SessionService

CODE = "N03B1CODE01"
SESSION_ID = uuid.uuid4()
URL = f"/api/v1/diagnostic/sessions/{SESSION_ID}/report"
ALLOWED = {"phase", "report_generation", "total_time_ms"}
FORBIDDEN = ("report_json", "level", "error_patterns", "correct_answer", "distractor", "weak_skills", "topic_breakdown",
             "overall_theta", "recommended_start", "action_plan", "student_id", "grade_level", "stop_reason")

SECRET_REPORT = {
    "level": {"status": "below", "theta": -0.4},
    "error_patterns": [{"task_id": "T1", "correct_answer": "KEY-42", "correct_answer_latex": "KEY-42",
                        "eval_category": "distractor", "distractor_explanation": "EXPLAINED"}],
    "action_plan": [{"skill_id": "G8_T1_K1"}],
}


def _service(*, report, answers=(1500, 2500), phase="completed"):
    service = object.__new__(SessionService)
    session = NS(id=SESSION_ID, student_id=uuid.uuid4(), phase=phase, grade_level=9, theta=-0.4, theta_se=0.3,
                 overall_level="below_grade", topic_breakdown={"G8_T1": {}}, weak_skills=["G8_T1_K1"], stop_reason="x")
    service.session_repo = NS(get_by_id=lambda _id: session)
    service.answer_repo = NS(get_total_time_ms=lambda _id: sum(answers),
                             get_session_answers=lambda _id: [NS(time_ms=t) for t in answers])
    service.report_repo = NS(get_by_session=lambda _id: report)
    return service


def _assert_public_shape(body):
    assert set(body) == ALLOWED, sorted(body)
    assert set(body["report_generation"]) == {"status"}
    text = json.dumps(body)
    for word in FORBIDDEN + ("KEY-42", "EXPLAINED"):
        assert word not in text, word


# ── the service: what is computed ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["ready", "generating", "failed", "pending"])
def test_the_service_answer_has_the_three_fields_and_none_of_the_report(status):
    report = NS(generation_status=status, report_json=SECRET_REPORT, report_schema_version=REPORT_SCHEMA_VERSION)
    body = _service(report=report).get_report_status(SESSION_ID)
    _assert_public_shape(body)
    assert body == {"phase": "completed", "report_generation": {"status": status}, "total_time_ms": 4000}


def test_without_a_report_row_the_status_is_pending():
    assert _service(report=None).get_report_status(SESSION_ID)["report_generation"] == {"status": "pending"}


def test_an_unfinished_attempt_has_no_status():
    with pytest.raises(ValueError):
        _service(report=None, phase="active").get_report_status(SESSION_ID)


# ── the route: what goes over the wire, even if the service returned too much ───────────────────────

class _Query:
    def __init__(self, session):
        self._session = session

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._session


class _Db:
    def __init__(self, session):
        self._session = session

    def query(self, *_a, **_k):
        return _Query(self._session)


@pytest.fixture
def api(monkeypatch):
    session = NS(id=SESSION_ID, invite_code=CODE, student_id=uuid.uuid4(), grade_level=9, phase="completed", created_at=None)
    seen = []

    async def capability(code, **kwargs):
        seen.append(code)
        return {"status": "completed"}

    class Bloated:
        """The shape the route returned before N03b-1: whatever the service adds, the response model cuts it."""

        def get_report_status(self, session_id):
            return {"phase": "completed", "report_generation": {"status": "ready", "stage": "ready", "attempts": 1,
                                                                  "is_current_schema": True},
                    "total_time_ms": 4000, "report_json": SECRET_REPORT, "level": SECRET_REPORT["level"],
                    "error_patterns": SECRET_REPORT["error_patterns"], "student_id": "S", "grade_level": 9}

    monkeypatch.setattr(diag_router, "validate_invite_capability", capability)
    app = FastAPI()
    app.include_router(diag_router.router, prefix="/api/v1")
    app.dependency_overrides[diag_router._service] = lambda: Bloated()
    app.dependency_overrides[get_db] = lambda: _Db(session)
    client = TestClient(app)
    client.seen = seen
    return client


def test_the_public_route_answers_with_the_three_fields_only(api):
    r = api.get(URL, headers={"X-Real-IP": "203.0.113.7", "X-Diagnostic-Invite-Code": CODE})
    assert r.status_code == 200
    _assert_public_shape(r.json())
    assert r.json() == {"phase": "completed", "report_generation": {"status": "ready"}, "total_time_ms": 4000}


def test_a_code_in_the_query_is_rejected(api):
    r = api.get(URL, params={"invite_code": CODE}, headers={"X-Real-IP": "203.0.113.7"})
    assert r.status_code == 404
    assert "report_json" not in r.text and api.seen == []


# ── staff: the page compares the report with the version the backend builds now ─────────────────────

def _staff_report(monkeypatch, *, version, status="ready"):
    session = NS(id=SESSION_ID, student_id=uuid.uuid4(), phase="completed", grade_level=9, theta=0.2, theta_se=0.3,
                 overall_level="at_grade", topic_breakdown={}, weak_skills=[], items_answered=0)
    report = NS(session_id=SESSION_ID, student_id=session.student_id, report_json={"report_meta": {"report_schema_version": version}},
                report_schema_version=version, generation_status=status, generation_stage="ready", generation_attempts=1,
                grade_level=9, overall_level="at_grade", weak_skills=[], narrative_ru=None, generated_at=None)

    class Db:
        def __init__(self):
            self._model = None

        def query(self, model):
            self._model = model
            return self

        def filter(self, *_a, **_k):
            return self

        order_by = limit = options = filter

        def first(self):
            return {"DiagSession": session, "DiagReport": report}.get(self._model.__name__)

        def all(self):
            return []

    monkeypatch.setattr(analytics_router, "await_on_loop", lambda *a, **k: None)
    monkeypatch.setattr(analytics_router, "_build_hierarchical_tree", lambda *a, **k: [])
    monkeypatch.setattr(analytics_router, "_build_diagnostic_trajectory", lambda *a, **k: [])
    return analytics_router.student_report(
        student_id=str(session.student_id), session_id=None, db=Db(), actor=NS(user_id="U", org_id="O", role="teacher"), _slot=None,
    )


@pytest.mark.parametrize("stored,current", [(REPORT_SCHEMA_VERSION - 1, False), (REPORT_SCHEMA_VERSION, True)])
def test_the_staff_answer_carries_the_current_schema_version(monkeypatch, stored, current):
    generation = _staff_report(monkeypatch, version=stored)["report_generation"]
    assert generation["current_schema_version"] == REPORT_SCHEMA_VERSION      # the one number the page compares with
    assert generation["is_current_schema"] is current


def test_the_full_report_stays_behind_the_staff_check():
    assert require_diagnostic_staff in {d.call for r in analytics_router.router.routes if r.name == "student_report"
                                        for d in r.dependant.dependencies}
