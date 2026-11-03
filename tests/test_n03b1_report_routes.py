"""N03b-1 (1, 5): the report is read by staff only; the schema version comes with the staff answer.

The report holds the level, the plan and the answer keys (``correct_answer`` of every wrong answer): the invite code of a
completed attempt must not read them (a recheck may issue the same tasks again).  The public route that answered by invite
code was first cut down to a state and then removed (nobody called it): there is no route to read a report by a code.
Staff read the report through the analytics router, with a session cookie.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace as NS

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import analytics_router, router as diag_router
from src.core.access import require_diagnostic_staff
from src.domain.report_generator import REPORT_SCHEMA_VERSION

SESSION_ID = uuid.uuid4()
CODE = "N03B1CODE01"


# ── no route reads a report by an invite code ────────────────────────────────────────────────────────

def test_no_diagnostic_route_serves_a_report():
    paths = {route.path for route in diag_router.router.routes}
    assert not [path for path in paths if "report" in path], sorted(paths)
    assert not hasattr(diag_router, "get_report")


@pytest.mark.parametrize("method", ["get", "post", "put", "delete"])
def test_the_old_report_address_is_gone_with_the_header_and_with_the_query(method):
    app = FastAPI()
    app.include_router(diag_router.router, prefix="/api/v1")
    client = TestClient(app)
    url = f"/api/v1/diagnostic/sessions/{SESSION_ID}/report"
    for kwargs in ({"headers": {"X-Diagnostic-Invite-Code": CODE}}, {"params": {"invite_code": CODE}}):
        response = getattr(client, method)(url, **kwargs)
        assert response.status_code in (404, 405), (method, kwargs, response.status_code)
        assert "report_json" not in response.text


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
