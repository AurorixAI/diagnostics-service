"""Wave B / P2 - unit tests that need no database: S-01, B-05 (Redis wrapper), B-09 (sandbox), B-12/B-13, T-02."""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace as NS

import pytest
import redis as redis_lib

from src import main as app_main
from src.core import config
from src.core.exceptions import AnswerInProgressError, AnswerNotCheckedError, StateStoreUnavailableError
from src.domain import answer_evaluator, session_service as ss
from src.domain import sympy_sandbox as sandbox_module
from src.domain.alpha_engine import AlphaTracker
from src.domain.answer_evaluator import AnswerEvaluator
from src.domain.navigators.topic_navigator import TopicEntry
from src.domain.session_service import SessionService
from src.domain.session_state import SessionState
from src.domain.sympy_sandbox import SandboxUnavailable, SympySandbox
from src.state.redis_state import RedisStateManager


# ── S-01: no token, no start ─────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("token", ["", "   ", "\n"])
def test_empty_internal_service_token_is_refused(token):
    with pytest.raises(RuntimeError, match="INTERNAL_SERVICE_TOKEN is empty"):
        config.require_internal_service_token(config.Settings(_env_file=None, internal_service_token=token))


def test_a_set_token_passes():
    config.require_internal_service_token(config.Settings(_env_file=None, internal_service_token="x" * 32))


def test_the_application_does_not_start_without_the_token_and_touches_nothing_first(monkeypatch):
    monkeypatch.setattr(config, "get_settings", lambda: config.Settings(_env_file=None, internal_service_token=""))
    touched = []
    monkeypatch.setattr("src.core.db_timezone.verify_database_timezone", lambda *_: touched.append("db"))

    async def start():
        async with app_main.lifespan(app_main.app):
            touched.append("started")
    with pytest.raises(RuntimeError, match="INTERNAL_SERVICE_TOKEN"):
        asyncio.run(start())
    assert touched == []                                   # failed before the database, migrations and workers


def test_the_container_entrypoint_stops_before_migrating(monkeypatch):
    from src.core import migration_runner
    monkeypatch.setattr(config, "get_settings", lambda: config.Settings(_env_file=None, internal_service_token=""))
    monkeypatch.setattr(migration_runner, "create_engine", lambda *a, **k: pytest.fail("touched the database"))
    with pytest.raises(RuntimeError, match="INTERNAL_SERVICE_TOKEN"):
        migration_runner.main()


# ── B-05: the Redis wrapper tells "down" from "empty" ────────────────────────────────────────────────────────────

class FakeClient:
    def __init__(self, store=None, error=None):
        self.store, self.error, self.expired = store or {}, error, []

    def get(self, key):
        if self.error: raise self.error
        return self.store.get(key)

    def expire(self, key, ttl):
        if self.error: raise self.error
        self.expired.append(key)


def manager(client):
    return RedisStateManager(client=client)


def test_load_of_a_missing_key_is_none_not_an_error():
    assert manager(FakeClient()).load("s1") is None


@pytest.mark.parametrize("error", [redis_lib.ConnectionError("down"), redis_lib.TimeoutError("slow"), ConnectionResetError()])
def test_load_while_redis_is_down_raises_unavailable_not_none(error):
    with pytest.raises(StateStoreUnavailableError):
        manager(FakeClient(error=error)).load("s1")


def test_load_of_an_unreadable_value_is_a_miss_so_the_database_snapshot_decides():
    assert manager(FakeClient(store={"diag:session:s1": b"{not json"})).load("s1") is None


def test_ttl_refresh_failure_does_not_lose_a_state_that_was_read():
    state = SessionState(session_id="s1", student_id="u", grade_level=9)
    import json
    client = FakeClient(store={"diag:session:s1": json.dumps(state.to_dict())})
    client.expire = lambda *_: (_ for _ in ()).throw(redis_lib.ConnectionError("down"))
    assert manager(client).load("s1").session_id == "s1"


def test_answer_lock_degrades_to_the_database_row_lock_when_redis_is_down():
    class Lock:
        def acquire(self, **_k): raise redis_lib.ConnectionError("down")
        def release(self): raise AssertionError("never acquired")
    client = FakeClient()
    client.lock = lambda *a, **k: Lock()
    with manager(client).answer_lock("s1"):
        ran = True
    assert ran


def test_answer_lock_still_refuses_a_second_request_when_redis_works():
    class Lock:
        def acquire(self, **_k): return False
    client = FakeClient()
    client.lock = lambda *a, **k: Lock()
    with pytest.raises(AnswerInProgressError), manager(client).answer_lock("s1"):
        pass


def test_an_error_in_the_body_is_not_swallowed_when_the_lock_is_degraded():
    class Lock:
        def acquire(self, **_k): raise redis_lib.ConnectionError("down")
    client = FakeClient()
    client.lock = lambda *a, **k: Lock()
    with pytest.raises(ValueError), manager(client).answer_lock("s1"):
        raise ValueError("inside")


# ── B-09: the sandbox ────────────────────────────────────────────────────────────────────────────────────────────

class FakeWorker:
    behaviour = "ok"
    created = 0

    def __init__(self, *_a):
        type(self).created += 1
        self.jobs = 0

    def alive(self): return True
    def kill(self): pass

    def ask(self, student, canonical, timeout):
        self.jobs += 1
        if self.behaviour == "timeout": raise sandbox_module._Timeout()
        if self.behaviour == "died": raise sandbox_module._WorkerGone("exited")
        return self.behaviour == "ok"


@pytest.fixture
def fake_sandbox(monkeypatch):
    monkeypatch.setattr(sandbox_module, "_Worker", FakeWorker)
    FakeWorker.behaviour, FakeWorker.created = "ok", 0
    box = SympySandbox(queue_wait=0.05)
    yield box
    box.close()


def test_a_worker_that_died_while_asking_is_not_checked_not_wrong(fake_sandbox):
    FakeWorker.behaviour = "died"
    with pytest.raises(SandboxUnavailable):
        fake_sandbox.equivalent("2*(x+1)", "2*x+2", "T")
    FakeWorker.behaviour = "ok"
    assert fake_sandbox._slots.get(timeout=0.1) is None        # the slot was given back, the next call can run
    fake_sandbox._slots.put(None)


def test_a_comparison_that_ran_too_long_is_still_not_equal(fake_sandbox):
    FakeWorker.behaviour = "timeout"
    assert fake_sandbox.equivalent("9**9**9", "2", "T") is False


def test_the_answer_of_a_healthy_worker_is_returned(fake_sandbox):
    assert fake_sandbox.equivalent("a", "b", "T") is True
    FakeWorker.behaviour = "no"
    assert fake_sandbox.equivalent("a", "b", "T") is False


def test_a_sandbox_that_cannot_start_is_not_checked(monkeypatch):
    def cannot(*_a): raise OSError("no fork")
    monkeypatch.setattr(sandbox_module, "_Worker", cannot)
    box = SympySandbox(queue_wait=0.05)
    with pytest.raises(SandboxUnavailable):
        box.equivalent("a", "b", "T")
    box.close()


def test_the_evaluator_raises_not_checked_and_never_returns_wrong_for_an_unavailable_sandbox(monkeypatch):
    def busy(student, canonical, task_id=None): raise SandboxUnavailable("busy")
    monkeypatch.setattr(answer_evaluator._SANDBOX, "equivalent", busy)
    task = NS(id="T", correct_answer="2*x+2", sympy_solution=None, answer_type="expression", distractor_meta=[])
    with pytest.raises(AnswerNotCheckedError):
        AnswerEvaluator().evaluate(task, "2*(x+1)")
    # answers that never reach the sandbox are graded as before, also while it is down
    assert AnswerEvaluator().evaluate(task, "2*x+2") == (1.0, "correct")
    assert AnswerEvaluator().evaluate(task, "не знаю") == (0.0, "idk")
    assert AnswerEvaluator().evaluate(task, "3**999999") == (0.0, "wrong")      # refused by the cheap check first


# ── B-13 / B-12 ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_subtopic_without_sequence_order_does_not_crash_the_navigation():
    service = object.__new__(SessionService)
    service.knowledge_repo = NS(get_subtopics_for_topic=lambda topic_id: [
        NS(id="L3-b", sequence_order=2, importance=None, name_ru=None),
        NS(id="L3-a", sequence_order=None, importance=7, name_ru="a"),       # a hand-inserted row
    ])
    picked = []
    service._pick_task_from_subtopic = lambda state, nav: picked.append([s.subtopic_id for s in nav.state.subtopics]) or "TASK"
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    assert service._init_subtopic_nav(state, TopicEntry("T", "S", 0, 5, "t")) == "TASK"
    assert picked == [["L3-a", "L3-b"]]                                      # NULL sorts first as 0, no TypeError


# ── T-02: parts that had no test ─────────────────────────────────────────────────────────────────────────────────

def test_alpha_tracker_updates_counts_and_survives_the_state_round_trip():
    tracker = AlphaTracker()
    assert tracker.get_alpha("T1") == 0.0 and tracker.get_count("T1") == 0
    assert tracker.update("T1", 1.0) == pytest.approx(0.2)
    assert tracker.update("T1", 0.0) == pytest.approx(0.0)
    assert tracker.update("T2", 0.0) == pytest.approx(-0.2)
    assert (tracker.get_count("T1"), tracker.get_count("T2")) == (2, 1)
    assert tracker.get_all() == {"T1": pytest.approx(0.0), "T2": pytest.approx(-0.2)}
    again = AlphaTracker.from_dict(tracker.to_dict())
    assert again.get_all() == tracker.get_all() and again.get_count("T1") == 2
    assert again.topic_level("T2") == tracker.topic_level("T2")


def fallback_service(candidates, tasks, *, boom=False):
    service = object.__new__(SessionService)
    service._fallback_skill_candidates = lambda state, skill_id: iter(candidates)
    def select(state, sid):
        if boom: raise RuntimeError("content-service down")
        return tasks.get(sid)
    service._select_task_for_skill = select
    service._set_context_for_skill = lambda state, sid: setattr(state, "current_skill_id", sid)
    service._task_to_out = lambda task, state: f"OUT:{task.id}"
    return service


def fresh_state():
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.current_section_id, state.current_topic_id, state.current_subtopic_id = "L1", "L2", "L3"
    return state


def test_fallback_serves_the_next_skill_with_a_task_and_remembers_where_to_return():
    service = fallback_service(["S1", "S2", "S3"], {"S3": NS(id="T3")})
    state = fresh_state()
    assert service._fallback_task(state, "S1") == "OUT:T3"                  # S1 is the empty one, S2 has nothing
    assert state.current_task_id == "T3" and state.current_skill_id == "S3"
    assert state.fallback_nav_context == {"section_id": "L1", "topic_id": "L2", "subtopic_id": "L3"}


def test_fallback_returns_none_when_the_grade_pool_is_exhausted():
    assert fallback_service(["S2", "S3"], {})._fallback_task(fresh_state(), "S1") is None


def test_fallback_ends_the_test_quietly_when_the_bank_is_unreachable(caplog):
    with caplog.at_level(logging.WARNING, logger=ss.log.name):
        assert fallback_service(["S2"], {}, boom=True)._fallback_task(fresh_state(), "S1") is None
    assert "Fallback search failed" in caplog.text
