"""Wave E7 / decision 8 (diag half): a typed answer is graded by the VALUE it says - equivalent notations of one number and of the empty set
are accepted the same (``fixtures/keyboard_answers_golden.json``, the table exam-service connects to in E-D)."""
import json
import pathlib
from types import SimpleNamespace

import pytest

from src.domain.answer_evaluator import AnswerEvaluator

GOLDEN = json.loads((pathlib.Path(__file__).parent / "fixtures" / "keyboard_answers_golden.json").read_text(encoding="utf-8"))
EVALUATOR = AnswerEvaluator()

# Typed answers the evaluator does not accept YET (decision 8 not applied); the code commit empties this set.
KNOWN_GAPS: set = set()                       # decision 8 is applied: every accepted notation of the table is graded correct


def verdict(key, typed):
    task = SimpleNamespace(id="golden", correct_answer=key, answer_type="text", sympy_solution=None, distractor_meta=[])
    return EVALUATOR.evaluate(task, typed)


def pairs(*kinds):
    return [pytest.param(case["key"], typed, id=f"{case['id']}|{typed}",
                         marks=[pytest.mark.xfail(strict=True, reason="decision 8 not applied yet")] if (case["id"], typed) in KNOWN_GAPS else [])
            for case in GOLDEN["cases"] for kind in kinds for typed in case.get(kind, [])]


@pytest.mark.parametrize("key, typed", pairs("accept"))
def test_equivalent_notations_are_graded_correct(key, typed):
    assert verdict(key, typed) == (1.0, "correct")


@pytest.mark.parametrize("key, typed", pairs("reject"))
def test_other_values_are_graded_wrong(key, typed):
    outcome, category = verdict(key, typed)
    assert outcome == 0.0 and category != "correct"


@pytest.mark.parametrize("case", GOLDEN["contested"], ids=lambda c: f"{c['key']}|{c['typed']}")
def test_the_contested_cases_have_one_verdict_in_both_services(case):
    assert case["diag"] == case["exam"]
    assert (verdict(case["key"], case["typed"])[0] == 1.0) is case["diag"]


def test_a_served_choice_is_still_compared_as_a_value_only():
    """The layer of equivalent notations is for typed answers: a choice of a multiple-choice task keeps the strict comparison."""
    task = SimpleNamespace(id="golden", correct_answer="21/5", answer_type="text", display_answer_type="mcq", sympy_solution=None, distractor_meta=[])
    assert EVALUATOR.evaluate(task, "21/5") == (1.0, "correct")
    assert EVALUATOR.evaluate(task, "42/10")[0] == 0.0


def test_a_distractor_that_is_a_notation_of_the_key_cannot_exist_but_one_of_another_value_is_still_found():
    task = SimpleNamespace(id="golden", correct_answer="21/5", answer_type="text", sympy_solution=None, distractor_meta=[{"value": "5/21"}, {"value": "4,3"}])
    assert EVALUATOR.evaluate(task, "4,3") == (0.0, "distractor")
    assert EVALUATOR.evaluate(task, "4,2") == (1.0, "correct")


@pytest.mark.parametrize("text, expected", [
    ("нет корней", True), ("  Нет   корней. ", True), ("$\\varnothing$", True), ("x \\in \\varnothing", True), ("x∈∅", True), ("\\emptyset", True),
    ("", False), (None, False), ("0", False), ("нет корней у уравнения", False), ("{}", False), ("x" * 3000, False),
])
def test_is_empty_set(text, expected):
    from src.domain.answer_value import is_empty_set
    assert is_empty_set(text) is expected


def test_a_space_in_a_mixed_number_is_not_a_thousands_separator():
    """«2 1/5» used to be read as 21/5 (a space between digits dropped by the float layer) and was graded correct for the key 21/5."""
    assert verdict("21/5", "2 1/5")[0] == 0.0
    assert verdict("11/5", "2 1/5") == (1.0, "correct")
    assert verdict("3 1/2", "31/2")[0] == 0.0           # and the key 3 1/2 is 7/2, not 31/2
    assert verdict("3 1/2", "7/2") == (1.0, "correct")
