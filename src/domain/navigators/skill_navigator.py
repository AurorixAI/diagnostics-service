"""
Diagnostic Service — SkillNavigator (L4 Binary Search) + DeepScanState

SkillNavigator:
  Binary search over atomic skills (L4) within one subtopic.
  Skills are sorted by irt_difficulty (easiest → hardest).
  Tracks failing_skill_id for DeepScan trigger.

DeepScanState:
  Prerequisite traversal for a failing skill.
  Keeps a queue of prerequisite skill_ids to test.
  Max items: deep_scan_max_items (default 6).
  Stops when: queue empty, max reached, or student answers correctly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


# ── SkillNavigator ────────────────────────────────────────────────────────

@dataclass
class SkillEntry:
    skill_id: str
    subtopic_id: str
    sequence_order: int
    irt_difficulty: float = 0.0
    name_ru: str = ""


@dataclass
class SkillNavigatorState:
    subtopic_id: str
    skills: List[SkillEntry]          # sorted by irt_difficulty
    cursor: int
    lo: int
    hi: int
    tested: List[str] = field(default_factory=list)
    results: Dict[str, bool] = field(default_factory=dict)
    exhausted: bool = False
    failing_skill_id: Optional[str] = None

    @property
    def current_skill(self) -> Optional[SkillEntry]:
        if self.exhausted or not self.skills:
            return None
        if 0 <= self.cursor < len(self.skills):
            return self.skills[self.cursor]
        return None


class SkillNavigator:
    """Binary search over L4 skills within one subtopic."""

    def __init__(self, state: SkillNavigatorState) -> None:
        self.state = state

    @classmethod
    def create(cls, subtopic_id: str, skills: List[SkillEntry]) -> "SkillNavigator":
        sorted_skills = sorted(skills, key=lambda s: s.irt_difficulty)
        n = len(sorted_skills)
        return cls(
            SkillNavigatorState(
                subtopic_id=subtopic_id,
                skills=sorted_skills,
                cursor=n // 2,
                lo=0,
                hi=n - 1,
            )
        )

    def peek_current(self) -> Optional[SkillEntry]:
        return self.state.current_skill

    def is_exhausted(self) -> bool:
        return self.state.exhausted

    def get_failing_skill(self) -> Optional[str]:
        return self.state.failing_skill_id

    def subtopic_score(self) -> float:
        """Fraction of correct answers across all tested skills [0.0–1.0].
        Returns 0.0 if no skills were tested yet."""
        results = self.state.results
        if not results:
            return 0.0
        return round(sum(1 for v in results.values() if v) / len(results), 4)

    def move(self, correct: bool) -> Optional[SkillEntry]:
        s = self.state
        current = s.current_skill
        if current is None:
            return None

        s.tested.append(current.skill_id)
        s.results[current.skill_id] = correct

        if correct:
            s.lo = s.cursor + 1
        else:
            s.failing_skill_id = current.skill_id
            s.hi = s.cursor - 1

        if s.lo > s.hi:
            s.exhausted = True
            return None

        s.cursor = (s.lo + s.hi) // 2
        return s.current_skill

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        s = self.state
        return {
            "subtopic_id": s.subtopic_id,
            "skills": [
                {
                    "skill_id": sk.skill_id,
                    "subtopic_id": sk.subtopic_id,
                    "sequence_order": sk.sequence_order,
                    "irt_difficulty": sk.irt_difficulty,
                    "name_ru": sk.name_ru,
                }
                for sk in s.skills
            ],
            "cursor": s.cursor,
            "lo": s.lo,
            "hi": s.hi,
            "tested": s.tested,
            "results": s.results,
            "exhausted": s.exhausted,
            "failing_skill_id": s.failing_skill_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillNavigator":
        skills = [SkillEntry(**sk) for sk in data["skills"]]
        state = SkillNavigatorState(
            subtopic_id=data["subtopic_id"],
            skills=skills,
            cursor=data["cursor"],
            lo=data["lo"],
            hi=data["hi"],
            tested=data["tested"],
            results=data["results"],
            exhausted=data["exhausted"],
            failing_skill_id=data.get("failing_skill_id"),
        )
        return cls(state)


# ── DeepScanState ─────────────────────────────────────────────────────────

@dataclass
class DeepScanState:
    """
    State for prerequisite graph traversal when a skill fails.

    Queue holds prerequisite skill_ids to test next.
    Gaps holds confirmed gap skill_ids.
    Stops when: queue empty | items_used >= max_items | correct answer seen.
    """
    origin_skill_id: str
    queue: List[str] = field(default_factory=list)    # next prereqs to test
    tested: List[str] = field(default_factory=list)   # already tested
    gaps: List[str] = field(default_factory=list)     # confirmed gaps
    current_skill_id: Optional[str] = None
    max_items: int = 6
    items_used: int = 0
    completed: bool = False

    def to_dict(self) -> dict:
        return {
            "origin_skill_id": self.origin_skill_id,
            "queue": self.queue,
            "tested": self.tested,
            "gaps": self.gaps,
            "current_skill_id": self.current_skill_id,
            "max_items": self.max_items,
            "items_used": self.items_used,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeepScanState":
        return cls(
            origin_skill_id=data["origin_skill_id"],
            queue=data["queue"],
            tested=data["tested"],
            gaps=data["gaps"],
            current_skill_id=data.get("current_skill_id"),
            max_items=data.get("max_items", 6),
            items_used=data.get("items_used", 0),
            completed=data.get("completed", False),
        )
