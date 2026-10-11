"""
Diagnostic Service — SessionService (Main Orchestrator)

Implements the T-Shape adaptive diagnostic algorithm:

  Phase 0  INIT        Build topic grid from knowledge_hierarchy (L2 nodes)
  Phase 1  WARMUP      Cross-section tasks around prior_theta (IRT-matched)
  Phase 2  NAVIGATION  Binary search L2 (topic) → L3 (subtopic) → L4 (skill)
  Phase 3  DEEP_SCAN   Prerequisite traversal on fail for high-importance topics
  Phase 4  COMPLETED   Persist, build breakdown, delete from Redis

Stopping criteria:
  Hard limit: configured max_items (42), including deep scan.
  Earlier: SE ≤ 0.30, minimum answers and minimum L1 coverage, outside deep scan.
  Section traversal alone enters precision targeting; bank exhaustion records
  insufficient precision rather than claiming the target has been reached.
"""
from __future__ import annotations

import copy
import logging
import random
import uuid
from typing import List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.exceptions import (
    GradeNotConfiguredError,
    NoTasksAvailableError,
    SessionExpiredError,
    SessionNotFoundError,
    SessionAlreadyStartedError,
    TaskOutOfSequenceError,
)
from src.domain.auth_sync_jobs import enqueue_auth_completion_sync, process_next_auth_completion_sync
from src.domain.report_jobs import enqueue_report_generation, process_next_report_job
from src.domain.report_generator import REPORT_SCHEMA_VERSION
from src.domain.level_policy import classify, count_solved, is_correct
from src.domain.alpha_engine import (
    AlphaTracker,
    IRTParams,
    ThetaState,
    theta_to_level,
    level_confidence,
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
from src.domain.task_evidence import capture_task, read_task, task_object
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
        # An invite represents exactly one attempt.  A normal refresh reaches
        # ``get_active_session``; a duplicate POST must never create a second
        # row just because two browser requests raced each other.
        if invite_code:
            existing = self.session_repo.get_by_invite_code(invite_code)
            if existing is not None:
                raise SessionAlreadyStartedError(str(existing.id))

        # 1. Validate task availability before claiming the one-time invite.
        # A temporary content-service outage must not leave a student with a
        # permanently blocked code and an empty diagnostic session.
        session_id = uuid.uuid4()
        state = SessionState(
            session_id=str(session_id),
            student_id=str(student_id),
            grade_level=grade_level,
        )
        state.theta = ThetaState(theta=prior_theta)

        # 2. Load topic grid → build TopicNavigator states per L1 section
        self._build_topic_grid(state)

        if not state.section_ids:
            raise GradeNotConfiguredError(grade_level)

        # 3. Pick first warmup task
        first_task = self._pick_warmup_task(state)

        # 4. Persist the session only after the first task is available.  The
        # partial unique index remains the final arbiter when two POSTs race.
        db_session = DiagSession(
            id=session_id,
            student_id=student_id,
            grade_level=grade_level,
            invite_code=invite_code,
            phase="warmup",
        )
        self.session_repo.add(db_session)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if invite_code:
                existing = self.session_repo.get_by_invite_code(invite_code)
                if existing is not None:
                    raise SessionAlreadyStartedError(str(existing.id)) from exc
            raise

        # 5. Persist resumable state before notifying auth-service.  If Redis
        # is unavailable at this point, the just-created database row has no
        # answers and no external side effect yet.  Remove it again instead of
        # leaving a one-time invite permanently claimed by an unrecoverable
        # session.
        try:
            self.redis.save(state)
        except Exception:
            try:
                self.db.delete(db_session)
                self.db.commit()
            except Exception:
                self.db.rollback()
                log.exception(
                    "Could not compensate failed Redis initialization for session %s",
                    db_session.id,
                )
            raise

        # 6. Notify monolith: invite → in_progress
        if invite_code:
            auth_client.notify_start(invite_code, str(db_session.id))

        return db_session.id, first_task

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC — Resume active session
    # ══════════════════════════════════════════════════════════════════════

    def get_active_session(
        self, invite_code: str
    ) -> Optional[Tuple[uuid.UUID, int, TaskOut, int]]:
        """Return (session_id, items_answered, current_task, total_time_ms) for an active session.

        Called on page load to check if the student has an unfinished session
        so the frontend can offer «Continue where you left off?» instead of
        starting a new one.

        Returns None when:
          - No session found for this invite_code
          - Session is already completed
          - Redis state has expired (TTL elapsed) — session is unrecoverable
        """
        db_session = self.session_repo.get_by_invite_code(invite_code)
        if db_session is None or db_session.phase in {"completed", "expired"}:
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

        total_time_ms = self.answer_repo.get_total_time_ms(db_session.id)
        return db_session.id, state.items_answered, task, total_time_ms

    def _current_task_from_state(self, state: SessionState) -> TaskOut:
        """Re-serve the current task stored in state (no DB write)."""
        skill_id = state.current_skill_id
        task_id = state.current_task_id

        if not skill_id or not task_id:
            raise ValueError("No current skill/task in state")

        # Load the task object by ID
        task = task_object(state.current_task_snapshot, task_id)
        if task is None:
            task = self.task_repo.get_by_id(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        return self._task_to_out(task, state, capture=False)

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

        # Completed attempts are durable, even after Redis eviction/outage.
        replay = self.get_completed_answer_result(session_id, task_id, student_answer)
        if replay is not None:
            return replay

        # Redis state is read-modify-written.  A lock makes a double click,
        # retry, or concurrent browser request harmless instead of counting the
        # same item twice.
        with self.redis.answer_lock(str(session_id)):
            return self._submit_answer_locked(
                session_id=session_id,
                task_id=task_id,
                student_answer=student_answer,
                time_ms=time_ms,
            )

    def get_completed_answer_result(
        self, session_id: uuid.UUID, task_id: str, student_answer: str
    ) -> Optional[AnswerResult]:
        """Replay only the exact final answer; never evaluate or enqueue again."""
        session = self.session_repo.get_fresh(session_id)
        if session is None:
            raise SessionNotFoundError(str(session_id))
        if session.phase != "completed":
            return None
        last = self.answer_repo.get_last_answer(session_id)
        if last is None or last.task_id != task_id or last.student_answer != student_answer:
            raise TaskOutOfSequenceError(str(session_id))
        snapshot = session.state_snapshot or {}
        theta = snapshot.get("theta") or {}
        result = AnswerResult(
            is_correct=is_correct(last.outcome),
            outcome=float(last.outcome),
            eval_category=last.eval_category,
            theta=float(theta.get("theta", session.theta if session.theta is not None else 0)),
            se=float(theta.get("se", session.theta_se if session.theta_se is not None else 1)),
            next_task=None,
            session_completed=True,
            stop_reason=session.stop_reason,
        )
        log.info("diagnostic_answer_replayed session_id=%s phase=completed", session_id)
        return result

    def _submit_answer_locked(
        self,
        *,
        session_id: uuid.UUID,
        task_id: str,
        student_answer: str,
        time_ms: Optional[int],
    ) -> AnswerResult:
        """Process one answer while holding the per-session Redis lock."""

        # PostgreSQL remains the final serialization barrier if a Redis lease
        # expires during slow evaluation. The final answer and completion
        # commit together below, so a second worker observes the durable result.
        self.session_repo.get_fresh(session_id, for_update=True)
        # A request admitted before completion can acquire the lock afterwards.
        replay = self.get_completed_answer_result(session_id, task_id, student_answer)
        if replay is not None:
            return replay

        # 1. Load state
        state = self.redis.load(str(session_id))
        if state is None:
            raise SessionExpiredError(str(session_id))

        if state.phase == "completed":
            from src.core.exceptions import SessionAlreadyCompletedError
            raise SessionAlreadyCompletedError(str(session_id))

        # Never let a client choose an arbitrary task or replay a previous one.
        # The requested task must be exactly the task the server issued.
        self._ensure_current_task(state, task_id)

        # 2. Evaluate the issued content even if the live bank changed meanwhile.
        # Legacy active sessions had no snapshot; bank repair preflight protects
        # their current/used IDs. Record their evaluation lookup as such.
        task = task_object(state.current_task_snapshot, task_id)
        if task is None:
            task = self.task_repo.get_by_id(task_id)
            if task is not None:
                opts, latex = build_diag_answer_options(task, seed=f"{state.session_id}:{task.id}")
                state.current_task_snapshot = capture_task(
                    task, opts, latex, diag_answer_type_for_display(task, opts),
                    provenance='legacy_answer_lookup',
                )
        if task is None:
            raise NoTasksAvailableError(task_id)

        # 3. Evaluate answer
        outcome, category = self.evaluator.evaluate(task, student_answer)
        correct = is_correct(outcome)

        # 4. Update global IRT theta only with measurement items.  Deep-scan
        # tasks are causal probes for prerequisites; mixing their often easier
        # content into global ability creates a misleadingly precise theta.
        theta_before = state.theta.theta
        if not state.is_in_deep_scan:
            params = IRTParams(
                a=float(task.irt_discrimination or 1.0),
                b=float(task.irt_difficulty or 0.0),
                c=float(task.irt_guessing or 0.0),
            )
            state.theta = update_theta(state.theta, params, outcome)

        # 5. Update per-topic alpha
        if state.current_topic_id:
            state.alpha_tracker.update(state.current_topic_id, outcome)

        # 6. Track item
        state.items_answered += 1
        state.used_task_ids.append(task_id)
        if not state.is_in_deep_scan and state.current_section_id:
            if state.current_section_id not in state.covered_section_ids:
                state.covered_section_ids.append(state.current_section_id)

        # 7. Log answer to DB.  A Deep Scan answer records the navigation skill
        # that started the scan and its 1-based step, so the report can build
        # the chain from a stored fact instead of guessing from neighbours.
        scan_origin: Optional[str] = None
        scan_step: Optional[int] = None
        if state.is_in_deep_scan and state.deep_scan:
            scan_origin = state.deep_scan.get("origin_skill_id")
            scan_step = int(state.deep_scan.get("items_used", 0)) + 1
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
            task_snapshot=copy.deepcopy(state.current_task_snapshot),
            deep_scan_origin_skill_id=scan_origin,
            deep_scan_step=scan_step,
        )
        # Inspect the navigation consequence before accepting an early stop.
        # Otherwise the final failed skill can end the test before the critical
        # prerequisite scan it is supposed to trigger.
        pending_probe = self._has_pending_critical_probe(state, correct)
        if self._should_stop(state, pending_critical_probe=pending_probe):
            return self._complete_session(state, outcome, category)

        # 9. Advance navigation → pick next task
        next_task = self._advance(state, correct)

        if next_task is None:
            if state.stop_reason is None:
                # Exhaustion fallback:
                # If target precision was not met, mark insufficient_precision
                if state.theta.se > settings.se_threshold:
                    state.stop_reason = "insufficient_precision"
                elif state.current_section_idx >= len(state.section_ids):
                    state.stop_reason = "precision_reached" if state.theta.se <= settings.se_threshold else "coverage_complete"
                else:
                    state.stop_reason = "bank_exhausted"
            return self._complete_session(state, outcome, category)

        # 10. Save updated state
        self.db.commit()
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

        report_generation = {
            "status": report.generation_status if report else "pending",
            "stage": report.generation_stage if report else "queued",
            "attempts": int(report.generation_attempts or 0) if report else 0,
            "is_current_schema": bool(
                report
                and report.report_json
                and report.report_schema_version >= REPORT_SCHEMA_VERSION
                and report.generation_status == "ready"
            ),
        }

        return {
            "session_id": str(session_id),
            "student_id": str(db_session.student_id),
            "grade_level": db_session.grade_level,
            "overall_theta": theta,
            "overall_level": db_session.overall_level or "at_grade",
            # Same level object as report_json.level (computed by level_policy).
            "level": report_json.get("level") or {
                **classify(theta, se, db_session.grade_level),
                "theta": theta, "se": se,
                **count_solved(answers),
            },
            "confidence_interval": [theta - 2 * se, theta + 2 * se],
            "topic_breakdown": db_session.topic_breakdown or {},
            "weak_skills": db_session.weak_skills or [],
            "recommended_start": (
                db_session.weak_skills[0] if db_session.weak_skills else None
            ),
            "items_total": len(answers),
            "total_time_ms": sum(answer.time_ms or 0 for answer in answers),
            "stop_reason": db_session.stop_reason,
            # Unified journal: error_patterns + full report_json
            "error_patterns": error_patterns,
            "distractor_errors": [
                ep for ep in error_patterns
                if isinstance(ep, dict) and ep.get("eval_category") == "distractor"
            ],
            "report_json": report_json,
            # Explicit flag so frontend knows full report is available
            "has_full_report": bool(report_json),
            # The public invite route remains informative without disclosing
            # raw worker exceptions or implementation details.
            "report_generation": report_generation,
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

    @staticmethod
    def _warmup_target_count(state: SessionState) -> int:
        return min(len(state.section_ids), settings.warmup_items)

    @staticmethod
    def _ensure_current_task(state: SessionState, task_id: str) -> None:
        if task_id != state.current_task_id:
            raise TaskOutOfSequenceError(state.session_id)

    @staticmethod
    def _has_minimum_section_coverage(state: SessionState) -> bool:
        required = min(len(state.section_ids), settings.min_section_coverage)
        covered = set(state.covered_section_ids) & set(state.section_ids)
        return len(covered) >= required

    def _pick_warmup_task(self, state: SessionState) -> TaskOut:
        """
        Pick a warmup task centered around current theta.
        Distributes warmup items across L1 sections so the baseline is not
        dominated by the first curricular domain.
        """
        warmup_count = self._warmup_target_count(state)
        if warmup_count <= 0:
            raise GradeNotConfiguredError(state.grade_level)
        # Baseline questions are distributed across L1 sections, not only the
        # first one.  This gives the early theta estimate cross-domain support.
        section_id = state.section_ids[state.items_answered % warmup_count]
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
        state.current_section_id = section_id
        state.current_skill_id = selected_skill_id
        state.current_topic_id = topic.topic_id
        state.current_subtopic_id = selected_sub_id

        return self._task_to_out(task, state)

    # ── Answer evaluation ──────────────────────────────────────────────────

    # ── Stopping criteria ─────────────────────────────────────────────────

    @staticmethod
    def _deep_scan_budget_spent(state: SessionState) -> bool:
        """True once the session's Deep Scan items reached DEEP_SCAN_SESSION_BUDGET."""
        return state.deep_scan_items_total >= settings.deep_scan_session_budget

    def _has_pending_critical_probe(self, state: SessionState, correct: bool) -> bool:
        """Preview the current L4 answer without mutating persisted navigation."""
        if state.phase != "navigation" or not state.current_skill_nav or not state.current_subtopic_nav:
            return False
        skills = SkillNavigator.from_dict(copy.deepcopy(state.current_skill_nav))
        subtopics = SubtopicNavigator.from_dict(state.current_subtopic_nav)
        current = subtopics.peek_current()
        if current is None or current.importance < settings.deep_scan_importance_threshold:
            return False
        if self._deep_scan_budget_spent(state):
            return False   # no scan can start, so there is nothing pending
        next_skill = skills.move(correct)
        if not skills.get_failing_skill():
            return False
        if next_skill is not None:
            # Finish measuring this important failed subtopic before deciding
            # whether its prerequisites need a causal probe.
            return True
        return skills.subtopic_score() < settings.mastery_threshold

    def _should_stop(self, state: SessionState, *, pending_critical_probe: bool = False) -> bool:
        if state.items_answered >= settings.max_items:
            state.stop_reason = "max_items_reached"
            if state.is_in_deep_scan or pending_critical_probe:
                state.deep_scan_incomplete = True
            return True
        if state.is_in_deep_scan or pending_critical_probe:
            return False
        if state.items_answered < settings.min_items:
            return False
        if not self._has_minimum_section_coverage(state):
            return False
        if state.theta.se <= settings.se_threshold:
            state.stop_reason = "precision_reached"
            return True
        if (
            state.items_answered >= settings.classification_min_items
            and state.theta.se <= settings.classification_se_threshold
            and level_confidence(state.theta) >= settings.classification_confidence_threshold
        ):
            state.stop_reason = "classification_confident"
            return True
        return False

    # ── Navigation dispatcher ─────────────────────────────────────────────

    def _advance(self, state: SessionState, correct: bool) -> Optional[TaskOut]:
        self._restore_fallback_context(state)
        if state.phase == "warmup":
            return self._advance_warmup(state, correct)
        if state.phase == "navigation":
            return self._advance_navigation(state, correct)
        if state.phase == "deep_scan":
            return self._advance_deep_scan(state, correct)
        if state.phase == "precision_targeting":
            return self._advance_precision_targeting(state, correct)
        return None

    def _advance_precision_targeting(self, state: SessionState, correct: bool) -> Optional[TaskOut]:
        return self._pick_precision_targeting_task(state)

    # ── Warmup phase ──────────────────────────────────────────────────────

    def _advance_warmup(self, state: SessionState, correct: bool) -> Optional[TaskOut]:
        if state.items_answered >= self._warmup_target_count(state):
            state.phase = "navigation"
            return self._start_navigation(state)
        return self._pick_warmup_task(state)

    # ── Navigation phase ──────────────────────────────────────────────────

    def _start_navigation(self, state: SessionState) -> Optional[TaskOut]:
        """Initialize subtopic navigation for current L1 section's current topic."""
        section_id = state.section_ids[state.current_section_idx]
        state.current_section_id = section_id
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
                    and not self._deep_scan_budget_spent(state)
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
            return self._pick_task_for_navigation(state, next_skill.skill_id)

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
        return self._pick_task_for_navigation(state, mid_skill.skill_id)

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
        """Advance sections, then keep measuring until a stopping rule is met."""
        state.current_section_idx += 1
        if state.current_section_idx >= len(state.section_ids):
            # All L1 sections traversed.
            # Use the same policy as answer submission.  A small SE alone
            # must not bypass the minimum answers or cross-section coverage.
            if self._should_stop(state):
                return None

            # Precision or baseline coverage is incomplete: keep collecting
            # evidence even if the section navigators have been exhausted.
            log.info(
                "Sections traversed; stopping policy not met (SE=%.2f, strict_threshold=%.2f, items=%d/%d). Entering precision_targeting",
                state.theta.se,
                settings.se_threshold,
                state.items_answered,
                settings.max_items,
            )
            state.phase = "precision_targeting"
            state.current_subtopic_nav = None
            state.current_skill_nav = None
            return self._pick_precision_targeting_task(state)

        state.current_subtopic_nav = None
        state.current_skill_nav = None
        return self._start_navigation(state)

    def _pick_precision_targeting_task(self, state: SessionState) -> Optional[TaskOut]:
        """Phase 2 CAT precision targeting: select IRT-informative tasks targeting b ≈ theta.

        For students performing below grade level (theta < -0.5), we expand the candidate pool
        to include foundational prerequisite skills from lower grades (Grade - 1, and if theta < -1.5,
        down to Grade - 2, with a floor of grade 5).

        Priority 1: Direct prerequisite skills linked to confirmed gaps / failed topics from Phase 1.
        Priority 2: Foundational core L4 skills from target lower grade(s) matching target_b ≈ theta.
        Priority 3: Available L4 skills in the current grade matching target_b ≈ theta.
        """
        current_grade = state.grade_level
        theta_val = state.theta.theta
        candidate_skills_ordered: List[str] = []
        visited_skills: set = set()

        if theta_val < -0.5:
            # 1. Target Lower Grades Pool
            min_grade = max(5, current_grade - 2 if theta_val < -1.5 else current_grade - 1)
            lower_grades = list(range(min_grade, current_grade))

            # Priority 1: Prerequisites of confirmed gaps / failed skills
            prereq_candidates: List[str] = []
            for gap_id in state.confirmed_gaps:
                try:
                    for pr_l4 in self._prereq_l4_ids(gap_id):
                        if pr_l4 not in visited_skills:
                            visited_skills.add(pr_l4)
                            prereq_candidates.append(pr_l4)
                except Exception as exc:
                    log.warning("Failed to resolve prereq L4s for gap %s: %s", gap_id, exc)

            random.shuffle(prereq_candidates)
            candidate_skills_ordered.extend(prereq_candidates)

            # Priority 2: Foundational L4 skills from lower grade(s)
            for g in lower_grades:
                lower_skills = self.knowledge_repo.get_by_level_and_grade("L4", g)
                lower_skill_ids = [s.id for s in lower_skills if s.id not in visited_skills]
                for sid in lower_skill_ids:
                    visited_skills.add(sid)
                random.shuffle(lower_skill_ids)
                candidate_skills_ordered.extend(lower_skill_ids)

        # Priority 3 (or Priority 1 for students with theta >= -0.5): Current grade L4 skills
        current_skills = self.knowledge_repo.get_by_level_and_grade("L4", current_grade)
        current_skill_ids = [s.id for s in current_skills if s.id not in visited_skills]
        for sid in current_skill_ids:
            visited_skills.add(sid)
        random.shuffle(current_skill_ids)
        candidate_skills_ordered.extend(current_skill_ids)

        if not candidate_skills_ordered:
            log.warning("No candidate skills found in precision targeting for grade %d", current_grade)
            state.stop_reason = "insufficient_precision"
            return None

        # Search for a task matching target_b ≈ theta in candidate skills
        for skill_id in candidate_skills_ordered:
            task = self.task_repo.get_task_by_difficulty_target(
                skill_id, target_b=theta_val, exclude_ids=state.used_task_ids
            )
            if task is not None:
                self._set_context_for_skill(state, skill_id)
                state.current_task_id = task.id
                log.info(
                    "Precision targeting selected task %s (skill %s, target_b=%.2f, current_se=%.2f, theta=%.2f)",
                    task.id,
                    skill_id,
                    theta_val,
                    state.theta.se,
                    theta_val,
                )
                return self._task_to_out(task, state)

        # Fallback: if difficulty-matching task wasn't found, pick any available task from candidate pool
        for skill_id in candidate_skills_ordered:
            tasks = self.task_repo.get_tasks_for_skill(
                skill_id, exclude_ids=state.used_task_ids, limit=1
            )
            if tasks:
                task = tasks[0]
                self._set_context_for_skill(state, skill_id)
                state.current_task_id = task.id
                log.info(
                    "Precision targeting fallback selected task %s (skill %s, current_se=%.2f)",
                    task.id,
                    skill_id,
                    state.theta.se,
                )
                return self._task_to_out(task, state)

        log.warning(
            "Precision targeting exhausted available tasks in bank for grade %d (SE=%.2f, items=%d)",
            current_grade,
            state.theta.se,
            state.items_answered,
        )
        state.stop_reason = "insufficient_precision"
        return None

    # ── Deep scan phase ───────────────────────────────────────────────────

    def _set_context_for_skill(self, state: SessionState, skill_id: str) -> None:
        """Set the real L4 → L3 → L2 → L1 context for a task.

        Deep-scan prerequisites can belong to a different topic than the
        failed skill.  Keeping the origin context would corrupt the answer log
        and topic-level report, so resolve it explicitly before issuing a task.
        """
        skill = self.knowledge_repo.get_by_id(skill_id)
        subtopic = (
            self.knowledge_repo.get_by_id(skill.parent_id)
            if skill is not None and getattr(skill, "parent_id", None)
            else None
        )
        topic = (
            self.knowledge_repo.get_by_id(subtopic.parent_id)
            if subtopic is not None and getattr(subtopic, "parent_id", None)
            else None
        )
        if topic is None:
            log.warning("Cannot resolve L1/L2 context for deep-scan skill %s", skill_id)
            state.current_skill_id = skill_id
            state.current_subtopic_id = None
            state.current_topic_id = None
            state.current_section_id = None
            return

        state.current_skill_id = skill_id
        state.current_subtopic_id = getattr(subtopic, "id", None)
        state.current_topic_id = topic.id
        state.current_section_id = getattr(topic, "parent_id", None)

    @staticmethod
    def _most_important_l4(children: list) -> Optional[str]:
        """Pick the L4 skill to probe for an L3 prerequisite.

        Importance is the knowledge-node ``importance`` field (1–10, default 5).
        The highest importance wins; among equally important children the
        middle one by ``sequence_order`` is taken (the former behaviour, a
        representative difficulty), with the id as the final tie-break so the
        choice never depends on database row order.
        """
        if not children:
            return None
        ordered = sorted(
            children,
            key=lambda c: (int(getattr(c, "sequence_order", 0) or 0), str(c.id)),
        )
        top = max(int(getattr(c, "importance", 5) or 5) for c in ordered)
        best = [c for c in ordered if int(getattr(c, "importance", 5) or 5) == top]
        return best[len(best) // 2].id

    def _prereq_l4_ids(self, skill_or_para_id: str) -> List[str]:
        """
        Resolve a failing L4 skill to a list of testable prerequisite L4 skill IDs.

        Data model: skill_prerequisites stores L3 (paragraph) → L3 links.
        Algorithm:
          1. If input is L4 → map to its parent L3 paragraph via parent_id.
          2. Look up hard prerequisites for that L3 paragraph.
          3. For each prerequisite L3 paragraph → resolve to its most important L4 child
             (see ``_most_important_l4``); order is criticality, weight, id.
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
        # ``prereqs`` arrive in a stable order: criticality desc, weight desc, id.
        for p in prereqs:
            prereq_id = p.prerequisite_id
            # prerequisite_id is typically an L3 paragraph → resolve to its most
            # important L4 child
            prereq_node = self.knowledge_repo.get_by_id(prereq_id)
            if prereq_node is None:
                log.warning("_prereq_l4_ids: prereq node not found for %s", prereq_id)
                continue
            if prereq_node.level == "L3":
                children = self.knowledge_repo.get_skills_for_subtopic(prereq_id)
                chosen = self._most_important_l4(children)
                if chosen is not None and chosen not in result:
                    result.append(chosen)
                    log.debug("_prereq_l4_ids: L3 %s → L4 child %s", prereq_id, chosen)
            elif prereq_node.level == "L4":
                # Already L4 — future-proof for direct L4 prerequisite links
                if prereq_id not in result:
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
        prereq_ids = [
            pid for pid in self._prereq_l4_ids(failing_skill_id)
            if pid not in state.deep_scan_tested and pid != failing_skill_id
        ]

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

        # Snapshot pre-deep-scan navigation context so traversing prerequisites
        # in other topics or lower grades does not corrupt current section navigation.
        state.saved_nav_context = {
            "section_idx": state.current_section_idx,
            "section_id": state.current_section_id,
            "topic_id": state.current_topic_id,
            "subtopic_id": state.current_subtopic_id,
            "skill_id": state.current_skill_id,
        }

        return self._next_deep_scan_task(state, scan)

    def _advance_deep_scan(
        self, state: SessionState, correct: bool
    ) -> Optional[TaskOut]:
        """Process one step of the deep scan prerequisite traversal."""
        if state.deep_scan is None:
            state.phase = "navigation"
            state.is_in_deep_scan = False
            if state.saved_nav_context:
                ctx = state.saved_nav_context
                state.current_section_idx = ctx.get("section_idx", state.current_section_idx)
                state.current_section_id = ctx.get("section_id")
                state.current_topic_id = ctx.get("topic_id")
                state.current_subtopic_id = ctx.get("subtopic_id")
                state.current_skill_id = ctx.get("skill_id")
                state.saved_nav_context = None
            return self._advance_topic(state, False)

        scan = DeepScanState.from_dict(state.deep_scan)
        scan.items_used += 1
        state.deep_scan_items_total += 1

        if scan.current_skill_id:
            scan.tested.append(scan.current_skill_id)

        budget_exceeded = (
            scan.items_used >= scan.max_items or self._deep_scan_budget_spent(state)
        )
        queue_empty = len(scan.queue) == 0

        if correct:
            # The student can do this prerequisite: this BRANCH is closed (its own
            # prerequisites are not descended into).  Other branches still waiting
            # in the queue are probed — the scan is bounded by max_items and by the
            # queue, not ended by the first correct answer.
            if budget_exceeded or queue_empty:
                self._finish_deep_scan(state, scan)
                return self._advance_topic(state, False)
            return self._next_deep_scan_task(state, scan)

        # Incorrect: this skill is a gap
        if scan.current_skill_id:
            scan.gaps.append(scan.current_skill_id)

        if budget_exceeded:
            self._finish_deep_scan(state, scan)
            return self._advance_topic(state, False)

        # Go deeper, whatever is left in the queue: a failed probe makes ITS OWN
        # prerequisites the next thing to test (depth first, ahead of the other
        # branches).  Skills already tested in this scan or in an earlier scan of
        # the session, already queued, or the scan's trigger are never repeated.
        # No prerequisites -> this skill is the root and the descent stops here
        # (the helper finishes the scan when nothing else is queued).
        if scan.current_skill_id:
            seen = set(scan.tested) | set(state.deep_scan_tested) | set(scan.queue) | {scan.origin_skill_id}
            new_prereqs = [
                pid for pid in self._prereq_l4_ids(scan.current_skill_id) if pid not in seen
            ]
            scan.queue = new_prereqs + scan.queue

        return self._next_deep_scan_task(state, scan)

    def _next_deep_scan_task(
        self, state: SessionState, scan: DeepScanState
    ) -> Optional[TaskOut]:
        """Issue the next probe from the queue, skipping skills with no unused task.

        A prerequisite without tasks is not evidence of anything (neither gap nor
        mastery): it is marked tested-without-answer and the next queued skill is
        tried.  Returning ``None`` here would make the caller complete the whole
        session as ``bank_exhausted``, so an exhausted queue instead finishes the
        scan and resumes the main CAT flow.
        """
        while scan.queue:
            next_skill_id = scan.queue.pop(0)
            scan.current_skill_id = next_skill_id
            self._set_context_for_skill(state, next_skill_id)
            task = self._pick_task_for_skill(state, next_skill_id)
            if task is not None:
                state.deep_scan = scan.to_dict()
                return task
            log.warning("Deep scan: no unused task for %s, skipping to next branch", next_skill_id)
            scan.tested.append(next_skill_id)
        scan.current_skill_id = None
        self._finish_deep_scan(state, scan)
        return self._advance_topic(state, False)

    def _finish_deep_scan(self, state: SessionState, scan: DeepScanState) -> None:
        """Finalize deep scan: collect gaps, reset flags and restore navigation context."""
        state.confirmed_gaps.extend(scan.gaps)
        for skill in scan.tested:
            if skill not in state.deep_scan_tested:
                state.deep_scan_tested.append(skill)
        if scan.origin_skill_id not in state.confirmed_gaps:
            state.confirmed_gaps.append(scan.origin_skill_id)
        state.deep_scan = None
        state.is_in_deep_scan = False
        state.phase = "navigation"

        # Restore pre-deep-scan navigation context
        if state.saved_nav_context:
            ctx = state.saved_nav_context
            state.current_section_idx = ctx.get("section_idx", state.current_section_idx)
            state.current_section_id = ctx.get("section_id")
            state.current_topic_id = ctx.get("topic_id")
            state.current_subtopic_id = ctx.get("subtopic_id")
            state.current_skill_id = ctx.get("skill_id")
            state.saved_nav_context = None

    # ── Task selection ─────────────────────────────────────────────────────

    def _select_task_for_skill(self, state: SessionState, skill_id: str):
        """IRT-nearest unused task for a skill, any unused task, or None."""
        task = self.task_repo.get_task_by_difficulty_target(
            skill_id, target_b=state.theta.theta, exclude_ids=state.used_task_ids
        )
        if task is None:
            tasks = self.task_repo.get_tasks_for_skill(
                skill_id, exclude_ids=state.used_task_ids, limit=1
            )
            if not tasks:
                log.warning("No unused tasks for skill %s", skill_id)
                return None
            task = tasks[0]
        return task

    def _pick_task_for_skill(
        self, state: SessionState, skill_id: str
    ) -> Optional[TaskOut]:
        """Select the IRT-optimal task for a skill at current theta."""
        task = self._select_task_for_skill(state, skill_id)
        if task is None:
            return None
        state.current_task_id = task.id
        state.current_skill_id = skill_id
        return self._task_to_out(task, state)

    # ── Fallback when a navigation skill has no unanswered task ────────────

    def _pick_task_for_navigation(
        self, state: SessionState, skill_id: str
    ) -> Optional[TaskOut]:
        """Task for the L4 the navigator points at; never ends the session just
        because that one skill is empty or already exhausted for this student."""
        task = self._pick_task_for_skill(state, skill_id)
        if task is not None:
            return task
        return self._fallback_task(state, skill_id)

    def _fallback_skill_candidates(self, state: SessionState, skill_id: str):
        """Yield L4 ids in fallback order: the other L4s of the same L3, the L4s
        of the other L3s of the same L2, then the L4s of the other L2s of the
        grade (same L1 section first).  Each group starts after the failed
        element and wraps, so the order is deterministic and close in the tree."""

        def rotated(items, current_id):
            ids = [i.id for i in items]
            if current_id in ids:
                k = ids.index(current_id) + 1
                return ids[k:] + ids[:k]
            return ids

        def l4_of(l3_id):
            for sk in self.knowledge_repo.get_skills_for_subtopic(l3_id):
                yield sk.id

        l4 = self.knowledge_repo.get_by_id(skill_id)
        l3 = self.knowledge_repo.get_by_id(l4.parent_id) if l4 is not None and l4.parent_id else None
        l2 = self.knowledge_repo.get_by_id(l3.parent_id) if l3 is not None and l3.parent_id else None
        l3_id = getattr(l3, "id", None)
        l2_id = getattr(l2, "id", None)

        if l3_id:   # 1) same L3
            sibs = self.knowledge_repo.get_skills_for_subtopic(l3_id)
            for sid in rotated(sibs, skill_id):
                yield sid
        if l2_id:   # 2) same L2
            subs = self.knowledge_repo.get_subtopics_for_topic(l2_id)
            for sub_id in rotated(subs, l3_id):
                if sub_id != l3_id:
                    yield from l4_of(sub_id)
        # 3) other L2 topics of the grade; the current L1 section first
        topics = self.knowledge_repo.get_by_level_and_grade("L2", state.grade_level)
        section = getattr(l2, "parent_id", None)
        ordered = rotated(topics, l2_id)
        by_id = {t.id: t for t in topics}
        ordered.sort(key=lambda tid: 0 if section and by_id[tid].parent_id == section else 1)  # stable
        for topic_id in ordered:
            if topic_id == l2_id:
                continue
            for sub in self.knowledge_repo.get_subtopics_for_topic(topic_id):
                yield from l4_of(sub.id)

    def _fallback_task(self, state: SessionState, empty_skill_id: str) -> Optional[TaskOut]:
        """Serve an unanswered task from the nearest other L4; None only when the
        whole grade pool has no unanswered task left."""
        tried = {empty_skill_id}
        try:
            for sid in self._fallback_skill_candidates(state, empty_skill_id):
                if sid in tried:
                    continue
                tried.add(sid)
                task = self._select_task_for_skill(state, sid)
                if task is None:
                    continue
                if state.fallback_nav_context is None:
                    state.fallback_nav_context = {
                        "section_id": state.current_section_id,
                        "topic_id": state.current_topic_id,
                        "subtopic_id": state.current_subtopic_id,
                    }
                self._set_context_for_skill(state, sid)   # attribute the answer to the real skill
                state.current_task_id = task.id
                log.info("Fallback task %s (skill %s) instead of exhausted skill %s",
                         task.id, sid, empty_skill_id)
                return self._task_to_out(task, state)
        except Exception as exc:   # content outage: keep the old behaviour (end), but say why
            log.warning("Fallback search failed for %s: %s", empty_skill_id, exc)
            return None
        log.warning("Grade %s pool exhausted (no unanswered task, last skill %s)",
                    state.grade_level, empty_skill_id)
        return None

    @staticmethod
    def _restore_fallback_context(state: SessionState) -> None:
        """After a fallback item is answered, point the cursor-side context back
        at the navigator's own section/topic/subtopic."""
        ctx = state.fallback_nav_context
        if ctx is None:
            return
        state.current_section_id = ctx.get("section_id")
        state.current_topic_id = ctx.get("topic_id")
        state.current_subtopic_id = ctx.get("subtopic_id")
        state.fallback_nav_context = None

    # ── Session completion ─────────────────────────────────────────────────

    def _complete_session(
        self, state: SessionState, outcome: float, category: str
    ) -> AnswerResult:
        """Finalize: persist to DB, remove from Redis, return result."""
        state.phase = "completed"
        if state.stop_reason is None:
            # Completion without a next task is never silently treated as a
            # precise result.  This default is mainly a guard for legacy paths.
            state.stop_reason = "bank_exhausted"

        topic_breakdown = {
            topic_id: {
                "alpha": alpha,
                "level": theta_to_level(alpha),
                # Observation count (AlphaTracker): lets the report require
                # >= 2 observations before calling a topic weak.
                "observations": state.alpha_tracker.get_count(topic_id),
            }
            for topic_id, alpha in state.alpha_tracker.get_all().items()
        }
        overall_level = classify(state.theta.theta, state.theta.se, state.grade_level)["category"]

        db_session = self.session_repo.get_by_id(uuid.UUID(state.session_id))
        if db_session is None:
            raise SessionNotFoundError(state.session_id)
        self.session_repo.mark_completed(
            db_session,
            theta=state.theta.theta,
            theta_se=state.theta.se,
            level=overall_level,
            weak_skills=state.confirmed_gaps,
            topic_breakdown=topic_breakdown,
            state_snapshot=state.to_dict(),
            items_answered=state.items_answered,
            stop_reason=state.stop_reason,
        )
        # The final answer, completed snapshot and BOTH durable jobs are one
        # transaction. A crash cannot leave an accepted result without the
        # work needed to produce its report and update the admin projection.
        enqueue_report_generation(self.db, db_session.id, commit=False)
        enqueue_auth_completion_sync(self.db, db_session, commit=False)
        self.db.commit()

        self.redis.delete(state.session_id)
        log.info(
            "Session %s completed: theta=%.3f se=%.3f level=%s gaps=%d stop_reason=%s classification_confidence=%.3f",
            state.session_id,
            state.theta.theta,
            state.theta.se,
            overall_level,
            len(state.confirmed_gaps),
            state.stop_reason,
            level_confidence(state.theta),
        )

        # Both derived report generation and the auth-service projection are
        # durable queues.  The threads only reduce first-response latency;
        # the lifespan worker resumes either job after a restart.
        try:
            import threading
            threading.Thread(target=process_next_report_job, daemon=True).start()
            threading.Thread(target=process_next_auth_completion_sync, daemon=True).start()
        except Exception as exc:
            log.warning("diagnostic_worker_acceleration_failed session_id=%s error_type=%s", db_session.id, type(exc).__name__)

        return AnswerResult(
            is_correct=is_correct(outcome),
            outcome=outcome,
            eval_category=category,
            theta=state.theta.theta,
            se=state.theta.se,
            next_task=None,
            session_completed=True,
            stop_reason=state.stop_reason,
        )

    # ── Utilities ──────────────────────────────────────────────────────────

    def _task_to_out(self, task: TaskMaster, state: SessionState, *, capture: bool = True) -> TaskOut:
        snapshot = state.current_task_snapshot
        if snapshot is not None and snapshot.get('task', {}).get('id') == task.id:
            payload = read_task(snapshot, task.id)
            task = task_object(snapshot, task.id)
            options = payload['display_options']
            options_latex = payload['display_options_latex']
            answer_type = payload['display_answer_type']
        else:
            options, options_latex = build_diag_answer_options(task, seed=f"{state.session_id}:{task.id}")
            answer_type = diag_answer_type_for_display(task, options)
            if capture:
                state.current_task_snapshot = capture_task(task, options, options_latex, answer_type)
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
            answer_type=answer_type,
            answer_options=options,
            answer_options_latex=options_latex,
            phase=state.phase,
            items_answered=state.items_answered,
            items_max=settings.max_items,
            is_deep_scan=state.is_in_deep_scan,
        )
