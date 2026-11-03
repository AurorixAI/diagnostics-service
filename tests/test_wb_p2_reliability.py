"""Wave B / P2 "Diagnostics: reliability" - scenario tests against a disposable PostgreSQL + Redis.

B-05/B-14  Redis down or empty is not "the attempt expired": the state is rebuilt from ``state_snapshot``.
B-06       a lost Redis write after the commit, a repeated answer: one row per (session, task), same result.
B-09       a busy/down SymPy sandbox is "not checked", never "wrong".

Run with A2_TEST_DATABASE_URL (database ``a2_diagnostic``), like test_completion_lifecycle.py.  No real clock is
read for a decision (LESSONS 76/82); the content bank and auth projection are stubbed at their boundaries.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import redis as redis_lib
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.api.router import router
from src.core import access
from src.core.database import get_db
from src.core.db_timezone import utc_connect_args
from src.domain import answer_evaluator
from src.domain import session_service as sessions
from src.domain.session_state import SessionState
from src.domain.sympy_sandbox import SandboxUnavailable
from src.models.base import Base
from src.models.diag_models import DiagAnswer, DiagReport, DiagSession
from tests.fake_content import bank_task
from src.state import redis_state
from src.state.redis_state import RedisStateManager

DB_URL = os.getenv("A2_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="Requires disposable PostgreSQL/Redis")
CODE = "WBP2TEST01"
ORDER = ["WB_A", "WB_B", "WB_C"]


def _task(task_id, answer, answer_type="numeric"):
    return bank_task(id=task_id, skill_id="WB_SKILL", question_text="Synthetic " + task_id,
                      question_latex="Synthetic " + task_id, answer_type=answer_type, correct_answer=answer,
                      irt_discrimination=1.0, irt_difficulty=0.0, irt_guessing=0.0)


BANK = {"WB_A": _task("WB_A", "4"), "WB_B": _task("WB_B", "2*x+2", "expression"), "WB_C": _task("WB_C", "7")}


class BrokenRedis:
    """What the client looks like while Redis is restarting: every call is a connection error."""

    def _down(self, *_a, **_k):
        raise redis_lib.ConnectionError("Synthetic Redis outage")

    get = setex = expire = delete = flushdb = _down

    def lock(self, *_a, **_k):
        broken = self

        class Lock:
            def acquire(self, *a, **k): broken._down()
            def release(self): broken._down()
        return Lock()


@pytest.fixture
def mid(monkeypatch):
    """An attempt in the middle of the test: task WB_A is current, WB_B and WB_C follow."""
    assert DB_URL and DB_URL.endswith("/a2_diagnostic"), "Use only the disposable a2_diagnostic database"
    engine = create_engine(DB_URL, connect_args=utc_connect_args(DB_URL))
    Base.metadata.create_all(engine, tables=[DiagSession.__table__, DiagAnswer.__table__, DiagReport.__table__])
    factory = sessionmaker(engine)
    with engine.begin() as connection:
        for table in [DiagReport.__table__, DiagAnswer.__table__, DiagSession.__table__]:
            connection.execute(table.delete())
    cache = RedisStateManager()
    cache._redis.flushdb()
    session_id, student_id = uuid.uuid4(), uuid.uuid4()
    invite = {"status": "in_progress", "student_id": str(student_id), "class_level": 9,
              "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}

    def start(with_snapshot=True):
        state = SessionState(session_id=str(session_id), student_id=str(student_id), grade_level=9)
        state.current_task_id, state.current_skill_id, state.current_topic_id = "WB_A", "WB_SKILL", "WB_TOPIC"
        with factory() as db:
            db.add(DiagSession(id=session_id, student_id=student_id, grade_level=9, invite_code=CODE, phase="warmup",
                               state_snapshot=state.to_dict() if with_snapshot else None))
            db.commit()
        cache.save(state)
        return state
    monkeypatch.setattr(sessions.TaskRepository, "get_by_id", lambda _self, task_id: BANK.get(task_id))
    monkeypatch.setattr(sessions.SessionService, "_should_stop", lambda *_, **__: False)

    def advance(self, state, correct):
        state.current_task_id = ORDER[state.items_answered]
        state.current_task_snapshot = None
        return self._task_to_out(BANK[state.current_task_id], state)
    monkeypatch.setattr(sessions.SessionService, "_advance", advance)
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

    class World:
        pass
    world = World()
    world.client, world.session_id, world.factory, world.cache, world.start = client, session_id, factory, cache, start
    world.monkeypatch = monkeypatch
    yield world
    client.close()
    engine.dispose()


def answer(world, task_id, value, code=CODE):
    return world.client.post(f"/api/v1/diagnostic/sessions/{world.session_id}/answer",
                             json={"task_id": task_id, "student_answer": value, "time_ms": 900},
                             headers={"X-Diagnostic-Invite-Code": code})


def resume(world):
    return world.client.get("/api/v1/diagnostic/sessions/by-invite", headers={"X-Diagnostic-Invite-Code": CODE})


def graded(world):
    """(outcome, eval_category) of the last stored answer: the grading is read from the journal, no longer from the public answer (N03b-1 R3)."""
    with world.factory() as db:
        last = db.query(DiagAnswer).order_by(DiagAnswer.answered_at.desc(), DiagAnswer.id.desc()).first()
        return float(last.outcome), last.eval_category


def rows(world):
    with world.factory() as db:
        return [(a.task_id, a.student_answer) for a in db.query(DiagAnswer).order_by(DiagAnswer.answered_at, DiagAnswer.id)]


def phase(world):
    with world.factory() as db:
        return db.get(DiagSession, world.session_id).phase


def break_redis(world):
    world.monkeypatch.setattr(redis_state, "get_redis_client", lambda: BrokenRedis())


# ── B-05 / B-14: Redis is a cache, PostgreSQL holds the attempt ───────────────────────────────────────────────────

def test_answer_commits_the_state_snapshot_with_the_answer_row(mid):
    mid.start()
    assert answer(mid, "WB_A", "4").status_code == 200
    with mid.factory() as db:
        row = db.get(DiagSession, mid.session_id)
        assert row.items_answered == 1
        assert row.state_snapshot["current_task_id"] == "WB_B" and row.state_snapshot["items_answered"] == 1


def test_redis_blink_in_the_middle_of_the_test_the_student_continues_where_he_was(mid):
    mid.start()
    assert answer(mid, "WB_A", "4").status_code == 200
    break_redis(mid)                                     # Redis restarts: reads, writes and the lock all fail
    lookup = resume(mid)
    assert lookup.status_code == 200, lookup.text        # not 410 "expired": the state comes from the database
    assert lookup.json()["status"] == "active" and lookup.json()["current_task"]["task_id"] == "WB_B"
    assert lookup.json()["items_answered"] == 1
    second = answer(mid, "WB_B", "2*x+2")
    assert second.status_code == 200, second.text
    assert second.json()["next_task"]["task_id"] == "WB_C" and graded(mid)[0] == 1.0
    assert rows(mid) == [("WB_A", "4"), ("WB_B", "2*x+2")]
    assert phase(mid) == "warmup"


def test_redis_back_after_the_blink_is_healed_from_the_database(mid):
    mid.start()
    assert answer(mid, "WB_A", "4").status_code == 200
    mid.cache._redis.flushdb()                           # evicted / restarted empty
    assert mid.cache.load(str(mid.session_id)) is None
    assert resume(mid).json()["current_task"]["task_id"] == "WB_B"
    assert mid.cache.load(str(mid.session_id)).current_task_id == "WB_B"      # the cache was rebuilt
    assert phase(mid) == "warmup"


def test_a_session_without_any_state_is_marked_expired_and_the_invite_is_released(mid):
    mid.start(with_snapshot=False)                       # an attempt that predates the snapshot
    mid.cache._redis.flushdb()                           # and Redis really lost it
    lookup = resume(mid)
    assert lookup.status_code == 410 and lookup.json()["detail"]["code"] == "SESSION_EXPIRED"
    assert "учебн" in lookup.json()["detail"]["message"]          # the student is told whom to ask
    assert phase(mid) == "expired"                       # no more "eternal" active row
    with mid.factory() as db:                            # the partial unique index no longer holds the code
        db.add(DiagSession(id=uuid.uuid4(), student_id=uuid.uuid4(), grade_level=9, invite_code=CODE, phase="warmup"))
        db.commit()


def test_redis_down_and_no_snapshot_is_retry_later_not_expired(mid):
    mid.start(with_snapshot=False)
    break_redis(mid)
    lookup = resume(mid)
    assert lookup.status_code == 503, lookup.text
    assert lookup.json()["detail"]["code"] == "STATE_UNAVAILABLE" and lookup.json()["detail"]["action"] == "retry"
    reply = answer(mid, "WB_A", "4")
    assert reply.status_code == 503 and reply.json()["detail"]["code"] == "STATE_UNAVAILABLE"
    assert phase(mid) == "warmup" and rows(mid) == []   # nothing was expired, nothing was lost or half-written


def test_answer_to_an_expired_attempt_is_410(mid):
    mid.start(with_snapshot=False)
    mid.cache._redis.flushdb()
    reply = answer(mid, "WB_A", "4")
    assert reply.status_code == 410 and reply.json()["detail"]["code"] == "SESSION_EXPIRED"
    assert phase(mid) == "expired"
    assert answer(mid, "WB_A", "4").status_code == 410   # and stays so


# ── B-06: the Redis write is lost after the answer was committed ──────────────────────────────────────────────────

def test_redis_save_lost_after_commit_the_student_still_gets_the_reply_and_the_repeat_is_idempotent(mid, monkeypatch):
    mid.start()
    original = RedisStateManager.save
    def lost(self, state): raise redis_lib.ConnectionError("Synthetic loss after COMMIT")
    monkeypatch.setattr(RedisStateManager, "save", lost)
    first = answer(mid, "WB_A", "4")
    assert first.status_code == 200, first.text           # the answer is durable; the cache is not the student's problem
    monkeypatch.setattr(RedisStateManager, "save", original)
    assert mid.cache.load(str(mid.session_id)).current_task_id == "WB_A"       # Redis really is one answer behind
    again = answer(mid, "WB_A", "4")                      # the client repeats (it may not have seen the reply)
    assert again.status_code == 200 and again.json() == first.json()
    assert rows(mid) == [("WB_A", "4")]
    assert resume(mid).json()["current_task"]["task_id"] == "WB_B"
    assert mid.cache.load(str(mid.session_id)).current_task_id == "WB_B"       # healed from the snapshot


def test_stale_redis_after_a_committed_answer_repeat_gets_the_stored_result_and_no_second_row(mid):
    mid.start()
    old_state = mid.cache.load(str(mid.session_id))       # Redis as it was BEFORE the answer
    first = answer(mid, "WB_A", "4")
    assert first.status_code == 200
    mid.cache.save(old_state)                             # the Redis write of the answer was lost: Redis is one behind
    again = answer(mid, "WB_A", "4")                      # the client never saw the reply and sends it again
    assert again.status_code == 200, again.text
    assert again.json() == first.json()                   # the same result and the same next task
    assert rows(mid) == [("WB_A", "4")]                   # no second row
    nxt = answer(mid, "WB_B", "2*x+2")                    # and the attempt goes on from the real position
    assert nxt.status_code == 200 and nxt.json()["next_task"]["task_id"] == "WB_C"
    assert rows(mid) == [("WB_A", "4"), ("WB_B", "2*x+2")]
    with mid.factory() as db:
        assert db.get(DiagSession, mid.session_id).items_answered == 2


def test_repeat_with_another_value_cannot_rewrite_the_answer(mid):
    mid.start()
    assert answer(mid, "WB_A", "4").status_code == 200
    changed = answer(mid, "WB_A", "5")
    assert changed.status_code == 409 and changed.json()["detail"]["code"] == "TASK_OUT_OF_SEQUENCE"
    assert rows(mid) == [("WB_A", "4")]


def test_database_refuses_a_second_answer_row_for_the_same_task(mid):
    mid.start()
    assert answer(mid, "WB_A", "4").status_code == 200
    with mid.factory() as db:
        db.add(DiagAnswer(session_id=mid.session_id, task_id="WB_A", skill_id="s", topic_id="t",
                          student_answer="4", outcome=1.0))
        with pytest.raises(IntegrityError):
            db.commit()
    assert rows(mid) == [("WB_A", "4")]


def test_unique_index_trips_inside_the_request_as_a_conflict_not_a_second_row(mid, monkeypatch):
    """The row lock makes this unreachable in practice; if it ever is reached, the answer is refused, not doubled."""
    mid.start()
    assert answer(mid, "WB_A", "4").status_code == 200
    monkeypatch.setattr(sessions.DiagAnswerRepository, "get_by_task", lambda *_: None)   # the check misses ...
    # ... and the state is rewound to WB_A as if it were stale, so the request reaches the INSERT
    state = mid.cache.load(str(mid.session_id))
    state.current_task_id, state.current_task_snapshot, state.items_answered, state.used_task_ids = "WB_A", None, 0, []
    with mid.factory() as db:
        row = db.get(DiagSession, mid.session_id)
        row.state_snapshot = state.to_dict()
        db.commit()
    mid.cache.save(state)
    reply = answer(mid, "WB_A", "4")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "TASK_OUT_OF_SEQUENCE"
    assert rows(mid) == [("WB_A", "4")]


# ── B-09: "not checked" is not "wrong" ───────────────────────────────────────────────────────────────────────────

def _reach_open_task(mid):
    mid.start()
    assert answer(mid, "WB_A", "4").status_code == 200   # now the typed (expression) task WB_B is current


def test_busy_sandbox_means_not_checked_nothing_recorded_and_the_resend_is_graded(mid, monkeypatch):
    _reach_open_task(mid)
    def busy(student, canonical, task_id=None): raise SandboxUnavailable("busy")
    monkeypatch.setattr(answer_evaluator._SANDBOX, "equivalent", busy)
    before = mid.cache.load(str(mid.session_id))
    reply = answer(mid, "WB_B", "2*(x+1)")                # a correct answer, written differently from the key
    assert reply.status_code == 503, reply.text
    assert reply.json()["detail"]["code"] == "ANSWER_NOT_CHECKED" and reply.json()["detail"]["action"] == "retry"
    assert "не засчитан как неверный" in reply.json()["detail"]["message"]
    assert rows(mid) == [("WB_A", "4")]                   # not recorded, so not counted as wrong
    after = mid.cache.load(str(mid.session_id))
    assert (after.items_answered, after.current_task_id, after.theta.theta) == (before.items_answered, "WB_B", before.theta.theta)
    assert resume(mid).json()["current_task"]["task_id"] == "WB_B"      # the same question is still waiting


def test_after_the_sandbox_recovers_the_resend_is_graded_correct(mid, monkeypatch):
    _reach_open_task(mid)
    calls = []
    def flaky(student, canonical, task_id=None):
        calls.append(student)
        if len(calls) == 1:
            raise SandboxUnavailable("died")
        return True
    monkeypatch.setattr(answer_evaluator._SANDBOX, "equivalent", flaky)
    assert answer(mid, "WB_B", "2*(x+1)").status_code == 503
    ok = answer(mid, "WB_B", "2*(x+1)")
    assert ok.status_code == 200, ok.text
    assert graded(mid) == (1.0, "correct")
    assert rows(mid) == [("WB_A", "4"), ("WB_B", "2*(x+1)")]


def test_a_comparison_that_ran_and_said_no_is_still_wrong(mid, monkeypatch):
    _reach_open_task(mid)
    monkeypatch.setattr(answer_evaluator._SANDBOX, "equivalent", lambda *a, **k: False)   # includes "ran too long"
    reply = answer(mid, "WB_B", "x+7")
    assert reply.status_code == 200 and graded(mid)[0] == 0.0
    assert rows(mid)[-1] == ("WB_B", "x+7")


# ── the migrations (a throw-away database) ───────────────────────────────────────────────────────────────────────

def _scratch_db():
    import subprocess
    from pathlib import Path
    from sqlalchemy.engine import make_url
    root = Path(__file__).parents[1]
    name = "a2_wbp2_" + uuid.uuid4().hex[:12]
    admin = create_engine(make_url(DB_URL).set(database="postgres"), isolation_level="AUTOCOMMIT",
                          connect_args=utc_connect_args(DB_URL))
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    url = make_url(DB_URL).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url, connect_args=utc_connect_args(url))

    def alembic(*args):
        return subprocess.run(["alembic", *args], cwd=root, env={**os.environ, "DATABASE_URL": url},
                              capture_output=True, text=True)

    def drop():
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
        admin.dispose()
    return engine, alembic, drop


def _answer_sql(conn, session_id, task_id):
    conn.execute(text("INSERT INTO diag_answers(id,session_id,task_id,skill_id,topic_id,student_answer,outcome,is_deep_scan)"
                      " VALUES (:i,:s,:t,'k','p','1',0,false)"), {"i": uuid.uuid4(), "s": session_id, "t": task_id})


def test_unique_migration_stops_with_a_clear_message_when_duplicates_exist_and_changes_nothing():
    engine, alembic, drop = _scratch_db()
    try:
        assert alembic("upgrade", "012_auth_sync_backoff").returncode == 0
        dup, clean = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            for sid in (dup, clean):
                conn.execute(text("INSERT INTO diag_sessions(id,student_id,grade_level,phase) VALUES (:i,:s,9,'completed')"),
                             {"i": sid, "s": uuid.uuid4()})
            _answer_sql(conn, dup, "T1"); _answer_sql(conn, dup, "T1"); _answer_sql(conn, dup, "T2")
            _answer_sql(conn, clean, "T1")
        failed = alembic("upgrade", "head")
        assert failed.returncode != 0
        assert "Cannot add UNIQUE (session_id, task_id)" in failed.stderr and "1 task(s) in 1 session(s)" in failed.stderr
        assert str(dup) in failed.stderr and "Nothing was changed" in failed.stderr
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "012_auth_sync_backoff"
            assert conn.scalar(text("SELECT count(*) FROM diag_answers")) == 4          # no row deleted or merged
        with engine.begin() as conn:                                                     # the owner resolves it by hand
            conn.execute(text("DELETE FROM diag_answers WHERE id = (SELECT id FROM diag_answers WHERE session_id=:s AND task_id='T1' LIMIT 1)"), {"s": dup})
        assert alembic("upgrade", "head").returncode == 0
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "013_unique_answer_per_task"
            assert conn.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname='uq_diag_answers_session_task'")).startswith("CREATE UNIQUE INDEX")
        assert alembic("downgrade", "012_auth_sync_backoff").returncode == 0
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM pg_indexes WHERE indexname='uq_diag_answers_session_task'")) == 0
    finally:
        drop()


def test_backoff_migration_makes_young_rows_failed_by_the_old_worker_due_again_and_leaves_old_ones_final():
    engine, alembic, drop = _scratch_db()
    try:
        assert alembic("upgrade", "011_report_narrative_cache").returncode == 0
        ids = {name: uuid.uuid4() for name in ("young", "old", "synced", "never_requested")}
        spec = {"young": ("failed", "1 day"), "old": ("failed", "10 days"), "synced": ("synced", "1 day"),
                "never_requested": ("failed", None)}
        with engine.begin() as conn:
            for name, (status, age) in spec.items():
                requested = f"(NOW() AT TIME ZONE 'UTC') - INTERVAL '{age}'" if age else "NULL"
                conn.execute(text(
                    "INSERT INTO diag_sessions(id,student_id,grade_level,phase,invite_code,auth_sync_status,auth_sync_attempts,auth_sync_requested_at)"
                    f" VALUES (:i,:s,9,'completed',:c,:st,5,{requested})"),
                    {"i": ids[name], "s": uuid.uuid4(), "c": f"C{ids[name].hex[:8]}", "st": status})
        assert alembic("upgrade", "012_auth_sync_backoff").returncode == 0
        with engine.connect() as conn:
            due = {name: conn.scalar(text("SELECT auth_sync_next_attempt_at IS NOT NULL FROM diag_sessions WHERE id=:i"), {"i": ids[name]})
                   for name in ids}
            assert due == {"young": True, "old": False, "synced": False, "never_requested": False}
            assert conn.scalar(text("SELECT max(auth_sync_requeues) FROM diag_sessions")) == 0
        assert alembic("downgrade", "011_report_narrative_cache").returncode == 0
    finally:
        drop()


# ── R3 #7: a snapshot that is ahead of a lagging Redis is never an expired attempt ───────────────────────────────────

def test_lagging_redis_with_a_snapshot_is_not_expired_and_the_repeat_is_answered(mid):
    mid.start()
    behind = mid.cache.load(str(mid.session_id))
    first = answer(mid, "WB_A", "4")
    mid.cache.save(behind)                                 # Redis is one answer behind the database
    repeat = answer(mid, "WB_A", "4")
    assert repeat.status_code == 200 and repeat.json() == first.json()
    assert phase(mid) == "warmup"                          # NOT 'expired'
    assert resume(mid).json()["current_task"]["task_id"] == "WB_B"
    assert phase(mid) == "warmup"


# ── R3 #10: only the uniqueness of the answer is "the state moved on" ────────────────────────────────────────────────

def test_another_integrity_error_is_not_hidden_behind_out_of_sequence(mid, monkeypatch):
    mid.start()
    class Diag:  # what psycopg2 puts on ``exc.orig``
        constraint_name = "diag_answers_session_id_fkey"
    class Orig(Exception):
        diag = Diag()
    def broken(self, **_kwargs): raise IntegrityError("INSERT", {}, Orig("Synthetic FK violation"))
    monkeypatch.setattr(sessions.DiagAnswerRepository, "log_answer", broken)
    reply = answer(mid, "WB_A", "4")
    assert reply.status_code == 500 and reply.json()["detail"]["code"] == "ANSWER_FAILED"     # a defect is visible
    assert rows(mid) == [] and phase(mid) == "warmup"


# ── R3 #11: two browser tabs of one student (real threads, real PostgreSQL) ──────────────────────────────────────────

@pytest.mark.parametrize("redis_up", [True, False])
@pytest.mark.parametrize("same_answer", [True, False])
def test_two_tabs_answer_the_same_question_at_once(mid, monkeypatch, redis_up, same_answer):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    mid.start()
    original = sessions.AnswerEvaluator.evaluate
    def slow(self, task, value):
        time.sleep(0.4)                                   # the first request holds its locks while the second arrives
        return original(self, task, value)
    monkeypatch.setattr(sessions.AnswerEvaluator, "evaluate", slow)
    if not redis_up:
        break_redis(mid)
    values = ["4", "4" if same_answer else "5"]
    def tab(index):
        time.sleep(0.15 * index)
        return answer(mid, "WB_A", values[index])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(tab, i) for i in range(2)]
        replies = [f.result(timeout=30) for f in futures]          # no hang, no deadlock
    codes = sorted(r.status_code for r in replies)
    assert rows(mid) == [("WB_A", "4")]                            # exactly one row, whatever happened
    if redis_up:
        assert codes == [200, 409]                                 # the second tab: "still being processed"
        assert replies[1].json()["detail"]["code"] == "ANSWER_IN_PROGRESS"
    elif same_answer:
        assert codes == [200, 200] and replies[0].json() == replies[1].json()      # waited on the row lock, got the stored result
    else:
        assert codes == [200, 409] and replies[1].json()["detail"]["code"] == "TASK_OUT_OF_SEQUENCE"
    with mid.factory() as db:
        assert db.get(DiagSession, mid.session_id).items_answered == 1
