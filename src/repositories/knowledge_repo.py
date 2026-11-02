"""Diagnostic Service — Read-only repositories for knowledge / task data.

Previously these classes held a SQLAlchemy Session and queried content-db
directly.  Now they call the content-service HTTP read API so that each
service owns only its own database.

The public method signatures are unchanged — session_service.py does not
need to know about the transport switch.
"""
from __future__ import annotations

import json
import logging
import math
import random
import threading
import time
import types
from typing import Any, List, Optional

from src.clients import content_client
from src.core.config import get_settings

BASE = "/api/v1/content"

log = logging.getLogger(__name__)

# content-service GET /tasks validates target_b with Query(ge=-4, le=4); anything outside
# is a 422 there, so the transport layer clamps instead of letting a caller break a session.
TARGET_B_MIN, TARGET_B_MAX = -4.0, 4.0

# Maximum additional IRT b-param distance allowed beyond the closest match.
# Keeps pool tight: tasks in pool differ by at most 0.1 from the best-matching task.
# Wider values (e.g. 0.5) incorrectly mix tasks of very different difficulty levels.
_IRT_TOLERANCE = 0.1

# P-02: skills probed per HTTP call and the row limit of that call (content-service allows up to 200).
PROBE_BATCH = 8
PROBE_LIMIT = 200


def _normalise_target_b(target_b: float, skill_id: str) -> float:
    """A target the content API accepts: NaN -> 0.0 (warning), +-inf and out-of-range values
    -> the nearest bound of [TARGET_B_MIN, TARGET_B_MAX].  A target-less request would not
    be neutral: content-service then orders by irt_difficulty ASC (the easiest items), and
    the clamp alone would turn NaN into the lowest bound."""
    if math.isnan(target_b):
        log.warning("target_b is NaN for skill %s, using the neutral target 0.0", skill_id)
        return 0.0
    return min(TARGET_B_MAX, max(TARGET_B_MIN, target_b))


def _ns(d: dict) -> types.SimpleNamespace:
    """Wrap a dict so attribute access works the same as on ORM objects."""
    return types.SimpleNamespace(**d)


# ── process cache of the knowledge hierarchy (WC-B P-01 / P-03) ────────────────────────────────────────────────────────
# One answer of a student made 1-4 HTTP calls to content-service for the SAME few nodes (the skill, its subtopic, its topic, the L4 list of the
# grade), a teacher's report 3 per answer twice over (~240 calls).  The hierarchy changes only with a content release, so a node read a minute ago
# is as good as one read now: raw answers are kept for ``knowledge_cache_ttl`` seconds (10 min, 0 = off).
#   * what is cached is the JSON TEXT; every read parses a fresh object, so nobody can change what the next caller gets;
#   * a 404 and an error are never cached, and a failed refresh drops the entry it was refreshing (no stale answer after an error);
#   * TASKS are not cached anywhere: the choice of a task follows the live bank.
_cache: dict[tuple, tuple[float, str]] = {}
_cache_lock = threading.Lock()
_CACHE_MAX_ENTRIES = 20_000


def _now() -> float:
    return time.monotonic()


def clear_hierarchy_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _hierarchy_json(key: tuple, path: str, *, allow_404: bool = False, **kwargs: Any) -> Any:
    """The decoded JSON of a content-service GET, from the cache while it is fresh.  ``None`` only for an allowed 404."""
    ttl = get_settings().knowledge_cache_ttl
    if ttl > 0:
        with _cache_lock:
            hit = _cache.get(key)
        if hit is not None and hit[0] > _now():
            return json.loads(hit[1])
    try:
        resp = content_client.get(path, **kwargs)
        if allow_404 and resp.status_code == 404:
            data = None
        else:
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        with _cache_lock:
            _cache.pop(key, None)  # a failed refresh must not leave the old answer to be served again
        raise
    if data is not None and ttl > 0:
        with _cache_lock:
            if len(_cache) >= _CACHE_MAX_ENTRIES:
                now = _now()
                for stale in [k for k, (expires, _raw) in _cache.items() if expires <= now]:
                    del _cache[stale]
                if len(_cache) >= _CACHE_MAX_ENTRIES:
                    _cache.clear()
            _cache[key] = (_now() + ttl, json.dumps(data))
    return data


class KnowledgeRepository:
    """Read knowledge_hierarchy via content-service API."""

    def get_by_id(self, node_id: str) -> Optional[types.SimpleNamespace]:
        data = _hierarchy_json(("id", node_id), f"{BASE}/skills/{node_id}", allow_404=True)
        return None if data is None else _ns(data)

    def get_children(self, parent_id: str) -> List[types.SimpleNamespace]:
        data = _hierarchy_json(("children", parent_id), f"{BASE}/skills/{parent_id}/children")
        # The API orders by sequence_order only; equal values come back in an
        # unspecified order, which made "which child" depend on the database.
        return sorted(
            (_ns(r) for r in data),
            key=lambda n: (int(getattr(n, "sequence_order", 0) or 0), str(n.id)),
        )

    def get_by_level_and_grade(self, level: str, grade: int) -> List[types.SimpleNamespace]:
        data = _hierarchy_json(("level_grade", level, grade), f"{BASE}/skills", params={"level": level, "grade": grade})
        return [_ns(r) for r in data]

    def get_subtopics_for_topic(self, topic_id: str) -> List[types.SimpleNamespace]:
        """All L3 subtopics for an L2 topic (= direct children)."""
        return self.get_children(topic_id)

    def get_skills_for_subtopic(self, subtopic_id: str) -> List[types.SimpleNamespace]:
        """All L4 atomic skills for an L3 subtopic (= direct children)."""
        return self.get_children(subtopic_id)


class SkillPrerequisiteRepository:
    """Read skill_prerequisites via content-service API."""

    def get_prerequisites(
        self, skill_id: str, *, hard_only: bool = False
    ) -> List[types.SimpleNamespace]:
        data = _hierarchy_json(
            ("prerequisites", skill_id, bool(hard_only)), f"{BASE}/skills/{skill_id}/prerequisites", params={"hard_only": hard_only},
        )
        # Stable order for the Deep Scan: most critical edge first, then the
        # heavier one, then id (the API only sorts by weight, ties unspecified).
        return sorted(
            (_ns(r) for r in data),
            key=lambda p: (
                -int(getattr(p, "criticality", 5) or 5),
                -float(getattr(p, "weight", 1.0) or 1.0),
                str(p.prerequisite_id),
            ),
        )


class TaskRepository:
    """Read tasks_master via content-service API."""

    def get_by_id(self, task_id: str) -> Optional[types.SimpleNamespace]:
        resp = content_client.get_task(task_id)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return _ns(resp.json())

    def get_tasks_for_skill(
        self,
        skill_id: str,
        *,
        difficulty: Optional[str] = None,
        exclude_ids: Optional[List[str]] = None,
        limit: int = 10,
        target_b: Optional[float] = None,
    ) -> List[types.SimpleNamespace]:
        params: dict = {"skill_id": skill_id, "limit": limit}
        if difficulty:
            params["difficulty"] = difficulty
        if target_b is not None:
            params["target_b"] = _normalise_target_b(target_b, skill_id)
        if exclude_ids:
            params["exclude_ids"] = exclude_ids
        resp = content_client.get(f"{BASE}/tasks", params=params)
        resp.raise_for_status()
        return [_ns(r) for r in resp.json()]

    def get_task_by_difficulty_target(
        self,
        skill_id: str,
        target_b: Optional[float],
        *,
        exclude_ids: Optional[List[str]] = None,
    ) -> Optional[types.SimpleNamespace]:
        """Fetch up to 20 candidates nearest target_b and randomly pick one from those
        closest to target_b (within _IRT_TOLERANCE band).

        Using random.choice instead of min() ensures that students with the same
        theta receive different task variants from the pool — critical for fairness
        when many tasks share the same irt_difficulty value.

        ``target_b`` is normalised first (``_normalise_target_b``): NaN -> 0.0 with a warning,
        +-inf / out-of-range -> +-4, so every caller is safe.  Only ``target_b=None`` sends no
        target: one of the candidates content-service returns without a target (it orders them
        by irt_difficulty ASC, i.e. the easiest) is picked at random.
        """
        if target_b is None:
            candidates = self.get_tasks_for_skill(
                skill_id, exclude_ids=exclude_ids, limit=20, target_b=None
            )
            return random.choice(candidates) if candidates else None
        target_b = _normalise_target_b(target_b, skill_id)   # as sent to the API
        candidates = self.get_tasks_for_skill(
            skill_id, exclude_ids=exclude_ids, limit=20, target_b=target_b
        )
        if not candidates:
            return None
        return self._pick_near_target(candidates, target_b)

    @staticmethod
    def _pick_near_target(candidates: List[types.SimpleNamespace], target_b: float) -> types.SimpleNamespace:
        """One of the candidates nearest to ``target_b`` (within ``_IRT_TOLERANCE`` of the best), chosen at random."""
        # Find the closest difficulty to target
        best_dist = min(abs(float(getattr(t, "irt_difficulty", 0) or 0) - target_b) for t in candidates)
        # Build pool of all candidates within tolerance of the best
        pool = [
            t for t in candidates
            if abs(float(getattr(t, "irt_difficulty", 0) or 0) - target_b) <= best_dist + _IRT_TOLERANCE
        ]
        return random.choice(pool)

    def get_tasks_for_skills(
        self,
        skill_ids: List[str],
        *,
        target_b: float,
        exclude_ids: Optional[List[str]] = None,
        limit: int = PROBE_LIMIT,
    ) -> List[types.SimpleNamespace]:
        """Tasks of SEVERAL skills in one call (content-service ``skill_ids``): nearest to ``target_b`` first across all of them, then LIMIT."""
        params: dict = {"skill_ids": list(skill_ids), "limit": limit, "target_b": _normalise_target_b(target_b, ",".join(skill_ids))}
        if exclude_ids:
            params["exclude_ids"] = exclude_ids
        resp = content_client.get(f"{BASE}/tasks", params=params)
        resp.raise_for_status()
        return [_ns(r) for r in resp.json()]

    def pick_task_by_difficulty_target(
        self,
        ordered_skill_ids: List[str],
        target_b: float,
        *,
        exclude_ids: Optional[List[str]] = None,
        batch: int = PROBE_BATCH,
        limit: int = PROBE_LIMIT,
    ) -> tuple[Optional[str], Optional[types.SimpleNamespace], set]:
        """(skill_id, task, skills known to have no free task): the FIRST skill of the list that has a free task, and a task of it near ``target_b``.

        The answer is the one a skill-by-skill scan gives (``get_task_by_difficulty_target`` for each skill in turn, the first hit wins): the
        first skill alone (as before), the skills after an exhausted first one at one HTTP call per ``batch`` skills instead of one per skill (P-02).  The batch call returns the tasks of its skills nearest to the target
        across all of them, cut at ``limit``; read it like this:
          * fewer rows than ``limit`` - the window is complete: a skill with no row has no free task;
          * ``limit`` rows - the window is cut: a skill with rows has its nearest tasks in it (a prefix of its own order), a skill WITHOUT rows may
            still have farther ones - that skill is asked alone, exactly as the scan would, and so is a skill with fewer than 20 rows in the window
            (its 20 nearest are not all there).
        """
        empty: set = set()
        if not ordered_skill_ids:
            return None, None, empty
        # The ordinary turn is the old one: ONE skill, the usual window of 20 rows.  Only when the first skill has no free task do the rest go in
        # batches - an ordinary turn never pulls the rows of 8 skills (R3 B4).
        first = ordered_skill_ids[0]
        task = self.get_task_by_difficulty_target(first, target_b, exclude_ids=exclude_ids)
        if task is not None:
            return first, task, empty
        empty.add(first)
        rest = ordered_skill_ids[1:]
        for start in range(0, len(rest), batch):
            chunk = rest[start:start + batch]
            rows = self.get_tasks_for_skills(chunk, target_b=target_b, exclude_ids=exclude_ids, limit=limit)
            cut = len(rows) >= limit
            by_skill: dict[str, list] = {}
            for row in rows:
                by_skill.setdefault(row.skill_id, []).append(row)
            for skill_id in chunk:
                own = by_skill.get(skill_id, [])
                if own and (len(own) >= 20 or not cut):
                    return skill_id, self._pick_near_target(own[:20], _normalise_target_b(target_b, skill_id)), empty
                if own or cut:
                    task = self.get_task_by_difficulty_target(skill_id, target_b, exclude_ids=exclude_ids)
                    if task is not None:
                        return skill_id, task, empty
                empty.add(skill_id)
        return None, None, empty

    def get_avg_difficulty_for_skills(
        self, skill_ids: List[str]
    ) -> dict[str, float]:
        """Returns {skill_id: avg_irt_difficulty} for the given skill list."""
        if not skill_ids:
            return {}
        resp = content_client.post(
            f"{BASE}/tasks/avg-difficulty",
            json={"skill_ids": skill_ids},
        )
        resp.raise_for_status()
        return resp.json()
