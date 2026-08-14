"""
Diagnostic Service — SessionService (Main Orchestrator)

Implements the T-Shape adaptive diagnostic algorithm:

  Phase 0  INIT        Build topic grid from knowledge_hierarchy (L2 nodes)
  Phase 1  WARMUP      3 tasks centered around prior_theta (IRT-matched)
  Phase 2  NAVIGATION  Binary search L2 (topic) → L3 (subtopic) → L4 (skill)
  Phase 3  DEEP_SCAN   Prerequisite traversal on fail for high-importance topics
  Phase 4  COMPLETED   Persist, build breakdown, delete from Redis

Stopping criteria (outside deep scan):
  SE ≤ 0.30  OR  items_answered ≥ 25  OR  all L1 sections exhausted
"""
from __future__ import annotations

import logging
import random
import uuid
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.exceptions import GradeNotConfiguredError, NoTasksAvailableError, SessionExpiredError
from src.domain.report_generator import generate_and_save_report
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
from src.domain.task_display import (
    build_diag_answer_options,
    diag_answer_type_for_display,
)
from src.domain.answer_evaluator import AnswerEvaluator
from src.domain.session_state import SessionState
from src.models.diag_models import DiagSession
from src.models.knowledge import TaskMaster
from src.repositories.diag_repo import (
    DiagAnswerRepository,
    DiagReportRepository,
    DiagSessionRepository,
)
from src.repositories.knowledge_repo import (
    KnowledgeRepository,
    SkillPrerequisiteRepository,
    TaskRepository,
)
from src.schemas.diag_schemas import AnswerResult, TaskOut
from src.state.redis_state import RedisStateManager
from src.core import auth_client

log = logging.getLogger(__name__)
settings = get_settings()


class SessionService:
    """Orchestrates the full lifecycle of a diagnostic session."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.session_repo = DiagSessionRepository(db)
        self.answer_repo = DiagAnswerRepository(db)
        self.report_repo = DiagReportRepository(db)
        # Knowledge/tasks come from content-service HTTP API (read-only)
        self.knowledge_repo = KnowledgeRepository()
        self.prereq_repo = SkillPrerequisiteRepository()
        self.task_repo = TaskRepository()
        self.redis = RedisStateManager()
        self.evaluator = AnswerEvaluator()

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

        # 6. Notify monolith: invite → in_progress
        if invite_code:
            auth_client.notify_start(invite_code, str(db_session.id))

        return db_session.id, first_task

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC — Resume active session
    # ══════════════════════════════════════════════════════════════════════

    def get_active_session(
        self, invite_code: str
    ) -> Optional[Tuple[uuid.UUID, int, TaskOut]]:
        """Return (session_id, items_answered, current_task) for an active session.

        Called on page load to check if the student has an unfinished session
        so the frontend can offer «Continue where you left off?» instead of
        starting a new one.

        Returns None when:
          - No session found for this invite_code
          - Session is already completed
          - Redis state has expired (TTL elapsed) — session is unrecoverable
        """
        db_session = self.session_repo.get_by_invite_code(invite_code)
        if db_session is None or db_session.phase == "completed":
            return None

        state = self.redis.load(str(db_session.id))
        if state is None:
            # Redis TTL expired — state is gone, cannot resume
            return None

        # Re-build current task from state
        try:
            task = self._current_task_from_state(state)
        except Exception:
            log.warning("get_active_session: could not rebuild task for %s", db_session.id)
            return None

        return db_session.id, state.items_answered, task

    def _current_task_from_state(self, state: SessionState) -> TaskOut:
        """Re-serve the current task stored in state (no DB write)."""
        skill_id = state.current_skill_id
        task_id = state.current_task_id

        if not skill_id or not task_id:
            raise ValueError("No current skill/task in state")

        # Load the task object by ID
        task = self.task_repo.get_by_id(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        return self._task_to_out(task, state)

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
        outcome, category = self.evaluator.evaluate(task, student_answer)
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

        # Pull full report_json (including error_patterns) from diag_reports
        report = self.report_repo.get_by_session(session_id)
        report_json: dict = {}
        error_patterns: list = []
        if report and report.report_json and isinstance(report.report_json, dict):
            report_json = report.report_json
            error_patterns = report_json.get("error_patterns", [])

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
            # Unified journal: error_patterns + full report_json
            "error_patterns": error_patterns,
            "report_json": report_json,
            # Explicit flag so frontend knows full report is available
            "has_full_report": bool(report_json),
        }

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE — Core algorithm helpers
    # ══════════════════════════════════════════════════════════════════════

    def _build_topic_grid(self, state: SessionState) -> None:
        """Build TopicNavigator per L1 section from knowledge_hierarchy (L2 nodes).

        Topics are sorted by sequence_order (curriculum / textbook order) — NOT by
        avg IRT difficulty.  Curriculum order encodes pedagogical prerequisites:
          T03 (Rational eq) comes before T04 (Irrational eq)
          T05 (Exponential)  comes before T06 (Logarithmic)
          T07 (Trig basics)  comes before T08 (Trig equations)

        Binary search on curriculum-ordered topics exploits the prerequisite
        guarantee: if a student passes a later topic they must know all earlier
        (prerequisite) topics, so we don't need to test them separately.
        """
        topics_l2 = self.knowledge_repo.get_by_level_and_grade("L2", state.grade_level)
        sections: dict[str, list[TopicEntry]] = {}
        for t in topics_l2:
            sid = t.parent_id  # L1 section id
            if sid not in sections:
                sections[sid] = []
            sections[sid].append(
                TopicEntry(
                    topic_id=t.id,
                    section_id=sid,
                    position=t.sequence_order or 0,
                    importance=t.importance or 5,
                    name_ru=t.name_ru or "",
                )
            )
        state.section_ids = list(sections.keys())
        for section_id, topics in sections.items():
            nav = TopicNavigator.create(section_id, topics)
            state.topic_navigator_states[section_id] = nav.to_dict()

    def _pick_warmup_task(self, state: SessionState) -> TaskOut:
        """
        Pick a warmup task centered around current theta.
        Distributes warmup items across DIFFERENT topics in the section so that
        the 3 warmup questions establish a broad multi-domain baseline.
        """
        section_id = state.section_ids[state.current_section_idx]
        nav = TopicNavigator.from_dict(state.topic_navigator_states[section_id])
        topics = nav.state.topics
        if not topics:
            raise GradeNotConfiguredError(state.grade_level)

        # Distribute warmup questions across distinct topics (0, 1, 2)
        topic_idx = state.items_answered % len(topics)
        topic = topics[topic_idx]

        subtopics = self.knowledge_repo.get_subtopics_for_topic(topic.topic_id)
        if not subtopics:
            # Fallback to current nav topic if selected topic has no subtopics
            topic = nav.peek_current() or topics[0]
            subtopics = self.knowledge_repo.get_subtopics_for_topic(topic.topic_id)

        if not subtopics:
            raise NoTasksAvailableError(topic.topic_id)

        mid = len(subtopics) // 2
        sub_candidates = subtopics[max(0, mid - 1): mid + 2]
        random.shuffle(sub_candidates)

        task = None
        selected_skill_id = None
        selected_sub_id = None

        # 1. Search subtopic candidates for unused tasks matching current theta
        for sub in sub_candidates:
            skills = self.knowledge_repo.get_skills_for_subtopic(sub.id)
            if not skills:
                continue
            skills_shuffled = list(skills)
            random.shuffle(skills_shuffled)
            for sk in skills_shuffled:
                t = self.task_repo.get_task_by_difficulty_target(
                    sk.id, target_b=state.theta.theta, exclude_ids=state.used_task_ids
                )
                if t is None:
                    ts = self.task_repo.get_tasks_for_skill(
                        sk.id, exclude_ids=state.used_task_ids, limit=1
                    )
                    if ts:
                        t = ts[0]
                if t is not None:
                    task = t
                    selected_skill_id = sk.id
                    selected_sub_id = sub.id
                    break
            if task is not None:
                break

        # 2. Fallback: search all subtopics in topic
        if task is None:
            for sub in subtopics:
                skills = self.knowledge_repo.get_skills_for_subtopic(sub.id)
                for sk in skills:
                    ts = self.task_repo.get_tasks_for_skill(
                        sk.id, exclude_ids=state.used_task_ids, limit=1
                    )
                    if not ts:
                        ts = self.task_repo.get_tasks_for_skill(sk.id, limit=1)
                    if ts:
                        task = ts[0]
                        selected_skill_id = sk.id
                        selected_sub_id = sub.id
                        break
                if task is not None:
                    break

        if task is None:
            raise NoTasksAvailableError(topic.topic_id)

        state.current_task_id = task.id
        state.current_skill_id = selected_skill_id
        state.current_topic_id = topic.topic_id
        state.current_subtopic_id = selected_sub_id

        return self._task_to_out(task, state)

    # ── Answer evaluation ──────────────────────────────────────────────────

    # ── Stopping criteria ─────────────────────────────────────────────────

    def _should_stop(self, state: SessionState) -> bool:
        if state.items_answered >= settings.max_items:
            return True
        if state.is_in_deep_scan:
            return False
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
                # Skill navigator exhausted — aggregate results to subtopic level
                state.current_skill_nav = None

                skill_score = skill_nav.subtopic_score()
                subtopic_pass = skill_score >= settings.mastery_threshold
                sub_nav.record_score(skill_score)
                # move() sets boundary_subtopic_id when subtopic fails — MUST happen before
                # needs_deep_scan() which reads boundary_subtopic_id to check importance.
                next_sub = sub_nav.move(subtopic_pass)
                state.current_subtopic_nav = sub_nav.to_dict()

                # Check Deep Scan AFTER sub_nav.move() so boundary_subtopic_id is populated.
                # needs_deep_scan() reads the FAILED L3 subtopic's own importance (8–10).
                if (
                    not subtopic_pass
                    and sub_nav.needs_deep_scan(settings.deep_scan_importance_threshold)
                    and skill_nav.get_failing_skill()
                ):
                    failing_skill = skill_nav.get_failing_skill()
                    log.info(
                        "Deep scan triggered for skill %s (failed subtopic %s, importance >= %d)",
                        failing_skill,
                        sub_nav.state.boundary_subtopic_id,
                        settings.deep_scan_importance_threshold,
                    )
                    state.phase = "deep_scan"
                    state.is_in_deep_scan = True
                    return self._init_deep_scan(state, failing_skill)

                if next_sub is None:
                    # All subtopics exhausted → advance to next topic
                    topic_pass = sub_nav.topic_score() >= settings.mastery_threshold
                    return self._advance_topic(state, topic_pass)
                return self._pick_task_from_subtopic(state, sub_nav)

            # Continue within skill navigator
            state.current_skill_nav = skill_nav.to_dict()
            state.current_skill_id = next_skill.skill_id
            state.current_subtopic_id = next_skill.subtopic_id
            return self._pick_task_for_skill(state, next_skill.skill_id)

        # No skill navigator yet — move subtopic cursor (safety path)
        next_sub = sub_nav.move(correct)
        state.current_subtopic_nav = sub_nav.to_dict()

        if next_sub is None:
            sub_scores = sub_nav.state.scores
            topic_pass = (
                sub_nav.topic_score() >= settings.mastery_threshold
                if sub_scores else correct
            )
            return self._advance_topic(state, topic_pass)

        return self._pick_task_from_subtopic(state, sub_nav)

    def _init_subtopic_nav(self, state: SessionState, topic: TopicEntry) -> Optional[TaskOut]:
        """Create a fresh SubtopicNavigator for a topic and pick first task.

        Subtopics are sorted by sequence_order (curriculum order) which encodes
        pedagogical prerequisites between subtopics within a topic.
        Binary search on curriculum-ordered subtopics exploits the same prerequisite
        guarantee as for topics: passing a later subtopic implies mastery of earlier ones.

        NOTE: L4 skills within a subtopic are sorted by irt_difficulty (in SkillNavigator)
        because skills within one subtopic have no strict inter-prerequisite structure.
        """
        raw_subs = self.knowledge_repo.get_subtopics_for_topic(topic.topic_id)
        subtopics = [
            SubtopicEntry(
                subtopic_id=s.id,
                topic_id=topic.topic_id,
                position=s.sequence_order,
                importance=s.importance or 5,
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
        if not raw_skills:
            # Skip subtopic
            next_sub = sub_nav.move(True)
            state.current_subtopic_nav = sub_nav.to_dict()
            if next_sub is None:
                return self._advance_topic(state, True)
            return self._pick_task_from_subtopic(state, sub_nav)

        # Fetch real avg IRT b-params from tasks_master in ONE query (no N+1)
        skill_ids = [s.id for s in raw_skills]
        avg_difficulty = self.task_repo.get_avg_difficulty_for_skills(skill_ids)

        skills = [
            SkillEntry(
                skill_id=s.id,
                subtopic_id=current_sub.subtopic_id,
                sequence_order=s.sequence_order,
                irt_difficulty=avg_difficulty.get(s.id, 0.0),  # real IRT b-param
                name_ru=s.name_ru or "",
            )
            for s in raw_skills
        ]

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

    def _prereq_l4_ids(self, skill_or_para_id: str) -> List[str]:
        """
        Resolve a failing L4 skill to a list of testable prerequisite L4 skill IDs.

        Data model: skill_prerequisites stores L3 (paragraph) → L3 links.
        Algorithm:
          1. If input is L4 → map to its parent L3 paragraph via parent_id.
          2. Look up hard prerequisites for that L3 paragraph.
          3. For each prerequisite L3 paragraph → resolve to its middle L4 child skill.
        This keeps the deep-scan engine purely L4-native (tasks live at L4).
        """
        node = self.knowledge_repo.get_by_id(skill_or_para_id)
        if node is None:
            log.warning("_prereq_l4_ids: node not found for %s", skill_or_para_id)
            return []

        # L4 skill → map to parent L3 paragraph for prerequisites lookup
        if node.level == "L4" and node.parent_id:
            lookup_id = node.parent_id
        else:
            lookup_id = skill_or_para_id

        prereqs = self.prereq_repo.get_prerequisites(lookup_id, hard_only=True)
        log.info(
            "_prereq_l4_ids: skill=%s → lookup_id=%s → %d hard prereqs",
            skill_or_para_id, lookup_id, len(prereqs),
        )

        result: List[str] = []
        for p in prereqs:
            prereq_id = p.prerequisite_id
            # prerequisite_id is typically an L3 paragraph → resolve to its middle L4 child
            prereq_node = self.knowledge_repo.get_by_id(prereq_id)
            if prereq_node is None:
                log.warning("_prereq_l4_ids: prereq node not found for %s", prereq_id)
                continue
            if prereq_node.level == "L3":
                children = self.knowledge_repo.get_skills_for_subtopic(prereq_id)
                if children:
                    # Pick middle child for representative difficulty
                    mid_child = children[len(children) // 2]
                    result.append(mid_child.id)
                    log.debug(
                        "_prereq_l4_ids: L3 %s → L4 child %s",
                        prereq_id, mid_child.id,
                    )
            elif prereq_node.level == "L4":
                # Already L4 — future-proof for direct L4 prerequisite links
                result.append(prereq_id)
            else:
                log.warning(
                    "_prereq_l4_ids: unexpected level %s for prereq %s",
                    prereq_node.level, prereq_id,
                )

        log.info("_prereq_l4_ids: resolved %d testable L4 skills for %s", len(result), skill_or_para_id)
        return result

    def _init_deep_scan(
        self, state: SessionState, failing_skill_id: str
    ) -> Optional[TaskOut]:
        """Build a DeepScanState from the prerequisite graph of the failing skill."""
        prereq_ids = self._prereq_l4_ids(failing_skill_id)

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

        # Go deeper: prepend this skill's prerequisites (resolved via L3 map)
        if scan.current_skill_id:
            new_prereqs = [
                pid
                for pid in self._prereq_l4_ids(scan.current_skill_id)
                if pid not in scan.tested
                and pid not in scan.queue
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
                # Retry without exclude_ids so we don't return None/stall if skill has tasks
                tasks = self.task_repo.get_tasks_for_skill(
                    skill_id, exclude_ids=None, limit=1
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
                items_answered=state.items_answered,    # ← Fix: was 0, now correct
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

        # Generate diagnostic report with Gemini narrative in background thread
        # Fire-and-forget: does not block answer submission HTTP response.
        if db_session:
            import threading

            def _bg_generate_report(sid_str: str, st_id: uuid.UUID, g_lvl: int, th: float, th_se: float, ov_lvl: str, t_bd: dict, w_sk: list, items_tot: int):
                try:
                    from src.core.database import SessionLocal
                    report_db = SessionLocal()
                    try:
                        generate_and_save_report(
                            report_db,
                            session_id=uuid.UUID(sid_str),
                            student_id=st_id,
                            grade_level=g_lvl,
                            theta=th,
                            theta_se=th_se,
                            overall_level=ov_lvl,
                            topic_breakdown=t_bd,
                            weak_skills=w_sk,
                            items_total=items_tot,
                        )
                    finally:
                        report_db.close()
                except Exception as exc:
                    log.warning("Report generation skipped (session safe): %s", exc)

            threading.Thread(
                target=_bg_generate_report,
                args=(
                    state.session_id,
                    db_session.student_id,
                    db_session.grade_level,
                    state.theta.theta,
                    state.theta.se,
                    overall_level,
                    topic_breakdown,
                    state.confirmed_gaps,
                    state.items_answered,
                ),
                daemon=True,
            ).start()

        # Notify monolith: invite → completed + save StudentDiagnosticResult
        invite_code = getattr(db_session, "invite_code", None)
        auth_client.notify_complete(
            invite_code or "",
            state.session_id,
            {
                "final_theta": state.theta.theta,
                "se": state.theta.se,
                "total_items": state.items_answered,
                "identified_gaps": state.confirmed_gaps,
                "topic_breakdown": topic_breakdown,
            },
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
        options, options_latex = build_diag_answer_options(task)
        img_url = (
            getattr(task, "question_image_url", None)
            or getattr(task, "image_url", None)
            or getattr(task, "figure_url", None)
        )
        return TaskOut(
            task_id=task.id,
            skill_id=state.current_skill_id or "",
            topic_id=state.current_topic_id or "",
            question_text=task.question_text,
            question_latex=task.question_latex,
            question_image_url=img_url,
            answer_type=diag_answer_type_for_display(task, options),
            answer_options=options,
            answer_options_latex=options_latex,
            phase=state.phase,
            items_answered=state.items_answered,
            items_max=settings.max_items,
            is_deep_scan=state.is_in_deep_scan,
        )

