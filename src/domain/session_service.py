"""
Diagnostic Service — SessionService (Main Orchestrator)

Implements the T-Shape adaptive diagnostic algorithm:

  Phase 0  INIT        Build topic grid from grade_topic_map
  Phase 1  WARMUP      3 tasks centered around prior_theta (IRT-matched)
  Phase 2  NAVIGATION  Binary search L2 (topic) → L3 (subtopic) → L4 (skill)
  Phase 3  DEEP_SCAN   Prerequisite traversal on fail for high-importance topics
  Phase 4  COMPLETED   Persist, build breakdown, delete from Redis

Stopping criteria (outside deep scan):
  SE ≤ 0.30  OR  items_answered ≥ 25  OR  all L1 sections exhausted
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.exceptions import GradeNotConfiguredError, NoTasksAvailableError, SessionExpiredError
from src.domain.alpha_engine import (
    AlphaTracker,
    IRTParams,
    ThetaState,
    theta_to_level,
    update_theta,
)
from src.domain.navigators.skill_navigator import DeepScanState, SkillEntry, SkillNavigator
from src.domain.navigators.subtopic_navigator import SubtopicEntry, SubtopicNavigator
from src.domain.navigators.topic_navigator import TopicEntry, TopicNavigator
from src.domain.session_state import SessionState
from src.models.diag_models import DiagSession
from src.models.knowledge import TaskMaster
from src.repositories.diag_repo import (
    DiagAnswerRepository,
    DiagSessionRepository,
    GradeTopicMapRepository,
)
from src.repositories.knowledge_repo import (
    KnowledgeRepository,
    SkillPrerequisiteRepository,
    TaskRepository,
)
from src.schemas.diag_schemas import AnswerResult, TaskOut
from src.state.redis_state import RedisStateManager

log = logging.getLogger(__name__)
settings = get_settings()


class SessionService:
    """Orchestrates the full lifecycle of a diagnostic session."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.session_repo = DiagSessionRepository(db)
        self.answer_repo = DiagAnswerRepository(db)
        self.gtm_repo = GradeTopicMapRepository(db)
        self.knowledge_repo = KnowledgeRepository(db)
        self.prereq_repo = SkillPrerequisiteRepository(db)
        self.task_repo = TaskRepository(db)
        self.redis = RedisStateManager()

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC — Create session
    # ══════════════════════════════════════════════════════════════════════

    def create_session(
        self,
        student_id: uuid.UUID,
        grade_level: int,
        invite_code: Optional[str] = None,
        prior_theta: float = 0.0,
    ) -> Tuple[uuid.UUID, TaskOut]:
        """
        Initialize a new diagnostic session.
        Returns (session_id, first_task).
        """
        # 1. Persist session row
        db_session = DiagSession(
            student_id=student_id,
            grade_level=grade_level,
            invite_code=invite_code,
            phase="warmup",
        )
        self.session_repo.add(db_session)
        self.db.commit()
        self.db.refresh(db_session)

        # 2. Build in-memory state
        state = SessionState(
            session_id=str(db_session.id),
            student_id=str(student_id),
            grade_level=grade_level,
        )
        state.theta = ThetaState(theta=prior_theta)

        # 3. Load topic grid → build TopicNavigator states per L1 section
        self._build_topic_grid(state)

        if not state.section_ids:
            raise GradeNotConfiguredError(grade_level)

        # 4. Pick first warmup task
        first_task = self._pick_warmup_task(state)

        # 5. Persist state to Redis
        self.redis.save(state)

        return db_session.id, first_task

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC — Submit answer
    # ══════════════════════════════════════════════════════════════════════

    def submit_answer(
        self,
        session_id: uuid.UUID,
        task_id: str,
        student_answer: str,
        time_ms: Optional[int] = None,
    ) -> AnswerResult:
        """Process one answer. Returns result + next task (or completed flag)."""

        # 1. Load state
        state = self.redis.load(str(session_id))
        if state is None:
            raise SessionExpiredError(str(session_id))

        if state.phase == "completed":
            from src.core.exceptions import SessionAlreadyCompletedError
            raise SessionAlreadyCompletedError(str(session_id))

        # 2. Fetch task from DB
        task = self.task_repo.get_by_id(task_id)
        if task is None:
            raise NoTasksAvailableError(task_id)

        # 3. Evaluate answer
        outcome, category = self._evaluate_answer(task, student_answer)
        correct = outcome >= 0.5

        # 4. Update IRT theta
        params = IRTParams(
            a=float(task.irt_discrimination or 1.0),
            b=float(task.irt_difficulty or 0.0),
            c=float(task.irt_guessing or 0.0),
        )
        theta_before = state.theta.theta
        state.theta = update_theta(state.theta, params, outcome)

        # 5. Update per-topic alpha
        if state.current_topic_id:
            state.alpha_tracker.update(state.current_topic_id, outcome)

        # 6. Track item
        state.items_answered += 1
        state.used_task_ids.append(task_id)

        # 7. Log answer to DB
        self.answer_repo.log_answer(
            session_id=session_id,
            task_id=task_id,
            skill_id=state.current_skill_id or "",
            topic_id=state.current_topic_id or "",
            subtopic_id=state.current_subtopic_id,
            student_answer=student_answer,
            time_ms=time_ms,
            outcome=outcome,
            eval_category=category,
            ai_evaluated=False,
            theta_before=theta_before,
            theta_after=state.theta.theta,
            se_after=state.theta.se,
            phase=state.phase,
            is_deep_scan=state.is_in_deep_scan,
        )
        self.db.commit()

        # 8. Stopping criteria (skip if inside deep scan)
        if self._should_stop(state):
            return self._complete_session(state, outcome, category)

        # 9. Advance navigation → pick next task
        next_task = self._advance(state, correct)

        if next_task is None:
            return self._complete_session(state, outcome, category)

        # 10. Save updated state
        self.redis.save(state)

        return AnswerResult(
            is_correct=correct,
            outcome=outcome,
            eval_category=category,
            theta=state.theta.theta,
            se=state.theta.se,
            next_task=next_task,
            session_completed=False,
        )

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC — Report data
    # ══════════════════════════════════════════════════════════════════════

    def get_report_data(self, session_id: uuid.UUID) -> dict:
        db_session = self.session_repo.get_by_id(session_id)
        if db_session is None or db_session.phase != "completed":
            raise ValueError("Session not found or not completed")
        answers = self.answer_repo.get_session_answers(session_id)
        theta = float(db_session.theta or 0)
        se = float(db_session.theta_se or 1)
        return {
            "session_id": str(session_id),
            "student_id": str(db_session.student_id),
            "grade_level": db_session.grade_level,
            "overall_theta": theta,
            "overall_level": db_session.overall_level or "at_grade",
            "confidence_interval": [theta - 2 * se, theta + 2 * se],
            "topic_breakdown": db_session.topic_breakdown or {},
            "weak_skills": db_session.weak_skills or [],
            "recommended_start": (
                db_session.weak_skills[0] if db_session.weak_skills else None
            ),
            "items_total": len(answers),
        }

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE — Core algorithm helpers
    # ══════════════════════════════════════════════════════════════════════

    def _build_topic_grid(self, state: SessionState) -> None:
        """Load grade_topic_map and build TopicNavigator per L1 section."""
        entries = self.gtm_repo.get_grade_topics(state.grade_level)
        sections: dict[str, list[TopicEntry]] = {}
        for e in entries:
            if e.section_id not in sections:
                sections[e.section_id] = []
            sections[e.section_id].append(
                TopicEntry(
                    topic_id=e.topic_id,
                    section_id=e.section_id,
                    position=e.position,
                    importance=e.importance,
                )
            )
        state.section_ids = list(sections.keys())
        for section_id, topics in sections.items():
            nav = TopicNavigator.create(section_id, topics)
            state.topic_navigator_states[section_id] = nav.to_dict()

    def _pick_warmup_task(self, state: SessionState) -> TaskOut:
        """
        Pick a warmup task centered around current theta.
        Uses mid-topic of current section → mid-subtopic → mid-skill.
        """
        section_id = state.section_ids[state.current_section_idx]
        nav = TopicNavigator.from_dict(state.topic_navigator_states[section_id])
        topic = nav.peek_current()
        if topic is None:
            raise GradeNotConfiguredError(state.grade_level)

        subtopics = self.knowledge_repo.get_subtopics_for_topic(topic.topic_id)
        if not subtopics:
            raise NoTasksAvailableError(topic.topic_id)

        mid_sub = subtopics[len(subtopics) // 2]
        skills = self.knowledge_repo.get_skills_for_subtopic(mid_sub.id)
        if not skills:
            raise NoTasksAvailableError(mid_sub.id)

        mid_skill = skills[len(skills) // 2]

        task = self.task_repo.get_task_by_difficulty_target(
            mid_skill.id,
            target_b=state.theta.theta,
            exclude_ids=state.used_task_ids,
        )
        if task is None:
            tasks = self.task_repo.get_tasks_for_skill(
                mid_skill.id, exclude_ids=state.used_task_ids, limit=1
            )
            if not tasks:
                raise NoTasksAvailableError(mid_skill.id)
            task = tasks[0]

        state.current_task_id = task.id
        state.current_skill_id = mid_skill.id
        state.current_topic_id = topic.topic_id
        state.current_subtopic_id = mid_sub.id

        return self._task_to_out(task, state)

    # ── Answer evaluation ──────────────────────────────────────────────────

    def _evaluate_answer(
        self, task: TaskMaster, student_answer: str
    ) -> Tuple[float, str]:
        """
        Simple deterministic evaluation.
        AI evaluation (Gemini) will be layered in Phase 2.
        Returns (outcome, category).
        """
        correct = str(task.correct_answer).strip().lower()
        given = str(student_answer).strip().lower()

        if given == correct:
            return 1.0, "correct"

        # Distractor check
        if task.distractor_meta and isinstance(task.distractor_meta, list):
            distractor_values = {
                str(d.get("value", "")).strip().lower()
                for d in task.distractor_meta
                if isinstance(d, dict)
            }
            if given in distractor_values:
                return 0.5, "distractor"

        if given in {"не знаю", "?", "skip", "idk", ""}:
            return 0.0, "idk"

        return 0.0, "wrong"

    # ── Stopping criteria ─────────────────────────────────────────────────

    def _should_stop(self, state: SessionState) -> bool:
        if state.is_in_deep_scan:
            return False
        if state.items_answered >= settings.max_items:
            return True
        if state.theta.se <= settings.se_threshold:
            return True
        return False

    # ── Navigation dispatcher ─────────────────────────────────────────────

    def _advance(self, state: SessionState, correct: bool) -> Optional[TaskOut]:
        if state.phase == "warmup":
            return self._advance_warmup(state, correct)
        if state.phase == "navigation":
            return self._advance_navigation(state, correct)
        if state.phase == "deep_scan":
            return self._advance_deep_scan(state, correct)
        return None

    # ── Warmup phase ──────────────────────────────────────────────────────

    def _advance_warmup(self, state: SessionState, correct: bool) -> Optional[TaskOut]:
        if state.items_answered >= settings.warmup_items:
            state.phase = "navigation"
            return self._start_navigation(state)
        return self._pick_warmup_task(state)

    # ── Navigation phase ──────────────────────────────────────────────────

    def _start_navigation(self, state: SessionState) -> Optional[TaskOut]:
        """Initialize subtopic navigation for current L1 section's current topic."""
        section_id = state.section_ids[state.current_section_idx]
        nav = TopicNavigator.from_dict(state.topic_navigator_states[section_id])
        topic = nav.peek_current()

        if topic is None:
            return self._next_section_or_done(state)

        state.current_topic_id = topic.topic_id
        state.current_skill_nav = None
        return self._init_subtopic_nav(state, topic)

    def _advance_navigation(self, state: SessionState, correct: bool) -> Optional[TaskOut]:
        """Handle one step of L3→L4 binary search navigation."""

        if state.current_subtopic_nav is None:
            return self._start_navigation(state)

        sub_nav = SubtopicNavigator.from_dict(state.current_subtopic_nav)

        if state.current_skill_nav:
            # We are inside a skill navigator (L4)
            skill_nav = SkillNavigator.from_dict(state.current_skill_nav)
            next_skill = skill_nav.move(correct)

            if next_skill is None:
                # Skill navigator exhausted
                state.current_skill_nav = None
                importance = sub_nav.state.topic_importance

                if (
                    not correct
                    and importance >= settings.deep_scan_importance_threshold
                    and skill_nav.get_failing_skill()
                ):
                    # Trigger deep scan
                    state.phase = "deep_scan"
                    state.is_in_deep_scan = True
                    return self._init_deep_scan(state, skill_nav.get_failing_skill())

                # Move subtopic
                next_sub = sub_nav.move(correct)
                state.current_subtopic_nav = sub_nav.to_dict()

                if next_sub is None:
                    return self._advance_topic(state, correct)
                return self._pick_task_from_subtopic(state, sub_nav)

            # Continue within skill navigator
            state.current_skill_nav = skill_nav.to_dict()
            state.current_skill_id = next_skill.skill_id
            state.current_subtopic_id = next_skill.subtopic_id
            return self._pick_task_for_skill(state, next_skill.skill_id)

        # No skill navigator yet — move subtopic cursor
        next_sub = sub_nav.move(correct)
        state.current_subtopic_nav = sub_nav.to_dict()

        if next_sub is None:
            return self._advance_topic(state, correct)

        return self._pick_task_from_subtopic(state, sub_nav)

    def _init_subtopic_nav(self, state: SessionState, topic: TopicEntry) -> Optional[TaskOut]:
        """Create a fresh SubtopicNavigator for a topic and pick first task."""
        raw_subs = self.knowledge_repo.get_subtopics_for_topic(topic.topic_id)
        subtopics = [
            SubtopicEntry(
                subtopic_id=s.id,
                topic_id=topic.topic_id,
                position=s.sequence_order,
                name_ru=s.name_ru or "",
            )
            for s in raw_subs
        ]
        if not subtopics:
            # Skip topic with no subtopics
            section_id = state.section_ids[state.current_section_idx]
            nav = TopicNavigator.from_dict(state.topic_navigator_states[section_id])
            next_topic = nav.move(True)  # treat as "passed"
            state.topic_navigator_states[section_id] = nav.to_dict()
            if next_topic is None:
                return self._next_section_or_done(state)
            state.current_topic_id = next_topic.topic_id
            return self._init_subtopic_nav(state, next_topic)

        sub_nav = SubtopicNavigator.create(topic.topic_id, topic.importance, subtopics)
        state.current_subtopic_nav = sub_nav.to_dict()
        return self._pick_task_from_subtopic(state, sub_nav)

    def _pick_task_from_subtopic(
        self, state: SessionState, sub_nav: SubtopicNavigator
    ) -> Optional[TaskOut]:
        """Build a SkillNavigator for the current subtopic and pick first task."""
        current_sub = sub_nav.peek_current()
        if current_sub is None:
            return None

        state.current_subtopic_id = current_sub.subtopic_id

        raw_skills = self.knowledge_repo.get_skills_for_subtopic(current_sub.subtopic_id)
        skills = [
            SkillEntry(
                skill_id=s.id,
                subtopic_id=current_sub.subtopic_id,
                sequence_order=s.sequence_order,
                irt_difficulty=float(s.importance or 0),
                name_ru=s.name_ru or "",
            )
            for s in raw_skills
        ]
        if not skills:
            # Skip subtopic
            next_sub = sub_nav.move(True)
            state.current_subtopic_nav = sub_nav.to_dict()
            if next_sub is None:
                return self._advance_topic(state, True)
            return self._pick_task_from_subtopic(state, sub_nav)

        skill_nav = SkillNavigator.create(current_sub.subtopic_id, skills)
        state.current_skill_nav = skill_nav.to_dict()

        mid_skill = skill_nav.peek_current()
        if mid_skill is None:
            return None

        state.current_skill_id = mid_skill.skill_id
        return self._pick_task_for_skill(state, mid_skill.skill_id)

    def _advance_topic(self, state: SessionState, correct: bool) -> Optional[TaskOut]:
        """Move topic navigator to next topic in current section."""
        section_id = state.section_ids[state.current_section_idx]
        nav = TopicNavigator.from_dict(state.topic_navigator_states[section_id])
        next_topic = nav.move(correct)
        state.topic_navigator_states[section_id] = nav.to_dict()

        if next_topic is None:
            return self._next_section_or_done(state)

        state.current_topic_id = next_topic.topic_id
        state.current_skill_nav = None
        return self._init_subtopic_nav(state, next_topic)

    def _next_section_or_done(self, state: SessionState) -> Optional[TaskOut]:
        """Advance to next L1 section; return None if all sections are done."""
        state.current_section_idx += 1
        if state.current_section_idx >= len(state.section_ids):
            return None   # all sections exhausted → session complete

        state.current_subtopic_nav = None
        state.current_skill_nav = None
        return self._start_navigation(state)

    # ── Deep scan phase ───────────────────────────────────────────────────

    def _init_deep_scan(
        self, state: SessionState, failing_skill_id: str
    ) -> Optional[TaskOut]:
        """Build a DeepScanState from the prerequisite graph of the failing skill."""
        prereqs = self.prereq_repo.get_prerequisites(failing_skill_id, hard_only=True)
        prereq_ids = [p.prerequisite_id for p in prereqs]

        scan = DeepScanState(
            origin_skill_id=failing_skill_id,
            queue=prereq_ids,
            max_items=settings.deep_scan_max_items,
        )

        if not prereq_ids:
            # No prerequisites → origin is a root gap
            state.confirmed_gaps.append(failing_skill_id)
            state.deep_scan = None
            state.is_in_deep_scan = False
            state.phase = "navigation"
            return self._advance_topic(state, False)

        next_skill_id = scan.queue.pop(0)
        scan.current_skill_id = next_skill_id
        state.deep_scan = scan.to_dict()
        state.current_skill_id = next_skill_id

        return self._pick_task_for_skill(state, next_skill_id)

    def _advance_deep_scan(
        self, state: SessionState, correct: bool
    ) -> Optional[TaskOut]:
        """Process one step of the deep scan prerequisite traversal."""
        if state.deep_scan is None:
            state.phase = "navigation"
            state.is_in_deep_scan = False
            return self._advance_topic(state, False)

        scan = DeepScanState.from_dict(state.deep_scan)
        scan.items_used += 1

        if scan.current_skill_id:
            scan.tested.append(scan.current_skill_id)

        budget_exceeded = scan.items_used >= scan.max_items
        queue_empty = len(scan.queue) == 0

        if correct:
            # Student can do this prerequisite → root cause found, stop scan
            self._finish_deep_scan(state, scan)
            return self._advance_topic(state, False)

        # Incorrect: this skill is a gap
        if scan.current_skill_id:
            scan.gaps.append(scan.current_skill_id)

        if budget_exceeded or queue_empty:
            self._finish_deep_scan(state, scan)
            return self._advance_topic(state, False)

        # Go deeper: prepend this skill's prerequisites
        if scan.current_skill_id:
            deeper = self.prereq_repo.get_prerequisites(
                scan.current_skill_id, hard_only=True
            )
            new_prereqs = [
                p.prerequisite_id
                for p in deeper
                if p.prerequisite_id not in scan.tested
                and p.prerequisite_id not in scan.queue
            ]
            scan.queue = new_prereqs + scan.queue

        if not scan.queue:
            self._finish_deep_scan(state, scan)
            return self._advance_topic(state, False)

        next_skill_id = scan.queue.pop(0)
        scan.current_skill_id = next_skill_id
        state.deep_scan = scan.to_dict()
        state.current_skill_id = next_skill_id

        return self._pick_task_for_skill(state, next_skill_id)

    def _finish_deep_scan(self, state: SessionState, scan: DeepScanState) -> None:
        """Finalize deep scan: collect gaps, reset flags."""
        state.confirmed_gaps.extend(scan.gaps)
        if scan.origin_skill_id not in state.confirmed_gaps:
            state.confirmed_gaps.append(scan.origin_skill_id)
        state.deep_scan = None
        state.is_in_deep_scan = False
        state.phase = "navigation"

    # ── Task selection ─────────────────────────────────────────────────────

    def _pick_task_for_skill(
        self, state: SessionState, skill_id: str
    ) -> Optional[TaskOut]:
        """Select the IRT-optimal task for a skill at current theta."""
        task = self.task_repo.get_task_by_difficulty_target(
            skill_id, target_b=state.theta.theta, exclude_ids=state.used_task_ids
        )
        if task is None:
            tasks = self.task_repo.get_tasks_for_skill(
                skill_id, exclude_ids=state.used_task_ids, limit=1
            )
            if not tasks:
                log.warning("No tasks for skill %s — skipping", skill_id)
                return None
            task = tasks[0]

        state.current_task_id = task.id
        state.current_skill_id = skill_id
        return self._task_to_out(task, state)

    # ── Session completion ─────────────────────────────────────────────────

    def _complete_session(
        self, state: SessionState, outcome: float, category: str
    ) -> AnswerResult:
        """Finalize: persist to DB, remove from Redis, return result."""
        state.phase = "completed"

        topic_breakdown = {
            topic_id: {
                "alpha": alpha,
                "level": theta_to_level(alpha),
            }
            for topic_id, alpha in state.alpha_tracker.get_all().items()
        }
        overall_level = theta_to_level(state.theta.theta)

        db_session = self.session_repo.get_by_id(uuid.UUID(state.session_id))
        if db_session:
            self.session_repo.mark_completed(
                db_session,
                theta=state.theta.theta,
                theta_se=state.theta.se,
                level=overall_level,
                weak_skills=state.confirmed_gaps,
                topic_breakdown=topic_breakdown,
                state_snapshot=state.to_dict(),
            )
            self.db.commit()

        self.redis.delete(state.session_id)
        log.info(
            "Session %s completed: theta=%.3f se=%.3f level=%s gaps=%d",
            state.session_id,
            state.theta.theta,
            state.theta.se,
            overall_level,
            len(state.confirmed_gaps),
        )

        return AnswerResult(
            is_correct=outcome >= 0.5,
            outcome=outcome,
            eval_category=category,
            theta=state.theta.theta,
            se=state.theta.se,
            next_task=None,
            session_completed=True,
        )

    # ── Utilities ──────────────────────────────────────────────────────────

    def _task_to_out(self, task: TaskMaster, state: SessionState) -> TaskOut:
        hints = task.hints if isinstance(task.hints, list) else []
        options = task.answer_options if isinstance(task.answer_options, list) else None
        return TaskOut(
            task_id=task.id,
            skill_id=state.current_skill_id or "",
            topic_id=state.current_topic_id or "",
            question_text=task.question_text,
            question_latex=task.question_latex,
            answer_type=task.answer_type,
            answer_options=options,
            hints=hints,
            phase=state.phase,
            items_answered=state.items_answered,
            items_max=settings.max_items,
            is_deep_scan=state.is_in_deep_scan,
        )
