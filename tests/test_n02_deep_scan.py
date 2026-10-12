"""N02: Deep Scan link, chains, branch continuation and stable ordering."""
import random
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest

from src.domain import report_generator as rg
from src.domain.navigators.skill_navigator import DeepScanState  # noqa: F401  (re-exported from the same module)
from src.domain.session_service import SessionService
from src.domain.session_state import SessionState

T0 = datetime(2026, 10, 1, 10, 0, 0)


@pytest.fixture(autouse=True)
def classic_scan_flags(monkeypatch):
    """This module describes the scan engine where ONE wrong answer makes a gap and probes target
    theta exactly.  The shipped defaults are variant OC15 (2 confirmation probes, offset 1.5), so
    the classic flags are set explicitly (the OC15 behaviour is tested in test_deep_scan_variants)."""
    from src.domain import session_service as ss
    monkeypatch.setattr(ss.settings, "deep_scan_confirm_probes", 1, raising=False)
    monkeypatch.setattr(ss.settings, "deep_scan_probe_difficulty_offset", 0.0, raising=False)


def answer(skill, outcome, *, minute, deep=False, origin=None, step=None, task="T", aid=None):
    return NS(id=aid or f"a{minute:03d}", skill_id=skill, task_id=None, outcome=outcome,
              is_deep_scan=deep, phase="deep_scan" if deep else "navigation",
              eval_category="correct" if outcome else "wrong", student_answer="1" if outcome else "0",
              answered_at=T0 + timedelta(minutes=minute),
              deep_scan_origin_skill_id=origin, deep_scan_step=step, topic_id="X")


def skills(*ids):
    return {i: {"name_ru": f"Навык {i}"} for i in ids}


def chains_of(answers, grade=8, ids=("G8_A", "G8_B", "G7_C", "G8_D")):
    return rg._reconstruct_root_cause_chains(answers, skills(*ids), [], grade)


# ── chains ────────────────────────────────────────────────────────────────────

def test_same_grade_prerequisite_chain_is_not_dropped_and_is_a_breakpoint():
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G8_B", 0, minute=2, deep=True, origin="G8_A", step=1),   # same grade 8
    ]
    chains = chains_of(answers)
    assert len(chains) == 1
    assert chains[0]["source_skill_id"] == "G8_A" and chains[0]["root_gap_skill_id"] == "G8_B"
    assert chains[0]["severity"] == "local_gap" and chains[0]["evidence_source"] == "stored_link"


def test_same_grade_failure_deeper_in_the_chain_beats_the_source_on_equal_grades():
    # The old tie-break returned the source whenever grades were equal.
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G8_B", 0, minute=2, deep=True, origin="G8_A", step=1),
        answer("G8_D", 0, minute=3, deep=True, origin="G8_A", step=2),
    ]
    assert chains_of(answers)[0]["root_gap_skill_id"] == "G8_D"


def test_lower_grade_failure_wins_and_correct_prerequisite_is_the_anchor():
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G8_B", 1, minute=2, deep=True, origin="G8_A", step=1),
        answer("G7_C", 0, minute=3, deep=True, origin="G8_A", step=2),
    ]
    chain = chains_of(answers)[0]
    assert chain["root_gap_skill_id"] == "G7_C" and chain["severity"] == "warning"
    assert chain["anchor_skill_id"] == "G8_B"
    assert [s["skill_id"] for s in chain["steps"]] == ["G8_A", "G8_B", "G7_C"]


def test_scan_where_every_prerequisite_was_answered_correctly_gives_no_chain():
    answers = [answer("G8_A", 0, minute=1), answer("G8_B", 1, minute=2, deep=True, origin="G8_A", step=1)]
    assert chains_of(answers) == []


@pytest.mark.parametrize("seed", range(6))
def test_chain_does_not_depend_on_row_order(seed):
    answers = [
        answer("G8_D", 1, minute=0),
        answer("G8_A", 0, minute=1),
        answer("G8_B", 0, minute=2, deep=True, origin="G8_A", step=1),
        answer("G7_C", 0, minute=3, deep=True, origin="G8_A", step=2),
    ]
    expected = chains_of(answers)
    shuffled = answers[:]
    random.Random(seed).shuffle(shuffled)
    assert chains_of(shuffled) == expected
    # and without timestamps the stored step orders the chain
    bare = [NS(**{**a.__dict__, "answered_at": None}) for a in shuffled]
    got = chains_of(bare)[0]
    assert [s["skill_id"] for s in got["steps"][1:]] == ["G8_B", "G7_C"]


def test_origin_link_attaches_the_scan_to_the_right_source_even_when_answers_interleave():
    # Legacy inference would pair the deep answer with the *last* wrong answer (G8_D).
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G8_D", 0, minute=2),
        answer("G7_C", 0, minute=3, deep=True, origin="G8_A", step=1),
    ]
    chain = chains_of(answers)[0]
    assert chain["source_skill_id"] == "G8_A" and chain["root_gap_skill_id"] == "G7_C"


def test_two_scans_from_two_origins_make_two_chains():
    answers = [
        answer("G8_A", 0, minute=1), answer("G7_C", 0, minute=2, deep=True, origin="G8_A", step=1),
        answer("G8_D", 0, minute=3), answer("G8_B", 0, minute=4, deep=True, origin="G8_D", step=1),
    ]
    got = {(c["source_skill_id"], c["root_gap_skill_id"]) for c in chains_of(answers)}
    assert got == {("G8_A", "G7_C"), ("G8_D", "G8_B")}


def test_legacy_answers_without_link_keep_the_inference_but_keep_same_grade_links():
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G8_B", 0, minute=2, deep=True),   # no origin link
    ]
    chains = chains_of(answers)
    assert len(chains) == 1 and chains[0]["evidence_source"] == "inferred"
    assert chains[0]["root_gap_skill_id"] == "G8_B"


def test_summary_sentence_depends_on_whether_a_deep_scan_ran():
    args = dict(class_equivalent="начало 8 класса", grade_level=8, score_pct=40,
                boundary={"breakpoint_skills": ["Дроби"]}, strong_skills=[], chains=[])
    without = rg._build_deterministic_summary(**args)
    ran = rg._build_deterministic_summary(**args, deep_scan_run=True)
    assert "без углублённой проверки" in without
    assert "без углублённой проверки" not in ran
    assert "углублённая проверка не подтвердила единую первопричину" in ran
    assert "Deep Scan" not in without + ran


@pytest.mark.parametrize("equivalent", ["начало 5 класса", "середина 8 класса", "конец 9 класса", "начало 11 класса"])
def test_conclusion_is_grammatical_for_every_class_equivalent(equivalent):
    text = rg._build_deterministic_summary(
        class_equivalent=equivalent, grade_level=11, score_pct=40, solved=10, total=25,
        boundary={"breakpoint_skills": ["Дроби"]}, strong_skills=[], chains=[{"root_gap_skill_name": "Дроби"}],
    )
    assert f"Уровень по результатам измерения — {equivalent} (заявлен 11 класс)." in text
    assert "соответствует" not in text and "Deep Scan" not in text
    assert "Углублённая проверка подтвердила первопричину: «Дроби»." in text

# ── ordering / importance ─────────────────────────────────────────────────────

def test_most_important_l4_with_stable_ties():
    child = lambda i, imp, seq: NS(id=i, importance=imp, sequence_order=seq)  # noqa: E731
    pick = SessionService._most_important_l4
    assert pick([child("a", 5, 1), child("b", 9, 2), child("c", 7, 3)]) == "b"
    # equal importance: the middle one by sequence_order (previous behaviour), independent of row order
    kids = [child("a", 5, 1), child("b", 5, 2), child("c", 5, 3)]
    for seed in range(5):
        random.Random(seed).shuffle(kids)
        assert pick(kids) == "b"
    assert pick([child("z", 5, 1), child("y", 5, 1)]) == "z"   # id breaks a sequence tie
    assert pick([]) is None


def test_prerequisite_order_is_by_criticality_weight_then_id(monkeypatch):
    from src.repositories import knowledge_repo as kr

    rows = [
        {"skill_id": "P", "prerequisite_id": "B", "weight": 0.5, "criticality": 9},
        {"skill_id": "P", "prerequisite_id": "A", "weight": 0.5, "criticality": 9},
        {"skill_id": "P", "prerequisite_id": "C", "weight": 0.9, "criticality": 5},
        {"skill_id": "P", "prerequisite_id": "D", "weight": 0.9, "criticality": 9},
    ]

    class Resp:
        def raise_for_status(self): pass
        def json(self): return list(rows)

    monkeypatch.setattr(kr.content_client, "get", lambda *a, **k: Resp())
    got = [p.prerequisite_id for p in kr.SkillPrerequisiteRepository().get_prerequisites("P", hard_only=True)]
    assert got == ["D", "A", "B", "C"]
    random.Random(1).shuffle(rows)
    assert [p.prerequisite_id for p in kr.SkillPrerequisiteRepository().get_prerequisites("P")] == got


# ── branch continuation ───────────────────────────────────────────────────────

def make_service(graph, picked):
    service = object.__new__(SessionService)
    service._prereq_l4_ids = lambda skill: list(graph.get(skill, []))
    service._set_context_for_skill = lambda state, skill: None
    service._pick_task_for_skill = lambda state, skill: picked.append(skill) or f"task:{skill}"
    service._advance_topic = lambda state, correct: "ADVANCED"
    return service


def scanning_state(current, queue, max_items=6, items_used=0, origin="G8_A"):
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.phase, state.is_in_deep_scan = "deep_scan", True
    state.deep_scan = DeepScanState(origin_skill_id=origin, queue=list(queue), current_skill_id=current,
                                    max_items=max_items, items_used=items_used).to_dict()
    return state


def test_first_correct_answer_closes_only_its_branch():
    picked = []
    service = make_service({"B": ["B1"]}, picked)
    state = scanning_state("A", ["B", "C"])
    assert service._advance_deep_scan(state, True) == "task:B"           # A correct -> next branch B, scan goes on
    assert state.is_in_deep_scan and state.deep_scan["queue"] == ["C"]
    assert service._advance_deep_scan(state, False) == "task:B1"          # B wrong -> descend into B's prerequisite
    assert state.deep_scan["queue"] == ["C"] and state.deep_scan["gaps"] == ["B"]
    assert service._advance_deep_scan(state, True) == "task:C"            # B1 correct: B's branch ends, C still probed
    assert service._advance_deep_scan(state, True) == "ADVANCED"          # queue empty -> scan finished
    assert not state.is_in_deep_scan and state.phase == "navigation"
    assert state.confirmed_gaps == ["B", "G8_A"]
    assert picked == ["B", "B1", "C"]


def test_correct_answer_does_not_descend_into_that_skills_prerequisites():
    picked = []
    service = make_service({"A": ["A1"]}, picked)
    state = scanning_state("A", ["B"])
    assert service._advance_deep_scan(state, True) == "task:B"
    assert "A1" not in picked and "A1" not in state.deep_scan["queue"]


def test_scan_cap_of_six_items_is_kept_after_a_correct_answer():
    picked = []
    service = make_service({}, picked)
    state = scanning_state("S6", ["S7", "S8"], max_items=6, items_used=5)
    assert service._advance_deep_scan(state, True) == "ADVANCED"          # 6th item answered -> stop
    assert picked == [] and not state.is_in_deep_scan


def test_a_long_run_never_exceeds_six_items():
    picked = []
    queue = [f"Q{i}" for i in range(1, 12)]
    service = make_service({}, picked)
    state = scanning_state("Q0", queue)
    answered = 1
    result = None
    while state.is_in_deep_scan:
        result = service._advance_deep_scan(state, answered % 2 == 0)
        answered += 1
        assert answered <= 7
    assert answered - 1 == 6 and result == "ADVANCED"


# ── robustness: skills without tasks ──────────────────────────────────────────

def make_service_with_bank(graph, no_tasks, picked):
    service = object.__new__(SessionService)
    service._prereq_l4_ids = lambda skill: list(graph.get(skill, []))
    service._set_context_for_skill = lambda state, skill: None
    service._pick_task_for_skill = (
        lambda state, skill: None if skill in no_tasks else (picked.append(skill) or f"task:{skill}")
    )
    service._advance_topic = lambda state, correct: "ADVANCED"
    return service


@pytest.mark.parametrize("correct", [True, False])
def test_skill_without_tasks_in_the_middle_of_the_queue_is_skipped(correct):
    picked = []
    service = make_service_with_bank({}, {"B"}, picked)
    state = scanning_state("A", ["B", "C"])
    assert service._advance_deep_scan(state, correct) == "task:C"   # B skipped, not a session end
    assert state.is_in_deep_scan and state.deep_scan["current_skill_id"] == "C"
    assert "B" in state.deep_scan["tested"] and "B" not in state.deep_scan["gaps"]   # no evidence either way
    assert state.deep_scan["items_used"] == 1                                        # a skipped skill costs no item


@pytest.mark.parametrize("correct", [True, False])
def test_queue_of_skills_without_tasks_finishes_the_scan_and_resumes_cat(correct):
    picked = []
    service = make_service_with_bank({}, {"B", "C"}, picked)
    state = scanning_state("A", ["B", "C"])
    assert service._advance_deep_scan(state, correct) == "ADVANCED"   # main flow continues, never None
    assert not state.is_in_deep_scan and state.phase == "navigation" and state.deep_scan is None
    assert "G8_A" in state.confirmed_gaps


def test_first_probe_without_tasks_does_not_end_the_session_either():
    picked = []
    service = make_service_with_bank({"G8_A": ["P1", "P2"]}, {"P1"}, picked)
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.phase, state.is_in_deep_scan = "deep_scan", True
    assert service._init_deep_scan(state, "G8_A") == "task:P2"
    state2 = SessionState(session_id="s", student_id="u", grade_level=8)
    state2.phase, state2.is_in_deep_scan = "deep_scan", True
    service2 = make_service_with_bank({"G8_A": ["P1"]}, {"P1"}, [])
    assert service2._init_deep_scan(state2, "G8_A") == "ADVANCED"
    assert not state2.is_in_deep_scan and state2.confirmed_gaps == ["G8_A"]


# ── labels ────────────────────────────────────────────────────────────────────

def test_backend_labels_match_the_front_end_dictionary():
    from src.domain import level_policy as lp
    assert lp.STATUS_LABEL_RU == {
        "critical": "Критическое отставание", "below": "Ниже уровня класса",
        "partial_gap": "Частичные пробелы", "on_level": "Соответствует уровню",
        "above": "Выше уровня класса",
    }
    assert lp.CATEGORY_LABEL_RU == {
        "below_grade": "Ниже уровня класса", "at_grade": "На уровне класса",
        "above_grade": "Выше уровня класса",
    }


# ── descent: a wrong probe tests ITS OWN prerequisites ────────────────────────

def test_three_level_descent_identifies_the_root_and_the_chain_reflects_it():
    picked = []
    service = make_service({"P1": ["PP1"]}, picked)          # trigger G8_A -> P1 -> PP1
    state = scanning_state("P1", [])                          # P1 was issued first; the queue is empty
    # trigger wrong (earlier) -> P1 wrong: descend even though nothing else is queued
    assert service._advance_deep_scan(state, False) == "task:PP1"
    assert state.deep_scan["gaps"] == ["P1"] and state.deep_scan["current_skill_id"] == "PP1"
    # PP1 correct and nothing left: the scan ends, P1 is the deepest failed skill
    assert service._advance_deep_scan(state, True) == "ADVANCED"
    assert state.confirmed_gaps == ["P1", "G8_A"] and picked == ["PP1"]
    assert state.deep_scan_tested == ["P1", "PP1"]
    answers = [
        answer("G8_A", 0, minute=1),
        answer("G8_B", 0, minute=2, deep=True, origin="G8_A", step=1),     # stands for P1
        answer("G7_C", 1, minute=3, deep=True, origin="G8_A", step=2),     # stands for PP1, correct
    ]
    chain = chains_of(answers)[0]
    assert [s["deep_scan_step"] for s in chain["steps"][1:]] == [1, 2]
    assert chain["root_gap_skill_id"] == "G8_B" and chain["anchor_skill_id"] == "G7_C"


def test_descent_stops_at_a_skill_without_prerequisites():
    service = make_service({"P1": []}, [])
    state = scanning_state("P1", [])
    assert service._advance_deep_scan(state, False) == "ADVANCED"      # P1 is the root
    assert state.confirmed_gaps == ["P1", "G8_A"]


def test_descent_respects_the_six_item_cap():
    picked = []
    graph = {f"L{i}": [f"L{i + 1}"] for i in range(20)}
    service = make_service(graph, picked)
    state = scanning_state("L0", [])
    answered, result = 1, None
    while state.is_in_deep_scan:
        result = service._advance_deep_scan(state, False)          # every probe is wrong
        answered += 1
        assert answered <= 7
    assert answered - 1 == 6 and picked == ["L1", "L2", "L3", "L4", "L5"] and result == "ADVANCED"


def test_descent_never_repeats_a_skill_even_across_scans():
    picked = []
    service = make_service({"P1": ["P2", "G8_A"], "P2": ["P1", "P3"]}, picked)   # cycle back to P1 and to the trigger
    state = scanning_state("P1", [])
    assert service._advance_deep_scan(state, False) == "task:P2"       # G8_A (trigger) is not re-queued
    assert service._advance_deep_scan(state, False) == "task:P3"       # P1 (already tested) is not re-queued
    assert picked == ["P2", "P3"]
    service._advance_deep_scan(state, True)                             # scan over
    # a later scan of the same session skips what was already probed
    service2 = make_service({"G8_Z": ["P1", "P3", "NEW"]}, [])
    state2 = SessionState(session_id="s", student_id="u", grade_level=8)
    state2.deep_scan_tested = list(state.deep_scan_tested)
    state2.phase, state2.is_in_deep_scan = "deep_scan", True
    assert service2._init_deep_scan(state2, "G8_Z") == "task:NEW"


# ── per-session Deep Scan budget (DEEP_SCAN_SESSION_BUDGET) ───────────────────

def test_session_budget_is_read_from_the_environment(monkeypatch):
    from src.core.config import Settings
    assert Settings().deep_scan_session_budget == 6                    # default
    monkeypatch.setenv("DEEP_SCAN_SESSION_BUDGET", "3")
    assert Settings().deep_scan_session_budget == 3


def test_running_scan_stops_when_the_session_budget_is_reached(monkeypatch):
    from src.domain import session_service as ss
    monkeypatch.setattr(ss.settings, "deep_scan_session_budget", 4, raising=False)
    picked = []
    graph = {f"L{i}": [f"L{i + 1}"] for i in range(20)}
    service = make_service(graph, picked)
    state = scanning_state("L0", [])
    state.deep_scan_items_total = 2                                    # two probes spent in an earlier scan
    assert service._advance_deep_scan(state, False) == "task:L1"      # total 3 < 4: keeps descending
    assert service._advance_deep_scan(state, False) == "ADVANCED"     # total 4 == budget: scan ends
    assert not state.is_in_deep_scan and state.deep_scan_items_total == 4
    assert picked == ["L1"]


def test_session_budget_is_shared_across_scans_but_per_scan_cap_stays(monkeypatch):
    from src.domain import session_service as ss
    monkeypatch.setattr(ss.settings, "deep_scan_session_budget", 100, raising=False)
    service = make_service({f"L{i}": [f"L{i + 1}"] for i in range(20)}, [])
    state = scanning_state("L0", [])
    while state.is_in_deep_scan:
        service._advance_deep_scan(state, False)
    assert state.deep_scan_items_total == 6                            # per-scan cap of 6 unchanged


def test_scan_cannot_start_once_the_budget_is_spent(monkeypatch):
    from src.domain import session_service as ss
    monkeypatch.setattr(ss.settings, "deep_scan_session_budget", 5, raising=False)
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    assert not SessionService._deep_scan_budget_spent(state)
    state.deep_scan_items_total = 5
    assert SessionService._deep_scan_budget_spent(state)
    # the early-stop guard must not wait for a scan that can no longer start
    state.phase, state.current_skill_nav, state.current_subtopic_nav = "navigation", {"x": 1}, {"x": 1}
    sub = NS(importance=10)
    monkeypatch.setattr(ss.SkillNavigator, "from_dict", staticmethod(lambda d: NS(move=lambda c: None, get_failing_skill=lambda: "S", subtopic_score=lambda: 0.0)))
    monkeypatch.setattr(ss.SubtopicNavigator, "from_dict", staticmethod(lambda d: NS(peek_current=lambda: sub)))
    service = object.__new__(SessionService)
    assert service._has_pending_critical_probe(state, False) is False
    state.deep_scan_items_total = 0
    assert service._has_pending_critical_probe(state, False) is True


def test_budget_counter_roundtrips_through_the_session_state_and_old_states_load():
    state = SessionState(session_id="s", student_id="u", grade_level=8)
    state.deep_scan_items_total = 3
    assert SessionState.from_dict(state.to_dict()).deep_scan_items_total == 3
    legacy = state.to_dict()
    legacy.pop("deep_scan_items_total")
    assert SessionState.from_dict(legacy).deep_scan_items_total == 0
