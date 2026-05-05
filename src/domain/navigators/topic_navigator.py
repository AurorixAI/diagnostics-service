"""
Diagnostic Service — TopicNavigator (L2 Binary Search)

Implements horizontal binary search across topics within one L1 section.
Each L1 section (e.g. G5_NAT, G5_FRAC) is navigated independently.

Binary search strategy:
  - cursor starts at len(topics) // 2
  - correct answer → move UP (lo = cursor + 1)
  - wrong answer   → move DOWN (hi = cursor − 1)
  - next cursor = (lo + hi) // 2
  - exhausted when lo > hi
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TopicEntry:
    topic_id: str
    section_id: str   # L1 parent id
    position: int     # 0-indexed within section
    importance: int   # 1–10
    name_ru: str = ""


@dataclass
class TopicNavigatorState:
    section_id: str
    topics: List[TopicEntry]          # sorted by position
    cursor: int
    lo: int
    hi: int
    tested: List[str] = field(default_factory=list)    # topic_ids tested so far
    results: Dict[str, bool] = field(default_factory=dict)  # topic_id → correct
    exhausted: bool = False

    @property
    def current_topic(self) -> Optional[TopicEntry]:
        if self.exhausted or not self.topics:
            return None
        if 0 <= self.cursor < len(self.topics):
            return self.topics[self.cursor]
        return None


class TopicNavigator:
    """Binary search over L2 topics within one L1 section."""

    def __init__(self, state: TopicNavigatorState) -> None:
        self.state = state

    @classmethod
    def create(cls, section_id: str, topics: List[TopicEntry]) -> "TopicNavigator":
        sorted_topics = sorted(topics, key=lambda t: t.position)
        n = len(sorted_topics)
        return cls(
            TopicNavigatorState(
                section_id=section_id,
                topics=sorted_topics,
                cursor=n // 2,
                lo=0,
                hi=n - 1,
            )
        )

    def peek_current(self) -> Optional[TopicEntry]:
        return self.state.current_topic

    def is_exhausted(self) -> bool:
        return self.state.exhausted

    def move(self, correct: bool) -> Optional[TopicEntry]:
        """
        Register result for current topic and advance cursor.
        Returns the next TopicEntry, or None if section is exhausted.
        """
        s = self.state
        current = s.current_topic
        if current is None:
            return None

        s.tested.append(current.topic_id)
        s.results[current.topic_id] = correct

        if correct:
            s.lo = s.cursor + 1   # move up to harder topics
        else:
            s.hi = s.cursor - 1   # move down to easier topics

        if s.lo > s.hi:
            s.exhausted = True
            return None

        s.cursor = (s.lo + s.hi) // 2
        return s.current_topic

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        s = self.state
        return {
            "section_id": s.section_id,
            "topics": [
                {
                    "topic_id": t.topic_id,
                    "section_id": t.section_id,
                    "position": t.position,
                    "importance": t.importance,
                    "name_ru": t.name_ru,
                }
                for t in s.topics
            ],
            "cursor": s.cursor,
            "lo": s.lo,
            "hi": s.hi,
            "tested": s.tested,
            "results": s.results,
            "exhausted": s.exhausted,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TopicNavigator":
        topics = [TopicEntry(**t) for t in data["topics"]]
        state = TopicNavigatorState(
            section_id=data["section_id"],
            topics=topics,
            cursor=data["cursor"],
            lo=data["lo"],
            hi=data["hi"],
            tested=data["tested"],
            results=data["results"],
            exhausted=data["exhausted"],
        )
        return cls(state)
