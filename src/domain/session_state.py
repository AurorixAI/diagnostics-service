"""
Diagnostic Service — SessionState

The complete in-memory state of one diagnostic session.
Serialized to/from plain JSON for Redis storage (NO Pickle).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.domain.alpha_engine import AlphaTracker, ThetaState


@dataclass
class SessionState:
    """
    Full serializable state for a diagnostic session.
    Stored in Redis as JSON. Reconstructed on every request.
    """

    session_id: str
    student_id: str
    grade_level: int

    # Phase: warmup | navigation | deep_scan | completed
    phase: str = "warmup"

    # IRT & topic mastery
    theta: ThetaState = field(default_factory=ThetaState)
    alpha_tracker: AlphaTracker = field(default_factory=AlphaTracker)

    # Item tracking
    items_answered: int = 0
    used_task_ids: List[str] = field(default_factory=list)

    # Section (L1) iteration
    current_section_idx: int = 0
    section_ids: List[str] = field(default_factory=list)
    current_section_id: Optional[str] = None
    covered_section_ids: List[str] = field(default_factory=list)

    # Navigator states (serialized as plain dicts)
    topic_navigator_states: Dict[str, dict] = field(default_factory=dict)
    current_subtopic_nav: Optional[dict] = None
    current_skill_nav: Optional[dict] = None
    deep_scan: Optional[dict] = None

    # Current task context
    current_task_id: Optional[str] = None
    current_task_snapshot: Optional[dict] = None
    current_skill_id: Optional[str] = None
    current_topic_id: Optional[str] = None
    current_subtopic_id: Optional[str] = None
    is_in_deep_scan: bool = False

    # Gaps found by deep scan
    confirmed_gaps: List[str] = field(default_factory=list)
    deep_scan_incomplete: bool = False
    saved_nav_context: Optional[dict] = None
    # Skills already probed by finished Deep Scans of this session: a later scan
    # never re-queues them.
    deep_scan_tested: List[str] = field(default_factory=list)
    # Deep Scan items answered so far in the whole session (session budget).
    deep_scan_items_total: int = 0
    # Probed skills whose gap was NOT confirmed (DEEP_SCAN_CONFIRM_PROBES > 1: wrong
    # answers short of the required number and no unused item left).  Not gaps.
    deep_scan_unconfirmed: List[str] = field(default_factory=list)

    # Navigation context to restore after a one-off fallback task (see
    # SessionService._fallback_task): the item came from a different L4/L3/L2
    # than the navigator is pointing at, so its answer is attributed to the real
    # skill but the cursor-side context must go back afterwards.
    fallback_nav_context: Optional[dict] = None

    # Why the diagnostic ended.  This is persisted into the final session and
    # report so a max-length result is never presented as a precision result.
    stop_reason: Optional[str] = None

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "student_id": self.student_id,
            "grade_level": self.grade_level,
            "phase": self.phase,
            "theta": {
                "theta": self.theta.theta,
                "se": self.theta.se,
                "posterior": self.theta.posterior,
            },
            "alpha_tracker": self.alpha_tracker.to_dict(),
            "items_answered": self.items_answered,
            "used_task_ids": self.used_task_ids,
            "current_section_idx": self.current_section_idx,
            "section_ids": self.section_ids,
            "current_section_id": self.current_section_id,
            "covered_section_ids": self.covered_section_ids,
            "topic_navigator_states": self.topic_navigator_states,
            "current_subtopic_nav": self.current_subtopic_nav,
            "current_skill_nav": self.current_skill_nav,
            "deep_scan": self.deep_scan,
            "current_task_id": self.current_task_id,
            "current_task_snapshot": self.current_task_snapshot,
            "current_skill_id": self.current_skill_id,
            "current_topic_id": self.current_topic_id,
            "current_subtopic_id": self.current_subtopic_id,
            "is_in_deep_scan": self.is_in_deep_scan,
            "confirmed_gaps": self.confirmed_gaps,
            "deep_scan_incomplete": self.deep_scan_incomplete,
            "saved_nav_context": self.saved_nav_context,
            "deep_scan_tested": self.deep_scan_tested,
            "deep_scan_items_total": self.deep_scan_items_total,
            "deep_scan_unconfirmed": self.deep_scan_unconfirmed,
            "fallback_nav_context": self.fallback_nav_context,
            "stop_reason": self.stop_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        theta_d = data["theta"]
        theta = ThetaState(
            theta=theta_d["theta"],
            se=theta_d["se"],
            posterior=theta_d["posterior"],
        )
        alpha = AlphaTracker.from_dict(data["alpha_tracker"])

        return cls(
            session_id=data["session_id"],
            student_id=data["student_id"],
            grade_level=data["grade_level"],
            phase=data["phase"],
            theta=theta,
            alpha_tracker=alpha,
            items_answered=data["items_answered"],
            used_task_ids=data["used_task_ids"],
            current_section_idx=data.get("current_section_idx", 0),
            section_ids=data.get("section_ids", []),
            current_section_id=data.get("current_section_id"),
            covered_section_ids=data.get("covered_section_ids", []),
            topic_navigator_states=data.get("topic_navigator_states", {}),
            current_subtopic_nav=data.get("current_subtopic_nav"),
            current_skill_nav=data.get("current_skill_nav"),
            deep_scan=data.get("deep_scan"),
            current_task_id=data.get("current_task_id"),
            current_task_snapshot=data.get("current_task_snapshot"),
            current_skill_id=data.get("current_skill_id"),
            current_topic_id=data.get("current_topic_id"),
            current_subtopic_id=data.get("current_subtopic_id"),
            is_in_deep_scan=data.get("is_in_deep_scan", False),
            confirmed_gaps=data.get("confirmed_gaps", []),
            deep_scan_incomplete=data.get("deep_scan_incomplete", False),
            saved_nav_context=data.get("saved_nav_context"),
            deep_scan_tested=data.get("deep_scan_tested", []),
            deep_scan_items_total=data.get("deep_scan_items_total", 0),
            deep_scan_unconfirmed=data.get("deep_scan_unconfirmed", []),
            fallback_nav_context=data.get("fallback_nav_context"),
            stop_reason=data.get("stop_reason"),
        )
