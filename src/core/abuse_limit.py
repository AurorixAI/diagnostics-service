"""Abuse limits for the PUBLIC diagnostic invite-code entry (ROADMAP #77).

A diagnostic invite is a code of 8 characters from a 31-character alphabet.  The public endpoints that take it
(``POST /sessions``, ``GET /sessions/active``, ``GET /sessions/by-invite``) answer differently for an unknown
code (403 INVITE_INVALID) and a known one, so the code space can be probed.  auth-service cannot throttle this by
the student's address: diagnostic-service calls it server-to-server, so the address it sees is ours.  The limit
therefore lives here, where the browser's address is known.

* What a guess costs is a FAILED lookup (unknown code, or a known code with another student / grade), so those are
  budgeted per client address: 20 per minute and 200 per hour.  A class behind one school NAT opens ~30 valid codes in
  a minute (about 2-3 calls each): valid lookups are not failures and are only capped against floods per address
  (300 per minute, 3000 per hour).
* One code is used by ONE student; 100 calls per hour per code is far above a student's (a few page loads and
  retries) and stops hammering a single code.  The key is a hash of the code: what a client types never becomes a key
  and the code never reaches a log line (it is a capability).
* When Redis is unreachable the counters run on per-process memory with ONE warning per outage (fail open).

The client address: nginx overwrites X-Real-IP with $remote_addr on the diagnostic locations; that header is the
only one trusted.  X-Forwarded-For is client-typed there (nginx does not set it), so it is ignored.  Without
X-Real-IP the request did not come through our proxy and the socket peer is the caller.
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import redis
from fastapi import HTTPException, Request

from src.core.config import get_settings

log = logging.getLogger("diagnostic_service.abuse_limit")

MSG_TOO_MANY_ATTEMPTS = "Слишком много попыток. Подождите минуту и попробуйте снова."


@dataclass(frozen=True)
class Limit:
    count: int
    window: int  # seconds


# ── the policy ─────────────────────────────────────────────────────────────────────────────────────────────
# Failed lookups per client address.
FAILS_PER_MINUTE = Limit(20, 60)
FAILS_PER_HOUR = Limit(200, 3600)
# Every lookup per client address: only a flood guard, far above a class behind one NAT.
ATTEMPTS_PER_MINUTE = Limit(300, 60)
ATTEMPTS_PER_HOUR = Limit(3000, 3600)
# Every lookup of one code, from any address.
CODE_PER_HOUR = Limit(100, 3600)
# invite_error codes that mean «this was a guess»: an unknown code, or a known one with another student / grade.
# An expired / used / not-yet-confirmed invite is a state, not a guess, and a student can meet it legitimately.
GUESS_CODES = frozenset({"INVITE_INVALID", "INVITE_STUDENT_MISMATCH", "INVITE_GRADE_MISMATCH"})


# ── client address ─────────────────────────────────────────────────────────────────────────────────────────
IPV6_BUCKET_PREFIX_LENGTH = 64


def _valid_ip(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """X-Real-IP (set by our nginx from the socket), else the socket peer.  Never X-Forwarded-For."""
    real_ip = _valid_ip(request.headers.get("x-real-ip"))
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def limit_bucket(address: str) -> str:
    """IPv4 as it is; IPv6 by its /64 (one subscriber owns 2**64 addresses); an IPv4-mapped IPv6 as its IPv4."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 4:
        return str(ip)
    if ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    return str(ipaddress.ip_network(f"{ip}/{IPV6_BUCKET_PREFIX_LENGTH}", strict=False))


def client_bucket(request: Request) -> str:
    return limit_bucket(client_ip(request))


def code_key(code: str) -> str:
    """The code as a short fixed-size key: what the client typed never becomes a key (length, characters)."""
    return hashlib.sha256((code or "").strip().upper().encode("utf-8")).hexdigest()[:24]


# ── counters ───────────────────────────────────────────────────────────────────────────────────────────────
# INCR + EXPIRE as ONE atomic step; later hits do not push the TTL out (a client that keeps retrying is let
# back in when the window ends).
_HIT_LUA = """
local c = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if c == 1 or ttl < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {c, ttl}
"""

def _now() -> float:
    return time.monotonic()


_REDIS_RETRY_AFTER = 30.0  # seconds without trying Redis after it failed
_REDIS_TIMEOUT = 0.25  # a counter must never hold a request (these endpoints are async: it blocks the loop)
_MEMORY_SOFT_LIMIT = 20_000
_MEMORY_HARD_LIMIT = 100_000


class _Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._memory: dict[str, list] = {}  # key -> [count, ends_at (monotonic)]
        self._client: Optional[redis.Redis] = None
        self._down_until = 0.0
        self._warned = False

    # -- Redis availability ------------------------------------------------------------------------------
    def _redis(self) -> Optional[redis.Redis]:
        if _now() < self._down_until:
            return None
        if self._client is None:
            settings = get_settings()
            if settings.app_env == "testing":
                return None  # the suite never talks to a real Redis; a test that wants one injects it (use_redis)
            self._client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=_REDIS_TIMEOUT,
                socket_timeout=_REDIS_TIMEOUT,
            )
        return self._client

    def _mark_down(self, exc: Exception) -> None:
        self._down_until = _now() + _REDIS_RETRY_AFTER
        if not self._warned:
            self._warned = True
            log.warning(
                "abuse_limit_redis_unavailable error_type=%s: invite-code limits run on per-process memory "
                "(not shared between workers) until Redis is back",
                type(exc).__name__,
            )

    def _mark_up(self) -> None:
        if self._warned:
            log.info("abuse_limit_redis_recovered")
        self._warned = False

    def use_redis(self, client: Optional[redis.Redis]) -> None:
        """Tests: count in this client (None = back to the default selection)."""
        self._client = client
        self._down_until = 0.0

    # -- operations --------------------------------------------------------------------------------------
    def hit(self, key: str, window: int) -> Tuple[int, int]:
        """Count one event in a fixed window: (events so far including this one, seconds left)."""
        client = self._redis()
        if client is not None:
            try:
                count, ttl = client.eval(_HIT_LUA, 1, key, window)
                self._mark_up()
                return int(count), max(int(ttl), 1)
            except Exception as exc:  # noqa: BLE001 - a counter store must never break a request
                self._mark_down(exc)
        now = _now()
        with self._lock:
            count, ends_at = self._memory.get(key, (0, 0.0))
            if ends_at <= now:
                count, ends_at = 0, now + window
            count += 1
            self._memory[key] = [count, ends_at]
            self._prune(now)
        return count, max(math.ceil(ends_at - now), 1)

    def peek(self, key: str) -> Tuple[int, int]:
        """(events in the current window, seconds left) without counting; (0, 0) when there is no window."""
        client = self._redis()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.get(key)
                pipe.ttl(key)
                value, ttl = pipe.execute()
                self._mark_up()
                return (int(value), max(int(ttl), 1)) if value is not None else (0, 0)
            except Exception as exc:  # noqa: BLE001
                self._mark_down(exc)
        now = _now()
        with self._lock:
            count, ends_at = self._memory.get(key, (0, 0.0))
        if ends_at <= now:
            return 0, 0
        return count, max(math.ceil(ends_at - now), 1)

    def _prune(self, now: float) -> None:
        """Keep a flood of fresh keys from growing process memory (caller holds the lock)."""
        if len(self._memory) <= _MEMORY_SOFT_LIMIT:
            return
        for stale in [k for k, (_, end) in self._memory.items() if end <= now]:
            del self._memory[stale]
        if len(self._memory) > _MEMORY_HARD_LIMIT:
            oldest = sorted(self._memory.items(), key=lambda item: item[1][1])
            for key, _ in oldest[: len(oldest) - _MEMORY_HARD_LIMIT // 2]:
                del self._memory[key]

    def reset(self) -> None:
        """Tests: forget every counter and every Redis decision."""
        with self._lock:
            self._memory.clear()
        self._client = None
        self._down_until = 0.0
        self._warned = False


counters = _Counters()


# ── the 429 ────────────────────────────────────────────────────────────────────────────────────────────────
def too_many_attempts(retry_after: int) -> HTTPException:
    """429 + Retry-After, in the {code, message, action} shape of every other diagnostic error (the page reads it)."""
    retry_after = max(int(retry_after), 1)
    if retry_after <= 90:
        message = MSG_TOO_MANY_ATTEMPTS
    else:
        message = f"Слишком много попыток. Подождите {math.ceil(retry_after / 60)} мин и попробуйте снова."
    return HTTPException(
        status_code=429,
        detail={"code": "TOO_MANY_ATTEMPTS", "message": message, "action": "retry"},
        headers={"Retry-After": str(retry_after)},
    )


# ── the invite-code policy ─────────────────────────────────────────────────────────────────────────────────
class InviteTicket:
    """One admitted lookup.  ``record(exc)`` classifies the error the lookup ended with."""

    def __init__(self, bucket: str) -> None:
        self._bucket = bucket

    def fail(self) -> None:
        counters.hit(f"diagfail:{FAILS_PER_MINUTE.window}:{self._bucket}", FAILS_PER_MINUTE.window)
        counters.hit(f"diagfail:{FAILS_PER_HOUR.window}:{self._bucket}", FAILS_PER_HOUR.window)

    def record(self, exc: BaseException) -> None:
        """Count the lookup as a guess when it ended in INVITE_INVALID / INVITE_STUDENT_MISMATCH / INVITE_GRADE_MISMATCH."""
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict) and detail.get("code") in GUESS_CODES:
            self.fail()


def admit_invite_attempt(request: Request, invite_code: Optional[str]) -> InviteTicket:
    """Admit (or refuse with 429 + Retry-After) one public lookup by invite code.

    A spent failure budget refuses first, before anything else is counted.
    """
    bucket = client_bucket(request)

    for limit in (FAILS_PER_MINUTE, FAILS_PER_HOUR):
        failures, left = counters.peek(f"diagfail:{limit.window}:{bucket}")
        if failures >= limit.count:
            log.warning("invite_lookup_refused reason=failures bucket=%s", bucket)
            raise too_many_attempts(left)

    uses, left = counters.hit(f"diagcode:{code_key(invite_code or '')}", CODE_PER_HOUR.window)
    if uses > CODE_PER_HOUR.count:
        log.warning("invite_lookup_refused reason=code_volume bucket=%s", bucket)
        raise too_many_attempts(left)

    for limit in (ATTEMPTS_PER_MINUTE, ATTEMPTS_PER_HOUR):
        attempts, left = counters.hit(f"diagtry:{limit.window}:{bucket}", limit.window)
        if attempts > limit.count:
            log.warning("invite_lookup_refused reason=flood bucket=%s", bucket)
            raise too_many_attempts(left)

    return InviteTicket(bucket)
