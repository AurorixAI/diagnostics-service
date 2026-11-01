"""
Diagnostic Service — Redis State Manager

Handles serialization of SessionState to/from Redis.
Key pattern : diag:session:{session_id}
Format      : JSON (never Pickle)
TTL         : 7200 seconds (2 hours), refreshed on each access
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Optional

import redis

from src.core.config import get_settings
from src.core.redis_client import get_redis_client
from src.domain.session_state import SessionState
from src.core.exceptions import AnswerInProgressError, StateStoreUnavailableError

log = logging.getLogger(__name__)

# What "Redis is down" looks like: connection refused / reset / timeout / loading / failover.
_UNAVAILABLE = (redis.RedisError, OSError)


class RedisStateManager:

    def __init__(self, client: Optional[redis.Redis] = None) -> None:
        self._redis: redis.Redis = client or get_redis_client()
        self._ttl: int = get_settings().redis_session_ttl

    # ── Key ────────────────────────────────────────────────────────────────

    @staticmethod
    def _key(session_id: str) -> str:
        return f"diag:session:{session_id}"

    # ── Public API ─────────────────────────────────────────────────────────

    def save(self, state: SessionState) -> None:
        """Serialize state to JSON and store in Redis with TTL."""
        try:
            payload = json.dumps(state.to_dict(), ensure_ascii=False)
            self._redis.setex(self._key(state.session_id), self._ttl, payload)
        except Exception as exc:
            log.error("Redis save failed for session %s: %s", state.session_id, exc)
            raise

    def load(self, session_id: str) -> Optional[SessionState]:
        """Load and deserialize SessionState.

        ``None`` = there is nothing usable under the key (missing, evicted, unreadable).  Redis being unreachable
        is a different fact and raises ``StateStoreUnavailableError`` (B-05): "the cache is down" must never read
        as "the attempt is gone".  The caller falls back to the database snapshot.
        """
        try:
            raw = self._redis.get(self._key(session_id))
        except _UNAVAILABLE as exc:
            log.warning("Redis unavailable while loading session %s: %s", session_id, type(exc).__name__)
            raise StateStoreUnavailableError(session_id) from exc
        if raw is None:
            return None
        try:
            state = SessionState.from_dict(json.loads(raw))
        except Exception as exc:
            log.error("Redis state of session %s is unreadable: %s", session_id, type(exc).__name__)
            return None
        try:
            self._redis.expire(self._key(session_id), self._ttl)   # refresh TTL on every access
        except _UNAVAILABLE as exc:
            log.warning("Redis TTL refresh failed for session %s: %s", session_id, type(exc).__name__)
        return state

    def delete(self, session_id: str) -> None:
        """Remove session from Redis on completion."""
        try:
            self._redis.delete(self._key(session_id))
        except Exception as exc:
            log.warning("Redis delete failed for session %s: %s", session_id, exc)

    @contextmanager
    def answer_lock(self, session_id: str):
        """Serialize answer submissions for one session.

        State lives in Redis.  Without a short per-session lock two browser
        requests can read the same state, both update theta, and both append an
        answer row.  The lock covers the full read/evaluate/persist transition.
        """
        lock = self._redis.lock(
            f"{self._key(session_id)}:answer-lock",
            timeout=30,
            blocking_timeout=0,
        )
        acquired = False
        try:
            try:
                acquired = bool(lock.acquire(blocking=False))
            except _UNAVAILABLE as exc:
                # B-05: the lock is an optimisation.  The final serialisation barrier is the row lock of the
                # session in PostgreSQL (FOR UPDATE in ``_submit_answer_locked``), so a Redis blip must not stop
                # the student: go on without it.
                log.warning("Redis answer lock unavailable for %s: %s; relying on the database row lock",
                            session_id, type(exc).__name__)
                yield
                return
            if not acquired:
                raise AnswerInProgressError(session_id)
            yield
        finally:
            if acquired:
                try:
                    lock.release()
                except Exception as exc:
                    log.warning("Redis answer lock release failed for %s: %s", session_id, exc)
