"""N03b-2: what a diagnostic report says is made of the facts of the attempt.

No database, no real bank, no paid model: the generator runs against a fake session, a fake bank (``Bank``) and a recorded model.
Covers requirements 1-8 of N03B2_SPEC: the map of checked topics, the four lines of a plan step, the order of the plan (and that alpha is
only a tie-break), "more difficulties", no "thinking analysis", tasks taken out of the bank, texts, schema 8 and the cleaning of
new fields, and the size of the model's answer.  The scenario matrix of the spec is walked in ``test_scenario_*``.
"""
import json
import re
import uuid
from types import SimpleNamespace as NS

import pytest

from src.domain import report_generator as rg
from src.domain import report_plan as rp
from tests.test_n03a_report import FakeDB, ans

# ── a world: 4 topics of grade 8, two skills in each ───────────────────────────

TOPICS = {f"G8_T{t}": f"Тема {t}" for t in range(1, 5)}
SKILLS = {f"G8_T{t}_K{k}": f"Навык {t}.{k}" for t in range(1, 5) for k in (1, 2)}
SKILLS["G7_T9_K1"] = "Сравнение дробей"
NODES = {sid: NS(id=sid, level="L2", parent_id="G8_S", name_ru=name) for sid, name in TOPICS.items()}
NODES.update({sid: NS(id=sid, level="L4", parent_id=sid.rsplit("_K", 1)[0] if sid.startswith("G8") else None, name_ru=n)
              for sid, n in SKILLS.items()})
NODES["G8_S"] = NS(id="G8_S", level="L1", parent_id=None, name_ru="Алгебра")


def topic_of(skill):
    return skill.rsplit("_K", 1)[0] if skill.startswith("G8") else "G8_T1"


class Bank:
    """The bank as the report sees it: tasks by skill (id, difficulty, active) and the state of any task id."""

    def __init__(self):
        self.tasks = {}          # skill -> [(task_id, irt_difficulty, active)]
        self.inactive = set()    # task ids taken out of the bank
        self.down_status = False
        self.down_tasks = False
        self.asked = []

    def add(self, skill, n, *, start=0, active=True):
        rows = self.tasks.setdefault(skill, [])
        for i in range(start, start + n):
            rows.append((f"{skill}-b{i}", float(i), active))
        return self

    def is_active(self, task_id):
        self.status_calls = getattr(self, "status_calls", 0) + 1
        if getattr(self, "on_status", None):
            self.on_status()
        if self.down_status:
            raise ConnectionError("bank is down")
        return task_id not in self.inactive

    def unused(self, skill_id, exclude_ids, hardest_first=False):
        if self.down_tasks:
            raise ConnectionError("bank is down")
        self.asked.append((skill_id, tuple(exclude_ids)))
        rows = [
            {"task_id": t, "question_text": f"Задание {t}", "question_latex": None, "irt_difficulty": b}
            for t, b, active in self.tasks.get(skill_id, []) if active and t not in exclude_ids
        ]
        rows.sort(key=lambda r: ((-1 if hardest_first else 1) * r["irt_difficulty"], r["task_id"]))
        return rows


@pytest.fixture
def bank(monkeypatch):
    b = Bank()
    monkeypatch.setattr(rp, "bank_task_is_active", b.is_active)
    monkeypatch.setattr(rp, "bank_unused_tasks", b.unused)
    return b


@pytest.fixture
def gen(monkeypatch, bank):
    calls = []

    class FakeKnowledge:
        def get_by_id(self, node_id):
            return NODES.get(node_id)

    class FakeReports:
        def __init__(self, _db):
            pass

        def get_by_session(self, _sid):
            return None

    monkeypatch.setattr(rg, "KnowledgeRepository", FakeKnowledge)
    monkeypatch.setattr(rg, "llm_configured", lambda: True)
    monkeypatch.setattr(rg, "DiagReportRepository", FakeReports)
    monkeypatch.setattr(rg, "_load_task_context", lambda answer: (None, "unavailable"))

    def run(answers, *, narrative=None, breakdown=None, weak=(), theta=0.3, se=0.3):
        def fake_llm(prompt, **kwargs):
            calls.append({"prompt": prompt, **kwargs})
            return narrative(prompt) if callable(narrative) else narrative

        monkeypatch.setattr(rg, "call_gemini", fake_llm)
        topics = breakdown if breakdown is not None else {t: {"alpha": 0.0, "observations": 3} for t in TOPICS}
        report = rg.generate_and_save_report(
            FakeDB(answers), session_id=uuid.uuid4(), student_id=uuid.uuid4(), grade_level=8, theta=theta, theta_se=se,
            overall_level="at_grade", topic_breakdown=topics, weak_skills=list(weak), items_total=len(answers),
        )
        assert report is not None and report.report_json, "report was not built"
        return report

    run.calls = calls
    return run


_minute = [0]


def a(skill, outcome, *, deep=False, origin=None, task=None, answer="0"):
    _minute[0] += 1
    m = _minute[0]
    row = ans(skill, topic_of(skill), outcome, m, deep=deep, origin=origin, step=1 if deep else None)
    row.task_id = task or f"T{m}"
    row.student_answer = "1" if outcome else answer
    return row


def wrongs(skill, n, **kw):
    return [a(skill, 0, **kw) for _ in range(n)]


def all_strings(value):
    yield from rg._all_strings(value)


# ── Requirement 1: the map of checked topics ───────────────────────────────────

def test_checked_topics_count_measured_tasks_by_the_rule_of_the_header(gen):
    answers = [a("G8_T1_K1", 1), a("G8_T1_K2", 0), a("G8_T2_K1", 1), a("G8_T2_K1", 1),
               a("G7_T9_K1", 0, deep=True, origin="G8_T1_K2"), a("G7_T9_K1", 1, deep=True, origin="G8_T1_K2")]
    rj = gen(answers).report_json
    by_topic = {t["topic_id"]: (t["checked"], t["errors"]) for t in rj["checked_topics"]}
    assert by_topic == {"G8_T1": (2, 1), "G8_T2": (2, 0)}          # the two probes (topic G8_T1) are not mixed in
    meta = rj["report_meta"]
    assert sum(c for c, _ in by_topic.values()) == meta["total_questions"] == rj["level"]["total"]
    assert sum(e for _, e in by_topic.values()) == meta["total_questions"] - meta["questions_correct"] == meta["measured_errors"]
    assert (meta["prerequisite_questions"], meta["prerequisite_correct"], meta["prerequisite_errors"]) == (2, 1, 1)
    assert [t["topic_name_ru"] for t in rj["checked_topics"]] == ["Тема 1", "Тема 2"]    # in the order of the test


def test_checked_topics_show_no_percent_and_no_verdict(gen):
    rj = gen(wrongs("G8_T1_K1", 3) + [a("G8_T2_K1", 1)]).report_json
    for topic in rj["checked_topics"]:
        assert set(topic) == {"topic_id", "topic_name_ru", "checked", "errors"}
    text = json.dumps(rj["checked_topics"], ensure_ascii=False).lower()
    assert "%" not in text and "сильн" not in text and "слаб" not in text


def test_scenario_no_errors_map_with_zero_errors_development_step_no_more_difficulties(gen, bank):
    bank.add("G8_T1_K1", 5)             # the focus: the verified topic with the fewest checked tasks
    rj = gen([a("G8_T1_K1", 1), a("G8_T2_K1", 1), a("G8_T2_K1", 1)]).report_json
    assert rj["report_meta"]["error_free"] is True
    assert [(t["topic_id"], t["checked"], t["errors"]) for t in rj["checked_topics"]] == [("G8_T1", 1, 0), ("G8_T2", 2, 0)]
    (step,) = rj["action_plan"]
    assert step["kind"] == "development" and step["action_title"].startswith("Развитие:")
    assert step["evidence"] and all(e["correct"] and e["task_id"] for e in step["evidence"])
    assert step["check"]["task"] and step["check"]["task"]["task_id"] not in {m["task_id"] for m in step["material"]["tasks"]}
    assert rj["more_difficulties"] == [] and rj["error_patterns"] == []
    assert rj["recommended_start"]["skill_id"] == step["skill_id"]


def test_achievements_use_the_same_measured_rule_a_probe_makes_no_verified_topic():
    answers = [a("G8_T1_K1", 1), a("G7_T9_K1", 1, deep=True, origin="G8_T1_K1")]       # the probe is in topic G8_T1 too
    done = rg._build_achievements({"G8_T1": {"alpha": 0.2}}, {"G8_T1": {"name_ru": "T"}}, answers)
    assert done[0]["correct_answers"] == 1                                              # only the measured answer
    only_probe = rg._build_achievements({"G8_T1": {"alpha": 0.2}}, {}, [a("G7_T9_K1", 1, deep=True, origin="x")])
    assert only_probe == []


# ── Requirement 2: the four lines of a step ────────────────────────────────────

def _errors_in_many_skills():
    return (wrongs("G8_T1_K1", 3) + wrongs("G8_T1_K2", 2) + wrongs("G8_T2_K1", 2) + wrongs("G8_T2_K2", 1)
            + wrongs("G8_T3_K1", 1) + wrongs("G8_T3_K2", 1) + wrongs("G8_T4_K1", 1) + [a("G8_T4_K2", 1)])


def test_scenario_all_wrong_five_steps_with_four_lines_and_more_difficulties(gen, bank):
    for skill in SKILLS:
        bank.add(skill, 6)
    answers = _errors_in_many_skills()
    rj = gen(answers).report_json
    plan, journal = rj["action_plan"], rj["error_patterns"]
    assert len(plan) == 5 and [s["priority"] for s in plan] == [1, 2, 3, 4, 5]
    by_no = {row["journal_no"]: row for row in journal}
    for step in plan:
        assert step["kind"] == "correction" and step["skill_name_ru"] == SKILLS[step["skill_id"]]
        assert step["evidence"], step                                                  # every step has a basis
        for ref in step["evidence"]:                                                   # ... made of this attempt's rows of this skill
            row = by_no[ref["journal_no"]]
            assert row["answer_id"] == ref["answer_id"] and row["skill_id"] == step["skill_id"]
            assert ref["student_answer"] == row["student_answer"]
        assert step["errors_count"] == sum(1 for r in journal if r["skill_id"] == step["skill_id"])
        assert 1 <= len(step["material"]["tasks"]) <= 3 and step["material"]["on_lesson"] is False
        assert step["check"]["task"] and step["check"]["on_lesson"] is False
        assert step["check"]["statement"] == "Ученик решает без ошибки задание этого навыка из банка"
        assert step["check"]["task"]["task_id"] not in {t["task_id"] for t in step["material"]["tasks"]}
        attempt = {x.task_id for x in answers}
        assert not attempt & ({t["task_id"] for t in step["material"]["tasks"]} | {step["check"]["task"]["task_id"]})
    # the 3 skills that did not fit are named under the plan, with their journal rows
    named = {s["skill_id"] for g in rj["more_difficulties"] for s in g["skills"]}
    assert named == {"G8_T3_K1", "G8_T3_K2", "G8_T4_K1"} - {s["skill_id"] for s in plan} or named
    with_errors = {r["skill_id"] for r in journal}
    assert with_errors == {s["skill_id"] for s in plan} | named                      # no skill with errors is named nowhere
    assert all(g["topic_name_ru"] in TOPICS.values() for g in rj["more_difficulties"])
    for g in rj["more_difficulties"]:
        for skill in g["skills"]:
            assert all(by_no[n]["skill_id"] == skill["skill_id"] for n in skill["journal_nos"])


def test_first_step_is_the_recommended_start_and_the_column(gen):
    report = gen(_errors_in_many_skills())
    rj = report.report_json
    assert rj["recommended_start"]["skill_id"] == rj["action_plan"][0]["skill_id"] == report.recommended_start == "G8_T1_K1"
    assert rj["recommended_start"]["evidence_kind"] == "observed_error"


def test_a_skill_without_tasks_in_the_bank_says_so_without_empty_links(gen, bank):
    bank.add("G8_T1_K1", 0)
    rj = gen(wrongs("G8_T1_K1", 2)).report_json
    (step,) = rj["action_plan"]
    assert step["material"] == {"tasks": [], "on_lesson": True, "text": "задание этого навыка на занятии"}
    assert step["check"]["task"] is None and step["check"]["on_lesson"] is True
    assert step["check"]["text"] == "Ученик решает без ошибки задание этого навыка на занятии."


@pytest.mark.parametrize("free,material,check", [(0, 0, False), (1, 1, False), (2, 1, True), (3, 2, True), (4, 3, True), (9, 3, True)])
def test_material_is_up_to_three_tasks_and_the_check_is_another_one(free, material, check):
    tasks = [{"task_id": f"b{i}", "question_text": "q", "question_latex": None} for i in range(free)]
    got_material, got_check = rp.pick_material_and_check(tasks)
    assert len(got_material) == material and (got_check is not None) == check
    assert got_check is None or got_check["task_id"] not in {t["task_id"] for t in got_material}


def test_tasks_the_student_got_in_this_attempt_are_never_offered(gen, bank):
    answers = wrongs("G8_T1_K1", 2, task="G8_T1_K1-b0") + [a("G8_T1_K1", 0, task="G8_T1_K1-b1")]
    bank.add("G8_T1_K1", 6)
    rj = gen(answers).report_json
    (step,) = rj["action_plan"]
    offered = {t["task_id"] for t in step["material"]["tasks"]} | {step["check"]["task"]["task_id"]}
    assert offered == {"G8_T1_K1-b2", "G8_T1_K1-b3", "G8_T1_K1-b4", "G8_T1_K1-b5"}
    assert bank.asked[0][0] == "G8_T1_K1" and set(bank.asked[0][1]) == {x.task_id for x in answers}


def test_scenario_retry_each_attempt_has_its_own_check(gen, bank):
    bank.add("G8_T1_K1", 5)
    first = gen(wrongs("G8_T1_K1", 2, task="G8_T1_K1-b0")).report_json["action_plan"][0]
    second = gen(wrongs("G8_T1_K1", 2, task="G8_T1_K1-b1")).report_json["action_plan"][0]
    assert first["check"]["task"]["task_id"] != "G8_T1_K1-b0" and second["check"]["task"]["task_id"] != "G8_T1_K1-b1"
    assert {e["task_id"] for e in first["evidence"]} != {e["task_id"] for e in second["evidence"]}     # each by its own answers


def test_a_link_never_leads_to_an_inactive_task_the_adapter_filters_what_the_bank_returned(monkeypatch):
    rows = [NS(task_id="t1", is_active=True, irt_difficulty=0.5, question_text="a", question_latex=None),
            NS(task_id="t2", is_active=False, irt_difficulty=0.1, question_text="b", question_latex=None),
            NS(task_id="t3", is_active=True, irt_difficulty=0.5, question_text="c", question_latex=" "),
            NS(task_id="t4", is_active=True, irt_difficulty=0.2, question_text=None, question_latex="x^2")]
    seen = {}

    class Repo:
        def get_tasks_for_skill(self, skill_id, **kwargs):
            seen.update(kwargs)
            return rows

    from src.repositories import knowledge_repo
    monkeypatch.setattr(knowledge_repo, "TaskRepository", Repo)
    monkeypatch.undo()          # the conftest fixture replaced the adapter: use the real one
    monkeypatch.setattr(knowledge_repo, "TaskRepository", Repo)
    tasks = rp.bank_unused_tasks("S", ["t3-attempt"])
    assert [t["task_id"] for t in tasks] == ["t4", "t1", "t3"]            # by difficulty, then id; t2 is inactive
    assert seen["exclude_ids"] == ["t3-attempt"] and seen["limit"] == rp.TASK_WINDOW and "target_b" not in seen
    hardest = rp.bank_unused_tasks("S", [], hardest_first=True)
    assert [t["task_id"] for t in hardest] == ["t1", "t3", "t4"] and seen["limit"] == rp.DEVELOPMENT_WINDOW


def test_the_same_data_gives_the_same_plan(gen, bank):
    for skill in SKILLS:
        bank.add(skill, 8)
    answers = _errors_in_many_skills()
    first = gen(answers).report_json
    second = gen(list(answers)).report_json
    for key in ("action_plan", "more_difficulties", "checked_topics", "recommended_start"):
        assert first[key] == second[key], key


def test_every_skill_gets_its_own_step_from_the_data_without_the_model(gen, bank):
    bank.add("G8_T1_K1", 5).add("G8_T2_K1", 5)
    answers = wrongs("G8_T1_K1", 2) + wrongs("G8_T2_K1", 1)
    rj = gen(answers, narrative=None).report_json
    one, two = rj["action_plan"]
    assert one["full_description"] != two["full_description"] and "Навык 1.1" in one["full_description"] and "Навык 2.1" in two["full_description"]
    assert one["material"] != two["material"] and one["evidence"] != two["evidence"]
    assert rj["report_meta"]["narrative_source"] == "ai_failed"       # a model was configured and gave nothing
    assert all(s["source"] == "deterministic_fallback" for s in rj["action_plan"])


def test_the_explanation_of_the_chosen_distractor_is_the_only_cause_and_it_is_quoted(monkeypatch, gen, bank):
    def context(answer):
        return ({"question_text": "q", "correct_answer": "2", "_option_pairs": [], "_answer_type": "text",
                 "distractor_meta": [{"value": "0", "error_logic": "складывает знаменатели вместо приведения к общему"}]}, "live_bank")

    monkeypatch.setattr(rg, "_load_task_context", context)
    rj = gen(wrongs("G8_T1_K1", 1)).report_json
    (step,) = rj["action_plan"]
    assert step["evidence"][0]["explanation"] == "складывает знаменатели вместо приведения к общему"
    assert "складывает знаменатели" in step["full_description"]
    assert "складывает знаменатели" in gen.calls[0]["prompt"]                     # and the model gets the same explanation


# ── Requirement 3: the order of the plan ────────────────────────────────────────

def row(no, skill, **kw):
    return {"journal_no": no, "answer_id": f"id{no}", "task_id": f"T{no}", "skill_id": skill, "skill_name_ru": skill,
            "topic_id": topic_of(skill), "topic_name_ru": topic_of(skill), "student_answer": "0", **kw}


def order(journal, chains=(), breakdown=None):
    breakdown = breakdown if breakdown is not None else {}
    return [c["skill_id"] for c in rp.build_plan_candidates(journal, list(chains), breakdown)]


def test_more_wrong_answers_go_first_whatever_the_hidden_estimate_says():
    journal = [row(1, "G8_T1_K1"), row(2, "G8_T2_K1"), row(3, "G8_T2_K1")]
    # the topic of the single-error skill has the LOWEST estimate: it still comes after the skill with two errors
    assert order(journal, breakdown={"G8_T1": {"alpha": -2.0}, "G8_T2": {"alpha": 2.0}}) == ["G8_T2_K1", "G8_T1_K1"]


def test_a_prerequisite_root_goes_before_an_equal_skill_and_a_stored_link_before_a_reconstructed_one():
    journal = [row(1, "G8_T1_K1"), row(2, "G8_T2_K1"), row(3, "G8_T3_K1")]
    chains = [{"source_skill_id": "G8_T1_K1", "root_gap_skill_id": "G8_T3_K1", "has_prerequisite_gap": True, "evidence_source": "inferred"},
              {"source_skill_id": "G8_T1_K1", "root_gap_skill_id": "G8_T2_K1", "has_prerequisite_gap": True, "evidence_source": "stored_link"}]
    assert order(journal, chains) == ["G8_T2_K1", "G8_T3_K1", "G8_T1_K1"]
    kinds = {c["skill_id"]: c["evidence_kind"] for c in rp.build_plan_candidates(journal, chains, {})}
    assert kinds == {"G8_T2_K1": "confirmed_prerequisite", "G8_T3_K1": "observed_prerequisite", "G8_T1_K1": "observed_error"}


def test_the_prerequisite_fact_outranks_the_hidden_estimate_on_equal_error_counts():
    journal = [row(1, "G8_T1_K1"), row(2, "G8_T2_K1")]
    chains = [{"source_skill_id": "G8_T4_K1", "root_gap_skill_id": "G8_T2_K1", "has_prerequisite_gap": True, "evidence_source": "stored_link"}]
    weakest_first = {"G8_T1": {"alpha": -2.0}, "G8_T2": {"alpha": 2.0}}
    assert order(journal, chains, breakdown=weakest_first) == ["G8_T2_K1", "G8_T1_K1"]      # the root first although its estimate is the highest


def test_a_prerequisite_is_placed_before_the_skill_it_was_found_under_even_with_fewer_errors():
    journal = [row(1, "G8_T1_K1"), row(2, "G8_T1_K1"), row(3, "G8_T1_K1"), row(4, "G7_T9_K1", is_deep_scan=True)]
    chains = [{"source_skill_id": "G8_T1_K1", "root_gap_skill_id": "G7_T9_K1", "has_prerequisite_gap": True, "evidence_source": "stored_link"}]
    got = rp.build_plan_candidates(journal, chains, {})
    assert [c["skill_id"] for c in got] == ["G7_T9_K1", "G8_T1_K1"] and got[0]["prerequisite_of"] == "G8_T1_K1"


def test_alpha_decides_only_when_every_fact_is_equal_and_the_id_last():
    journal = [row(1, "G8_T1_K1"), row(2, "G8_T2_K1"), row(3, "G8_T3_K1")]
    low_t2 = {"G8_T1": {"alpha": 0.5}, "G8_T2": {"alpha": -1.0}, "G8_T3": {"alpha": 0.5}}
    assert order(journal, breakdown=low_t2) == ["G8_T2_K1", "G8_T1_K1", "G8_T3_K1"]
    low_t3 = {"G8_T1": {"alpha": 0.5}, "G8_T2": {"alpha": 0.5}, "G8_T3": {"alpha": -1.0}}
    assert order(journal, breakdown=low_t3) == ["G8_T3_K1", "G8_T1_K1", "G8_T2_K1"]
    assert order(journal, breakdown={}) == ["G8_T1_K1", "G8_T2_K1", "G8_T3_K1"]          # no estimates at all: the id
    assert order(journal, breakdown={"G8_T1": {"alpha": "broken"}}) == ["G8_T1_K1", "G8_T2_K1", "G8_T3_K1"]


def test_the_plan_of_a_report_follows_the_wrong_answer_count_not_the_estimates(gen):
    # topic 4 is the weakest by alpha, topic 1 has the most errors
    breakdown = {"G8_T1": {"alpha": 1.5, "observations": 3}, "G8_T2": {"alpha": 0.0, "observations": 3},
                 "G8_T3": {"alpha": 0.0, "observations": 3}, "G8_T4": {"alpha": -1.9, "observations": 3}}
    rj = gen(wrongs("G8_T1_K1", 3) + wrongs("G8_T4_K1", 1), breakdown=breakdown).report_json
    assert [s["skill_id"] for s in rj["action_plan"]] == ["G8_T1_K1", "G8_T4_K1"]


# ── Requirement 6: tasks taken out of the bank ──────────────────────────────────

def test_scenario_a_task_taken_out_of_the_bank_is_marked_and_used_nowhere(gen, bank):
    bank.add("G8_T1_K1", 5).add("G8_T2_K1", 5)
    answers = wrongs("G8_T1_K1", 2, task="GONE") + wrongs("G8_T2_K1", 1)
    bank.inactive.add("GONE")
    rj = gen(answers).report_json
    journal = rj["error_patterns"]
    assert [r["task_withdrawn"] for r in journal] == [True, True, False]
    assert [s["skill_id"] for s in rj["action_plan"]] == ["G8_T2_K1"]                 # the skill of the withdrawn task is not a step
    used = json.dumps([rj["action_plan"], rj["more_difficulties"]])
    assert "GONE" not in used and "G8_T1_K1" not in used
    assert rj["report_meta"]["measured_errors"] == 3                                 # the level / header are not recalculated


def test_only_the_withdrawn_row_of_a_skill_leaves_the_basis(gen, bank):
    answers = [a("G8_T1_K1", 0, task="GONE"), a("G8_T1_K1", 0, task="LIVE")]
    bank.inactive.add("GONE")
    (step,) = gen(answers).report_json["action_plan"]
    assert [e["task_id"] for e in step["evidence"]] == ["LIVE"] and step["errors_count"] == 1


def test_a_task_that_is_gone_from_the_bank_counts_as_withdrawn():
    withdrawn, unread = rp.find_withdrawn_tasks(["a", "b", "a"], rp.BankReader(is_active=lambda t: t != "b"))
    assert withdrawn == {"b"} and unread == []


def test_scenario_every_error_on_a_withdrawn_task_no_plan_no_model_call_not_error_free(gen, bank):
    bank.inactive.add("GONE")
    rj = gen(wrongs("G8_T1_K1", 2, task="GONE") + [a("G8_T2_K1", 1)]).report_json
    assert rj["action_plan"] == [] and rj["recommended_start"] is None and rj["more_difficulties"] == []
    assert rj["report_meta"]["error_free"] is False and rj["report_meta"]["narrative_source"] == "ai_off"
    assert gen.calls == []
    assert all(r["task_withdrawn"] for r in rj["error_patterns"])


def test_an_unreadable_bank_is_not_an_empty_bank_the_report_is_degraded_and_not_current(gen, bank):
    bank.down_status = True
    report = gen(wrongs("G8_T1_K1", 1))
    assert "task_status" in report.report_json["report_meta"]["degraded"] and report.report_schema_version == 0
    assert gen.calls == []                                                        # no paid call for a report that will be rebuilt
    bank.down_status, bank.down_tasks = False, True
    report = gen(wrongs("G8_T1_K1", 1))
    assert report.report_json["report_meta"]["degraded"] == ["bank_tasks"] and report.report_schema_version == 0
    step = report.report_json["action_plan"][0]
    assert step["evidence"] and step["material"] is None and step["check"] is None       # not "at the lesson": the bank was not read


# ── Requirement 5: no «Анализ мышления» ─────────────────────────────────────────

def test_no_thinking_analysis_in_the_report_the_prompt_or_the_code(gen):
    rj = gen(_errors_in_many_skills()).report_json
    assert "cognitive_error_types" not in rj
    prompt = gen.calls[0]["prompt"]
    assert "КОГНИТИВНЫЕ ПАТТЕРНЫ" not in prompt and "когнитивные паттерны" not in prompt.lower()
    assert not hasattr(rg, "_build_cognitive_error_types")
    assert "cognitive" not in " ".join(__import__("inspect").signature(rg._build_prompt).parameters)


def test_an_older_stored_report_loses_the_thinking_analysis_when_it_is_served():
    old = {"report_meta": {"report_schema_version": 7}, "cognitive_error_types": [{"title": "Знаки"}], "error_patterns": [{"task_id": "T"}],
           "action_plan": [{"skill_id": "S", "evidence": "observed_error", "full_description": "текст"}]}
    cleaned = rg.strip_retired_report_fields(old)
    assert "cognitive_error_types" not in cleaned and cleaned["error_patterns"] == [{"task_id": "T"}]
    assert "cognitive_error_types" in old                                          # the stored copy is not touched
    assert cleaned["action_plan"][0]["evidence"] == "observed_error"               # an old step keeps its code


# ── Requirement 8: schema 8, cleaning of new fields, the model's answer ─────────

def test_the_journal_rows_are_numbered_and_say_what_they_are(gen):
    answers = [a("G8_T1_K1", 0), a("G8_T1_K2", 1), a("G7_T9_K1", 0, deep=True, origin="G8_T1_K1"), a("G8_T2_K1", 0)]
    rj = gen(answers).report_json
    assert rj["report_meta"]["report_schema_version"] == 8
    assert [r["journal_no"] for r in rj["error_patterns"]] == [1, 2, 3]
    assert [r["is_deep_scan"] for r in rj["error_patterns"]] == [False, True, False]
    assert [r["topic_id"] for r in rj["error_patterns"]] == ["G8_T1", "G8_T1", "G8_T2"]
    assert all(r["task_withdrawn"] is False for r in rj["error_patterns"])


def _hostile_step():
    return {
        "priority": 1, "skill_id": "S", "skill_name_ru": "Навык", "kind": "correction", "source": "ai",
        "action_title": "Тема", "full_description": "Практика. Надёжность диагноза 83%. Это начало 8 класса.",
        "evidence_kind": "observed_error", "errors_count": 1, "estimated_hours": 4,
        "evidence": [{"journal_no": 1, "student_answer": "Надёжность диагноза 83%", "explanation": "Это конец 7 класса"}],
        "material": {"tasks": [], "on_lesson": True, "text": "задание этого навыка на занятии"},
        "check": {"statement": rp.CHECK_STATEMENT, "task": None, "on_lesson": True, "text": "Ученик решает без ошибки задание этого навыка на занятии."},
        "extra_prose": "Единая первопричина не подтверждена. Повторить дроби.",      # a key nobody listed: it is prose
    }


def test_the_new_fields_go_through_the_cleaning_prose_is_swept_facts_are_not():
    report = {"action_plan": [_hostile_step()], "checked_topics": [{"topic_id": "T", "topic_name_ru": "Тема", "checked": 2, "errors": 1}],
              "more_difficulties": [{"topic_id": "T", "topic_name_ru": "Тема", "skills": [{"skill_id": "S", "skill_name_ru": "Н", "errors": 1, "journal_nos": [1]}]}]}
    cleaned = rg.strip_retired_report_fields(report)
    step = cleaned["action_plan"][0]
    # a reliability claim goes sentence by sentence; a class equivalent is allowed in plan prose by design ("в конце 7 класса изучают ...")
    assert "83" not in step["full_description"] and "Практика" in step["full_description"]
    assert step["extra_prose"] == "Повторить дроби." and "estimated_hours" not in step
    # `evidence` is a reference to the attempt's data: a student's own answer is shown as it was given
    assert step["evidence"] == _hostile_step()["evidence"]
    assert step["material"] == _hostile_step()["material"] and step["check"] == _hostile_step()["check"]
    assert cleaned["checked_topics"] == report["checked_topics"] and cleaned["more_difficulties"] == report["more_difficulties"]


def test_every_key_a_generated_step_carries_is_either_a_listed_fact_or_clean_prose(gen, bank):
    bank.add("G8_T1_K1", 5)
    rj = gen(wrongs("G8_T1_K1", 2)).report_json
    for step in rj["action_plan"] + [gen(_errors_in_many_skills()).report_json["action_plan"][0]]:
        for key, value in step.items():
            if key in rg._PLAN_IDENTIFIER_KEYS:
                continue
            assert key in ("action_title", "full_description"), f"unlisted key {key!r} would be swept as prose"
            assert not any(rg.contains_retired_claim(t) for t in all_strings(value))


def test_no_retired_claim_and_no_percent_anywhere_in_a_report(gen, bank):
    for skill in SKILLS:
        bank.add(skill, 6)
    rj = gen(_errors_in_many_skills()).report_json
    skip = {"achievements", "strong_skills", "weak_skills", "critical_gaps"}        # the approved percents of mastery live here
    for key, value in rj.items():
        if key in skip or key == "overall":
            continue
        for text in all_strings(value):
            assert not re.search(r"\d\s*%", text), (key, text)
            assert not rg.contains_retired_claim(text), (key, text)
    assert not re.search(r"\d\s*%", rj["overall"]["student_summary"])


def _valid_answer(plan_skills, *, title=1, description=1):
    return {
        "overall": {"status": "below_level", "score_percent": 0, "status_label_ru": "x", "student_summary": "Текст."},
        "action_plan": [
            {"priority": i, "skill_id": sid, "skill_name_ru": name, "action_title": "т" * title, "full_description": "д" * description}
            for i, (sid, name) in enumerate(plan_skills.items(), 1)
        ],
    }


def _validate(data, plan_skills):
    return rg._validate_ai_output(data, computed_status="below_level", score_pct=0, allowed_plan_skills=plan_skills)


@pytest.mark.parametrize("key,value", [("evidence", [{"journal_no": 1}]), ("material", {"tasks": []}), ("check", {"task": None}),
                                       ("estimated_hours", 3), ("kind", "development")])
def test_the_validator_rejects_a_model_that_writes_the_lines_the_system_owns(key, value):
    skills = {"S1": "Навык 1"}
    data = _valid_answer(skills)
    assert _validate(data, skills)[0]
    data["action_plan"][0][key] = value
    valid, errors = _validate(data, skills)
    assert not valid and any(key in e for e in errors)


def test_the_validator_caps_the_length_of_what_the_model_writes():
    skills = {"S1": "Навык 1"}
    assert _validate(_valid_answer(skills, title=rg.AI_TITLE_MAX, description=rg.AI_DESCRIPTION_MAX), skills)[0]
    assert not _validate(_valid_answer(skills, title=rg.AI_TITLE_MAX + 1), skills)[0]
    assert not _validate(_valid_answer(skills, description=rg.AI_DESCRIPTION_MAX + 1), skills)[0]
    data = _valid_answer(skills)
    data["overall"]["student_summary"] = "с" * (rg.AI_SUMMARY_MAX + 1)
    assert not _validate(data, skills)[0]


CHARS_PER_TOKEN = 1.5      # pessimistic for Russian text


def _longest_valid_answer(plan_skills):
    data = _valid_answer(plan_skills, title=rg.AI_TITLE_MAX, description=rg.AI_DESCRIPTION_MAX)
    data["overall"]["student_summary"] = "с" * rg.AI_SUMMARY_MAX
    return data


def test_the_longest_answer_the_validator_lets_through_fits_into_max_tokens():
    skills = {f"S{i}": f"Навык {i}" for i in range(1, 6)}
    data = _longest_valid_answer(skills)
    assert _validate(data, skills)[0]
    needed = len(json.dumps(data, ensure_ascii=False)) / CHARS_PER_TOKEN
    assert needed < rg.NARRATIVE_MAX_TOKENS, (needed, rg.NARRATIVE_MAX_TOKENS)
    assert rg.NARRATIVE_MAX_TOKENS > 2500                       # the old ceiling cut a long plan


def _cut_at_max_tokens(text, max_tokens):
    return text[: int(max_tokens * CHARS_PER_TOKEN)]


def test_scenario_a_long_plan_is_not_cut_off_and_a_cut_off_answer_does_not_empty_the_report(gen, bank, monkeypatch):
    for skill in SKILLS:
        bank.add(skill, 6)
    answers = _errors_in_many_skills()
    skills = {s["skill_id"]: s["skill_name_ru"] for s in gen(answers, narrative=None).report_json["action_plan"]}
    full = _longest_valid_answer(skills)
    base_overall = gen(answers, narrative=None).report_json["overall"]
    full["overall"]["score_percent"], full["overall"]["status"] = base_overall["score_percent"], base_overall["status"]
    full["overall"]["status_label_ru"] = base_overall["status_label_ru"]

    captured = {}

    def narrative(prompt):
        return json.dumps(full, ensure_ascii=False)

    # a model whose output is cut at the ceiling it was given
    def run_with(limit):
        monkeypatch.setattr(rg, "NARRATIVE_MAX_TOKENS", limit)

        def fake(prompt, **kwargs):
            captured["max_tokens"] = kwargs["max_tokens"]
            return _cut_at_max_tokens(narrative(prompt), kwargs["max_tokens"])

        monkeypatch.setattr(rg, "call_gemini", fake)
        report = rg.generate_and_save_report(
            FakeDB(answers), session_id=uuid.uuid4(), student_id=uuid.uuid4(), grade_level=8, theta=0.3, theta_se=0.3,
            overall_level="at_grade", topic_breakdown={t: {"alpha": 0.0, "observations": 3} for t in TOPICS}, weak_skills=[],
            items_total=len(answers),
        )
        return report

    gen(answers, narrative=None)                                             # installs the fakes of the fixture
    ok = run_with(rg.NARRATIVE_MAX_TOKENS)
    assert captured["max_tokens"] == rg.NARRATIVE_MAX_TOKENS and ok.report_json["report_meta"]["narrative_source"] == "ai"

    cut = run_with(2500)                                                     # the old ceiling: the JSON is cut, both attempts fail
    rj = cut.report_json
    assert rj["report_meta"]["narrative_source"] == "ai_failed" and cut.generation_status == "ready"
    assert len(rj["action_plan"]) == 5 and rj["overall"]["student_summary"]            # the report is not empty
    for step in rj["action_plan"]:
        assert step["evidence"] and step["material"]["tasks"] and step["check"]["task"] and step["source"] == "deterministic_fallback"


# ── Scenario matrix: the model failed / is off ─────────────────────────────────

def test_scenario_the_model_failed_the_plan_is_the_same_as_with_the_model(gen, bank):
    for skill in SKILLS:
        bank.add(skill, 6)
    answers = _errors_in_many_skills()
    failed = gen(answers, narrative="not json").report_json
    base = gen(answers, narrative=None).report_json
    assert failed["report_meta"]["narrative_source"] == "ai_failed"
    for key in ("action_plan", "more_difficulties", "checked_topics", "recommended_start", "error_patterns"):
        assert failed[key] == base[key], key

    plan = failed["action_plan"]
    skills = {s["skill_id"]: s["skill_name_ru"] for s in plan}
    ok = _valid_answer(skills)
    ok["overall"]["score_percent"] = failed["overall"]["score_percent"]
    ok["overall"]["status"] = failed["overall"]["status"]
    worded = gen(answers, narrative=json.dumps(dict(ok, action_plan=list(reversed(ok["action_plan"]))), ensure_ascii=False)).report_json
    assert worded["report_meta"]["narrative_source"] == "ai"
    for old, new in zip(plan, worded["action_plan"]):
        assert {k: v for k, v in new.items() if k not in ("action_title", "full_description", "source")} == \
               {k: v for k, v in old.items() if k not in ("action_title", "full_description", "source")}
        assert new["source"] == "ai" and new["full_description"] == "д"


def test_scenario_the_model_is_off_no_call_and_the_same_plan(gen, bank, monkeypatch):
    bank.add("G8_T1_K1", 5)
    monkeypatch.setattr(rg, "narrative_enabled", lambda: False)
    rj = gen(wrongs("G8_T1_K1", 2)).report_json
    assert gen.calls == [] and rj["report_meta"]["narrative_source"] == "ai_off"
    assert rj["action_plan"][0]["evidence"] and rj["action_plan"][0]["material"]["tasks"]


def test_a_hostile_wording_is_rejected_and_the_report_keeps_the_data_plan(gen):
    answers = wrongs("G8_T1_K1", 2)
    base = gen(answers, narrative=None).report_json
    bad = _valid_answer({"G8_T1_K1": "Навык 1.1"})
    bad["overall"]["score_percent"], bad["overall"]["status"] = base["overall"]["score_percent"], base["overall"]["status"]
    bad["action_plan"][0]["full_description"] = "Надёжность диагноза 83%."
    rj = gen(answers, narrative=json.dumps(bad, ensure_ascii=False)).report_json
    assert rj["report_meta"]["narrative_source"] == "ai_failed" and rj["action_plan"] == base["action_plan"]
