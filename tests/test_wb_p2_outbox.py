"""B-03: the completion callback to auth-service survives an outage of auth-service and a restart of this one.

A fixed, fake clock drives everything (``auth_sync_jobs._now``): the tests never read the real time and never sleep
(LESSONS 76/82).  PostgreSQL is real - the whole point is that the queue lives in the row.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core import auth_client
from src.core.db_timezone import utc_connect_args
from src.domain import auth_sync_jobs as sync_jobs
from src.models.base import Base
from src.models.diag_models import DiagAnswer, DiagReport, DiagSession

DB_URL = os.getenv("A2_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
HOUR = 3600


class World:
    """A completed attempt waiting for auth-service, a fake clock, and an auth-service that is down until told."""

    def __init__(self, factory, monkeypatch):
        self.factory, self.now, self.calls = factory, T0, []
        self.auth_up_from = None                      # None = down forever; a datetime = reachable from then on
        self.fresh_engine_each_tick = False
        self.session_id = uuid.uuid4()
        with factory() as db:
            db.add(DiagSession(id=self.session_id, student_id=uuid.uuid4(), grade_level=9, invite_code="OUTBOX0001",
                               phase="completed", theta=0.3, theta_se=0.25, overall_level="at_grade"))
            db.commit()
            sync_jobs.enqueue_auth_completion_sync(db, db.get(DiagSession, self.session_id))
        monkeypatch.setattr(sync_jobs, "_now", lambda: self.now)
        monkeypatch.setattr(sync_jobs, "SessionLocal", self._session_local)
        monkeypatch.setattr(sync_jobs.auth_client, "notify_complete", self._notify)

    def _session_local(self):
        if self.fresh_engine_each_tick:               # a restarted process: nothing in memory, only the database
            engine = create_engine(DB_URL, connect_args=utc_connect_args(DB_URL))
            session = sessionmaker(engine)()
            close = session.close
            session.close = lambda: (close(), engine.dispose())
            return session
        return self.factory()

    def _notify(self, code, session_id, payload):
        self.calls.append(self.now)
        return self.auth_up_from is not None and self.now >= self.auth_up_from

    def row(self):
        with self.factory() as db:
            r = db.get(DiagSession, self.session_id)
            return {"status": r.auth_sync_status, "attempts": r.auth_sync_attempts, "requeues": r.auth_sync_requeues,
                    "next": r.auth_sync_next_attempt_at, "error": r.auth_sync_error, "completed": r.auth_sync_completed_at}

    def run(self, until, step=timedelta(seconds=30)):
        """The worker loop: poll every ``step`` of fake time until ``until`` or until the row is synced."""
        end = T0 + until
        while self.now <= end:
            sync_jobs.process_next_auth_completion_sync()
            if self.row()["status"] == "synced":
                return
            self.now += step


@pytest.fixture
def world(monkeypatch):
    assert DB_URL and DB_URL.endswith("/a2_diagnostic"), "Use only the disposable a2_diagnostic database"
    engine = create_engine(DB_URL, connect_args=utc_connect_args(DB_URL))
    Base.metadata.create_all(engine, tables=[DiagSession.__table__, DiagAnswer.__table__, DiagReport.__table__])
    with engine.begin() as connection:
        for table in [DiagReport.__table__, DiagAnswer.__table__, DiagSession.__table__]:
            connection.execute(table.delete())
    yield World(sessionmaker(engine), monkeypatch)
    engine.dispose()


pytestmark = pytest.mark.skipif(not DB_URL, reason="Requires disposable PostgreSQL")


def test_the_retry_schedule_is_a_growing_pause_within_about_six_hours():
    pauses = [sync_jobs.backoff_after(n).total_seconds() for n in range(1, sync_jobs.MAX_SYNC_ATTEMPTS)]
    assert len(pauses) == sync_jobs.MAX_SYNC_ATTEMPTS - 1 == 9
    assert pauses == sorted(pauses) and pauses[0] == 30 and len(set(pauses)) == len(pauses)    # strictly growing
    assert sum(pauses) <= 6 * HOUR
    assert sync_jobs.backoff_after(99).total_seconds() == pauses[-1]                           # never out of range


def test_auth_service_down_for_ten_minutes_the_result_still_arrives(world):
    world.auth_up_from = T0 + timedelta(minutes=10)
    world.run(until=timedelta(hours=1))
    row = world.row()
    assert row["status"] == "synced" and row["completed"] is not None and row["error"] is None
    assert world.calls[-1] >= T0 + timedelta(minutes=10)           # delivered only once auth-service was back
    assert row["attempts"] == len(world.calls) == 6                # 0 s, 30 s, 90 s, 3.5 min, 8.5 min, 18.5 min
    gaps = [(b - a).total_seconds() for a, b in zip(world.calls, world.calls[1:])]
    assert gaps == [30, 60, 120, 300, 600]                         # a pause that grows, not a hammer every 2 s


def test_nothing_is_sent_while_the_pause_lasts(world):
    world.auth_up_from = None
    sync_jobs.process_next_auth_completion_sync()
    assert len(world.calls) == 1 and world.row()["status"] == "pending"
    world.now += timedelta(seconds=29)
    assert sync_jobs.process_next_auth_completion_sync() is False and len(world.calls) == 1
    world.now += timedelta(seconds=1)
    sync_jobs.process_next_auth_completion_sync()
    assert len(world.calls) == 2


def test_the_queue_survives_a_restart_of_the_service_between_every_attempt(world):
    world.fresh_engine_each_tick = True                            # every poll is a brand-new process
    world.auth_up_from = T0 + timedelta(hours=2)
    world.run(until=timedelta(hours=4), step=timedelta(minutes=1))
    assert world.row()["status"] == "synced"
    assert world.calls[-1] >= T0 + timedelta(hours=2)


def test_ten_attempts_in_about_six_hours_then_hourly_requeue_for_a_day_then_one_error_line(world, caplog):
    world.auth_up_from = None                                      # never comes back
    with caplog.at_level(logging.WARNING, logger=sync_jobs.log.name):
        world.run(until=timedelta(hours=6))        # the first series ends at about 5 h 20 min; the requeue is an hour later
        first_series = list(world.calls)
        row = world.row()
        assert len(first_series) == sync_jobs.MAX_SYNC_ATTEMPTS == 10
        assert first_series[-1] - T0 <= timedelta(hours=6)         # all ten attempts fit into the six hours
        assert row["status"] == "failed" and row["requeues"] == 0 and row["next"] is not None
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]      # not an alert yet: it will retry
        world.run(until=timedelta(hours=40), step=timedelta(minutes=5))
        row = world.row()
        assert row["status"] == "failed" and row["requeues"] == sync_jobs.MAX_REQUEUES == 24 and row["next"] is None
        assert len(world.calls) == 10 + 24
        requeue_gaps = {(b - a) for a, b in zip(world.calls[10:], world.calls[11:])}
        assert requeue_gaps == {timedelta(hours=1)}                # once an hour
        errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(errors) == 1 and errors[0].startswith("diagnostic_auth_sync_permanently_failed")
        assert str(world.session_id) in errors[0]
        before = len(world.calls)
        world.run(until=timedelta(hours=80), step=timedelta(minutes=30))
        assert len(world.calls) == before                          # the final failure is final


def test_a_long_outage_is_delivered_by_the_hourly_requeue(world):
    world.auth_up_from = T0 + timedelta(hours=9)                   # longer than the first series (about 5.3 h)
    world.run(until=timedelta(hours=12), step=timedelta(minutes=5))
    row = world.row()
    assert row["status"] == "synced" and 1 <= row["requeues"] <= 4
    assert row["attempts"] == 10 + row["requeues"]


def test_enqueue_starts_a_clean_series(world):
    world.auth_up_from = None
    world.run(until=timedelta(hours=7))
    assert world.row()["status"] == "failed"
    with world.factory() as db:
        sync_jobs.enqueue_auth_completion_sync(db, db.get(DiagSession, world.session_id))
    row = world.row()
    assert (row["status"], row["attempts"], row["requeues"], row["next"]) == ("pending", 0, 0, None)


def test_a_crash_of_the_callback_is_scheduled_like_an_unanswered_one(world, monkeypatch):
    def explode(*_a): raise RuntimeError("Synthetic crash inside the callback")
    monkeypatch.setattr(sync_jobs.auth_client, "notify_complete", explode)
    assert sync_jobs.process_next_auth_completion_sync() is False
    row = world.row()
    assert row["status"] == "pending" and row["next"] is not None and "RuntimeError" in row["error"]
    assert row["next"].replace(tzinfo=timezone.utc) == T0 + timedelta(seconds=30)


# ── R3 #4: a permanent "no" is not worth the whole ladder ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [400, 404, 409, 422])
def test_a_permanent_refusal_is_final_after_three_attempts_with_one_error_line(world, monkeypatch, caplog, status):
    monkeypatch.setattr(sync_jobs.auth_client, "notify_complete", lambda *a: world.calls.append(world.now) or auth_client.Rejected(status))
    with caplog.at_level(logging.WARNING, logger=sync_jobs.log.name):
        world.run(until=timedelta(hours=30), step=timedelta(seconds=30))
    row = world.row()
    assert len(world.calls) == sync_jobs.REJECTED_AFTER_ATTEMPTS == 3                 # not 34
    assert (row["status"], row["next"], row["attempts"]) == ("failed", None, 3)
    assert f"HTTP {status}" in row["error"]
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == [f"diagnostic_auth_sync_rejected session_id={world.session_id} status={status} attempts=3"]
    assert world.calls[-1] - T0 <= timedelta(minutes=5)                                 # and it is quick: 0 s, 30 s, 90 s


def test_a_refusal_after_network_failures_is_final_too_and_a_later_success_is_still_possible_before_that(world, monkeypatch):
    answers = iter([False, False, auth_client.Rejected(400)])                           # two outages, then a refusal
    monkeypatch.setattr(sync_jobs.auth_client, "notify_complete", lambda *a: world.calls.append(world.now) or next(answers))
    world.run(until=timedelta(hours=1))
    assert world.row()["status"] == "failed" and world.row()["next"] is None and len(world.calls) == 3


def test_a_refusal_below_three_attempts_keeps_the_pause(world, monkeypatch):
    monkeypatch.setattr(sync_jobs.auth_client, "notify_complete", lambda *a: world.calls.append(world.now) or auth_client.Rejected(409))
    sync_jobs.process_next_auth_completion_sync()
    row = world.row()
    assert row["status"] == "pending" and row["next"].replace(tzinfo=timezone.utc) == T0 + timedelta(seconds=30)


@pytest.mark.parametrize("code,expected", [
    (200, True), (204, True),
    (400, "rejected"), (404, "rejected"), (409, "rejected"), (422, "rejected"),
    (401, False), (403, False), (408, False), (425, False), (429, False), (500, False), (502, False), (503, False),
])
def test_notify_complete_classifies_the_answer_of_auth_service(monkeypatch, code, expected):
    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def post(self, url, **_kwargs): return httpx.Response(200 if url.endswith("/start") else code)
    monkeypatch.setattr(auth_client.httpx, "Client", Client)
    monkeypatch.setattr(auth_client, "_internal_headers", lambda: {"X-Internal-Service-Token": "t"})
    result = auth_client.notify_complete("CODE", "S1", {})
    if expected == "rejected":
        assert isinstance(result, auth_client.Rejected) and result.status == code and not result
    else:
        assert result is expected


def test_network_error_is_retry_not_rejected(monkeypatch):
    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def post(self, url, **_kwargs): raise httpx.ConnectError("down")
    monkeypatch.setattr(auth_client.httpx, "Client", Client)
    monkeypatch.setattr(auth_client, "_internal_headers", lambda: {"X-Internal-Service-Token": "t"})
    assert auth_client.notify_complete("CODE", "S1", {}) is False
