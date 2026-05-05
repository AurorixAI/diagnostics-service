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
from typing import Optional

import redis

from src.core.config import get_settings
from src.core.redis_client import get_redis_client
from src.domain.session_state import SessionState

log = logging.getLogger(__name__)


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
        """Load and deserialize SessionState. Returns None if expired/missing."""
        try:
            raw = self._redis.get(self._key(session_id))
            if raw is None:
                return None
            data = json.loads(raw)
            # Refresh TTL on every access
            self._redis.expire(self._key(session_id), self._ttl)
            return SessionState.from_dict(data)
        except Exception as exc:
            log.error("Redis load failed for session %s: %s", session_id, exc)
            return None

    def delete(self, session_id: str) -> None:
        """Remove session from Redis on completion."""
        try:
            self._redis.delete(self._key(session_id))
        except Exception as exc:
            log.warning("Redis delete failed for session %s: %s", session_id, exc)
