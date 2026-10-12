"""DIAG-1 stage 2: Deep Scan variants behind config flags.

  DEEP_SCAN_PROBE_DIFFICULTY_OFFSET  probe items target theta - offset
  DEEP_SCAN_CONFIRM_PROBES           a gap needs N wrong answers on different items
  DEEP_SCAN_TRIGGER_MODE             "importance" (current) | "hard_prereq"

Defaults must reproduce the behaviour from before the flags existed.
"""
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

def test_flag_defaults_keep_the_current_behaviour(monkeypatch):
    for name in ("DEEP_SCAN_PROBE_DIFFICULTY_OFFSET", "DEEP_SCAN_CONFIRM_PROBES", "DEEP_SCAN_TRIGGER_MODE"):
        monkeypatch.delenv(name, raising=False)
    cfg = Settings(_env_file=None)
    assert cfg.deep_scan_probe_difficulty_offset == 0.0
    assert cfg.deep_scan_confirm_probes == 1
    assert cfg.deep_scan_trigger_mode == "importance"
    assert cfg.deep_scan_importance_threshold == 8 and cfg.deep_scan_max_items == 6
    assert cfg.deep_scan_session_budget == 6


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
        best = min(free, key=lambda k: (abs(free[k] - target_b), k))
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

def test_default_one_wrong_answer_is_a_gap_at_once():
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
    assert not service._l3_warrants_deep_scan(NS(subtopic_id="L3_5", importance=5))
    assert service._l3_warrants_deep_scan(NS(subtopic_id="L3_8", importance=8))
    assert service.calls == []                                         # the current rule does not even look up edges


def test_hard_prereq_mode_fires_for_unimportant_l3_with_a_hard_edge_and_not_without(monkeypatch):
    monkeypatch.setattr(ss.settings, "deep_scan_trigger_mode", "hard_prereq", raising=False)
    service = service_with_edges({"L3_5": [EDGE]})
    assert service._l3_warrants_deep_scan(NS(subtopic_id="L3_5", importance=5))
    assert not service._l3_warrants_deep_scan(NS(subtopic_id="L3_9", importance=9))   # no edges: importance is ignored
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
                                      "trigger_mode": "hard_prereq"}
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
