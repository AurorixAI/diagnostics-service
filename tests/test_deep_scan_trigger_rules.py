"""DIAG-1 stage 3b: Deep Scan trigger discrimination behind config flags.

  DEEP_SCAN_TRIGGER_RULE   "current" (default) | "d1" | "d2"   - what a failed L3 must also show to start a scan
  DEEP_SCAN_RESIDUAL_MIN   threshold of the d2 residual sum(p_hat - x)                     (default 1.0)
  DEEP_SCAN_PROBE_MIN_P    D3: a probe whose expected p of a correct answer is below this is not spent  (default 0 = off)

The defaults must reproduce the previous behaviour exactly; the rules are frozen per session and the early-stop preview
(`_has_pending_critical_probe`) must answer the same question as the answer path (`_advance_navigation`).
"""
import copy
import itertools
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.domain import session_service as ss
from src.domain.alpha_engine import IRTParams, ThetaState, p_correct
from src.domain.navigators.skill_navigator import DeepScanState, SkillEntry, SkillNavigator
from src.domain.navigators.subtopic_navigator import SubtopicEntry, SubtopicNavigator
from src.domain.session_service import SessionService
from src.domain.session_state import SessionState
from tests.test_deep_scan_variants import (
    EDGE, answering_service, make_service, scanning_state, service_with_edges, set_live,
)


# ── config ────────────────────────────────────────────────────────────────────

def clean_env(monkeypatch):
    for name in ("DEEP_SCAN_TRIGGER_RULE", "DEEP_SCAN_RESIDUAL_MIN", "DEEP_SCAN_PROBE_MIN_P"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_reproduce_the_previous_behaviour(monkeypatch):
    clean_env(monkeypatch)
    st = Settings(_env_file=None)
    assert (st.deep_scan_trigger_rule, st.deep_scan_residual_min, st.deep_scan_probe_min_p) == ("current", 1.0, 0.0)


def test_flags_are_overridable_from_the_environment(monkeypatch):
    clean_env(monkeypatch)
    monkeypatch.setenv("DEEP_SCAN_TRIGGER_RULE", "d2")
    monkeypatch.setenv("DEEP_SCAN_RESIDUAL_MIN", "1.5")
    monkeypatch.setenv("DEEP_SCAN_PROBE_MIN_P", "0.3")
    st = Settings(_env_file=None)
    assert (st.deep_scan_trigger_rule, st.deep_scan_residual_min, st.deep_scan_probe_min_p) == ("d2", 1.5, 0.3)


@pytest.mark.parametrize("name,value", [
    ("DEEP_SCAN_TRIGGER_RULE", "d3"), ("DEEP_SCAN_TRIGGER_RULE", ""),
    ("DEEP_SCAN_RESIDUAL_MIN", "0"), ("DEEP_SCAN_RESIDUAL_MIN", "-1"), ("DEEP_SCAN_RESIDUAL_MIN", "nan"),
    ("DEEP_SCAN_PROBE_MIN_P", "-0.1"), ("DEEP_SCAN_PROBE_MIN_P", "1.1"), ("DEEP_SCAN_PROBE_MIN_P", "nan"),
])
def test_invalid_flag_values_are_rejected(monkeypatch, name, value):
    clean_env(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# ── helpers: an L3 visit one answer before its end ────────────────────────────

def visit_outcomes(n_l4):
    """Every possible correctness sequence of one L3 visit (binary search over ``n_l4`` skills)."""
    skills = [SkillEntry(f"S{i}", "L3", i, float(i)) for i in range(n_l4)]
    found = []

    def rec(nav, seq):
        for ok in (True, False):
            nxt = SkillNavigator.from_dict(copy.deepcopy(nav))
            more = nxt.move(ok)
            if more is None:
                found.append(seq + [ok])
            else:
                rec(nxt.to_dict(), seq + [ok])

    rec(SkillNavigator.create("L3", skills).to_dict(), [])
    return found


def visit_state(n_l4, seq, k, p_hats, importance=9):
    """Navigation state ready to receive answer ``seq[k]``: seq[:k] are in the navigator, p_hats[:k+1] recorded."""
    skills = [SkillEntry(f"S{i}", "L3", i, float(i)) for i in range(n_l4)]
    nav = SkillNavigator.create("L3", skills)
    for ok in seq[:k]:
        assert nav.move(ok) is not None
    state = SessionState(session_id="s", student_id="u", grade_level=8, phase="navigation",
                         items_answered=14, section_ids=["a"], covered_section_ids=["a"])
    state.theta = ThetaState(theta=0.0, se=0.25)
    subtopics = SubtopicNavigator.create("topic", 5, [SubtopicEntry("L3", "topic", 0, importance)])
    state.current_subtopic_nav, state.current_skill_nav = subtopics.to_dict(), nav.to_dict()
    state.visit_p_hats = list(p_hats[:k + 1])
    return state


def stubbed(edges=None):
    service = service_with_edges(edges or {})
    service._advance_topic = lambda state, passed: "TOPIC"
    service._init_deep_scan = lambda state, skill: f"SCAN:{skill}"
    service._pick_task_for_navigation = lambda state, skill: f"NAV:{skill}"
    service._pick_task_from_subtopic = lambda state, nav: "NEXT_L3"
    return service


def expected(rule, seq, p_hats, residual_min=1.0, n_l4=1):
    """Independent restatement of the rule: does a visit with outcomes ``seq`` start a scan (gate and budget aside)?"""
    n_wrong = seq.count(False)
    failed = (seq.count(True) / len(seq)) < 0.6
    if not failed or n_wrong == 0:
        return False
    if rule == "current":
        return True
    if rule == "d1":
        return n_wrong >= 2 or (n_l4 == 1 and n_wrong >= 1)
    resid = sum(p_hats[:len(seq)]) - seq.count(True)
    return resid >= residual_min


P_PATTERNS = {"low": 0.3, "mid": 0.55, "high": 0.9}


# ── the rules and the preview agree, on every possible visit ──────────────────

@pytest.mark.parametrize("rule", ["current", "d1", "d2"])
@pytest.mark.parametrize("n_l4", [1, 2, 3, 4, 5, 6])
def test_trigger_and_early_stop_preview_agree_on_every_visit(monkeypatch, rule, n_l4):
    set_live(monkeypatch, trigger_rule=rule, residual_min=1.0, importance_threshold=8, trigger_mode="importance",
             session_budget=6)
    fired = 0
    for seq in visit_outcomes(n_l4):
        for pname, pv in P_PATTERNS.items():
            p_hats = [pv] * len(seq)
            want = expected(rule, seq, p_hats, n_l4=n_l4)
            state = visit_state(n_l4, seq, len(seq) - 1, p_hats)
            service = stubbed()
            assert service._has_pending_critical_probe(state, seq[-1]) is want, (rule, n_l4, seq, pname)
            result = service._advance_navigation(state, seq[-1])
            assert str(result).startswith("SCAN:") is want, (rule, n_l4, seq, pname)
            assert state.is_in_deep_scan is want
            fired += want
    assert fired > 0 or (rule == "d2" and n_l4 <= 2)        # the grid really exercises firing visits


@pytest.mark.parametrize("rule", ["current", "d1", "d2"])
def test_a_scan_never_starts_unless_the_preview_said_so(monkeypatch, rule):
    """A stop is deferred whenever a scan may start: preview False => the answer path does not scan."""
    set_live(monkeypatch, trigger_rule=rule, residual_min=0.6, importance_threshold=8, trigger_mode="importance")
    for n_l4 in (1, 2, 3, 5):
        for seq in visit_outcomes(n_l4):
            for k in range(len(seq)):
                p_hats = [0.7] * len(seq)
                state_a = visit_state(n_l4, seq, k, p_hats)
                state_b = visit_state(n_l4, seq, k, p_hats)
                pending = stubbed()._has_pending_critical_probe(state_a, seq[k])
                result = stubbed()._advance_navigation(state_b, seq[k])
                if str(result).startswith("SCAN:"):
                    assert pending, (rule, n_l4, seq, k)


@pytest.mark.parametrize("rule", ["current", "d1", "d2"])
def test_mid_visit_preview_stays_conservative(monkeypatch, rule):
    """While the visit continues, a failing skill in an important L3 keeps the stop deferred (the rule is decided at the end)."""
    set_live(monkeypatch, trigger_rule=rule, importance_threshold=8, trigger_mode="importance")
    seq = [False, True, True, False, True]
    state = visit_state(6, seq, 0, [0.5] * 5)
    assert stubbed()._has_pending_critical_probe(state, False) is True            # wrong, visit goes on
    assert stubbed()._has_pending_critical_probe(visit_state(6, seq, 0, [0.5] * 5), True) is False   # nothing failed yet


def test_current_rule_is_the_old_behaviour_on_every_visit(monkeypatch):
    """default = trigger iff the L3 failed (score < 0.6) with a failing skill in an important L3."""
    set_live(monkeypatch, trigger_rule="current", importance_threshold=8, trigger_mode="importance")
    assert ss.settings.deep_scan_trigger_rule == "current"
    for n_l4 in (1, 3, 4):
        for seq in visit_outcomes(n_l4):
            state = visit_state(n_l4, seq, len(seq) - 1, [0.5] * len(seq))
            want = (seq.count(True) / len(seq)) < 0.6
            assert stubbed()._has_pending_critical_probe(state, seq[-1]) is want


# ── d1 ─────────────────────────────────────────────────────────────────────────

def test_d1_needs_two_wrong_answers_or_one_when_the_l3_has_a_single_l4(monkeypatch):
    set_live(monkeypatch, trigger_rule="d1", importance_threshold=8, trigger_mode="importance")
    service = stubbed()
    # single L4, one wrong answer: scan
    assert service._advance_navigation(visit_state(1, [False], 0, [0.5]), False) == "SCAN:S0"
    # three L4: right then wrong = 1 wrong (score 0.5): failed, but not enough evidence
    state = visit_state(3, [True, False], 1, [0.5, 0.5])
    assert service._has_pending_critical_probe(state, False) is False
    assert service._advance_navigation(state, False) == "TOPIC" and not state.is_in_deep_scan
    # three L4: wrong, wrong = 2 wrong: scan
    state = visit_state(3, [False, False], 1, [0.5, 0.5])
    assert service._has_pending_critical_probe(state, False) is True
    assert service._advance_navigation(state, False) == "SCAN:S0" and state.is_in_deep_scan


# ── d2 ─────────────────────────────────────────────────────────────────────────

def test_d2_uses_the_residual_of_the_visit_against_the_threshold(monkeypatch):
    set_live(monkeypatch, trigger_rule="d2", residual_min=1.0, importance_threshold=8, trigger_mode="importance")
    service = stubbed()
    # wrong, wrong with p_hat 0.6 + 0.5 = 1.1 >= 1.0 -> scan
    state = visit_state(3, [False, False], 1, [0.6, 0.5])
    assert service._has_pending_critical_probe(state, False) is True
    assert service._advance_navigation(state, False) == "SCAN:S0"
    # 0.4 + 0.5 = 0.9 < 1.0 -> an expected failure, no scan
    state = visit_state(3, [False, False], 1, [0.4, 0.5])
    assert service._has_pending_critical_probe(state, False) is False
    assert service._advance_navigation(state, False) == "TOPIC"
    # exactly the threshold fires (>=)
    state = visit_state(3, [False, False], 1, [0.5, 0.5])
    assert service._advance_navigation(state, False) == "SCAN:S0"


def test_d2_threshold_comes_from_the_flag(monkeypatch):
    set_live(monkeypatch, trigger_rule="d2", residual_min=1.3, importance_threshold=8, trigger_mode="importance")
    state = visit_state(3, [False, False], 1, [0.6, 0.6])                        # 1.2
    assert stubbed()._advance_navigation(state, False) == "TOPIC"
    set_live(monkeypatch, residual_min=1.2)
    state = visit_state(3, [False, False], 1, [0.6, 0.6])
    assert stubbed()._advance_navigation(state, False) == "SCAN:S0"


def test_d2_residual_counts_correct_answers_against_the_wrong_ones(monkeypatch):
    # 5 L4: right, right, wrong, wrong -> p_hat 0.9 0.9 0.9 0.9: (0.9-1)+(0.9-1)+0.9+0.9 = 1.6
    set_live(monkeypatch, trigger_rule="d2", residual_min=1.0, importance_threshold=8, trigger_mode="importance")
    full = [seq for seq in visit_outcomes(5) if seq.count(False) >= 2 and (seq.count(True) / len(seq)) < 0.6]
    assert full
    for seq in full:
        p = [0.9] * len(seq)
        resid = sum(p) - seq.count(True)
        state = visit_state(5, seq, len(seq) - 1, p)
        assert (stubbed()._advance_navigation(state, seq[-1]).startswith("SCAN:")) is (resid >= 1.0)


def test_visit_residual_helper():
    nav = SkillNavigator.create("L3", [SkillEntry(f"S{i}", "L3", i, float(i)) for i in range(5)])
    nav.move(True); nav.move(False)
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.visit_p_hats = [0.8, 0.4]
    assert SessionService._visit_residual(state, nav) == pytest.approx((0.8 - 1) + 0.4)
    state.visit_p_hats = [0.4]                                                   # list shorter than the results: last pair
    assert SessionService._visit_residual(state, nav) == pytest.approx(0.4)
    state.visit_p_hats = []
    assert SessionService._visit_residual(state, nav) == 0.0


# ── combination with the importance / hard-prerequisite gate ───────────────────

@pytest.mark.parametrize("rule", ["d1", "d2"])
@pytest.mark.parametrize("importance,edges,gate", [(5, {"L3": [EDGE]}, True), (5, {}, False), (9, {}, False), (9, {"L3": [EDGE]}, True)])
def test_rule_is_applied_on_top_of_the_hard_prereq_gate(monkeypatch, rule, importance, edges, gate):
    set_live(monkeypatch, trigger_rule=rule, residual_min=1.0, trigger_mode="hard_prereq")
    state = visit_state(3, [False, False], 1, [0.7, 0.7], importance=importance)       # strong evidence for d1 and d2
    service = stubbed(edges)
    assert service._has_pending_critical_probe(state, False) is gate
    assert (service._advance_navigation(state, False) == "SCAN:S0") is gate
    weak = visit_state(3, [True, False], 1, [0.7, 0.7], importance=importance)          # failed (0.5) but weak evidence
    assert stubbed(edges)._advance_navigation(weak, False) == "TOPIC"


def test_rule_is_applied_on_top_of_the_importance_gate(monkeypatch):
    set_live(monkeypatch, trigger_rule="d1", importance_threshold=8, trigger_mode="importance")
    for importance, gate in ((7, False), (8, True), (10, True)):
        state = visit_state(3, [False, False], 1, [0.5, 0.5], importance=importance)
        assert stubbed()._has_pending_critical_probe(state, False) is gate


@pytest.mark.parametrize("grade,importance,edges,gate", [
    (5, 9, {}, True),                   # A9 below the gate grade: importance gate (hard edges are not looked at)
    (5, 5, {"L3": [EDGE]}, False),
    (6, 5, {"L3": [EDGE]}, True),       # from the gate grade: hard_prereq gate
    (6, 9, {}, False),
    (8, 5, {"L3": [EDGE]}, True),
])
def test_rule_d2_is_applied_on_top_of_the_grade_gated_hard_prereq_mode(monkeypatch, grade, importance, edges, gate):
    """A9: TRIGGER_RULE=d2, RESIDUAL_MIN=1.0, TRIGGER_MODE=hard_prereq, HARD_PREREQ_MIN_GRADE=6."""
    set_live(monkeypatch, trigger_rule="d2", residual_min=1.0, trigger_mode="hard_prereq", hard_prereq_min_grade=6)
    strong = visit_state(3, [False, False], 1, [0.7, 0.7], importance=importance)       # residual 1.4 >= 1.0
    strong.grade_level = grade
    service = stubbed(edges)
    assert service._has_pending_critical_probe(strong, False) is gate
    assert (service._advance_navigation(strong, False) == "SCAN:S0") is gate
    weak = visit_state(3, [True, False], 1, [0.7, 0.7], importance=importance)           # residual 0.4 < 1.0
    weak.grade_level = grade
    assert stubbed(edges)._advance_navigation(weak, False) == "TOPIC"


def test_budget_still_blocks_every_rule(monkeypatch):
    for rule in ("current", "d1", "d2"):
        set_live(monkeypatch, trigger_rule=rule, importance_threshold=8, trigger_mode="importance", session_budget=2)
        state = visit_state(3, [False, False], 1, [0.8, 0.8])
        state.deep_scan_items_total = 2
        assert stubbed()._has_pending_critical_probe(state, False) is False
        assert stubbed()._advance_navigation(state, False) == "TOPIC"


# ── freezing ───────────────────────────────────────────────────────────────────

def test_create_session_freezes_the_new_flags(monkeypatch):
    set_live(monkeypatch, trigger_rule="d2", residual_min=1.4, probe_min_p=0.25)
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    frozen = SessionService._scan_params(state)
    assert (frozen["trigger_rule"], frozen["residual_min"], frozen["probe_min_p"]) == ("d2", 1.4, 0.25)
    set_live(monkeypatch, trigger_rule="current", residual_min=9.0, probe_min_p=0.9)        # config edited mid-session
    assert SessionService._peek_scan_params(state)["trigger_rule"] == "d2"
    assert SessionService._peek_scan_params(state)["residual_min"] == 1.4
    assert SessionService._peek_scan_params(state)["probe_min_p"] == 0.25


def test_frozen_rule_decides_after_the_setting_changes(monkeypatch):
    set_live(monkeypatch, trigger_rule="d1", importance_threshold=8, trigger_mode="importance")
    state = visit_state(3, [True, False], 1, [0.7, 0.7])                         # one wrong in a 3-skill L3
    SessionService._scan_params(state)
    set_live(monkeypatch, trigger_rule="current")                               # live rule would scan; frozen d1 does not
    assert stubbed()._has_pending_critical_probe(state, False) is False
    assert stubbed()._advance_navigation(state, False) == "TOPIC"
    other = visit_state(3, [True, False], 1, [0.7, 0.7])
    set_live(monkeypatch, trigger_rule="current")
    SessionService._scan_params(other)
    set_live(monkeypatch, trigger_rule="d1")                                    # live d1 would not scan; frozen current does
    assert stubbed()._advance_navigation(other, False) == "SCAN:S2"


def test_preview_never_freezes_a_pre_flag_session_and_uses_live_rule(monkeypatch):
    set_live(monkeypatch, trigger_rule="d1", importance_threshold=8, trigger_mode="importance")
    state = visit_state(3, [True, False], 1, [0.7, 0.7])
    assert state.deep_scan_params is None
    before = copy.deepcopy(state.to_dict())
    assert stubbed()._has_pending_critical_probe(state, False) is False        # live d1
    assert state.deep_scan_params is None and state.to_dict() == before


def test_params_stored_before_the_new_keys_existed_fill_them_from_the_live_settings(monkeypatch):
    set_live(monkeypatch, trigger_rule="d2", residual_min=1.2, probe_min_p=0.1)
    old = {"confirm_probes": 2, "probe_difficulty_offset": 1.5, "trigger_mode": "importance",
           "importance_threshold": 8, "session_budget": 6, "max_items": 6}           # a stage-2 session
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.deep_scan_params = dict(old)
    peeked = SessionService._peek_scan_params(state)
    assert (peeked["trigger_rule"], peeked["residual_min"], peeked["probe_min_p"]) == ("d2", 1.2, 0.1)
    assert state.deep_scan_params == old                                         # peek stores nothing
    frozen = SessionService._scan_params(state)
    assert frozen["trigger_rule"] == "d2" and state.deep_scan_params is frozen
    set_live(monkeypatch, trigger_rule="current")
    assert SessionService._scan_params(state)["trigger_rule"] == "d2"


# ── p_hat bookkeeping in the session state ─────────────────────────────────────

def test_visit_p_hats_roundtrip_and_legacy_states_load_empty():
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.visit_p_hats = [0.25, 0.5]
    assert SessionState.from_dict(state.to_dict()).visit_p_hats == [0.25, 0.5]
    data = state.to_dict()
    del data["visit_p_hats"]
    assert SessionState.from_dict(data).visit_p_hats == []
    data["visit_p_hats"] = None
    assert SessionState.from_dict(data).visit_p_hats == []


def submit_one(monkeypatch, state, theta_item):
    task = NS(id="T", irt_discrimination=theta_item[0], irt_difficulty=theta_item[1], irt_guessing=theta_item[2])
    monkeypatch.setattr(ss, "task_object", lambda snapshot, task_id: task)
    state.current_task_id, state.current_task_snapshot = "T", {"id": "T"}
    service = answering_service(state, [])
    service._submit_answer_locked(session_id="sid", task_id="T", student_answer="1", time_ms=1)


def test_navigation_answer_records_p_hat_at_the_theta_before_it(monkeypatch):
    set_live(monkeypatch, importance_threshold=8)
    state = visit_state(3, [False], 0, [])
    state.visit_p_hats = []
    state.theta = ThetaState(theta=0.4, se=0.5)
    submit_one(monkeypatch, state, (1.3, 0.1, 0.2))
    assert state.visit_p_hats == [pytest.approx(p_correct(0.4, IRTParams(a=1.3, b=0.1, c=0.2)))]
    assert state.theta.theta != 0.4                                                # theta moved AFTER p_hat was taken


def test_warmup_and_deep_scan_answers_record_no_p_hat(monkeypatch):
    state = visit_state(3, [False], 0, [])
    state.phase = "warmup"
    submit_one(monkeypatch, state, (1.0, 0.0, 0.0))
    assert state.visit_p_hats == []
    scan = scanning_state("B", ["C"])
    scan.theta = ThetaState(theta=0.0)
    submit_one(monkeypatch, scan, (1.0, 0.0, 0.0))
    assert scan.visit_p_hats == []


def test_new_l3_visit_resets_the_p_hats():
    service = object.__new__(SessionService)
    service.knowledge_repo = NS(get_skills_for_subtopic=lambda sid: [NS(id="S1", sequence_order=0, name_ru="")])
    service.task_repo = NS(get_avg_difficulty_for_skills=lambda ids: {})
    service._pick_task_for_navigation = lambda state, skill: f"NAV:{skill}"
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.visit_p_hats = [0.3, 0.6]
    sub_nav = SubtopicNavigator.create("topic", 5, [SubtopicEntry("L3", "topic", 0, 9)])
    assert service._pick_task_from_subtopic(state, sub_nav) == "NAV:S1"
    assert state.visit_p_hats == [] and state.current_skill_nav["subtopic_id"] == "L3"


# ── D3: probe_min_p ─────────────────────────────────────────────────────────────

class Bank:
    """Items of several skills with 3PL parameters; the unused item nearest to target_b is served."""

    def __init__(self, items):                       # {skill: [(a, b, c), ...]}
        self.items = {s: {f"{s}.{i}": abc for i, abc in enumerate(v)} for s, v in items.items()}

    def _task(self, skill, tid):
        a, b, c = self.items[skill][tid]
        return NS(id=tid, irt_discrimination=a, irt_difficulty=b, irt_guessing=c)

    def get_task_by_difficulty_target(self, skill_id, target_b, *, exclude_ids=None):
        free = {k: v for k, v in self.items.get(skill_id, {}).items() if k not in (exclude_ids or [])}
        if not free:
            return None
        best = min(free, key=lambda k: (abs(free[k][1] - target_b), k))
        return self._task(skill_id, best)

    def get_tasks_for_skill(self, skill_id, *, exclude_ids=None, limit=1, **kw):
        return [self._task(skill_id, k) for k in self.items.get(skill_id, {}) if k not in (exclude_ids or [])][:limit]


def scan_service(bank):
    service = object.__new__(SessionService)
    service.task_repo = bank
    service._task_to_out = lambda task, state: task.id
    service._set_context_for_skill = lambda state, skill: None
    service._advance_topic = lambda state, correct: "ADVANCED"
    service._prereq_l4_ids = lambda skill: []
    return service


def scan_state(theta, queue, current="A", **flags):
    state = scanning_state(current, queue)
    state.theta = ThetaState(theta=theta)
    SessionService._scan_params(state)
    state.deep_scan_params.update({"probe_difficulty_offset": 0.0, **flags})
    return state


def test_probe_min_p_is_off_by_default_and_reads_nothing(monkeypatch):
    set_live(monkeypatch, probe_min_p=0.0)
    service = scan_service(Bank({"A": [(1.0, 3.0, 0.0)]}))
    state = scan_state(-2.0, [])
    assert service._pick_task_for_skill(state, "A") == "A.0"                       # p = 0.007, still served
    assert service._probe_too_hard(state, NS(id="x")) is False                     # attributes are not even read


def test_a_probe_below_the_threshold_is_not_spent(monkeypatch):
    set_live(monkeypatch, probe_min_p=0.5)
    service = scan_service(Bank({"A": [(1.0, 1.5, 0.0)]}))                         # p(theta=0) = 0.18 < 0.5
    state = scan_state(0.0, [])
    state.deep_scan_params["probe_min_p"] = 0.5
    before = (state.current_task_id, state.current_skill_id)
    assert service._pick_task_for_skill(state, "A") is None
    assert (state.current_task_id, state.current_skill_id) == before                # nothing was issued


def test_probe_at_exactly_the_threshold_is_spent_and_guessing_counts(monkeypatch):
    service = scan_service(Bank({"A": [(1.0, 0.0, 0.0)], "B": [(1.0, 3.0, 0.25)]}))
    state = scan_state(0.0, [], probe_min_p=0.5)
    assert service._pick_task_for_skill(state, "A") == "A.0"                       # p = 0.5 = threshold: kept
    p_b = p_correct(0.0, IRTParams(a=1.0, b=3.0, c=0.25))                          # 0.25 + 0.75 * 0.047 = 0.285
    assert service._probe_too_hard(state, NS(id="B.0", irt_discrimination=1.0, irt_difficulty=3.0, irt_guessing=0.25)) is (p_b < 0.5)
    state.deep_scan_params["probe_min_p"] = 0.28
    assert service._pick_task_for_skill(state, "B") == "B.0"                       # the guessing floor lifts p above 0.28
    state.deep_scan_params["probe_min_p"] = 0.3
    assert service._pick_task_for_skill(state, "B") is None


def test_navigation_items_are_never_filtered_by_probe_min_p(monkeypatch):
    service = scan_service(Bank({"A": [(1.0, 3.0, 0.0)]}))
    state = scan_state(0.0, [], probe_min_p=0.9)
    state.is_in_deep_scan, state.phase = False, "navigation"
    assert service._pick_task_for_skill(state, "A") == "A.0"


def test_too_hard_probe_skips_the_skill_and_the_scan_goes_on(monkeypatch):
    service = scan_service(Bank({"A": [(1.0, 3.0, 0.0)], "B": [(1.0, 0.0, 0.0)]}))
    state = scan_state(0.0, ["A", "B"], current="X", probe_min_p=0.4)
    ds = DeepScanState.from_dict(state.deep_scan)
    assert service._next_deep_scan_task(state, ds) == "B.0"                          # A skipped, B probed
    assert "A" in ds.tested and "A" not in ds.gaps and "A" not in ds.unconfirmed       # no evidence either way
    assert ds.current_skill_id == "B"


def test_retry_probe_too_hard_leaves_the_gap_unconfirmed(monkeypatch):
    service = scan_service(Bank({"A": [(1.0, 0.0, 0.0), (1.0, 3.0, 0.0)]}))
    state = scan_state(0.0, [], current="A", probe_min_p=0.4, confirm_probes=2)
    state.deep_scan = DeepScanState(origin_skill_id="O", queue=[], current_skill_id="A", max_items=6).to_dict()
    state.used_task_ids.append("A.0")                                                # the first probe was served and failed
    result = service._advance_deep_scan(state, False)                                # wrong; retry would be A.1 (p=0.047)
    assert result == "ADVANCED"
    assert "A" in state.deep_scan_unconfirmed and "A" not in state.confirmed_gaps
    assert "O" in state.confirmed_gaps                                               # the origin is recorded as always


def test_all_probes_too_hard_finishes_the_scan_without_spending_items(monkeypatch):
    service = scan_service(Bank({"A": [(1.0, 3.5, 0.0)], "B": [(1.0, 3.5, 0.0)]}))
    state = scan_state(0.0, ["A", "B"], current="X", probe_min_p=0.5)
    state.deep_scan = None
    ds = DeepScanState(origin_skill_id="O", queue=["A", "B"], max_items=6)
    assert service._next_deep_scan_task(state, ds) == "ADVANCED"
    assert state.deep_scan_items_total == 0 and state.confirmed_gaps == ["O"] and not state.is_in_deep_scan


def test_probe_min_p_is_frozen_at_session_start(monkeypatch):
    set_live(monkeypatch, probe_min_p=0.5)
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.theta = ThetaState(theta=0.0)
    SessionService._scan_params(state)
    set_live(monkeypatch, probe_min_p=0.0)                                             # live off, frozen 0.5
    state.is_in_deep_scan = True
    service = scan_service(Bank({"A": [(1.0, 3.0, 0.0)]}))
    assert service._pick_task_for_skill(state, "A") is None
