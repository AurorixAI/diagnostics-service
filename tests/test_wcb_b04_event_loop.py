"""WC-B B-04: the start / resume / report handlers do their blocking work in threads, a bounded number of them, and the loop stays free.

Before: ``create_session`` & co called the synchronous service ON the event loop - 5-8 HTTP calls to content-service per start, so 30 students pressing
«Start» together froze the worker for the sum of their calls (answers, health checks wait) and a dead content-service froze it for ~33 s per start.
A plain move to the thread pool is not enough: 30 threads meet a pool of 15 connections (5 + 10) and the surplus gets ``QueuePool limit ... timed out``.
So the work goes through ``sync_work_slots`` (< the pool).  The scenarios below run the real router with a fake service that holds a real pooled
connection for 0.1 s per start (the stand-in for the HTTP calls made with an open session); the pool timeout is scaled down in the same proportion
(0.05 s here ~ 30 s in production against calls of seconds).  Controls reproduce the old code (the call inline) and the unbounded pool of threads."""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from src.api import router as router_module
from src.core import database
from src.core.config import get_settings
from src.core.sync_slots import run_sync_limited
from src.schemas.diag_schemas import AnswerResult, TaskOut

HOLD = 0.1          # seconds a start keeps its connection (the HTTP calls to content-service)
STARTS = 30
TASK = TaskOut(task_id="T1", skill_id="S1", topic_id="TP1", question_text="2+2", answer_type="exact_number", phase="warmup", items_answered=0, items_max=42)


def test_the_slots_are_below_the_pool_of_connections():
    assert get_settings().sync_work_slots < database.POOL_SIZE + database.MAX_OVERFLOW
    assert database.POOL_SIZE + database.MAX_OVERFLOW == 15


class FakeService:
    """create_session holds a pooled connection for HOLD seconds, like the real one does while it calls content-service with an open session."""

    def __init__(self, engine):
        self.engine = engine
        self.running = 0
        self.peak = 0
        self.errors: list[str] = []
        self.lock = threading.Lock()

    def create_session(self, **kwargs):
        with self.lock:
            self.running += 1
            self.peak = max(self.peak, self.running)
        try:
            with Session(self.engine) as s:
                s.execute(text("select 1"))      # the connection is taken here and kept until the block ends
                time.sleep(HOLD)
            return uuid.uuid4(), TASK
        except Exception as exc:
            self.errors.append(type(exc).__name__)
            raise
        finally:
            with self.lock:
                self.running -= 1

    def get_completed_answer_result(self, *a, **kw):
        return None

    def submit_answer(self, **kw):
        return AnswerResult(is_correct=True, outcome=1.0, eval_category="correct", theta=0.1, se=0.9)


class FakeDb:
    def query(self, *a):
        return self

    def filter(self, *a):
        return self

    def first(self):
        return SimpleNamespace(invite_code="INV", student_id=uuid.uuid4(), grade_level=7, created_at=None)


@pytest.fixture
def world(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path}/pool.db", pool_size=database.POOL_SIZE, max_overflow=database.MAX_OVERFLOW, pool_timeout=0.05,
        connect_args={"check_same_thread": False},
    )
    service = FakeService(engine)
    app = FastAPI()
    app.include_router(router_module.router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    async def no_invite_check(*a, **kw):
        return {"status": "confirmed"}

    monkeypatch.setattr(router_module, "validate_invite_capability", no_invite_check)
    monkeypatch.setattr(router_module, "validate_invite_state", lambda *a, **kw: None)
    app.dependency_overrides[router_module._service] = lambda: service
    app.dependency_overrides[router_module.get_db] = lambda: FakeDb()
    yield app, service
    engine.dispose()


async def burst(app, *, with_answers=False):
    """30 students start at once; a heartbeat and /health run beside them; optionally 10 answers arrive in the middle of the burst."""
    gaps, health, answers = [], [], []
    stop = asyncio.Event()

    async def heartbeat():
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=30) as client:
        beat = asyncio.create_task(heartbeat())

        async def start(i):
            return await client.post("/api/v1/diagnostic/sessions", json={
                "student_id": str(uuid.uuid4()), "grade_level": 7, "invite_code": f"INV{i:04d}"})

        async def ping():
            for _ in range(6):
                await asyncio.sleep(0.05)
                t = time.perf_counter()
                r = await client.get("/health")
                health.append((r.status_code, time.perf_counter() - t))

        async def answer(i):
            t = time.perf_counter() + 0.1             # the moment the student MEANT to send it: a frozen loop must not hide the wait
            await asyncio.sleep(0.1)
            r = await client.post(f"/api/v1/diagnostic/sessions/{uuid.uuid4()}/answer", headers={"X-Diagnostic-Invite-Code": "INV"},
                                  json={"task_id": "T1", "student_answer": "4"})
            answers.append((r.status_code, time.perf_counter() - t))

        t0 = time.perf_counter()
        jobs = [start(i) for i in range(STARTS)] + [ping()] + ([answer(i) for i in range(10)] if with_answers else [])
        results = await asyncio.gather(*jobs, return_exceptions=True)
        total = time.perf_counter() - t0
        stop.set()
        await beat
    starts = results[:STARTS]
    return SimpleNamespace(statuses=[r.status_code if hasattr(r, "status_code") else repr(r) for r in starts], max_gap=max(gaps), health=health,
                           answers=answers, total=total)


def test_30_simultaneous_starts_finish_without_a_pool_timeout_and_the_loop_stays_free(world):
    app, service = world
    out = asyncio.run(burst(app, with_answers=True))
    print(f"\nB-04 new: {STARTS} starts in {out.total:.2f} s, peak threads {service.peak}, pool errors {len(service.errors)}, "
          f"loop max gap {out.max_gap * 1000:.0f} ms, /health max {max(t for _, t in out.health) * 1000:.0f} ms, "
          f"answers max {max(t for _, t in out.answers) * 1000:.0f} ms")
    assert out.statuses == [201] * STARTS
    assert service.errors == []                                   # no QueuePool timeout
    assert service.peak <= get_settings().sync_work_slots < 15    # never more threads than slots, slots below the pool
    # thresholds are a multiple of HOLD (a loop that ran a start inline would stand still for HOLD per start, 2.9 s in the control below) with ~30x
    # headroom over what is measured: a scheduler hiccup of a shared CI runner cannot turn this red, a blocked loop always does
    assert out.max_gap < 3 * HOLD
    assert all(code == 200 for code, _ in out.health) and max(t for _, t in out.health) < 3 * HOLD
    assert [code for code, _ in out.answers] == [200] * 10 and max(t for _, t in out.answers) < 3 * HOLD     # answers are accepted in the middle of the burst


def test_control_the_old_code_froze_the_loop_for_the_sum_of_the_starts(world, monkeypatch):
    app, service = world

    async def inline(func, *args, **kwargs):          # what the handler did before: the blocking call on the event loop
        return func(*args, **kwargs)

    monkeypatch.setattr(router_module, "run_sync_limited", inline)
    out = asyncio.run(burst(app, with_answers=True))
    print(f"B-04 old (inline): {STARTS} starts in {out.total:.2f} s, loop max gap {out.max_gap * 1000:.0f} ms, /health max "
          f"{max(t for _, t in out.health) * 1000:.0f} ms, answers max {max(t for _, t in out.answers) * 1000:.0f} ms")
    assert out.max_gap >= HOLD * 0.9                                 # the loop stood still for a whole start at a time
    assert max(t for _, t in out.answers) > 2 * HOLD                  # answers waited for the starts


def test_control_threads_without_the_limit_run_into_the_pool_timeout(world, monkeypatch):
    app, service = world

    async def unbounded(func, *args, **kwargs):       # the naive fix: run_in_threadpool (40 threads) in front of 15 connections
        return await run_in_threadpool(func, *args, **kwargs)

    monkeypatch.setattr(router_module, "run_sync_limited", unbounded)
    out = asyncio.run(burst(app))
    print(f"B-04 naive threadpool (no limit): peak threads {service.peak}, pool errors {len(service.errors)} of {STARTS}, statuses 201: "
          f"{out.statuses.count(201)}")
    assert service.peak > 15 or service.errors
    assert service.errors, "30 threads against 15 connections must hit the pool timeout in this scaled scenario"
    assert out.statuses.count(201) < STARTS


def test_a_dead_content_service_does_not_stop_the_worker(world):
    """The service sleeps 0.5 s per start (a bank that does not answer): /health and the loop stay alive while the 8 slots are busy."""
    app, service = world
    original = service.create_session

    def slow(**kw):
        with service.lock:
            service.running += 1
        try:
            time.sleep(0.5)
            raise RuntimeError("content-service is down")
        finally:
            with service.lock:
                service.running -= 1

    service.create_session = slow

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=30) as client:
            starts = [asyncio.create_task(client.post("/api/v1/diagnostic/sessions", json={
                "student_id": str(uuid.uuid4()), "grade_level": 7, "invite_code": f"INV{i:04d}"})) for i in range(12)]
            await asyncio.sleep(0.2)
            t = time.perf_counter()
            r = await client.get("/health")
            health = time.perf_counter() - t
            done = await asyncio.gather(*starts)
            return r.status_code, health, [d.status_code for d in done]

    code, health, statuses = asyncio.run(scenario())
    assert code == 200 and health < 0.3        # the starts sleep 0.5 s each: an inline call would hold the loop that long
    assert statuses == [500] * 12                                     # each start fails as before (SESSION_START_FAILED), nobody hangs


# ── the analytics handlers (a teacher's report / skill map / group overview / heatmap / timeline) ───────────────────────
from fastapi import HTTPException

from src.api import analytics_router
from src.core.access import require_diagnostic_staff


class ThreadFakeDb:
    """Records the thread every query ran in; every query is empty (the answers are the empty-student shapes)."""

    def __init__(self):
        self.threads = set()

    def query(self, *a):
        self.threads.add(threading.get_ident())
        return self

    def __getattr__(self, name):
        if name in ("filter", "order_by", "limit", "options"):
            return lambda *a, **kw: self
        raise AttributeError(name)

    def first(self):
        self.threads.add(threading.get_ident())
        return None

    def all(self):
        self.threads.add(threading.get_ident())
        return []


def analytics_app(monkeypatch, deny=None):
    app = FastAPI()
    app.include_router(analytics_router.router, prefix="/api/v1")
    db = ThreadFakeDb()
    access_threads = []
    loop_thread = {}

    async def access(actor, student_id):
        access_threads.append(threading.get_ident())
        loop_thread["id"] = threading.get_ident()
        if deny and student_id == deny:
            raise HTTPException(403, "Нет доступа к ученику")

    monkeypatch.setattr(analytics_router, "require_student_report_access", access)
    app.dependency_overrides[analytics_router.get_db] = lambda: db
    app.dependency_overrides[require_diagnostic_staff] = lambda: SimpleNamespace(user_id="U", org_id="O", role="teacher")
    return app, db, access_threads


STUDENTS = [str(uuid.uuid4()) for _ in range(3)]


def test_the_analytics_handlers_are_plain_functions_with_a_slot_taken_after_the_access_check():
    for fn in (analytics_router.student_skill_map, analytics_router.student_timeline, analytics_router.student_report,
               analytics_router.group_overview, analytics_router.group_skill_heatmap):
        assert not asyncio.iscoroutinefunction(fn), fn.__name__          # FastAPI runs them in the thread pool
    expected = {"student_skill_map", "student_timeline", "student_report", "group_overview", "group_skill_heatmap"}
    slotted = set()
    for route in analytics_router.router.routes:
        calls = [d.call.__name__ for d in route.dependant.dependencies]
        if "sync_slot" in calls:
            slotted.add(route.name)
            assert calls.index("sync_slot") > calls.index("require_diagnostic_staff"), route.name      # R3 B1: rights first, slot after
    assert slotted == expected


def test_requests_without_rights_hold_no_slot_while_auth_is_slow(monkeypatch):
    """R3 B1: 10 requests that auth will refuse (slow auth) must not take the slots of the students' starts."""
    limiter_state = {}
    app = FastAPI()
    app.include_router(analytics_router.router, prefix="/api/v1")
    app.include_router(router_module.router, prefix="/api/v1")
    service = FakeService(None)
    service.create_session = lambda **kw: (uuid.uuid4(), TASK)

    async def slow_refusal():
        from src.core import sync_slots
        limiter_state["borrowed_max"] = max(limiter_state.get("borrowed_max", 0), sync_slots._limiter().borrowed_tokens)
        await asyncio.sleep(0.3)                                   # a slow auth-service
        raise HTTPException(401, "no rights")

    async def no_invite_check(*a, **kw):
        return {"status": "confirmed"}

    monkeypatch.setattr(router_module, "validate_invite_capability", no_invite_check)
    app.dependency_overrides[require_diagnostic_staff] = slow_refusal
    app.dependency_overrides[analytics_router.get_db] = lambda: ThreadFakeDb()
    app.dependency_overrides[router_module._service] = lambda: service

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=30) as client:
            junk = [asyncio.create_task(client.get(f"/api/v1/analytics/students/{STUDENTS[0]}/skill-map")) for _ in range(10)]
            await asyncio.sleep(0.1)                               # all ten are inside the slow check now
            from src.core import sync_slots
            held = sync_slots._limiter().borrowed_tokens
            start = await client.post("/api/v1/diagnostic/sessions", json={"student_id": str(uuid.uuid4()), "grade_level": 7, "invite_code": "INV1"})
            refused = await asyncio.gather(*junk)
            return held, start.status_code, [r.status_code for r in refused]

    held, start_status, refused = asyncio.run(scenario())
    assert held == 0                                               # the ten refused requests hold no slot during the auth call
    assert start_status == 201 and refused == [401] * 10


def test_group_overview_asks_access_on_the_loop_and_reads_the_database_in_a_thread(monkeypatch):
    app, db, access_threads = analytics_app(monkeypatch)
    client_thread = threading.get_ident()

    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            return await client.get("/api/v1/analytics/groups/overview", params=[("student_ids", s) for s in STUDENTS])

    r = asyncio.run(call())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student_count"] == 3 and body["avg_theta"] is None and body["level_distribution"]["no_data"] == 3
    assert [s["student_id"] for s in body["students"]] == STUDENTS or sorted(s["student_id"] for s in body["students"]) == sorted(STUDENTS)
    assert len(access_threads) == 3 and set(access_threads) == {client_thread}     # the async access check ran on the loop (the test's own thread)
    assert db.threads and client_thread not in db.threads                           # the queries ran in worker threads, not on the loop


def test_a_refusal_of_the_access_check_reaches_the_teacher_as_itself(monkeypatch):
    app, db, access_threads = analytics_app(monkeypatch, deny=STUDENTS[1])

    async def call(path, **params):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            return await client.get(path, **params)

    r = asyncio.run(call("/api/v1/analytics/groups/heatmap", params=[("student_ids", s) for s in STUDENTS]))
    assert r.status_code == 403 and "Нет доступа" in r.text
    r = asyncio.run(call(f"/api/v1/analytics/students/{STUDENTS[1]}/skill-map"))
    assert r.status_code == 403
    r = asyncio.run(call(f"/api/v1/analytics/students/{STUDENTS[0]}/skill-map"))
    assert r.status_code == 200 and r.json()["total_topics"] == 0 and r.json()["skills"] == []
    r = asyncio.run(call(f"/api/v1/analytics/students/{STUDENTS[0]}/timeline"))
    assert r.status_code == 200
    r = asyncio.run(call(f"/api/v1/analytics/students/{STUDENTS[0]}/report"))
    assert r.status_code == 200 and r.json() == {"report": None}


def test_a_class_of_teachers_opening_reports_cannot_exhaust_the_pool(monkeypatch):
    """40 report requests at once: at most ``sync_work_slots`` of them run their handler at the same time."""
    app, db, access_threads = analytics_app(monkeypatch)
    running, peak, lock = 0, 0, threading.Lock()
    real_query = db.query

    def query(*a):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.03)
        with lock:
            running -= 1
        return real_query(*a)

    db.query = query

    async def many():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=30) as client:
            return await asyncio.gather(*[client.get(f"/api/v1/analytics/students/{STUDENTS[0]}/skill-map") for _ in range(40)])

    rs = asyncio.run(many())
    assert [r.status_code for r in rs] == [200] * 40
    assert peak <= get_settings().sync_work_slots
