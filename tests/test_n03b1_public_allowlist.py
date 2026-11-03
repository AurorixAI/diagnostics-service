"""N03b-1 R3: every PUBLIC route (held by an invite code, not by a staff session) answers with an allowlisted set of fields.

The invite code lives on the student's device, so the answer of any public route is readable by the student (DevTools).
The level, theta/se, was-it-right, the category, the stop reason, the answer key must never be among the fields: a new
field in a public response model fails here until a person adds it to the list below on purpose.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from src.api import router as diag_router
from src.core.database import get_db
from src.main import app
from src.schemas.diag_schemas import AnswerResult, TaskOut, public_answer, public_task

# What src/app/d/[code]/page.tsx reads of a task.
TASK = {"task_id", "question_text", "question_latex", "question_image_url", "answer_type", "answer_options",
        "answer_options_latex", "items_answered", "items_max"}
ALLOWED = {
    ("POST", "/api/v1/diagnostic/sessions"): {"session_id", "first_task"} | TASK,
    ("POST", "/api/v1/diagnostic/sessions/{session_id}/answer"): {"next_task", "session_completed", "total_time_ms"} | TASK,
    ("GET", "/api/v1/diagnostic/sessions/by-invite"): {"session_id", "status", "items_answered", "current_task", "total_time_ms"} | TASK,
}
# Not student data: probes and the API documentation.  Staff routes (a session cookie) are checked by their own guards.
SYSTEM = {"/health/live", "/health/ready", "/health", "/version", "/metrics", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
STAFF_PREFIX = "/api/v1/analytics/"
SECRETS = ("theta", "se", "is_correct", "outcome", "eval_category", "stop_reason", "level", "report_json", "correct_answer",
           "skill_id", "topic_id", "phase", "is_deep_scan", "distractor", "weak_skills", "topic_breakdown", "error_patterns")


def _public_routes():
    found = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path in SYSTEM or route.path.startswith(STAFF_PREFIX):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            found[(method, route.path)] = route
    return found


def _field_names(model) -> set[str]:
    schema = model.model_json_schema()
    names: set[str] = set()
    for node in [schema, *schema.get("$defs", {}).values()]:
        names |= set(node.get("properties", {}))
    return names


def test_the_public_routes_are_found_and_each_one_is_on_the_list():
    found = _public_routes()
    assert len(found) > 0, "no public route found: the guard would pass on nothing"
    assert set(found) == set(ALLOWED), f"a public route appeared or went: {sorted(set(found) ^ set(ALLOWED))}"


def test_every_public_response_model_has_exactly_the_allowed_fields():
    checked = 0
    for key, route in _public_routes().items():
        assert route.response_model is not None, f"{key} answers without a response model (nothing cuts its answer)"
        names = _field_names(route.response_model)
        assert names == ALLOWED[key], (key, sorted(names ^ ALLOWED[key]))
        assert not names & set(SECRETS), (key, sorted(names & set(SECRETS)))
        checked += 1
    assert checked == len(ALLOWED) > 0


def _internal_task() -> TaskOut:
    return TaskOut(task_id="T1", skill_id="G8_T1_K1", topic_id="G8_T1", question_text="2+2", answer_type="mc",
                   answer_options=["3", "4"], answer_options_latex=["3", "4"], phase="deep_scan", items_answered=3,
                   items_max=15, is_deep_scan=True)


def test_the_conversion_copies_only_the_allowed_fields():
    task = public_task(_internal_task())
    assert set(task.model_dump()) == TASK
    result = public_answer(AnswerResult(is_correct=False, outcome=0.0, eval_category="distractor", theta=-1.2, se=0.3,
                                        next_task=_internal_task(), session_completed=True, stop_reason="x"), 4000)
    assert set(result.model_dump()) == ALLOWED[("POST", "/api/v1/diagnostic/sessions/{session_id}/answer")] - TASK
    assert set(result.next_task.model_dump()) == TASK


class _Db:
    def query(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return SimpleNamespace(invite_code="CODE0001", student_id="s", grade_level=7)


def _answer_api(monkeypatch, result: AnswerResult, total_ms=4000, replay=None):
    async def invite(*_a, **_k):
        return {"status": "in_progress"}

    class Service:
        answer_repo = SimpleNamespace(get_total_time_ms=lambda _id: total_ms)

        def get_completed_answer_result(self, *_a):
            return replay

        def submit_answer(self, **_k):
            return result

    monkeypatch.setattr(diag_router, "validate_invite_capability", invite)
    test_app = FastAPI()
    test_app.include_router(diag_router.router, prefix="/api/v1")
    test_app.dependency_overrides[get_db] = lambda: _Db()
    test_app.dependency_overrides[diag_router._service] = lambda: Service()
    return TestClient(test_app)


def _post(client):
    return client.post(f"/api/v1/diagnostic/sessions/{uuid.uuid4()}/answer", json={"task_id": "T1", "student_answer": "4", "time_ms": 900},
                       headers={"X-Diagnostic-Invite-Code": "CODE0001"})


def _full(**over):
    base = dict(is_correct=False, outcome=0.0, eval_category="distractor", theta=-1.2, se=0.3, next_task=_internal_task(),
                session_completed=False, stop_reason=None)
    return AnswerResult(**{**base, **over})


def test_the_answer_on_the_wire_has_no_result_and_no_internal_task_fields(monkeypatch):
    body = _post(_answer_api(monkeypatch, _full())).json()
    assert set(body) == {"next_task", "session_completed", "total_time_ms"}
    assert set(body["next_task"]) == TASK
    assert body["total_time_ms"] is None                      # the time is for the final answer only
    text = str(body)
    for word in ("theta", "is_correct", "eval_category", "distractor", "G8_T1", "deep_scan", "stop_reason"):
        assert word not in text, word


@pytest.mark.parametrize("via_replay", [False, True])
def test_the_final_answer_carries_the_server_total_time(monkeypatch, via_replay):
    final = _full(next_task=None, session_completed=True, stop_reason="classification_confident")
    client = _answer_api(monkeypatch, final, total_ms=757_000, replay=final if via_replay else None)
    body = _post(client).json()
    assert body == {"next_task": None, "session_completed": True, "total_time_ms": 757_000}
