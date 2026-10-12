"""Policy tests for precise, bounded adaptive diagnostics."""
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.core.exceptions import TaskOutOfSequenceError
from src.domain import session_service as session_service_module
from src.domain.alpha_engine import IRTParams, ThetaState, update_theta
from src.domain.session_service import SessionService
from src.domain.session_state import SessionState


def make_state(**overrides) -> SessionState:
    state = SessionState(
        session_id="session-1",
        student_id="student-1",
        grade_level=10,
        section_ids=["l1-a", "l1-b", "l1-c"],
        current_task_id="task-current",
    )
    for name, value in overrides.items():
        setattr(state, name, value)
    return state


class AdaptiveDiagnosticPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        adaptive_settings = SimpleNamespace(
            warmup_items=5,
            min_items=12,
            max_items=42,
            se_threshold=0.30,
            classification_min_items=20,
            classification_se_threshold=0.40,
            classification_confidence_threshold=0.90,
            min_section_coverage=5,
            deep_scan_max_items=4,
            deep_scan_importance_threshold=8,
            deep_scan_confirm_probes=1,
            deep_scan_probe_difficulty_offset=0.0,
            deep_scan_trigger_mode="importance",
            mastery_threshold=0.6,
        )
        self.settings_patch = patch.object(
            session_service_module, "settings", adaptive_settings
        )
        self.settings_patch.start()

    def tearDown(self) -> None:
        self.settings_patch.stop()

    def test_precision_requires_minimum_items_and_section_coverage(self) -> None:
        service = object.__new__(SessionService)
        state = make_state(items_answered=11, covered_section_ids=["l1-a", "l1-b", "l1-c"])
        state.theta = ThetaState(se=0.20)
        self.assertFalse(service._should_stop(state))

        state.items_answered = 12
        state.covered_section_ids = ["l1-a", "l1-b"]
        self.assertFalse(service._should_stop(state))

        state.covered_section_ids.append("l1-c")
        self.assertTrue(service._should_stop(state))
        self.assertEqual(state.stop_reason, "precision_reached")

    def test_hard_limit_wins_and_records_an_incomplete_deep_scan(self) -> None:
        service = object.__new__(SessionService)
        state = make_state(items_answered=42, is_in_deep_scan=True)
        state.theta = ThetaState(se=0.10)

        self.assertTrue(service._should_stop(state))
        self.assertEqual(state.stop_reason, "max_items_reached")
        self.assertTrue(state.deep_scan_incomplete)

    def test_twenty_five_answers_do_not_impose_a_limit(self) -> None:
        service = object.__new__(SessionService)
        state = make_state(items_answered=25, covered_section_ids=["l1-a", "l1-b", "l1-c"])
        state.theta = ThetaState(se=0.45)
        self.assertFalse(service._should_stop(state))
        self.assertIsNone(state.stop_reason)

    def test_other_grade_sections_do_not_replace_baseline_coverage(self) -> None:
        service = object.__new__(SessionService)
        state = make_state(items_answered=20, covered_section_ids=["l1-a", "other-grade-b", "other-grade-c"])
        state.theta = ThetaState(se=0.20)
        self.assertFalse(service._should_stop(state))
        self.assertIsNone(state.stop_reason)

    def test_warmup_spans_available_sections(self) -> None:
        state = make_state(section_ids=["l1-a", "l1-b", "l1-c"])
        self.assertEqual(SessionService._warmup_target_count(state), 3)

    def test_stale_or_arbitrary_task_cannot_be_scored(self) -> None:
        state = make_state(current_task_id="task-current")
        with self.assertRaises(TaskOutOfSequenceError):
            SessionService._ensure_current_task(state, "another-task")

    def test_task_preflight_does_not_consume_one_time_invite(self) -> None:
        """A temporary empty/broken task bank must leave the invite restartable."""
        service = object.__new__(SessionService)
        persisted = []
        service.session_repo = SimpleNamespace(
            get_by_invite_code=lambda _code: None,
            add=lambda session: persisted.append(session),
        )
        service.db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
        service.redis = SimpleNamespace(save=lambda _state: None)
        service._build_topic_grid = lambda _state: None

        from src.core.exceptions import GradeNotConfiguredError

        with self.assertRaises(GradeNotConfiguredError):
            service.create_session(
                student_id="student-1",
                grade_level=10,
                invite_code="ONE-TIME-CODE",
            )

        self.assertEqual(persisted, [])

    def test_redis_initialisation_failure_releases_one_time_invite(self) -> None:
        """A session without resumable state must not strand an invite."""
        service = object.__new__(SessionService)
        persisted = []
        deleted = []
        service.session_repo = SimpleNamespace(
            get_by_invite_code=lambda _code: None,
            add=lambda session: persisted.append(session),
        )
        service.db = SimpleNamespace(
            commit=lambda: None,
            rollback=lambda: None,
            delete=lambda session: deleted.append(session),
        )

        def redis_save(_state) -> None:
            raise RuntimeError("redis unavailable")

        service.redis = SimpleNamespace(save=redis_save)
        service._build_topic_grid = lambda state: state.section_ids.append("l1-a")
        service._pick_warmup_task = lambda _state: SimpleNamespace(id="first-task")

        with self.assertRaisesRegex(RuntimeError, "redis unavailable"):
            service.create_session(
                student_id="student-1",
                grade_level=10,
                invite_code="ONE-TIME-CODE",
            )

        self.assertEqual(len(persisted), 1)
        self.assertEqual(deleted, persisted)

    def test_task_pool_exhaustion_never_reuses_an_answered_task(self) -> None:
        class EmptyTaskRepo:
            def __init__(self):
                self.fallback_exclude_ids = None

            def get_task_by_difficulty_target(self, *args, **kwargs):
                return None

            def get_tasks_for_skill(self, _skill_id, *, exclude_ids, limit):
                self.fallback_exclude_ids = exclude_ids
                return []

        service = object.__new__(SessionService)
        service.task_repo = EmptyTaskRepo()
        state = make_state(used_task_ids=["already-shown"])

        self.assertIsNone(service._pick_task_for_skill(state, "skill-1"))
        self.assertEqual(service.task_repo.fallback_exclude_ids, ["already-shown"])

    def test_current_irt_engine_reaches_target_at_42_not_40(self) -> None:
        def simulate(question_count: int) -> float:
            state = ThetaState()
            for index in range(question_count):
                state = update_theta(
                    state,
                    IRTParams(a=1.0, b=state.theta, c=0.0),
                    float(index % 2),
                )
            return state.se

        self.assertGreater(simulate(40), 0.30)
        self.assertLessEqual(simulate(42), 0.30)

    def test_state_round_trip_preserves_audit_fields(self) -> None:
        state = make_state(
            current_section_id="l1-a",
            covered_section_ids=["l1-a", "l1-b"],
            deep_scan_incomplete=True,
            stop_reason="max_items_reached",
            saved_nav_context={"section_idx": 2, "section_id": "l1-b", "topic_id": "top-1"},
        )
        restored = SessionState.from_dict(state.to_dict())

        self.assertEqual(restored.current_section_id, "l1-a")
        self.assertEqual(restored.covered_section_ids, ["l1-a", "l1-b"])
        self.assertTrue(restored.deep_scan_incomplete)
        self.assertEqual(restored.stop_reason, "max_items_reached")
        self.assertEqual(
            restored.saved_nav_context,
            {"section_idx": 2, "section_id": "l1-b", "topic_id": "top-1"},
        )

    def test_next_section_transitions_to_precision_targeting_when_se_high(self) -> None:
        service = object.__new__(SessionService)
        service.knowledge_repo = SimpleNamespace(
            get_by_level_and_grade=lambda level, grade: [SimpleNamespace(id="skill-cat-1")]
        )
        fake_task = SimpleNamespace(
            id="task-cat-1",
            content={"title": "Test CAT Task"},
            answer_type="single_choice",
            options=["A", "B"],
            hint=None,
            difficulty=0.5,
        )
        service.task_repo = SimpleNamespace(
            get_task_by_difficulty_target=lambda skill_id, target_b, exclude_ids: fake_task
        )
        service._set_context_for_skill = lambda state, skill_id: None
        service._task_to_out = lambda task, state: SimpleNamespace(id=task.id)

        state = make_state(
            section_ids=["sec-1", "sec-2"],
            current_section_idx=1,
            items_answered=18,
        )
        state.theta = ThetaState(theta=0.5, se=0.45)

        next_task = service._next_section_or_done(state)
        self.assertIsNotNone(next_task)
        self.assertEqual(state.phase, "precision_targeting")
        self.assertEqual(state.current_task_id, "task-cat-1")

    def test_next_section_stops_immediately_when_se_satisfied(self) -> None:
        service = object.__new__(SessionService)
        state = make_state(
            section_ids=["sec-1", "sec-2"],
            current_section_idx=1,
            items_answered=20,
            covered_section_ids=["sec-1", "sec-2"],
        )
        state.theta = ThetaState(theta=0.5, se=0.25)

        next_task = service._next_section_or_done(state)
        self.assertIsNone(next_task)
        self.assertEqual(state.stop_reason, "precision_reached")

    def test_section_exhaustion_cannot_bypass_minimum_answers(self) -> None:
        service = object.__new__(SessionService)
        service._pick_precision_targeting_task = lambda state: "next-evidence-task"
        state = make_state(section_ids=["sec-1", "sec-2"], current_section_idx=1,
                           items_answered=11, covered_section_ids=["sec-1", "sec-2"])
        state.theta = ThetaState(se=0.20)
        self.assertEqual(service._next_section_or_done(state), "next-evidence-task")
        self.assertEqual(state.phase, "precision_targeting")
        self.assertIsNone(state.stop_reason)

    def test_section_exhaustion_cannot_bypass_minimum_coverage(self) -> None:
        service = object.__new__(SessionService)
        service._pick_precision_targeting_task = lambda state: "next-evidence-task"
        state = make_state(section_ids=["sec-1", "sec-2"], current_section_idx=1,
                           items_answered=20, covered_section_ids=["sec-1"])
        state.theta = ThetaState(se=0.20)
        self.assertEqual(service._next_section_or_done(state), "next-evidence-task")
        self.assertIsNone(state.stop_reason)

    def test_section_exhaustion_preserves_limit_reason_when_se_is_small(self) -> None:
        service = object.__new__(SessionService)
        state = make_state(section_ids=["sec-1", "sec-2"], current_section_idx=1,
                           items_answered=42, covered_section_ids=["sec-1", "sec-2"])
        state.theta = ThetaState(se=0.20)
        self.assertIsNone(service._next_section_or_done(state))
        self.assertEqual(state.stop_reason, "max_items_reached")

    def test_deep_scan_context_snapshot_and_restoration(self) -> None:
        service = object.__new__(SessionService)
        state = make_state(
            current_section_idx=2,
            current_section_id="sec-grade6",
            current_topic_id="top-grade6",
            current_subtopic_id="sub-grade6",
            current_skill_id="skill-grade6",
        )

        service._prereq_l4_ids = lambda failing_id: ["skill-grade5-prereq"]
        service.task_repo = SimpleNamespace(
            get_task_by_difficulty_target=lambda skill_id, target_b, exclude_ids: SimpleNamespace(
                id="task-prereq",
                content={"title": "Grade 5 Prereq"},
                answer_type="single_choice",
                options=[],
                hint=None,
                difficulty=0.0,
            )
        )
        service._set_context_for_skill = lambda state, skill_id: setattr(state, "current_section_id", "sec-grade5")
        service._task_to_out = lambda task, state: SimpleNamespace(id=task.id)

        # 1. Initialize deep scan
        task = service._init_deep_scan(state, "skill-grade6")
        self.assertIsNotNone(task)
        self.assertIsNotNone(state.saved_nav_context)
        self.assertEqual(state.saved_nav_context["section_id"], "sec-grade6")
        self.assertEqual(state.current_section_id, "sec-grade5")

        # 2. Finish deep scan
        from src.domain.navigators.skill_navigator import DeepScanState
        scan = DeepScanState.from_dict(state.deep_scan)
        service._finish_deep_scan(state, scan)

        # Navigation context should be restored back to Grade 6
        self.assertIsNone(state.saved_nav_context)
        self.assertEqual(state.current_section_id, "sec-grade6")
        self.assertEqual(state.current_section_idx, 2)
        self.assertEqual(state.current_topic_id, "top-grade6")
        self.assertEqual(state.phase, "navigation")
        self.assertFalse(state.is_in_deep_scan)

    def test_precision_targeting_expands_to_lower_grade_prereqs_for_struggling_student(self) -> None:
        service = object.__new__(SessionService)
        service._task_to_out = lambda task, state: SimpleNamespace(id=task.id)
        service._set_context_for_skill = lambda state, skill_id: None
        service._prereq_l4_ids = lambda gap: ["prereq-l4-skill-5"]

        called_grades = []
        def mock_get_by_level_and_grade(level, grade):
            called_grades.append(grade)
            return [SimpleNamespace(id=f"g{grade}-skill-1")]

        service.knowledge_repo = SimpleNamespace(
            get_by_level_and_grade=mock_get_by_level_and_grade,
        )

        queried_skills = []
        def mock_get_task_by_difficulty_target(skill_id, target_b, exclude_ids=None):
            queried_skills.append(skill_id)
            if skill_id == "prereq-l4-skill-5":
                return SimpleNamespace(id="task-prereq-found")
            return None

        service.task_repo = SimpleNamespace(
            get_task_by_difficulty_target=mock_get_task_by_difficulty_target,
            get_tasks_for_skill=lambda *args, **kwargs: [],
        )

        state = make_state(
            grade_level=7,
            confirmed_gaps=["gap-skill-1"],
            used_task_ids=[],
        )
        state.theta = ThetaState(theta=-1.6, se=0.35)

        task = service._pick_precision_targeting_task(state)
        self.assertIsNotNone(task)
        self.assertEqual(task.id, "task-prereq-found")
        self.assertIn("prereq-l4-skill-5", queried_skills)
        # For theta = -1.6, min_grade is max(5, 7 - 2) = 5, so lower_grades = [5, 6]
        self.assertIn(5, called_grades)
        self.assertIn(6, called_grades)
        self.assertIn(7, called_grades)

    def test_precision_targeting_stays_in_grade_for_strong_student(self) -> None:
        service = object.__new__(SessionService)
        service._task_to_out = lambda task, state: SimpleNamespace(id=task.id)
        service._set_context_for_skill = lambda state, skill_id: None
        service._prereq_l4_ids = lambda gap: ["prereq-should-not-be-called"]

        called_grades = []
        def mock_get_by_level_and_grade(level, grade):
            called_grades.append(grade)
            return [SimpleNamespace(id=f"g{grade}-skill-1")]

        service.knowledge_repo = SimpleNamespace(
            get_by_level_and_grade=mock_get_by_level_and_grade,
        )

        queried_skills = []
        def mock_get_task_by_difficulty_target(skill_id, target_b, exclude_ids=None):
            queried_skills.append(skill_id)
            return SimpleNamespace(id="task-grade6-found")

        service.task_repo = SimpleNamespace(
            get_task_by_difficulty_target=mock_get_task_by_difficulty_target,
            get_tasks_for_skill=lambda *args, **kwargs: [],
        )

        state = make_state(
            grade_level=6,
            confirmed_gaps=["gap-skill-1"],
            used_task_ids=[],
        )
        state.theta = ThetaState(theta=0.8, se=0.35)

        task = service._pick_precision_targeting_task(state)
        self.assertIsNotNone(task)
        self.assertEqual(task.id, "task-grade6-found")
        # For theta >= -0.5, lower grades and prereqs are NOT queried
        self.assertEqual(called_grades, [6])
        self.assertEqual(queried_skills, ["g6-skill-1"])


if __name__ == "__main__":
    unittest.main()
