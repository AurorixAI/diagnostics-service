"""
Diagnostic Service — SubtopicNavigator (L3 Binary Search)

Within an L2 topic, navigates L3 subtopics using binary search.
Tracks the last-failed subtopic (boundary_subtopic_id) so the
SessionService can decide whether to trigger a deep scan.

Deep scan is triggered when:
  importance >= deep_scan_importance_threshold (default 8)
  AND a subtopic was failed (boundary_subtopic_id is set)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SubtopicEntry:
    subtopic_id: str
    topic_id: str
    position: int       # sequence_order from knowledge_hierarchy
    importance: int = 5  # L3 paragraph importance (1-10)
    name_ru: str = ""


@dataclass
class SubtopicNavigatorState:
    topic_id: str
    topic_importance: int
    subtopics: List[SubtopicEntry]
    cursor: int
    lo: int
    hi: int
    tested: List[str] = field(default_factory=list)
    results: Dict[str, bool] = field(default_factory=dict)
    scores: Dict[str, float] = field(default_factory=dict)  # skill-score per subtopic [0.0–1.0]
    exhausted: bool = False
    boundary_subtopic_id: Optional[str] = None  # last failed subtopic

    @property
    def current_subtopic(self) -> Optional[SubtopicEntry]:
        if self.exhausted or not self.subtopics:
            return None
        if 0 <= self.cursor < len(self.subtopics):
            return self.subtopics[self.cursor]
        return None


class SubtopicNavigator:
    """Binary search over L3 subtopics within one L2 topic."""

    def __init__(self, state: SubtopicNavigatorState) -> None:
        self.state = state

    @classmethod
    def create(
        cls, topic_id: str, importance: int, subtopics: List[SubtopicEntry]
    ) -> "SubtopicNavigator":
        sorted_subs = sorted(subtopics, key=lambda s: s.position)
        n = len(sorted_subs)
        return cls(
            SubtopicNavigatorState(
                topic_id=topic_id,
                topic_importance=importance,
                subtopics=sorted_subs,
                cursor=n // 2,
                lo=0,
                hi=n - 1,
            )
        )

    def peek_current(self) -> Optional[SubtopicEntry]:
        return self.state.current_subtopic

    def is_exhausted(self) -> bool:
        return self.state.exhausted

    def needs_deep_scan(self, threshold: int) -> bool:
        """True if the failed subtopic itself is important enough to warrant deep scan."""
        if self.state.boundary_subtopic_id is None:
            return False
        for sub in self.state.subtopics:
            if sub.subtopic_id == self.state.boundary_subtopic_id:
                return sub.importance >= threshold
        return False

    def record_score(self, score: float) -> None:
        """Store the skill-aggregated score [0.0–1.0] for the current subtopic.
        Call this BEFORE move() so the current subtopic is still set."""
        current = self.state.current_subtopic
        if current is not None:
            self.state.scores[current.subtopic_id] = round(score, 4)

    def topic_score(self) -> float:
        """Mean of all recorded subtopic scores. Returns 0.0 if nothing scored yet."""
        s = self.state.scores
        if not s:
            return 0.0
        return round(sum(s.values()) / len(s), 4)

    def move(self, correct: bool) -> Optional[SubtopicEntry]:
        """
        Register result and advance. Returns next SubtopicEntry or None.
        """
        s = self.state
        current = s.current_subtopic
        if current is None:
            return None

        s.tested.append(current.subtopic_id)
        s.results[current.subtopic_id] = correct

        if correct:
            s.lo = s.cursor + 1
        else:
            s.boundary_subtopic_id = current.subtopic_id
            s.hi = s.cursor - 1

        if s.lo > s.hi:
            s.exhausted = True
            return None

        s.cursor = (s.lo + s.hi) // 2
        return s.current_subtopic

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        s = self.state
        return {
            "topic_id": s.topic_id,
            "topic_importance": s.topic_importance,
            "subtopics": [
                {
                    "subtopic_id": st.subtopic_id,
                    "topic_id": st.topic_id,
                    "position": st.position,
                    "importance": st.importance,
                    "name_ru": st.name_ru,
                }
                for st in s.subtopics
            ],
            "cursor": s.cursor,
            "lo": s.lo,
            "hi": s.hi,
            "tested": s.tested,
            "results": s.results,
            "scores": s.scores,
            "exhausted": s.exhausted,
            "boundary_subtopic_id": s.boundary_subtopic_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubtopicNavigator":
        subtopics = [SubtopicEntry(**st) for st in data["subtopics"]]
        state = SubtopicNavigatorState(
            topic_id=data["topic_id"],
            topic_importance=data["topic_importance"],
            subtopics=subtopics,
            cursor=data["cursor"],
            lo=data["lo"],
            hi=data["hi"],
            tested=data["tested"],
            results=data["results"],
            scores=data.get("scores", {}),
            exhausted=data["exhausted"],
            boundary_subtopic_id=data.get("boundary_subtopic_id"),
        )
        return cls(state)
