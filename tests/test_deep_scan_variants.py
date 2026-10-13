"""DIAG-1 stage 2: Deep Scan variants behind config flags.

  DEEP_SCAN_PROBE_DIFFICULTY_OFFSET  probe items target theta - offset
  DEEP_SCAN_CONFIRM_PROBES           a gap needs N wrong answers on different items
  DEEP_SCAN_TRIGGER_MODE             "importance" (current) | "hard_prereq"
  DEEP_SCAN_HARD_PREREQ_MIN_GRADE    "hard_prereq" applies only from this grade (0 = every grade)

The shipped defaults are variant OC15 (offset 1.5, 2 confirmation probes, importance trigger;
owner-approved 2026-10-12).  The pre-OC15 behaviour (offset 0, 1 probe) is selected explicitly
by the tests that describe it.
"""
import copy
import random
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.domain import report_generator as rg
from src.domain import session_service as ss
from src.domain.alpha_engine import ThetaState
from src.domain.navigators.skill_navigator import DeepScanState, SkillEntry, SkillNavigator
from src.domain.navigators.subtopic_navigator import SubtopicEntry, SubtopicNavigator
from src.domain.session_service import SessionService
from src.domain.session_state import SessionState

T0 = datetime(2026, 10, 1, 10, 0, 0)


# ── helpers ───────────────────────────────────────────────────────────────────

def make_service(graph, picked, bank=None):
    """Service with a stubbed bank.  ``bank`` = {skill: number of unused items}; skills
    that are not listed have an unlimited number."""
    left = dict(bank or {})

    def pick(state, skill):
        if skill in left:
            if left[skill] <= 0:
                return None
            left[skill] -= 1
        picked.append(skill)
        return f"task:{skill}"

    service = object.__new__(SessionService)
    service._prereq_l4_ids = lambda skill: list(graph.get(skill, []))
    service._set_context_for_skill = lambda state, skill: None
    service._pick_task_for_skill = pick
    service._advance_topic = lambda state, correct: "ADVANCED"
    return service


def scanning_state(current, queue, max_items=6, items_used=0, origin="G8_A"):
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.phase, state.is_in_deep_scan = "deep_scan", True
    state.deep_scan = DeepScanState(origin_skill_id=origin, queue=list(queue), current_skill_id=current,
                                    max_items=max_items, items_used=items_used).to_dict()
    return state


@pytest.fixture
def confirm2(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 2, raising=False)


def answer(skill, outcome, *, minute, deep=False, origin=None, step=None):
    return NS(id=f"a{minute:03d}", skill_id=skill, task_id=None, outcome=outcome,
              is_deep_scan=deep, phase="deep_scan" if deep else "navigation",
              eval_category="correct" if outcome else "wrong", student_answer="1" if outcome else "0",
              answered_at=T0 + timedelta(minutes=minute),
              deep_scan_origin_skill_id=origin, deep_scan_step=step, topic_id="X")


def chains_of(answers, confirm=None, grade=8):
    names = {i: {"name_ru": f"Навык {i}"} for i in ("G8_A", "G8_B", "G7_C", "G8_D", "G6_E")}
    return rg._reconstruct_root_cause_chains(answers, names, [], grade, confirm_probes=confirm)


# ── config: defaults and environment ──────────────────────────────────────────

def test_flag_defaults_are_variant_oc15(monkeypatch):
    for name in ("DEEP_SCAN_PROBE_DIFFICULTY_OFFSET", "DEEP_SCAN_CONFIRM_PROBES", "DEEP_SCAN_TRIGGER_MODE",
                 "DEEP_SCAN_HARD_PREREQ_MIN_GRADE"):
        monkeypatch.delenv(name, raising=False)
    cfg = Settings(_env_file=None)
    assert cfg.deep_scan_hard_prereq_min_grade == 0                    # grade gate off: previous behaviour
    assert cfg.deep_scan_probe_difficulty_offset == 1.5
    assert cfg.deep_scan_confirm_probes == 2
    assert cfg.deep_scan_trigger_mode == "importance"                  # unchanged by OC15
    assert cfg.deep_scan_importance_threshold == 8 and cfg.deep_scan_max_items == 6
    assert cfg.deep_scan_session_budget == 6


def test_pre_oc15_behaviour_is_selectable_from_the_environment(monkeypatch):
    monkeypatch.setenv("DEEP_SCAN_PROBE_DIFFICULTY_OFFSET", "0.0")
    monkeypatch.setenv("DEEP_SCAN_CONFIRM_PROBES", "1")
    cfg = Settings(_env_file=None)
    assert (cfg.deep_scan_probe_difficulty_offset, cfg.deep_scan_confirm_probes) == (0.0, 1)


def test_flags_are_overridable_from_the_environment(monkeypatch):
    monkeypatch.setenv("DEEP_SCAN_PROBE_DIFFICULTY_OFFSET", "1.0")
    monkeypatch.setenv("DEEP_SCAN_CONFIRM_PROBES", "2")
    monkeypatch.setenv("DEEP_SCAN_TRIGGER_MODE", "hard_prereq")
    cfg = Settings(_env_file=None)
    assert (cfg.deep_scan_probe_difficulty_offset, cfg.deep_scan_confirm_probes,
            cfg.deep_scan_trigger_mode) == (1.0, 2, "hard_prereq")


@pytest.mark.parametrize("name,value", [
    ("DEEP_SCAN_CONFIRM_PROBES", "0"),
    ("DEEP_SCAN_TRIGGER_MODE", "always"),
    ("DEEP_SCAN_HARD_PREREQ_MIN_GRADE", "-1"),
    ("DEEP_SCAN_PROBE_DIFFICULTY_OFFSET", "nan"),
])
def test_invalid_flag_values_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# ── 1. probe difficulty offset ────────────────────────────────────────────────

class FakeTasks:
    """Bank of one skill; get_task_by_difficulty_target = the unused item nearest to target_b."""

    def __init__(self, difficulties):
        self.items = {f"t{i}": b for i, b in enumerate(difficulties)}
        self.targets = []

    def get_task_by_difficulty_target(self, skill_id, target_b, *, exclude_ids=None):
        self.targets.append(target_b)
        free = {k: b for k, b in self.items.items() if k not in (exclude_ids or [])}
        if not free:
            return None
        best = min(free, key=lambda k: (abs(free[k] - target_b) if target_b is not None else 0.0, k))
        return NS(id=best, irt_difficulty=free[best])

    def get_tasks_for_skill(self, skill_id, *, exclude_ids=None, limit=1, **kw):
        return [NS(id=k, irt_difficulty=b) for k, b in self.items.items() if k not in (exclude_ids or [])][:limit]


def state_with_theta(theta, *, scanning):
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.theta = ThetaState(theta=theta)
    state.is_in_deep_scan = scanning
    state.phase = "deep_scan" if scanning else "navigation"
    return state


def service_with_bank(bank):
    service = object.__new__(SessionService)
    service.task_repo = bank
    return service


def test_probe_offset_selects_an_easier_item(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", 1.0, raising=False)
    bank = FakeTasks([-2.0, -0.5, 0.4, 1.6])
    service = service_with_bank(bank)
    state = state_with_theta(0.5, scanning=True)
    assert service._select_task_for_skill(state, "S").irt_difficulty == -0.5    # nearest to 0.5 - 1.0
    assert bank.targets == [-0.5]


def test_default_offset_targets_theta_exactly(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", 0.0, raising=False)
    bank = FakeTasks([-2.0, -0.5, 0.4, 1.6])
    state = state_with_theta(0.5, scanning=True)
    assert service_with_bank(bank)._select_task_for_skill(state, "S").irt_difficulty == 0.4
    assert bank.targets == [0.5]


def test_offset_never_touches_measurement_items(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", 1.0, raising=False)
    bank = FakeTasks([-2.0, -0.5, 0.4, 1.6])
    state = state_with_theta(0.5, scanning=False)                # navigation / warm-up / precision targeting
    assert service_with_bank(bank)._select_task_for_skill(state, "S").irt_difficulty == 0.4
    assert bank.targets == [0.5]


# ── 2. confirmation by N wrong answers on different items ────────────────────

def test_one_probe_setting_makes_a_wrong_answer_a_gap_at_once(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 1, raising=False)   # pre-OC15 rule (default is 2)
    picked = []
    service = make_service({"B": ["B1"]}, picked)
    state = scanning_state("B", ["C"])
    assert service._advance_deep_scan(state, False) == "task:B1"      # descends immediately, no re-probe of B
    assert state.deep_scan["gaps"] == ["B"] and picked == ["B1"]
    assert state.deep_scan["unconfirmed"] == []


def test_two_wrong_answers_on_one_skill_confirm_the_gap(confirm2):
    picked = []
    service = make_service({"B": ["B1"]}, picked)
    state = scanning_state("B", ["C"])
    assert service._advance_deep_scan(state, False) == "task:B"        # first miss: same skill again
    assert state.deep_scan["gaps"] == [] and state.deep_scan["queue"] == ["C"]
    assert state.deep_scan["wrong_counts"] == {"B": 1} and state.deep_scan["current_skill_id"] == "B"
    assert state.deep_scan_items_total == 1
    assert service._advance_deep_scan(state, False) == "task:B1"       # second miss: gap, descend
    assert state.deep_scan["gaps"] == ["B"]
    assert state.deep_scan["queue"] == ["C"]                           # B1 first (depth first), then C
    assert state.deep_scan["items_used"] == 2 and state.deep_scan_items_total == 2
    assert picked == ["B", "B1"]
    assert state.deep_scan["tested"] == ["B"]                          # one entry per skill, not per item


def test_a_correct_answer_after_one_miss_closes_the_branch(confirm2):
    picked = []
    service = make_service({"B": ["B1"]}, picked)
    state = scanning_state("B", ["C"])
    assert service._advance_deep_scan(state, False) == "task:B"
    assert service._advance_deep_scan(state, True) == "task:C"        # mastered: no gap, no descent
    assert state.deep_scan["gaps"] == [] and state.deep_scan["unconfirmed"] == []
    assert "B1" not in picked
    assert service._advance_deep_scan(state, True) == "ADVANCED"
    assert state.confirmed_gaps == ["G8_A"] and state.deep_scan_unconfirmed == []


def test_correct_first_answer_is_unchanged_with_confirmation_on(confirm2):
    service = make_service({}, [])
    state = scanning_state("B", ["C"])
    assert service._advance_deep_scan(state, True) == "task:C"
    assert state.deep_scan["wrong_counts"] == {}


def test_running_out_of_items_before_confirmation_is_no_gap_and_is_recorded(confirm2):
    picked = []
    service = make_service({"B": ["B1"]}, picked, bank={"B": 0})       # B has no second item
    state = scanning_state("B", ["C"])
    assert service._advance_deep_scan(state, False) == "task:C"        # B unconfirmed -> next branch
    assert state.deep_scan["gaps"] == [] and state.deep_scan["unconfirmed"] == ["B"]
    assert "B1" not in picked                                          # unconfirmed: its prerequisites are not scanned
    assert service._advance_deep_scan(state, True) == "ADVANCED"
    assert state.deep_scan is None and state.phase == "navigation"
    assert state.confirmed_gaps == ["G8_A"]                            # only the origin
    assert state.deep_scan_unconfirmed == ["B"] and "B" in state.deep_scan_tested


def test_unconfirmed_last_skill_finishes_the_scan_and_resumes_cat(confirm2):
    service = make_service({}, [], bank={"B": 0})
    state = scanning_state("B", [])
    assert service._advance_deep_scan(state, False) == "ADVANCED"
    assert not state.is_in_deep_scan and state.confirmed_gaps == ["G8_A"]
    assert state.deep_scan_unconfirmed == ["B"]


def test_extra_probes_count_against_the_per_scan_cap(confirm2):
    picked = []
    service = make_service({}, picked)
    state = scanning_state("B", ["C"], max_items=2)
    assert service._advance_deep_scan(state, False) == "task:B"       # item 1 of 2
    assert service._advance_deep_scan(state, False) == "ADVANCED"      # item 2 of 2: confirmed AT the cap, scan ends
    assert state.confirmed_gaps == ["B", "G8_A"] and state.deep_scan_unconfirmed == []
    assert state.deep_scan_items_total == 2 and picked == ["B"]


def test_cap_reached_before_confirmation_leaves_the_skill_unconfirmed(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 3, raising=False)
    service = make_service({}, [])
    state = scanning_state("B", ["C"], max_items=2)
    assert service._advance_deep_scan(state, False) == "task:B"
    assert service._advance_deep_scan(state, False) == "ADVANCED"      # cap hit with 2 of 3 misses
    assert state.confirmed_gaps == ["G8_A"] and state.deep_scan_unconfirmed == ["B"]


def test_extra_probes_count_against_the_session_budget(confirm2, monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_session_budget", 1, raising=False)
    service = make_service({}, [])
    state = scanning_state("B", ["C"])
    assert service._advance_deep_scan(state, False) == "ADVANCED"      # budget spent after one miss
    assert state.confirmed_gaps == ["G8_A"] and state.deep_scan_unconfirmed == ["B"]
    assert state.deep_scan_items_total == 1


def test_three_probe_confirmation_and_deeper_chain(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 3, raising=False)
    picked = []
    service = make_service({"B": ["B1"], "B1": ["B2"]}, picked)
    state = scanning_state("B", [])
    for _ in range(2):
        assert service._advance_deep_scan(state, False) == "task:B"
    assert service._advance_deep_scan(state, False) == "task:B1"
    assert state.deep_scan["gaps"] == ["B"]
    assert service._advance_deep_scan(state, False) == "task:B1"       # B1 needs three misses as well
    assert state.deep_scan["gaps"] == ["B"] and picked == ["B", "B", "B1", "B1"]


def test_retries_use_different_items_of_the_skill(confirm2):
    bank = FakeTasks([0.0, 0.1, 0.2])
    service = object.__new__(SessionService)
    service.task_repo = bank
    service._prereq_l4_ids = lambda skill: []
    service._set_context_for_skill = lambda state, skill: None
    service._task_to_out = lambda task, state: task.id
    service._advance_topic = lambda state, correct: "ADVANCED"
    state = scanning_state("B", [])
    state.theta = ThetaState(theta=0.0)
    first = service._pick_task_for_skill(state, "B")
    state.used_task_ids.append(first)                                  # what submit_answer does
    second = service._advance_deep_scan(state, False)
    assert second != first and second in bank.items
    state.used_task_ids.append(second)
    assert service._advance_deep_scan(state, False) == "ADVANCED"      # confirmed, nothing queued
    assert state.confirmed_gaps == ["B", "G8_A"]


def test_scan_state_roundtrips_and_legacy_states_load():
    scan = DeepScanState(origin_skill_id="O", wrong_counts={"B": 1}, unconfirmed=["C"])
    back = DeepScanState.from_dict(scan.to_dict())
    assert back.wrong_counts == {"B": 1} and back.unconfirmed == ["C"]
    legacy = scan.to_dict()
    del legacy["wrong_counts"], legacy["unconfirmed"]
    old = DeepScanState.from_dict(legacy)
    assert old.wrong_counts == {} and old.unconfirmed == []
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.deep_scan_unconfirmed = ["B"]
    assert SessionState.from_dict(state.to_dict()).deep_scan_unconfirmed == ["B"]
    data = state.to_dict()
    del data["deep_scan_unconfirmed"]
    assert SessionState.from_dict(data).deep_scan_unconfirmed == []


# ── 3. trigger mode ───────────────────────────────────────────────────────────

def service_with_edges(edges):
    service = object.__new__(SessionService)
    calls = []

    def get_prerequisites(l3, hard_only=False):
        calls.append((l3, hard_only))
        return list(edges.get(l3, []))

    service.prereq_repo = NS(get_prerequisites=get_prerequisites)
    service.calls = calls
    return service


EDGE = NS(prerequisite_id="P")


def test_importance_mode_ignores_hard_edges(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "importance", raising=False)
    service = service_with_edges({"L3_5": [EDGE], "L3_8": []})
    state = state_with_theta(0.0, scanning=False)
    assert not service._l3_warrants_deep_scan(state, NS(subtopic_id="L3_5", importance=5))
    assert service._l3_warrants_deep_scan(state, NS(subtopic_id="L3_8", importance=8))
    assert service.calls == []                                         # the current rule does not even look up edges


def test_hard_prereq_mode_fires_for_unimportant_l3_with_a_hard_edge_and_not_without(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "hard_prereq", raising=False)
    service = service_with_edges({"L3_5": [EDGE]})
    state = state_with_theta(0.0, scanning=False)
    assert service._l3_warrants_deep_scan(state, NS(subtopic_id="L3_5", importance=5))
    assert not service._l3_warrants_deep_scan(state, NS(subtopic_id="L3_9", importance=9))   # no edges: importance is ignored
    assert ("L3_5", True) in service.calls                              # HARD edges only


def navigation_state(importance, subtopic_id="L3"):
    """A student who is on the last skill of one L3; the next wrong answer fails that L3."""
    state = SessionState(session_id="s", student_id="u", grade_level=8, phase="navigation",
                         items_answered=14, section_ids=["a"], covered_section_ids=["a"])
    state.theta = ThetaState(theta=0.0, se=0.25)
    subtopics = SubtopicNavigator.create("topic", 5, [SubtopicEntry(subtopic_id, "topic", 0, importance)])
    skills = SkillNavigator.create(subtopic_id, [SkillEntry("S1", subtopic_id, 0, 0.0)])
    state.current_subtopic_nav, state.current_skill_nav = subtopics.to_dict(), skills.to_dict()
    return state


@pytest.mark.parametrize("importance,edges,fires", [
    (5, {"L3": [EDGE]}, True),      # low importance, hard edge  -> scan
    (5, {}, False),                 # low importance, no edge    -> no scan
    (9, {}, False),                 # high importance, no edge   -> no scan (importance is ignored)
    (9, {"L3": [EDGE]}, True),
])
def test_hard_prereq_trigger_and_pending_probe_agree(monkeypatch, importance, edges, fires):
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "hard_prereq", raising=False)
    service = service_with_edges(edges)
    service._advance_topic = lambda state, passed: "TOPIC"
    service._init_deep_scan = lambda state, skill: f"SCAN:{skill}"
    service._pick_task_for_navigation = lambda state, skill: f"NAV:{skill}"
    service._pick_task_from_subtopic = lambda state, nav: "NEXT_L3"

    state = navigation_state(importance)
    assert service._has_pending_critical_probe(state, False) is fires      # early stop is blocked iff a scan will start
    assert service._has_pending_critical_probe(state, True) is False        # a correct answer fails nothing
    result = service._advance_navigation(state, False)
    assert (result == "SCAN:S1") is fires
    assert state.is_in_deep_scan is fires
    if not fires:
        assert result == "TOPIC"


def test_importance_mode_trigger_and_pending_probe_are_unchanged(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "importance", raising=False)
    for importance, fires in ((7, False), (8, True), (10, True)):
        service = service_with_edges({"L3": [EDGE]})                        # edges present but irrelevant
        service._advance_topic = lambda state, passed: "TOPIC"
        service._init_deep_scan = lambda state, skill: f"SCAN:{skill}"
        state = navigation_state(importance)
        assert service._has_pending_critical_probe(state, False) is fires
        assert (service._advance_navigation(state, False) == "SCAN:S1") is fires


def test_failed_subtopic_helper_matches_needs_deep_scan():
    nav = SubtopicNavigator.create("t", 5, [SubtopicEntry("a", "t", 0, 9), SubtopicEntry("b", "t", 1, 3)])
    assert nav.failed_subtopic() is None and not nav.needs_deep_scan(8)
    nav.state.boundary_subtopic_id = "a"
    assert nav.failed_subtopic().subtopic_id == "a" and nav.needs_deep_scan(8)
    nav.state.boundary_subtopic_id = "b"
    assert not nav.needs_deep_scan(8) and nav.needs_deep_scan(3)


# ── report chains with confirmed steps ────────────────────────────────────────

def test_confirmed_gap_becomes_one_failed_step_of_the_chain():
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G7_C", 0, minute=2, deep=True, origin="G8_A", step=1),
        answer("G7_C", 0, minute=3, deep=True, origin="G8_A", step=2),     # second miss on another item
    ]
    chain = chains_of(answers, confirm=2)[0]
    assert chain["root_gap_skill_id"] == "G7_C" and chain["has_prerequisite_gap"]
    assert chain["steps_count"] == 2                                       # source + ONE step for the skill
    probe = chain["steps"][1]
    assert probe["probe_attempts"] == 2 and probe["gap_confirmed"] is True


def test_single_miss_without_confirmation_is_not_a_failed_step():
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G7_C", 0, minute=2, deep=True, origin="G8_A", step=1),     # the skill ran out of items
    ]
    assert chains_of(answers, confirm=2) == []                             # no confirmed gap -> no causal chain
    assert len(chains_of(answers, confirm=1)) == 1                         # same data, default rule: a gap


def test_miss_then_correct_is_mastery_and_an_anchor():
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G8_B", 0, minute=2, deep=True, origin="G8_A", step=1),
        answer("G8_B", 1, minute=3, deep=True, origin="G8_A", step=2),     # mastered after all
        answer("G6_E", 0, minute=4, deep=True, origin="G8_A", step=3),
        answer("G6_E", 0, minute=5, deep=True, origin="G8_A", step=4),     # confirmed
    ]
    chain = chains_of(answers, confirm=2)[0]
    assert chain["root_gap_skill_id"] == "G6_E"
    assert chain["anchor_skill_id"] == "G8_B"
    by_skill = {s["skill_id"]: s for s in chain["steps"]}
    assert by_skill["G8_B"]["outcome"] == 1.0 and by_skill["G8_B"]["gap_confirmed"] is False
    assert by_skill["G8_B"]["probe_attempts"] == 2
    assert chain["steps_count"] == 3


def test_unconfirmed_step_does_not_hide_a_confirmed_one():
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G7_C", 0, minute=2, deep=True, origin="G8_A", step=1),     # unconfirmed (one miss, out of items)
        answer("G8_D", 0, minute=3, deep=True, origin="G8_A", step=2),
        answer("G8_D", 0, minute=4, deep=True, origin="G8_A", step=3),     # confirmed
    ]
    chain = chains_of(answers, confirm=2)[0]
    assert chain["root_gap_skill_id"] == "G8_D"                            # not the lower-grade but unconfirmed G7_C
    unconfirmed = [s for s in chain["steps"] if s["skill_id"] == "G7_C"][0]
    assert unconfirmed["gap_confirmed"] is False and unconfirmed["probe_attempts"] == 1


def test_chain_does_not_depend_on_row_order_with_confirmation():
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G7_C", 0, minute=2, deep=True, origin="G8_A", step=1),
        answer("G7_C", 0, minute=3, deep=True, origin="G8_A", step=2),
        answer("G6_E", 1, minute=4, deep=True, origin="G8_A", step=3),
    ]
    expected = chains_of(answers, confirm=2)
    for seed in range(5):
        shuffled = list(answers)
        random.Random(seed).shuffle(shuffled)
        assert chains_of(shuffled, confirm=2) == expected


def test_default_chain_is_unchanged_and_carries_no_probe_fields():
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G7_C", 0, minute=2, deep=True, origin="G8_A", step=1),
        answer("G6_E", 1, minute=3, deep=True, origin="G8_A", step=2),
    ]
    chain = chains_of(answers)[0]                       # confirm_probes None -> Settings default (1)
    assert chain["root_gap_skill_id"] == "G7_C" and chain["steps_count"] == 3
    assert all("gap_confirmed" not in s and "probe_attempts" not in s for s in chain["steps"])
    assert chains_of(answers, confirm=1)[0] == chain


def test_report_without_a_stored_threshold_uses_the_old_rule_whatever_the_settings(monkeypatch):
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G7_C", 0, minute=2, deep=True, origin="G8_A", step=1),
    ]
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 3, raising=False)
    assert len(chains_of(answers)) == 1                    # old session / no stored N -> 1, not the live setting
    assert chains_of(answers) == chains_of(answers, confirm=1)


# ── the flags are frozen per session; a rebuilt report must not change ────────

def frozen_state(graph=None, bank=None):
    service = make_service(graph or {}, [], bank=bank)
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.phase, state.is_in_deep_scan = "deep_scan", True
    return service, state


def test_first_scan_freezes_the_session_flags(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 2, raising=False)
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", 1.0, raising=False)
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "hard_prereq", raising=False)
    service, state = frozen_state({"G8_A": ["B"]})
    assert state.deep_scan_params is None
    service._init_deep_scan(state, "G8_A")
    assert state.deep_scan_params == {"confirm_probes": 2, "probe_difficulty_offset": 1.0,
                                      "trigger_mode": "hard_prereq",
                                      "importance_threshold": ss.settings.deep_scan_importance_threshold,
                                      "session_budget": ss.settings.deep_scan_session_budget,
                                      "max_items": ss.settings.deep_scan_max_items, **STAGE3B_DEFAULTS,
                                      "hard_prereq_min_grade": 0}
    stored = dict(state.deep_scan_params)
    # the settings change later (config redeploy / env edit): the session keeps its own values
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 1, raising=False)
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", 0.0, raising=False)
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "importance", raising=False)
    assert service._advance_deep_scan(state, False) == "task:B"        # still needs a 2nd miss on B
    assert state.deep_scan["gaps"] == [] and state.deep_scan["wrong_counts"] == {"B": 1}
    assert state.deep_scan_params == stored


def test_frozen_offset_is_used_for_probe_selection_after_the_setting_changes(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", 1.0, raising=False)
    state = state_with_theta(0.5, scanning=True)
    SessionService._scan_params(state)
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", 0.0, raising=False)
    bank = FakeTasks([-2.0, -0.5, 0.4, 1.6])
    assert service_with_bank(bank)._select_task_for_skill(state, "S").irt_difficulty == -0.5


def test_session_flags_roundtrip_and_old_states_load_as_none():
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    assert state.to_dict()["deep_scan_params"] is None
    state.deep_scan_params = {"confirm_probes": 2, "probe_difficulty_offset": 1.0, "trigger_mode": "importance"}
    assert SessionState.from_dict(state.to_dict()).deep_scan_params == state.deep_scan_params
    legacy = state.to_dict()
    del legacy["deep_scan_params"]
    assert SessionState.from_dict(legacy).deep_scan_params is None


def test_rebuilt_report_gives_the_same_chains_after_the_setting_changes(monkeypatch):
    """Session ran with N=2 (stored in its state); the report is rebuilt later under other settings."""
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 2, raising=False)
    service, state = frozen_state({}, bank=None)
    SessionService._scan_params(state)
    stored_n = state.deep_scan_params["confirm_probes"]
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G7_C", 0, minute=2, deep=True, origin="G8_A", step=1),
        answer("G7_C", 0, minute=3, deep=True, origin="G8_A", step=2),     # confirmed with N = 2
        answer("G8_D", 0, minute=4, deep=True, origin="G8_A", step=3),     # one miss: unconfirmed with N = 2
    ]
    at_creation = chains_of(answers, confirm=stored_n)
    assert at_creation[0]["root_gap_skill_id"] == "G7_C"
    for live in (1, 2, 3, 5):
        monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", live, raising=False)
        restored = SessionState.from_dict(state.to_dict())                 # what the report job reads
        assert chains_of(answers, confirm=restored.deep_scan_params["confirm_probes"]) == at_creation


@pytest.mark.parametrize("snapshot,expected", [
    ({"deep_scan_params": {"confirm_probes": 2, "probe_difficulty_offset": 1.0, "trigger_mode": "importance"}},
     {"confirm_probes": 2, "probe_difficulty_offset": 1.0, "trigger_mode": "importance"}),
    ({}, None),                                            # session from before the flags: old rule
])
def test_report_job_passes_the_sessions_stored_params_to_the_generator(monkeypatch, snapshot, expected):
    from src.domain import report_jobs
    session = NS(id="sid", student_id="u", grade_level=8, theta=0.1, theta_se=0.3, overall_level="at_grade",
                 topic_breakdown={}, weak_skills=[], items_answered=20, stop_reason="precision_reached",
                 state_snapshot=snapshot)
    captured = {}
    monkeypatch.setattr(report_jobs, "SessionLocal", lambda: NS(close=lambda: None, rollback=lambda: None))
    monkeypatch.setattr(report_jobs, "recover_stale_report_jobs", lambda db: 0)
    monkeypatch.setattr(report_jobs, "_claim_next_report", lambda db: (NS(id="rid", report_json=None), session))
    monkeypatch.setattr(report_jobs, "generate_and_save_report",
                        lambda db, **kw: captured.update(kw) or NS(generation_status="ready"))
    assert report_jobs.process_next_report_job() is True
    assert captured["deep_scan_params"] == expected


def test_probe_target_is_clamped_to_the_content_api_range(monkeypatch):
    # theta -2.52 with offset 1.5 used to request target_b=-4.02 -> content-service 422 (ge=-4)
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", 1.5, raising=False)
    bank = FakeTasks([-3.9, -2.0, 0.4])
    state = state_with_theta(-2.52, scanning=True)
    assert service_with_bank(bank)._select_task_for_skill(state, "S").irt_difficulty == -3.9
    assert bank.targets == [-4.0]


def test_trigger_mode_is_frozen_at_session_start_not_read_live(monkeypatch):
    """Review #3: the trigger is evaluated before any scan, so the mode must come from the
    session's frozen flags, not the live setting (a mid-session config change must not flip it)."""
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "importance", raising=False)
    service = service_with_edges({"L3_5": [EDGE]})
    state = state_with_theta(0.0, scanning=False)
    SessionService._scan_params(state)                                 # what create_session does
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "hard_prereq", raising=False)
    assert not service._l3_warrants_deep_scan(state, NS(subtopic_id="L3_5", importance=5))
    assert state.deep_scan_params["trigger_mode"] == "importance"


def test_create_session_freezes_the_flags_before_any_navigation(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "hard_prereq", raising=False)
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 2, raising=False)
    service = object.__new__(SessionService)
    service.session_repo = NS(get_by_invite_code=lambda _code: None)
    seen = []

    class Stop(Exception):
        pass

    def build_grid(state):
        seen.append(dict(state.deep_scan_params or {}))
        raise Stop

    service._build_topic_grid = build_grid
    with pytest.raises(Stop):
        service.create_session(student_id="u", grade_level=8)
    assert seen == [{"confirm_probes": 2, "probe_difficulty_offset": ss.settings.deep_scan_probe_difficulty_offset,
                     "trigger_mode": "hard_prereq",
                     "importance_threshold": ss.settings.deep_scan_importance_threshold,
                     "session_budget": ss.settings.deep_scan_session_budget,
                     "max_items": ss.settings.deep_scan_max_items, **STAGE3B_DEFAULTS,
                     "hard_prereq_min_grade": 0}]


def test_negative_offset_target_is_clamped_to_the_upper_bound(monkeypatch):
    # a negative offset makes probes HARDER: theta 3.2 + 1.5 = 4.7 would be a 422 (le=4) in content-service
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", -1.5, raising=False)
    bank = FakeTasks([0.4, 3.9])
    state = state_with_theta(3.2, scanning=True)
    assert service_with_bank(bank)._select_task_for_skill(state, "S").irt_difficulty == 3.9
    assert bank.targets == [4.0]


# ── every flag is frozen at creation; nothing in the session flow reads the live settings ─────────────────

ALL_KEYS = {"confirm_probes", "probe_difficulty_offset", "trigger_mode",
            "importance_threshold", "session_budget", "max_items",
            "trigger_rule", "residual_min", "probe_min_p",                  # stage 3b added these three
            "hard_prereq_min_grade"}                                        # DIAG-1 grade gate
STAGE3B_DEFAULTS = {"trigger_rule": "current", "residual_min": 1.0, "probe_min_p": 0.0}


def set_live(monkeypatch, **flags):
    for name, value in flags.items():
        monkeypatch.setattr(ss.settings, f"deep_scan_{name}", value, raising=False)


def test_create_session_freezes_all_flags(monkeypatch):
    set_live(monkeypatch, confirm_probes=3, probe_difficulty_offset=0.75, trigger_mode="hard_prereq",
             importance_threshold=9, session_budget=4, max_items=3, hard_prereq_min_grade=6)
    service = object.__new__(SessionService)
    service.session_repo = NS(get_by_invite_code=lambda _code: None)
    seen = []

    class Stop(Exception):
        pass

    def build_grid(state):
        seen.append(state.deep_scan_params)
        raise Stop

    service._build_topic_grid = build_grid
    with pytest.raises(Stop):
        service.create_session(student_id="u", grade_level=8)
    assert seen == [{"confirm_probes": 3, "probe_difficulty_offset": 0.75, "trigger_mode": "hard_prereq",
                     "importance_threshold": 9, "session_budget": 4, "max_items": 3, **STAGE3B_DEFAULTS,
                     "hard_prereq_min_grade": 6}]
    assert set(seen[0]) == ALL_KEYS


def test_frozen_importance_threshold_is_used_after_the_setting_changes(monkeypatch):
    set_live(monkeypatch, importance_threshold=8)
    service = service_with_edges({})
    state = state_with_theta(0.0, scanning=False)
    SessionService._scan_params(state)                                  # create_session
    set_live(monkeypatch, importance_threshold=3)                       # config edited mid-session
    assert not service._l3_warrants_deep_scan(state, NS(subtopic_id="L3", importance=5))
    assert service._l3_warrants_deep_scan(state, NS(subtopic_id="L3", importance=8))
    other = state_with_theta(0.0, scanning=False)
    set_live(monkeypatch, importance_threshold=3)
    SessionService._scan_params(other)
    set_live(monkeypatch, importance_threshold=10)
    assert service._l3_warrants_deep_scan(other, NS(subtopic_id="L3", importance=5))     # frozen 3, not live 10


def test_frozen_session_budget_is_used_after_the_setting_changes(monkeypatch):
    set_live(monkeypatch, session_budget=2)
    state = state_with_theta(0.0, scanning=False)
    SessionService._scan_params(state)
    set_live(monkeypatch, session_budget=100)
    state.deep_scan_items_total = 1
    assert not SessionService._deep_scan_budget_spent(state)
    state.deep_scan_items_total = 2
    assert SessionService._deep_scan_budget_spent(state)                # frozen 2, live 100 ignored
    # ... and the scan engine obeys it: the second probe spends the budget and ends the scan
    service = make_service({}, [])
    scan_state = scanning_state("B", ["C"])
    scan_state.deep_scan_params = dict(state.deep_scan_params)
    scan_state.deep_scan_items_total = 1
    assert service._advance_deep_scan(scan_state, True) == "ADVANCED"
    other = state_with_theta(0.0, scanning=False)
    set_live(monkeypatch, session_budget=1)
    SessionService._scan_params(other)
    set_live(monkeypatch, session_budget=0)
    other.deep_scan_items_total = 0
    assert not SessionService._deep_scan_budget_spent(other)            # frozen 1, live 0 ignored


def test_frozen_max_items_caps_the_scan_after_the_setting_changes(monkeypatch):
    set_live(monkeypatch, max_items=2)
    service, state = frozen_state({"G8_A": ["B", "C", "D"]})
    SessionService._scan_params(state)
    set_live(monkeypatch, max_items=6)
    service._init_deep_scan(state, "G8_A")
    assert state.deep_scan["max_items"] == 2                            # frozen 2, live 6 ignored
    assert service._advance_deep_scan(state, True) == "task:C"
    assert service._advance_deep_scan(state, True) == "ADVANCED"        # per-scan cap of 2 reached


# ── backward compatibility: sessions stored before the flags / before some flag existed ───────────────────

def test_preview_paths_do_not_freeze_a_pre_flag_session(monkeypatch):
    set_live(monkeypatch, importance_threshold=8, trigger_mode="importance", session_budget=6)
    service = service_with_edges({})
    state = navigation_state(9)
    assert state.deep_scan_params is None
    before = copy.deepcopy(state.to_dict())
    assert service._has_pending_critical_probe(state, False) is True    # live fallback: importance 9 >= 8
    assert state.deep_scan_params is None
    assert service._l3_warrants_deep_scan(state, NS(subtopic_id="L3", importance=9))
    assert SessionService._deep_scan_budget_spent(state) is False
    assert SessionService._peek_scan_params(state)["session_budget"] == 6
    assert state.deep_scan_params is None and state.to_dict() == before


def test_partially_stored_params_fall_back_to_live_settings_without_mutation(monkeypatch):
    set_live(monkeypatch, importance_threshold=8, session_budget=6, max_items=6)
    old = {"confirm_probes": 2, "probe_difficulty_offset": 0.5, "trigger_mode": "importance"}   # before the 3 new keys
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.deep_scan_params = dict(old)
    peeked = SessionService._peek_scan_params(state)
    assert peeked["confirm_probes"] == 2 and peeked["probe_difficulty_offset"] == 0.5
    assert (peeked["importance_threshold"], peeked["session_budget"], peeked["max_items"]) == (8, 6, 6)
    assert state.deep_scan_params == old                                # peek stores nothing
    service = service_with_edges({})
    assert service._l3_warrants_deep_scan(state, NS(subtopic_id="L3", importance=8))
    assert state.deep_scan_params == old
    # first real use freezes the missing keys; stored ones are kept as they were
    set_live(monkeypatch, importance_threshold=5)
    frozen = SessionService._scan_params(state)
    assert set(frozen) == ALL_KEYS and frozen["importance_threshold"] == 5 and frozen["confirm_probes"] == 2
    set_live(monkeypatch, importance_threshold=9)
    assert SessionService._scan_params(state)["importance_threshold"] == 5


def test_complete_params_are_returned_as_is(monkeypatch):
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    SessionService._scan_params(state)
    stored = state.deep_scan_params
    assert SessionService._peek_scan_params(state) is stored and SessionService._scan_params(state) is stored


# ── D1: a non-finite target must not clamp to the easiest items ───────────────

@pytest.mark.parametrize("scanning", [False, True])
def test_nan_target_is_logged_and_replaced_by_the_neutral_zero(scanning, caplog):
    # min(4, max(-4, nan)) is -4.0, and a target-less request is ordered by difficulty ASC:
    # both would serve the easiest items, so NaN falls back to 0.0
    bank = FakeTasks([-3.9, 0.4, 1.6])
    state = state_with_theta(float("nan"), scanning=scanning)
    with caplog.at_level("WARNING", logger=ss.log.name):
        task = service_with_bank(bank)._select_task_for_skill(state, "S")
    assert bank.targets == [0.0]
    assert task is not None and task.irt_difficulty == 0.4
    assert any("NaN target_b" in r.message for r in caplog.records)


@pytest.mark.parametrize("theta,expected", [(float("inf"), 4.0), (float("-inf"), -4.0)])
def test_infinite_target_is_clamped_to_the_api_bound(theta, expected):
    bank = FakeTasks([-3.9, 0.4, 3.9])
    task = service_with_bank(bank)._select_task_for_skill(state_with_theta(theta, scanning=False), "S")
    assert bank.targets == [expected]
    assert task.irt_difficulty == (3.9 if expected > 0 else -3.9)


def test_finite_target_is_still_clamped_not_dropped(caplog):
    bank = FakeTasks([-3.9, 0.4, 3.9])
    with caplog.at_level("WARNING", logger=ss.log.name):
        task = service_with_bank(bank)._select_task_for_skill(state_with_theta(9.0, scanning=False), "S")
    assert bank.targets == [4.0] and task.irt_difficulty == 3.9
    assert not caplog.records


def test_nan_target_with_no_unused_task_returns_none():
    bank = FakeTasks([0.4])
    state = state_with_theta(float("nan"), scanning=False)
    state.used_task_ids.append("t0")                                    # the only task is used: both paths find nothing
    assert service_with_bank(bank)._select_task_for_skill(state, "S") is None
    assert bank.targets == [0.0]


# ── D2: a pre-flag session is frozen by answer handling, previews never freeze ────────────────────────────

def answering_service(state, seen):
    """Service whose collaborators are stubbed just enough to run _submit_answer_locked up to the
    early-stop decision; ``seen`` records the frozen params at the moment of the critical-probe preview."""
    service = object.__new__(SessionService)
    service.session_repo = NS(get_fresh=lambda sid, for_update=False: None)
    service.get_completed_answer_result = lambda sid, task_id, answer: None
    service.redis = NS(load=lambda sid: state)
    service.evaluator = NS(evaluate=lambda task, answer: (1.0, "correct"))
    service.answer_repo = NS(log_answer=lambda **kw: None)
    real_preview = service._has_pending_critical_probe

    def preview(st, correct):
        seen.append(copy.deepcopy(st.deep_scan_params))
        return real_preview(st, correct)

    service._has_pending_critical_probe = preview
    service._should_stop = lambda st, pending_critical_probe=False: True
    service._complete_session = lambda st, outcome, category: "DONE"
    return service


def test_answer_handling_freezes_a_pre_flag_session_before_any_preview(monkeypatch):
    set_live(monkeypatch, importance_threshold=8, session_budget=6, max_items=6, trigger_mode="importance",
             confirm_probes=1, probe_difficulty_offset=0.0)
    task = NS(id="T", irt_discrimination=1.0, irt_difficulty=0.0, irt_guessing=0.0)
    monkeypatch.setattr(ss, "task_object", lambda snapshot, task_id: task)
    state = navigation_state(9)
    state.current_task_id, state.current_task_snapshot = "T", {"id": "T"}
    assert state.deep_scan_params is None                               # created before the flags existed
    seen = []
    service = answering_service(state, seen)
    result = service._submit_answer_locked(session_id="sid", task_id="T", student_answer="1", time_ms=1)
    assert result == "DONE"
    assert len(seen) == 1 and set(seen[0]) == ALL_KEYS                  # frozen BEFORE the preview ran
    assert state.deep_scan_params["importance_threshold"] == 8
    # the config changes afterwards: the frozen values keep deciding
    set_live(monkeypatch, importance_threshold=3)
    assert SessionService._peek_scan_params(state)["importance_threshold"] == 8
    # ... while previews on another pre-flag state still never freeze it
    other = navigation_state(9)
    assert service._l3_warrants_deep_scan(other, NS(subtopic_id="L3", importance=5)) is True   # live 3
    assert other.deep_scan_params is None


def test_answer_handling_leaves_complete_params_untouched(monkeypatch):
    task = NS(id="T", irt_discrimination=1.0, irt_difficulty=0.0, irt_guessing=0.0)
    monkeypatch.setattr(ss, "task_object", lambda snapshot, task_id: task)
    state = navigation_state(9)
    state.current_task_id, state.current_task_snapshot = "T", {"id": "T"}
    SessionService._scan_params(state)
    stored = state.deep_scan_params
    set_live(monkeypatch, importance_threshold=2, session_budget=1)
    seen = []
    answering_service(state, seen)._submit_answer_locked(session_id="sid", task_id="T", student_answer="1", time_ms=1)
    assert state.deep_scan_params is stored and seen == [stored]


def test_a_new_session_freezes_the_oc15_defaults(monkeypatch):
    for name in ("DEEP_SCAN_PROBE_DIFFICULTY_OFFSET", "DEEP_SCAN_CONFIRM_PROBES", "DEEP_SCAN_TRIGGER_MODE",
                 "DEEP_SCAN_IMPORTANCE_THRESHOLD", "DEEP_SCAN_SESSION_BUDGET", "DEEP_SCAN_MAX_ITEMS",
                 "DEEP_SCAN_HARD_PREREQ_MIN_GRADE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ss, "settings", Settings(_env_file=None))
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    assert SessionService._scan_params(state) == {
        "confirm_probes": 2, "probe_difficulty_offset": 1.5, "trigger_mode": "importance",
        "importance_threshold": 8, "session_budget": 6, "max_items": 6, **STAGE3B_DEFAULTS,
        "hard_prereq_min_grade": 0}


# ── DIAG-1 grade gate: DEEP_SCAN_HARD_PREREQ_MIN_GRADE ────────────────────────
# "hard_prereq" applies only from the gate grade; below it the default ("importance") rule decides.
# The mode and the gate are frozen per session; 0 = no gate = the behaviour before the setting existed.

GATE_GRADES = (5, 6, 8, 11)


def at_grade(state, grade):
    state.grade_level = grade
    return state


def gate_decisions(grade):
    """(unimportant L3 with a hard edge fires, important L3 without edges fires) for a session of ``grade``."""
    service = service_with_edges({"L3_edge": [EDGE]})
    state = at_grade(state_with_theta(0.0, scanning=False), grade)
    return (service._l3_warrants_deep_scan(state, NS(subtopic_id="L3_edge", importance=5)),
            service._l3_warrants_deep_scan(state, NS(subtopic_id="L3_imp", importance=9)))


@pytest.mark.parametrize("grade", GATE_GRADES)
def test_gate_zero_keeps_hard_prereq_in_every_grade(monkeypatch, grade):
    set_live(monkeypatch, trigger_mode="hard_prereq", hard_prereq_min_grade=0)
    assert gate_decisions(grade) == (True, False)                      # exactly the pre-gate hard_prereq rule


@pytest.mark.parametrize("grade", GATE_GRADES)
@pytest.mark.parametrize("gate", [0, 6, 9])
def test_importance_mode_ignores_the_gate_in_every_grade(monkeypatch, grade, gate):
    set_live(monkeypatch, trigger_mode="importance", hard_prereq_min_grade=gate)
    assert gate_decisions(grade) == (False, True)                      # the gate only limits hard_prereq


@pytest.mark.parametrize("grade,expected", [
    (4, (False, True)),             # below the gate: the default importance rule
    (5, (False, True)),
    (6, (True, False)),             # from the gate grade: hard_prereq
    (7, (True, False)),
    (8, (True, False)),
    (11, (True, False)),
])
def test_gate_six_limits_hard_prereq_to_grade_six_and_up(monkeypatch, grade, expected):
    set_live(monkeypatch, trigger_mode="hard_prereq", hard_prereq_min_grade=6)
    assert gate_decisions(grade) == expected


def test_below_the_gate_the_importance_threshold_is_the_frozen_one(monkeypatch):
    set_live(monkeypatch, trigger_mode="hard_prereq", hard_prereq_min_grade=6, importance_threshold=8)
    service = service_with_edges({})
    state = at_grade(state_with_theta(0.0, scanning=False), 5)
    SessionService._scan_params(state)
    set_live(monkeypatch, importance_threshold=3)
    assert not service._l3_warrants_deep_scan(state, NS(subtopic_id="L3", importance=7))
    assert service._l3_warrants_deep_scan(state, NS(subtopic_id="L3", importance=8))
    assert service.calls == []                                         # importance rule: no edge lookup


@pytest.mark.parametrize("grade,importance,edges,fires", [
    (5, 5, {"L3": [EDGE]}, False),      # gate 6, grade 5: a hard edge alone does not start a scan
    (5, 9, {}, True),                   # ... the importance rule does
    (6, 5, {"L3": [EDGE]}, True),       # grade 6: hard_prereq
    (6, 9, {}, False),
    (9, 5, {"L3": [EDGE]}, True),
    (9, 9, {}, False),
])
def test_gate_trigger_and_pending_probe_agree(monkeypatch, grade, importance, edges, fires):
    set_live(monkeypatch, trigger_mode="hard_prereq", hard_prereq_min_grade=6)
    service = service_with_edges(edges)
    service._advance_topic = lambda state, passed: "TOPIC"
    service._init_deep_scan = lambda state, skill: f"SCAN:{skill}"
    service._pick_task_for_navigation = lambda state, skill: f"NAV:{skill}"
    service._pick_task_from_subtopic = lambda state, nav: "NEXT_L3"

    state = at_grade(navigation_state(importance), grade)
    assert service._has_pending_critical_probe(state, False) is fires      # early stop is blocked iff a scan will start
    assert service._has_pending_critical_probe(state, True) is False
    result = service._advance_navigation(state, False)
    assert (result == "SCAN:S1") is fires
    assert state.is_in_deep_scan is fires
    if not fires:
        assert result == "TOPIC"


def test_gate_is_frozen_at_session_start_not_read_live(monkeypatch):
    set_live(monkeypatch, trigger_mode="hard_prereq", hard_prereq_min_grade=6)
    service = service_with_edges({"L3_edge": [EDGE]})
    grade5 = at_grade(state_with_theta(0.0, scanning=False), 5)
    grade8 = at_grade(state_with_theta(0.0, scanning=False), 8)
    SessionService._scan_params(grade5)
    SessionService._scan_params(grade8)
    sub = NS(subtopic_id="L3_edge", importance=5)
    assert not service._l3_warrants_deep_scan(grade5, sub) and service._l3_warrants_deep_scan(grade8, sub)
    for live_gate in (0, 3, 9):                                        # config edited mid-session
        set_live(monkeypatch, hard_prereq_min_grade=live_gate)
        assert not service._l3_warrants_deep_scan(grade5, sub)
        assert service._l3_warrants_deep_scan(grade8, sub)
    assert grade5.deep_scan_params["hard_prereq_min_grade"] == 6
    # the other direction: a session frozen with gate 0 keeps hard_prereq in grade 5 when the gate is switched on
    set_live(monkeypatch, hard_prereq_min_grade=0)
    old = at_grade(state_with_theta(0.0, scanning=False), 5)
    SessionService._scan_params(old)
    set_live(monkeypatch, hard_prereq_min_grade=6)
    assert service._l3_warrants_deep_scan(old, sub)
    # the frozen mode itself is untouched by the gate: it is still reported as the session's trigger_mode
    assert grade5.deep_scan_params["trigger_mode"] == "hard_prereq"


def test_session_stored_without_the_gate_key_reads_the_live_default_and_is_not_mutated(monkeypatch):
    """A session stored before the setting existed (the six older keys): like every newer flag, the
    missing key comes from the settings - the default 0 keeps hard_prereq in all grades."""
    set_live(monkeypatch, hard_prereq_min_grade=0)
    six_old = {"confirm_probes": 2, "probe_difficulty_offset": 1.5, "trigger_mode": "hard_prereq",
               "importance_threshold": 8, "session_budget": 6, "max_items": 6}
    service = service_with_edges({"L3_edge": [EDGE]})
    sub = NS(subtopic_id="L3_edge", importance=5)
    state = at_grade(state_with_theta(0.0, scanning=False), 5)
    state.deep_scan_params = dict(six_old)
    assert SessionService._peek_scan_params(state)["hard_prereq_min_grade"] == 0
    assert service._l3_warrants_deep_scan(state, sub)                  # default 0: hard_prereq as before
    assert state.deep_scan_params == six_old                           # previews store nothing
    # first real use freezes the missing key; later config changes no longer matter
    frozen = SessionService._scan_params(state)
    assert set(frozen) == ALL_KEYS and frozen["hard_prereq_min_grade"] == 0
    set_live(monkeypatch, hard_prereq_min_grade=6)
    assert service._l3_warrants_deep_scan(state, sub)
    # an importance-mode session stored without the key is unaffected whatever the live gate is
    importance = at_grade(state_with_theta(0.0, scanning=False), 5)
    importance.deep_scan_params = dict(six_old, trigger_mode="importance")
    assert not service._l3_warrants_deep_scan(importance, sub)
    assert service._l3_warrants_deep_scan(importance, NS(subtopic_id="L3_imp", importance=9))


def test_pre_flag_session_without_any_params_uses_the_live_gate_without_freezing(monkeypatch):
    set_live(monkeypatch, trigger_mode="hard_prereq", hard_prereq_min_grade=6)
    service = service_with_edges({"L3_edge": [EDGE]})
    state = at_grade(navigation_state(5, "L3_edge"), 5)
    assert state.deep_scan_params is None
    assert not service._l3_warrants_deep_scan(state, NS(subtopic_id="L3_edge", importance=5))
    assert state.deep_scan_params is None


def test_applied_trigger_mode_and_grade_are_logged(monkeypatch, caplog):
    set_live(monkeypatch, trigger_mode="hard_prereq", hard_prereq_min_grade=6)
    messages = {}
    for grade in (5, 8):
        service = service_with_edges({"L3": [EDGE]} if grade == 8 else {})
        service._advance_topic = lambda state, passed: "TOPIC"
        service._init_deep_scan = lambda state, skill: "SCAN"
        state = at_grade(navigation_state(9 if grade == 5 else 5), grade)
        caplog.clear()
        with caplog.at_level("INFO", logger=ss.log.name):
            assert service._advance_navigation(state, False) == "SCAN"
        messages[grade] = [r.getMessage() for r in caplog.records if "Deep scan triggered" in r.getMessage()]
    assert len(messages[5]) == 1 and "trigger mode importance, grade 5" in messages[5][0]
    assert len(messages[8]) == 1 and "trigger mode hard_prereq, grade 8" in messages[8][0]


def test_gate_is_read_from_the_environment_and_reaches_the_session(monkeypatch):
    """The A9 grade rule through the real settings object: HARD_PREREQ_MIN_GRADE=6 with TRIGGER_MODE=hard_prereq."""
    monkeypatch.setenv("DEEP_SCAN_TRIGGER_MODE", "hard_prereq")
    monkeypatch.setenv("DEEP_SCAN_HARD_PREREQ_MIN_GRADE", "6")
    cfg = Settings(_env_file=None)
    assert (cfg.deep_scan_trigger_mode, cfg.deep_scan_hard_prereq_min_grade) == ("hard_prereq", 6)
    monkeypatch.setattr(ss, "settings", cfg)
    service = service_with_edges({"L3_edge": [EDGE]})
    sub = NS(subtopic_id="L3_edge", importance=5)
    states = {g: at_grade(state_with_theta(0.0, scanning=False), g) for g in (5, 6)}
    for state in states.values():
        assert SessionService._scan_params(state)["hard_prereq_min_grade"] == 6
    assert not service._l3_warrants_deep_scan(states[5], sub)
    assert service._l3_warrants_deep_scan(states[6], sub)
