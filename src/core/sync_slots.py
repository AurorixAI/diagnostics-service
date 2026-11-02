"""Diagnostic Service - bounded synchronous work next to the event loop (WC-B B-04).

The handlers that read the database and the content bank with the synchronous SQLAlchemy / httpx clients must not run on the event loop (a start
costs 5-8 HTTP calls to content-service: 50-200 ms of a frozen loop per student, ~33 s when the bank is down; a teacher's report up to 240 calls).
They run in the thread pool - but the pool of connections of one worker is ``POOL_SIZE + MAX_OVERFLOW`` = 15 and anyio's default limit is 40
threads: 30 students pressing «Start» together would put 30 threads in front of 15 connections and the rest would wait ``pool_timeout`` (30 s)
for a connection.  So the work of these handlers goes through ONE limiter, ``sync_work_slots`` (< the pool, the rest of the pool belongs to the
answers and to the sessions that stay open across an ``await``): a request over the limit waits as a coroutine (no thread, no connection) and the
loop keeps accepting answers and health checks.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable

import anyio
import anyio.from_thread
import anyio.to_thread

from src.core.config import get_settings

_state: dict[str, Any] = {"loop": None, "limiter": None}


def _limiter() -> anyio.CapacityLimiter:
    """The limiter of the running loop (one per worker in production; a test that starts a new loop gets a new one)."""
    loop = asyncio.get_running_loop()
    if _state["loop"] is not loop:
        _state["limiter"] = anyio.CapacityLimiter(get_settings().sync_work_slots)
        _state["loop"] = loop
    return _state["limiter"]


async def run_sync_limited(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a blocking function in a worker thread, at most ``sync_work_slots`` of them at the same time."""
    return await anyio.to_thread.run_sync(functools.partial(func, *args, **kwargs), limiter=_limiter())


async def sync_slot():
    """Dependency of a plain ``def`` route: the request holds one slot from before its thread starts until its answer is built."""
    async with _limiter():
        yield


def await_on_loop(func: Callable[..., Any], *args: Any) -> Any:
    """For a ``def`` handler that runs in a worker thread: call the coroutine function ``func(*args)`` on the event loop and wait for its result
    (the access check of auth-service is asynchronous; the handler itself is synchronous)."""
    return anyio.from_thread.run(func, *args)
