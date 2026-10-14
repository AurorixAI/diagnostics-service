"""
Diagnostic Service - SymPy in a killable subprocess.

``parse_expr`` evaluates what a student typed and ``simplify`` can run for minutes; a huge ``int ** int`` holds the
GIL, so neither a thread nor a signal handler can stop it, and grading runs inside the service process.  The only
hard time limit is a separate process that the service kills: ``SympySandbox.equivalent`` sends the pair of
expressions to a long-lived worker (``python -m src.domain.sympy_sandbox``), waits ``timeout`` seconds for the
answer and otherwise kills the worker (a new one starts on demand).  A refused, too slow or crashed comparison
is "not equal"; the text of the answer is never logged.

Protocol (one JSON array / one line per request over stdin, one byte per reply over stdout):
  worker -> b"ready\\n" once SymPy is imported and warm;  service -> b'["student", "canonical"]\\n';
  worker -> b"1\\n" (equivalent) or b"0\\n".
A worker that sees EOF on stdin (the service died) exits, so none is left behind.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import selectors
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WORKER_MODULE = "src.domain.sympy_sandbox"


class _Timeout(Exception):
    pass


class _WorkerGone(Exception):
    pass


class _Worker:
    """One worker process: started with its SymPy imports done, asked one question at a time."""

    def __init__(self, memory_mb: int, startup_timeout: float):
        env = dict(os.environ, SYMPY_SANDBOX_MEMORY_MB=str(memory_mb), PYTHONUNBUFFERED="1")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", _WORKER_MODULE],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=str(_PROJECT_ROOT), env=env,
            start_new_session=True,           # a Ctrl-C meant for the service must not land in the worker
        )
        self.jobs = 0
        self._buffer = b""
        try:
            if self._read_line(time.monotonic() + startup_timeout) != b"ready":
                raise _WorkerGone("worker did not start")
        except BaseException:
            self.kill()
            raise

    def _read_line(self, deadline: float) -> bytes:
        fd = self.proc.stdout.fileno()
        with selectors.DefaultSelector() as selector:       # not select(): a busy server has descriptors above 1024
            selector.register(fd, selectors.EVENT_READ)
            while b"\n" not in self._buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise _Timeout()
                chunk = os.read(fd, 4096)
                if not chunk:
                    raise _WorkerGone("worker exited")
                self._buffer += chunk
        line, _, self._buffer = self._buffer.partition(b"\n")
        return line

    def ask(self, student: str, canonical: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        self.jobs += 1
        try:
            self.proc.stdin.write(json.dumps([student, canonical]).encode("ascii") + b"\n")
            self.proc.stdin.flush()
        except OSError:
            raise _WorkerGone("worker is not accepting requests")
        return self._read_line(deadline) == b"1"

    def alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self) -> None:
        try:
            self.proc.kill()
        except OSError:
            pass
        for stream in (self.proc.stdin, self.proc.stdout):
            try:
                stream.close()
            except OSError:
                pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


class SympySandbox:
    """At most ``workers`` comparisons at a time, each on its own worker process, started lazily and reused.

    A caller waits up to ``queue_wait`` seconds for a free slot, then the answer is "not equal" (logged).  A
    worker is replaced after ``jobs_per_worker`` requests (SymPy caches grow) and whenever it timed out or died.
    """

    def __init__(self, *, workers: int = 1, timeout: float = 1.0, queue_wait: float = 3.0,
                 startup_timeout: float = 30.0, jobs_per_worker: int = 200, memory_mb: int = 1024):
        self._timeout = timeout
        self._queue_wait = queue_wait
        self._startup_timeout = startup_timeout
        self._jobs_per_worker = jobs_per_worker
        self._memory_mb = memory_mb
        self._workers = workers
        self._slots: "queue.Queue[None]" = queue.Queue()
        for _ in range(workers):
            self._slots.put(None)
        self._idle: List[_Worker] = []
        self._starting = 0                     # replacements being started in the background
        self._cond = threading.Condition()
        self._registered = False

    def equivalent(self, student: str, canonical: str, task_id=None) -> bool:
        try:
            self._slots.get(timeout=self._queue_wait)
        except queue.Empty:
            log.warning("sympy_sandbox_busy task_id=%s answer_len=%s", task_id, len(student))
            return False
        worker: Optional[_Worker] = None
        try:
            worker = self._take()
            result = worker.ask(student, canonical, self._timeout)
        except _Timeout:
            log.warning("sympy_timeout task_id=%s answer_len=%s limit_s=%s", task_id, len(student), self._timeout)
            self._replace(worker)
            return False
        except Exception as exc:               # a worker that cannot start or died: the comparison is not made
            log.warning("sympy_sandbox_failed task_id=%s error_type=%s", task_id, type(exc).__name__)
            self._replace(worker)
            return False
        else:
            self._release(worker)
            return result
        finally:
            self._slots.put(None)

    def _take(self) -> _Worker:
        with self._cond:
            while True:
                while self._idle:
                    worker = self._idle.pop()
                    if worker.alive():
                        return worker
                    worker.kill()
                if not self._starting:         # otherwise wait for the replacement that is already on its way
                    break
                self._cond.wait()
            if not self._registered:
                self._registered = True
                atexit.register(self.close)
        return _Worker(self._memory_mb, self._startup_timeout)

    def _release(self, worker: _Worker) -> None:
        if worker.jobs >= self._jobs_per_worker:
            worker.kill()
            return
        with self._cond:
            self._idle.append(worker)

    def _replace(self, worker: Optional[_Worker]) -> None:
        """Kill a worker that timed out or died; its successor starts in the background, so the next answer does
        not pay for the start (~0.6 s: the SymPy import)."""
        if worker is not None:
            worker.kill()
        with self._cond:
            self._starting += 1
        threading.Thread(target=self._start_replacement, daemon=True, name="sympy-sandbox-start").start()

    def _start_replacement(self) -> None:
        worker = None
        try:
            worker = _Worker(self._memory_mb, self._startup_timeout)
        except Exception as exc:
            log.warning("sympy_sandbox_start_failed error_type=%s", type(exc).__name__)
        with self._cond:
            self._starting -= 1
            if worker is not None and len(self._idle) < self._workers:
                self._idle.append(worker)
                worker = None
            self._cond.notify_all()
        if worker is not None:
            worker.kill()

    def close(self) -> None:
        with self._cond:
            idle, self._idle = self._idle, []
        for worker in idle:
            worker.kill()


# ── the worker process ────────────────────────────────────────────────────────────────────────────────────────────

def _limit_memory(megabytes: int) -> None:
    """A runaway ``9**9**9`` must die with MemoryError, not take the host down with it (Linux enforces RLIMIT_AS)."""
    try:
        import resource
        limit = megabytes * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):
        pass


def main() -> None:
    reply = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)                              # whatever SymPy prints must not corrupt the protocol
    _limit_memory(int(os.environ.get("SYMPY_SANDBOX_MEMORY_MB", "1024")))
    from .answer_evaluator import _sympy_equivalent
    _sympy_equivalent("2*x+2", "2*(x+1)")      # warm up: the first simplify() imports half of SymPy
    reply.write(b"ready\n")
    for line in sys.stdin.buffer:
        try:
            student, canonical = json.loads(line)
            equal = _sympy_equivalent(student, canonical)
        except Exception:                       # includes MemoryError: "not equal", and the loop goes on
            equal = False
        try:
            reply.write(b"1\n" if equal else b"0\n")
        except OSError:                         # the service is gone
            return


if __name__ == "__main__":
    main()
