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
KNOWN_GAPS = {
    ("fraction-key", "\\frac{21}{5}"),
    ("fraction-key", "\\dfrac{21}{5}"),
    ("fraction-key", "$\\dfrac{21}{5}$"),
    ("latex-fraction-key", "21/5"),
    ("latex-fraction-key", "4,2"),
    ("latex-fraction-key", "4.2"),
    ("latex-fraction-key", "42/10"),
    ("decimal-comma-key", "\\frac{21}{5}"),
    ("half", "\\frac{1}{2}"),
    ("mixed-number-key", "7/2"),
    ("mixed-number-key", "3,5"),
    ("mixed-number-key", "3.5"),
    ("mixed-number-key", "\\frac{7}{2}"),
    ("empty-set-latex-key", "\u2205"),
    ("empty-set-latex-key", "\\emptyset"),
    ("empty-set-latex-key", "\u043d\u0435\u0442 \u043a\u043e\u0440\u043d\u0435\u0439"),
    ("empty-set-latex-key", "\u041d\u0435\u0442 \u043a\u043e\u0440\u043d\u0435\u0439."),
    ("empty-set-latex-key", "\u043a\u043e\u0440\u043d\u0435\u0439 \u043d\u0435\u0442"),
    ("empty-set-latex-key", "\u043d\u0435\u0442 \u0440\u0435\u0448\u0435\u043d\u0438\u0439"),
    ("empty-set-latex-key", "\u0440\u0435\u0448\u0435\u043d\u0438\u0439 \u043d\u0435\u0442"),
    ("empty-set-latex-key", "\u043f\u0443\u0441\u0442\u043e\u0435 \u043c\u043d\u043e\u0436\u0435\u0441\u0442\u0432\u043e"),
    ("empty-set-latex-key", "x \\in \\varnothing"),
    ("empty-set-words-key", "\u043a\u043e\u0440\u043d\u0435\u0439 \u043d\u0435\u0442"),
    ("empty-set-words-key", "\\varnothing"),
    ("empty-set-words-key", "\u2205"),
    ("empty-set-words-key", "\\emptyset"),
}


def verdict(key, typed):
    task = SimpleNamespace(id="golden", correct_answer=key, answer_type="text", sympy_solution=None, distractor_meta=[])
    return EVALUATOR.evaluate(task, typed)


def pairs(kind):
    return [pytest.param(case["key"], typed, id=f"{case['id']}|{typed}",
                         marks=[pytest.mark.xfail(strict=True, reason="decision 8 not applied yet")] if (case["id"], typed) in KNOWN_GAPS else [])
            for case in GOLDEN["cases"] for typed in case[kind]]


@pytest.mark.parametrize("key, typed", pairs("accept"))
def test_equivalent_notations_are_graded_correct(key, typed):
    assert verdict(key, typed) == (1.0, "correct")


@pytest.mark.parametrize("key, typed", pairs("reject"))
def test_other_values_are_graded_wrong(key, typed):
    outcome, category = verdict(key, typed)
    assert outcome == 0.0 and category != "correct"


@pytest.mark.parametrize("case", GOLDEN["contested"], ids=lambda c: f"{c['key']}|{c['typed']}")
def test_the_contested_cases_keep_the_verdict_of_diagnostic(case):
    assert (verdict(case["key"], case["typed"])[0] == 1.0) is case["diag"]
