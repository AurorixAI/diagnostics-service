"""A navigation L4 with no unanswered task must never end the session by itself.

Tree (grade 9):  S1 -> T1 -> P1 -> a, b      T2 -> P3 -> d
                            P2 -> c
Fallback order: other L4 of the same L3, other L3 of the same L2, other L2, and
only when the whole grade pool is exhausted does the selector return None.
"""
from __future__ import annotations

from types import SimpleNamespace as NS
import unittest

from src.domain.navigators.skill_navigator import SkillEntry, SkillNavigator
from src.domain.navigators.subtopic_navigator import SubtopicEntry, SubtopicNavigator
from src.domain.session_service import SessionService
from src.domain.session_state import SessionState

NODES = {
    "S1": NS(id="S1", level="L1", parent_id=None, name_ru="", sequence_order=1),
    "T1": NS(id="T1", level="L2", parent_id="S1", name_ru="", sequence_order=1),
    "T2": NS(id="T2", level="L2", parent_id="S1", name_ru="", sequence_order=2),
    "P1": NS(id="P1", level="L3", parent_id="T1", name_ru="", sequence_order=1),
    "P2": NS(id="P2", level="L3", parent_id="T1", name_ru="", sequence_order=2),
    "P3": NS(id="P3", level="L3", parent_id="T2", name_ru="", sequence_order=1),
    "x": NS(id="x", level="L4", parent_id="P1", name_ru="", sequence_order=1),
    "a": NS(id="a", level="L4", parent_id="P1", name_ru="", sequence_order=2),
    "b": NS(id="b", level="L4", parent_id="P1", name_ru="", sequence_order=3),
    "c": NS(id="c", level="L4", parent_id="P2", name_ru="", sequence_order=1),
    "d": NS(id="d", level="L4", parent_id="P3", name_ru="", sequence_order=1),
}


def children(pid):
    return sorted((n for n in NODES.values() if n.parent_id == pid), key=lambda n: n.sequence_order)


class FakeKnowledge:
    def get_by_id(self, nid):
        return NODES.get(nid)

    def get_children(self, pid):
        return children(pid)

    get_skills_for_subtopic = get_subtopics_for_topic = get_children

    def get_by_level_and_grade(self, level, grade):
        return [n for n in NODES.values() if n.level == level]


class FakeTasks:
    """pool: skill_id -> task ids still in the bank (before per-student exclusion)."""

    def __init__(self, pool):
        self.pool = pool

    def _left(self, skill_id, exclude_ids):
        return [t for t in self.pool.get(skill_id, []) if t not in (exclude_ids or [])]

    def get_task_by_difficulty_target(self, skill_id, target_b, *, exclude_ids=None):
        left = self._left(skill_id, exclude_ids)
        return NS(id=left[0], skill_id=skill_id) if left else None

    def get_tasks_for_skill(self, skill_id, *, exclude_ids=None, limit=10, **kw):
        return [NS(id=t, skill_id=skill_id) for t in self._left(skill_id, exclude_ids)][:limit]


def make_service(pool):
    service = object.__new__(SessionService)
    service.knowledge_repo = FakeKnowledge()
    service.task_repo = FakeTasks(pool)
    service._task_to_out = lambda task, state: NS(task_id=task.id, skill_id=state.current_skill_id,
                                                  topic_id=state.current_topic_id)
    return service


def make_state(**kw):
    st = SessionState(session_id="s", student_id="u", grade_level=9, section_ids=["S1"],
                      current_section_id="S1", current_topic_id="T1", current_subtopic_id="P1")
    for k, v in kw.items():
        setattr(st, k, v)
    return st


class NavigationFallbackTests(unittest.TestCase):
    def test_normal_skill_is_not_replaced(self):
        service = make_service({"a": ["a1"], "b": ["b1"]})
        state = make_state()
        out = service._pick_task_for_navigation(state, "a")
        self.assertEqual((out.task_id, state.current_skill_id), ("a1", "a"))
        self.assertIsNone(state.fallback_nav_context)

    def test_empty_l4_falls_back_to_next_l4_of_same_l3(self):
        service = make_service({"a": [], "b": ["b1"], "c": ["c1"]})
        state = make_state()
        out = service._pick_task_for_navigation(state, "a")
        self.assertEqual(out.task_id, "b1")                 # same L3, next after a
        self.assertEqual(state.current_skill_id, "b")
        self.assertEqual(state.current_subtopic_id, "P1")

    def test_exhausted_l4_for_this_student_falls_back_and_context_is_restored(self):
        service = make_service({"a": ["a1"], "b": ["b1"], "c": ["c1"]})
        state = make_state(used_task_ids=["a1", "b1"], current_topic_id="T1")
        out = service._pick_task_for_navigation(state, "a")  # a and b answered; L3 P1 has x (empty) only
        self.assertEqual(out.task_id, "c1")                 # other L3 (P2) of the same L2
        self.assertEqual((state.current_skill_id, state.current_subtopic_id), ("c", "P2"))
        self.assertIsNotNone(state.fallback_nav_context)
        state.current_topic_id = "T9"                       # something the fallback context changed
        state.current_section_id = "SX"
        service._restore_fallback_context(state)
        self.assertEqual((state.current_topic_id, state.current_subtopic_id, state.current_section_id),
                         ("T1", "P1", "S1"))
        self.assertIsNone(state.fallback_nav_context)

    def test_whole_l2_empty_falls_back_to_another_l2(self):
        service = make_service({"d": ["d1"]})
        state = make_state()
        out = service._pick_task_for_navigation(state, "a")
        self.assertEqual(out.task_id, "d1")
        self.assertEqual((state.current_skill_id, state.current_topic_id), ("d", "T2"))

    def test_all_exhausted_returns_none(self):
        service = make_service({"a": ["a1"], "d": ["d1"]})
        state = make_state(used_task_ids=["a1", "d1"])
        self.assertIsNone(service._pick_task_for_navigation(state, "a"))
        self.assertIsNone(state.fallback_nav_context)

    def test_advance_inside_skill_navigator_no_longer_ends_session(self):
        # skills x < a < b by difficulty; the cursor starts on a; a correct answer moves to b (empty).
        service = make_service({"x": ["x1"], "a": ["a1"], "b": [], "c": ["c1"]})
        skills = [SkillEntry("x", "P1", 1, -1.0), SkillEntry("a", "P1", 2, 0.0), SkillEntry("b", "P1", 3, 1.0)]
        state = make_state(items_answered=5, used_task_ids=["a1"])
        state.current_skill_nav = SkillNavigator.create("P1", skills).to_dict()
        state.current_subtopic_nav = SubtopicNavigator.create(
            "T1", 5, [SubtopicEntry("P1", "T1", 1), SubtopicEntry("P2", "T1", 2)]).to_dict()
        state.phase = "navigation"
        out = service._advance_navigation(state, True)
        self.assertIsNotNone(out)
        self.assertEqual(out.task_id, "x1")                 # nearest other L4 of P1

    def test_first_skill_of_subtopic_empty_does_not_end_session(self):
        service = make_service({"x": [], "a": [], "b": ["b1"]})
        service.task_repo.get_avg_difficulty_for_skills = lambda ids: {"x": 0.0, "a": 0.0, "b": 0.0}
        sub_nav = SubtopicNavigator.create("T1", 5, [SubtopicEntry("P1", "T1", 1)])
        state = make_state()
        out = service._pick_task_from_subtopic(state, sub_nav)
        self.assertEqual(out.task_id, "b1")

    def test_state_roundtrip_keeps_fallback_context(self):
        state = make_state(fallback_nav_context={"section_id": "S1", "topic_id": "T1", "subtopic_id": "P1"})
        self.assertEqual(SessionState.from_dict(state.to_dict()).fallback_nav_context,
                         state.fallback_nav_context)
        legacy = state.to_dict()
        legacy.pop("fallback_nav_context")
        self.assertIsNone(SessionState.from_dict(legacy).fallback_nav_context)


if __name__ == "__main__":
    unittest.main()
