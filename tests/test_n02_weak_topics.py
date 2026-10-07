"""N02: a topic is weak only with evidence; L2/L4 are not duplicated."""
from types import SimpleNamespace as NS

from src.domain.report_generator import _build_plan_candidates, _build_skill_blocks, _make_l2_resolver

NAMES = {
    "G9_T1": {"name_ru": "Дроби"}, "G9_T2": {"name_ru": "Степени"},
    "G9_T1_S1_K1": {"name_ru": "Сложение дробей"}, "G9_T1_S1_K2": {"name_ru": "Сокращение дробей"},
    "G9_T2_S1_K1": {"name_ru": "Степень с нулём"},
}
PARENT = {"G9_T1_S1_K1": "G9_T1", "G9_T1_S1_K2": "G9_T1", "G9_T2_S1_K1": "G9_T2"}


def ans(topic, outcome, skill="x", deep=False):
    return NS(topic_id=topic, outcome=outcome, skill_id=skill, is_deep_scan=deep)


def l2_of(sid):
    return sid if sid in ("G9_T1", "G9_T2") else PARENT.get(sid)


def blocks(breakdown, answers, confirmed=()):
    return _build_skill_blocks(breakdown, list(confirmed), NAMES, answers, l2_of=l2_of)


def ids(items):
    return [i["skill_id"] for i in items]


def test_topic_with_only_correct_answers_is_never_weak_whatever_its_alpha():
    # alpha 0.2 (one correct answer) is 55%: below the old 65% threshold.
    strong, weak, critical = blocks({"G9_T1": {"alpha": 0.2, "observations": 1}}, [ans("G9_T1", 1)])
    assert weak == critical == [] and strong == []
    # even if the stored alpha is low and there are several observations
    _, weak, critical = blocks({"G9_T1": {"alpha": -0.5, "observations": 3}},
                               [ans("G9_T1", 1), ans("G9_T1", 1), ans("G9_T1", 1)])
    assert weak == critical == []


def test_single_correct_answer_with_a_confirmed_gap_elsewhere_is_not_weak():
    _, weak, critical = blocks({"G9_T1": {"alpha": 0.2, "observations": 1},
                                "G9_T2": {"alpha": -0.4, "observations": 2}},
                               [ans("G9_T1", 1), ans("G9_T2", 0), ans("G9_T2", 0)],
                               confirmed=["G9_T2_S1_K1"])
    assert ids(weak + critical) == ["G9_T2"]


def test_wrong_attempt_with_two_observations_and_low_mastery_is_weak():
    _, weak, _ = blocks({"G9_T1": {"alpha": 0.0, "observations": 2}}, [ans("G9_T1", 1), ans("G9_T1", 0)])
    assert ids(weak) == ["G9_T1"]
    assert weak[0]["wrong_attempts"] == 1 and weak[0]["observations"] == 2
    assert weak[0]["confirmed_by_deep_scan"] is False


def test_single_observation_is_not_enough_without_deep_scan_confirmation():
    _, weak, critical = blocks({"G9_T1": {"alpha": -0.2, "observations": 1}}, [ans("G9_T1", 0)])
    assert weak == critical == []


def test_deep_scan_confirmation_makes_a_single_wrong_attempt_weak_and_maps_l4_to_l2():
    _, weak, _ = blocks({"G9_T1": {"alpha": -0.2, "observations": 1}}, [ans("G9_T1", 0)],
                        confirmed=["G9_T1_S1_K1"])
    assert ids(weak) == ["G9_T1"]
    assert weak[0]["confirmed_by_deep_scan"] is True
    assert [d["skill_id"] for d in weak[0]["detail_skills"]] == ["G9_T1_S1_K1"]
    assert weak[0]["detail_skills"][0]["skill_name_ru"] == "Сложение дробей"


def test_confirmed_children_of_one_topic_collapse_into_one_item_without_duplicates():
    _, weak, critical = blocks({"G9_T1": {"alpha": -0.4, "observations": 2}}, [ans("G9_T1", 0), ans("G9_T1", 0)],
                               confirmed=["G9_T1_S1_K1", "G9_T1_S1_K2", "G9_T1_S1_K1", "G9_T1"])
    items = weak + critical
    assert ids(items) == ["G9_T1"]
    assert [d["skill_id"] for d in items[0]["detail_skills"]] == ["G9_T1_S1_K1", "G9_T1_S1_K2"]


def test_confirmed_gap_without_any_wrong_attempt_in_its_topic_is_ignored():
    _, weak, critical = blocks({"G9_T1": {"alpha": 0.4, "observations": 2}}, [ans("G9_T1", 1), ans("G9_T1", 1)],
                               confirmed=["G9_T1_S1_K1"])
    assert weak == critical == []


def test_unresolvable_confirmed_gap_does_not_invent_a_parent():
    _, weak, _ = _build_skill_blocks({"G9_T1": {"alpha": -0.2, "observations": 1}}, ["UNKNOWN_SKILL"], NAMES,
                                     [ans("G9_T1", 0)], l2_of=lambda sid: None)
    assert weak == []


def test_critical_requires_the_same_evidence_and_low_mastery():
    _, weak, critical = blocks({"G9_T1": {"alpha": -1.2, "observations": 4}},
                               [ans("G9_T1", 0)] * 4)
    assert ids(critical) == ["G9_T1"] and weak == []


def test_observation_count_falls_back_to_the_answer_journal_for_old_sessions():
    _, weak, _ = blocks({"G9_T1": {"alpha": 0.0}}, [ans("G9_T1", 1), ans("G9_T1", 0)])
    assert ids(weak) == ["G9_T1"]
    _, weak, _ = blocks({"G9_T1": {"alpha": -0.2}}, [ans("G9_T1", 0)])
    assert weak == []


def test_plan_does_not_duplicate_parent_and_child():
    weak = [{"skill_id": "G9_T1", "skill_name_ru": "Дроби", "detail_skills": [
        {"skill_id": "G9_T1_S1_K1", "skill_name_ru": "Сложение дробей"}]}]
    errors = [{"skill_id": "G9_T1_S1_K1", "skill_name_ru": "Сложение дробей"},
              {"skill_id": "G9_T1_S1_K2", "skill_name_ru": "Сокращение дробей"},
              {"skill_id": "G9_T2_S1_K1", "skill_name_ru": "Степень с нулём"}]
    plan = _build_plan_candidates([], [], weak, errors, l2_of=l2_of)
    assert ids(plan) == ["G9_T1", "G9_T2_S1_K1"]
    assert [d["skill_id"] for d in plan[0]["details"]] == ["G9_T1_S1_K1", "G9_T1_S1_K2"]


def test_plan_parent_arriving_after_its_confirmed_prerequisite_is_noted_not_repeated():
    chains = [{"root_gap_skill_id": "G9_T1_S1_K1", "root_gap_skill_name": "Сложение дробей"}]
    weak = [{"skill_id": "G9_T1", "skill_name_ru": "Дроби"}]
    plan = _build_plan_candidates(chains, [], weak, [], l2_of=l2_of)
    assert ids(plan) == ["G9_T1_S1_K1"]
    assert plan[0]["parent_topic_id"] == "G9_T1"
    assert plan[0]["evidence"] == "confirmed_prerequisite"


def test_l2_resolver_walks_the_hierarchy_and_never_guesses():
    nodes = {
        "K": NS(id="K", level="L4", parent_id="S"), "S": NS(id="S", level="L3", parent_id="T"),
        "T": NS(id="T", level="L2", parent_id="L1"), "L1": NS(id="L1", level="L1", parent_id=None),
        "ORPHAN": NS(id="ORPHAN", level="L4", parent_id=None),
    }
    calls = []

    class Repo:
        def get_by_id(self, node_id):
            calls.append(node_id)
            if node_id == "BOOM":
                raise RuntimeError("content-service down")
            return nodes.get(node_id)

    resolve = _make_l2_resolver(Repo())
    assert resolve("K") == "T" and resolve("T") == "T"
    assert resolve("ORPHAN") is None and resolve("MISSING") is None and resolve("BOOM") is None
    n = len(calls)
    assert resolve("K") == "T" and len(calls) == n  # cached
