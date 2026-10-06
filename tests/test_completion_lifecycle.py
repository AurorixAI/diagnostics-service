"""A2 HTTP regressions against a disposable PostgreSQL + Redis pair.

Run with A2_TEST_DATABASE_URL pointing at database ``a2_diagnostic``. No
production/student bank is used. Auth projection/content are controlled at
their HTTP/repository boundaries; persistence and locking are real.
"""
from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.router import router
from src.core import access
from src.core.database import get_db
from src.domain import session_service as sessions
from src.domain import auth_sync_jobs as sync_jobs
from src.domain.session_state import SessionState
from src.models.base import Base
from src.models.diag_models import DiagAnswer, DiagReport, DiagSession
from src.models.knowledge import TaskMaster
from src.state.redis_state import RedisStateManager

DB_URL = os.getenv("A2_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="Requires disposable A2 PostgreSQL/Redis")
CODE = "A2TEST0001"
PAYLOAD = {"task_id": "A2_FINAL", "student_answer": "4", "time_ms": 1500}


@pytest.fixture
def scenario(monkeypatch):
    assert DB_URL and DB_URL.endswith("/a2_diagnostic"), "Use only the disposable a2_diagnostic database"
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine, tables=[DiagSession.__table__, DiagAnswer.__table__, DiagReport.__table__])
    factory = sessionmaker(engine)
    with engine.begin() as connection:
        for table in [DiagReport.__table__, DiagAnswer.__table__, DiagSession.__table__]:
            connection.execute(table.delete())
    redis = RedisStateManager()
    redis._redis.flushdb()
    session_id, student_id = uuid.uuid4(), uuid.uuid4()
    invite = {"status": "in_progress", "student_id": str(student_id), "class_level": 9,
              "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    with factory() as db:
        db.add(DiagSession(id=session_id, student_id=student_id, grade_level=9, invite_code=CODE, phase="warmup"))
        db.commit()
    state = SessionState(session_id=str(session_id), student_id=str(student_id), grade_level=9)
    state.current_task_id = PAYLOAD["task_id"]
    state.current_skill_id, state.current_topic_id = "A2_SKILL", "A2_TOPIC"
    redis.save(state)
    task = TaskMaster(id=PAYLOAD["task_id"], skill_id="A2_SKILL", question_text="Synthetic fixture",
                      question_latex="Synthetic fixture", answer_type="numeric", correct_answer="4",
                      irt_discrimination=1.0, irt_difficulty=0.0, irt_guessing=0.0)
    monkeypatch.setattr(sessions.TaskRepository, "get_by_id", lambda *_: task)
    monkeypatch.setattr(sessions.SessionService, "_should_stop", lambda *_, **__: True)
    monkeypatch.setattr(sessions, "process_next_report_job", lambda: False)
    monkeypatch.setattr(sessions, "process_next_auth_completion_sync", lambda: False)

    class AuthProjection:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def get(self, _url): return httpx.Response(200, json=dict(invite))
    monkeypatch.setattr(access.httpx, "AsyncClient", AuthProjection)

    def db_dependency():
        with factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = db_dependency
    client = TestClient(app)
    yield client, session_id, invite, factory, redis
    client.close()
    engine.dispose()


def submit(client, session_id, payload=None, code=CODE):
    return client.post(f"/api/v1/diagnostic/sessions/{session_id}/answer",
                       json=payload or PAYLOAD, headers={"X-Diagnostic-Invite-Code": code})


def assert_single_completion(factory):
    with factory() as db:
        assert db.query(DiagSession).count() == 1
        assert db.query(DiagAnswer).count() == 1
        assert db.query(DiagReport).count() == 1
        session = db.query(DiagSession).one()
        assert session.phase == "completed"
        assert session.items_answered == 1
        assert session.auth_sync_status == "pending"
        assert session.auth_sync_attempts == 0
        assert session.auth_sync_requested_at is not None
        assert db.query(DiagReport).one().generation_attempts == 0


@pytest.mark.parametrize("projection", ["confirmed", "in_progress", "completed", "expired"])
def test_final_answer_replay_and_refresh_survive_callback_lag_and_expiry(scenario, projection, monkeypatch):
    client, session_id, invite, factory, redis = scenario
    first = submit(client, session_id)
    assert first.status_code == 200, first.text
    assert first.json()["session_completed"] is True
    assert redis.load(str(session_id)) is None
    invite["status"] = projection
    invite["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    # Replaying committed results must not require ephemeral Redis or content.
    def no_redis(*_args): raise AssertionError("Completed replay must not touch Redis")
    monkeypatch.setattr(RedisStateManager, "answer_lock", no_redis)
    monkeypatch.setattr(RedisStateManager, "load", no_redis)
    repeat = submit(client, session_id)
    assert repeat.status_code == 200, repeat.text
    assert repeat.json() == first.json()
    lookup = client.get("/api/v1/diagnostic/sessions/by-invite", params={"invite_code": CODE})
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["status"] == "completed"
    assert lookup.json()["session_id"] == str(session_id)
    report = client.get(f"/api/v1/diagnostic/sessions/{session_id}/report", params={"invite_code": CODE})
    assert report.status_code == 200, report.text
    assert report.json()["items_total"] == 1
    assert report.json()["total_time_ms"] == PAYLOAD["time_ms"]
    assert_single_completion(factory)


@pytest.mark.parametrize("changed", [{"task_id": "OTHER"}, {"student_answer": "5"}])
def test_completed_attempt_cannot_change_final_answer(scenario, changed):
    client, session_id, _invite, factory, _redis = scenario
    assert submit(client, session_id).status_code == 200
    replay = submit(client, session_id, {**PAYLOAD, **changed})
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "TASK_OUT_OF_SEQUENCE"
    assert_single_completion(factory)


@pytest.mark.parametrize("projection", ["completed", "expired"])
def test_terminal_invite_never_starts_second_attempt(scenario, projection):
    client, session_id, invite, factory, _redis = scenario
    assert submit(client, session_id).status_code == 200
    invite["status"] = projection
    response = client.post("/api/v1/diagnostic/sessions", json={
        "student_id": invite["student_id"], "grade_level": 9, "invite_code": CODE})
    assert response.status_code in {409, 410}
    assert_single_completion(factory)


def test_expired_active_attempt_rejects_new_answer_without_writes(scenario):
    client, session_id, invite, factory, _redis = scenario
    invite["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    response = submit(client, session_id)
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "INVITE_EXPIRED"
    assert response.json()["detail"]["action"] == "contact_center"
    with factory() as db:
        assert db.query(DiagAnswer).count() == 0
        assert db.query(DiagSession).one().phase == "warmup"


def test_foreign_capability_cannot_submit_or_read_result(scenario):
    client, session_id, _invite, factory, _redis = scenario
    assert submit(client, session_id).status_code == 200
    assert submit(client, session_id, code="FOREIGN").status_code == 403
    assert client.get(f"/api/v1/diagnostic/sessions/{session_id}/report",
                      params={"invite_code": "FOREIGN"}).status_code == 404
    assert_single_completion(factory)


@pytest.mark.parametrize("field,value", [("student_id", str(uuid.uuid4())), ("class_level", 8)])
def test_invite_projection_must_match_owned_student_and_grade(scenario, field, value):
    client, session_id, invite, factory, _redis = scenario
    invite[field] = value
    assert submit(client, session_id).status_code == 403
    assert client.get("/api/v1/diagnostic/sessions/by-invite", params={"invite_code": CODE}).status_code == 403
    with factory() as db:
        assert db.query(DiagAnswer).count() == 0


def test_overlapping_final_requests_create_one_answer_and_one_report(scenario, monkeypatch):
    client, session_id, _invite, factory, _redis = scenario
    original = sessions.AnswerEvaluator.evaluate
    def delayed_evaluate(self, task, answer):
        time.sleep(0.25)
        return original(self, task, answer)
    monkeypatch.setattr(sessions.AnswerEvaluator, "evaluate", delayed_evaluate)
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: submit(client, session_id), range(3)))
    assert any(x.status_code == 200 for x in responses)
    assert all(x.status_code in {200, 409} for x in responses)
    for response in responses:
        if response.status_code == 409:
            assert response.json()["detail"]["code"] == "ANSWER_IN_PROGRESS"
    committed = next(x.json() for x in responses if x.status_code == 200)
    assert submit(client, session_id).json() == committed
    assert_single_completion(factory)


def test_failed_final_persistence_rolls_back_answer_before_retry(scenario, monkeypatch):
    client, session_id, _invite, factory, _redis = scenario
    original = sessions.DiagSessionRepository.mark_completed
    def fail_commit(*_args, **_kwargs): raise RuntimeError("Synthetic failure before final commit")
    monkeypatch.setattr(sessions.DiagSessionRepository, "mark_completed", fail_commit)
    assert submit(client, session_id).status_code == 500
    with factory() as db:
        assert db.query(DiagAnswer).count() == 0
        assert db.query(DiagSession).one().phase == "warmup"
    monkeypatch.setattr(sessions.DiagSessionRepository, "mark_completed", original)
    assert submit(client, session_id).status_code == 200
    assert_single_completion(factory)


@pytest.mark.parametrize("job", ["enqueue_report_generation", "enqueue_auth_completion_sync"])
def test_final_answer_snapshot_and_jobs_are_atomic(scenario, monkeypatch, job):
    client, session_id, _invite, factory, _redis = scenario
    original = getattr(sessions, job)
    def fail_enqueue(*_args, **_kwargs): raise RuntimeError("Synthetic outbox failure")
    monkeypatch.setattr(sessions, job, fail_enqueue)
    assert submit(client, session_id).status_code == 500
    with factory() as db:
        assert db.query(DiagAnswer).count() == 0
        assert db.query(DiagReport).count() == 0
        session = db.query(DiagSession).one()
        assert session.phase == "warmup"
        assert session.auth_sync_status == "not_requested"
    monkeypatch.setattr(sessions, job, original)
    assert submit(client, session_id).status_code == 200
    assert_single_completion(factory)


@pytest.mark.parametrize("attempts,expected", [(1, "synced"), (5, "failed")])
def test_abandoned_completion_callback_is_recovered_after_restart(scenario, monkeypatch, attempts, expected):
    client, session_id, _invite, factory, _redis = scenario
    assert submit(client, session_id).status_code == 200
    with factory() as db:
        session = db.get(DiagSession, session_id)
        session.auth_sync_status = "syncing"
        session.auth_sync_attempts = attempts
        session.auth_sync_started_at = datetime.now(timezone.utc)-timedelta(minutes=3)
        db.commit()
    delivered = []
    monkeypatch.setattr(sync_jobs, "SessionLocal", factory)
    monkeypatch.setattr(sync_jobs.auth_client, "notify_complete", lambda *args: delivered.append(args) or True)
    assert sync_jobs.process_next_auth_completion_sync() is (expected == "synced")
    with factory() as db:
        session = db.get(DiagSession, session_id)
        assert session.auth_sync_status == expected
        assert session.auth_sync_attempts == (2 if expected == "synced" else 5)
        assert db.query(DiagAnswer).count() == db.query(DiagReport).count() == 1
    assert len(delivered) == (1 if expected == "synced" else 0)


def test_recent_completion_callback_claim_is_not_stolen(scenario, monkeypatch):
    client, session_id, _invite, factory, _redis = scenario
    assert submit(client, session_id).status_code == 200
    with factory() as db:
        session = db.get(DiagSession, session_id)
        session.auth_sync_status = "syncing"
        session.auth_sync_attempts = 1
        session.auth_sync_started_at = datetime.now(timezone.utc)
        db.commit()
    monkeypatch.setattr(sync_jobs, "SessionLocal", factory)
    def unexpected_callback(*_args): raise AssertionError("Recent claim must remain exclusive")
    monkeypatch.setattr(sync_jobs.auth_client, "notify_complete", unexpected_callback)
    assert sync_jobs.process_next_auth_completion_sync() is False
    with factory() as db:
        assert db.get(DiagSession, session_id).auth_sync_status == "syncing"


def test_restore_storage_outage_is_retryable_without_creating_attempt(scenario, monkeypatch):
    client, session_id, _invite, factory, _redis = scenario
    def unavailable(*_args): raise RuntimeError("Synthetic storage outage")
    monkeypatch.setattr(RedisStateManager, "load", unavailable)
    response = client.get("/api/v1/diagnostic/sessions/by-invite", params={"invite_code": CODE})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "SESSION_RESTORE_FAILED"
    assert response.json()["detail"]["action"] == "retry"
    with factory() as db:
        assert db.query(DiagSession).count() == 1
        assert db.query(DiagAnswer).count() == 0
        assert db.get(DiagSession, session_id).phase == "warmup"


def test_late_callback_cannot_overwrite_reclaimed_job(scenario, monkeypatch):
    client, session_id, _invite, factory, _redis = scenario
    assert submit(client, session_id).status_code == 200
    monkeypatch.setattr(sync_jobs, "SessionLocal", factory)
    def late_callback(*_args):
        with factory() as db:
            session = db.get(DiagSession, session_id)
            session.auth_sync_status = "syncing"
            session.auth_sync_attempts = 2
            session.auth_sync_started_at = datetime.now(timezone.utc)+timedelta(seconds=1)
            db.commit()
        return True
    monkeypatch.setattr(sync_jobs.auth_client, "notify_complete", late_callback)
    assert sync_jobs.process_next_auth_completion_sync() is False
    with factory() as db:
        session = db.get(DiagSession, session_id)
        assert session.auth_sync_status == "syncing"
        assert session.auth_sync_attempts == 2
        assert session.auth_sync_completed_at is None


def test_active_restore_and_missing_state_do_not_offer_new_attempt(scenario):
    client, session_id, _invite, _factory, redis = scenario
    lookup = client.get("/api/v1/diagnostic/sessions/by-invite", params={"invite_code": CODE})
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["current_task"]["task_id"] == PAYLOAD["task_id"]
    redis.delete(str(session_id))
    lookup = client.get("/api/v1/diagnostic/sessions/by-invite", params={"invite_code": CODE})
    assert lookup.status_code == 410
    assert lookup.json()["detail"]["code"] == "SESSION_EXPIRED"


def test_db_row_lock_prevents_duplicates_when_redis_lease_is_lost(scenario, monkeypatch):
    client, session_id, _invite, factory, _redis = scenario
    monkeypatch.setattr(RedisStateManager, "answer_lock", lambda *_: nullcontext())
    original = sessions.AnswerEvaluator.evaluate
    def delayed(self, task, answer):
        time.sleep(0.15)
        return original(self, task, answer)
    monkeypatch.setattr(sessions.AnswerEvaluator, "evaluate", delayed)
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: submit(client, session_id), range(3)))
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json() == responses[2].json()
    assert_single_completion(factory)


def test_restore_observes_completion_committed_during_auth_check(scenario, monkeypatch):
    client, session_id, _invite, factory, _redis = scenario
    original = access.validate_invite_capability
    async def completing_callback(*args, **kwargs):
        invite = await original(*args, **kwargs)
        with factory() as db:
            sessions.SessionService(db).submit_answer(session_id, **PAYLOAD)
        return invite
    from src.api import router as route_module
    monkeypatch.setattr(route_module, "validate_invite_capability", completing_callback)
    response = client.get("/api/v1/diagnostic/sessions/by-invite", params={"invite_code": CODE})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert_single_completion(factory)


def test_expiry_projection_change_during_accepted_submit_keeps_completion(scenario, monkeypatch):
    client, session_id, projection, factory, _redis = scenario
    original = access.validate_invite_capability
    async def expiry_race(*args, **kwargs):
        admitted = await original(*args, **kwargs)
        projection["status"] = "expired"
        projection["expires_at"] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        return admitted
    from src.api import router as route_module
    monkeypatch.setattr(route_module, "validate_invite_capability", expiry_race)
    response = submit(client, session_id)
    assert response.status_code == 200, response.text
    assert response.json()["session_completed"] is True
    assert submit(client, session_id).json() == response.json()
    assert_single_completion(factory)


def test_issued_key_and_irt_are_used_after_bank_edit_with_durable_snapshot(scenario, monkeypatch):
    client, session_id, _projection, factory, redis = scenario
    from src.domain.task_evidence import capture_task
    from src.domain.alpha_engine import IRTParams, update_theta
    state = redis.load(str(session_id))
    original = TaskMaster(id=PAYLOAD['task_id'],skill_id='A2_SKILL',question_text='Original',
                          question_latex='$x=4$',answer_type='numeric',correct_answer='4',
                          irt_discrimination=1.,irt_difficulty=-.5,irt_guessing=0.)
    state.current_task_snapshot = capture_task(original,None,None,'numeric')
    expected = update_theta(state.theta, IRTParams(a=1.,b=-.5,c=0.),1.)
    redis.save(state)
    monkeypatch.setattr(sessions.TaskRepository,'get_by_id',lambda *_:pytest.fail('live bank must not re-grade issued content'))
    response = submit(client,session_id)
    assert response.status_code==200 and response.json()['is_correct'] is True
    with factory() as db:
        saved=db.query(DiagAnswer).one()
        assert saved.task_snapshot['task']['correct_answer']=='4'
        assert saved.task_snapshot['provenance']=='issued'
        assert saved.task_snapshot['task']['question_latex']=='$x=4$'
        assert float(saved.theta_after)==pytest.approx(expected.theta,abs=.0001)
    assert submit(client,session_id).json()==response.json()
    assert_single_completion(factory)


def test_legacy_answer_records_lookup_provenance_without_issued_claim(scenario):
    client,session_id,_projection,factory,_redis=scenario
    assert submit(client,session_id).status_code==200
    with factory() as db:
        snapshot=db.query(DiagAnswer).one().task_snapshot
        assert snapshot['provenance']=='legacy_answer_lookup'
        assert snapshot['task']['correct_answer']=='4'


def test_next_issued_snapshot_does_not_overwrite_saved_previous_answer(scenario, monkeypatch):
    client,session_id,_projection,factory,redis=scenario
    monkeypatch.setattr(sessions.SessionService,'_should_stop',lambda *_,**__:False)
    next_task=TaskMaster(id='A2_NEXT',skill_id='A2_SKILL',question_text='Next',
                         question_latex='$x=99$',answer_type='numeric',correct_answer='99')
    def advance(service,state,correct):
        state.current_task_id=next_task.id
        return service._task_to_out(next_task,state)
    monkeypatch.setattr(sessions.SessionService,'_advance',advance)
    response=submit(client,session_id)
    assert response.status_code==200 and response.json()['next_task']['task_id']=='A2_NEXT'
    with factory() as db:
        snapshot=db.query(DiagAnswer).one().task_snapshot
        assert snapshot['task']['id']==PAYLOAD['task_id'] and snapshot['task']['correct_answer']=='4'
    assert redis.load(str(session_id)).current_task_snapshot['task']['correct_answer']=='99'
