"""Diagnostic Service — Read-only repositories for knowledge / task data.

Previously these classes held a SQLAlchemy Session and queried content-db
directly.  Now they call the content-service HTTP read API so that each
service owns only its own database.

The public method signatures are unchanged — session_service.py does not
need to know about the transport switch.
"""
from __future__ import annotations

import random
import types
from typing import List, Optional

from src.clients import content_client

BASE = "/api/v1/content"

# Maximum additional IRT b-param distance allowed beyond the closest match.
# Keeps pool tight: tasks in pool differ by at most 0.1 from the best-matching task.
# Wider values (e.g. 0.5) incorrectly mix tasks of very different difficulty levels.
_IRT_TOLERANCE = 0.1


def _ns(d: dict) -> types.SimpleNamespace:
    """Wrap a dict so attribute access works the same as on ORM objects."""
    return types.SimpleNamespace(**d)


class KnowledgeRepository:
    """Read knowledge_hierarchy via content-service API."""

    def get_by_id(self, node_id: str) -> Optional[types.SimpleNamespace]:
        resp = content_client.get(f"{BASE}/skills/{node_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return _ns(resp.json())

    def get_children(self, parent_id: str) -> List[types.SimpleNamespace]:
        resp = content_client.get(f"{BASE}/skills/{parent_id}/children")
        resp.raise_for_status()
        return [_ns(r) for r in resp.json()]

    def get_by_level_and_grade(self, level: str, grade: int) -> List[types.SimpleNamespace]:
        resp = content_client.get(
            f"{BASE}/skills",
            params={"level": level, "grade": grade},
        )
        resp.raise_for_status()
        return [_ns(r) for r in resp.json()]

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
        resp = content_client.get(
            f"{BASE}/skills/{skill_id}/prerequisites",
            params={"hard_only": hard_only},
        )
        resp.raise_for_status()
        return [_ns(r) for r in resp.json()]


class TaskRepository:
    """Read tasks_master via content-service API."""

    def get_by_id(self, task_id: str) -> Optional[types.SimpleNamespace]:
        resp = content_client.get(f"{BASE}/tasks/{task_id}")
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
    ) -> List[types.SimpleNamespace]:
        params: dict = {"skill_id": skill_id, "limit": limit}
        if difficulty:
            params["difficulty"] = difficulty
        if exclude_ids:
            params["exclude_ids"] = exclude_ids
        resp = content_client.get(f"{BASE}/tasks", params=params)
        resp.raise_for_status()
        return [_ns(r) for r in resp.json()]

    def get_task_by_difficulty_target(
        self,
        skill_id: str,
        target_b: float,
        *,
        exclude_ids: Optional[List[str]] = None,
    ) -> Optional[types.SimpleNamespace]:
        """Fetch up to 20 IRT-sorted candidates and randomly pick one from those
        closest to target_b (within _IRT_TOLERANCE band).

        Using random.choice instead of min() ensures that students with the same
        theta receive different task variants from the pool — critical for fairness
        when many tasks share the same irt_difficulty value.
        """
        candidates = self.get_tasks_for_skill(
            skill_id, exclude_ids=exclude_ids, limit=20
        )
        if not candidates:
            return None

        # Find the closest difficulty to target
        best_dist = min(abs(float(getattr(t, "irt_difficulty", 0) or 0) - target_b) for t in candidates)
        # Build pool of all candidates within tolerance of the best
        pool = [
            t for t in candidates
            if abs(float(getattr(t, "irt_difficulty", 0) or 0) - target_b) <= best_dist + _IRT_TOLERANCE
        ]
        return random.choice(pool)

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

