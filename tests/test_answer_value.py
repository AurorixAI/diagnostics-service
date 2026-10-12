from types import SimpleNamespace

from fractions import Fraction

import pytest

from src.domain.answer_evaluator import AnswerEvaluator
from src.domain.answer_value import answer_value_key, answers_equivalent, display_student_answer, exact_number


@pytest.mark.parametrize("first, second", [
    ("0,22", r"$\dfrac{11}{50}$"),
    ("$0.5$", "1/2"),
    ("3 4/9", r"$3\dfrac{4}{9}$"),
    (r"$3 \dfrac{4}{9}$", r"3\frac{4}{9}"),
    ("$[-4$; $2]$ и $[6$; $8)$", "$[-4; 2]$ и $[6; 8)$"),
    (r"$6\,000$", "6000"),
    (r"$(-\infty; 2)$", "(-∞; 2)"),
    (r"$\left(1; 2\right)$", "(1; 2)"),
    (r"-\dfrac{1}{2}", "-0,5"),
    (r"\dfrac{-1}{2}", "-1/2"),
    ("да", " Да "),
    ("$0{,}78^{-0{,}7}$", "$0.78^{-0.7}$"),
    (r"$\log_{0{,}2} 0{,}7$", r"$\log_{0.2} 0.7$"),
    (r"$\sin{\alpha}$", r"$\sin \alpha$"),
    (r"$\dfrac{1}{\cos^{2}{\alpha}}$", r"$\dfrac{1}{\cos^{2} \alpha}$"),
    (r"$\log_{2}{x}$", r"$\log_{2} x$"),
    ("Если $a = -4$, то $x \\in [-a; 4)$.", "Если $a = -4$, то $x \\in [-a; 4)$"),
    ("$25, 9, -39, -52;$", "$25, 9, -39, -52$"),
])
def test_answers_equivalent_recognises_one_value_in_two_notations(first, second):
    assert answers_equivalent(first, second)
    assert answers_equivalent(second, first)


@pytest.mark.parametrize("first, second", [
    ("1/3", "0,33"),
    ("3 4/9", "34/9"),
    ("(-∞; 2)", "(-∞; 2]"),
    ("x", "-x"),
    ("0,22", "0,23"),
    ("51\\%", "0,51"),
    ("2; 3", "3; 2"),
    ("1/0", "0"),
    ("", ""),
    ("$2$", "$2x$"),
    (r"\sqrt{2}", "2"),
    ("да", "нет"),
    (r"$\dfrac{\sqrt{2}}{2}$", r"$\sqrt{\dfrac{2}{2}}$"),
    ("1, 2", "1.2"),
    (r"$\log_{0.2} 0.7$", r"$\log_{0.7} 0.2$"),
    (r"$\sin \alpha$", r"$\sin 2\alpha$"),
    (r"$\sin{x}$", r"$\sin{y}$"),
    ("1.", "1.5"),
    (r"$x \in (4; -a]$", r"$x \in (4; -a)$"),
])
def test_answers_equivalent_never_merges_different_answers(first, second):
    assert not answers_equivalent(first, second)
    assert not answers_equivalent(second, first)


@pytest.mark.parametrize("value, expected", [
    ("7", Fraction(7)), ("-0,25", Fraction(-1, 4)), (r"$\dfrac{3}{8}$", Fraction(3, 8)),
    (r"$2\dfrac{1}{3}$", Fraction(7, 3)), (r"$-1\dfrac{1}{2}$", Fraction(-3, 2)), ("5 1/4", Fraction(21, 4)),
    (r"$60\,000$", Fraction(60000)), ("12 345", Fraction(12345)), (r"$0{,}5$", Fraction(1, 2)),
])
def test_exact_number_parses_unambiguous_numbers(value, expected):
    assert exact_number(value) == expected


@pytest.mark.parametrize("value", ["x + 1", "(1; 2)", "1, 2", "3 4", "50\\%", r"\sqrt{3}", "1/0", "", "2; 3"])
def test_exact_number_refuses_everything_else(value):
    assert exact_number(value) is None


def test_answer_value_key_normalizes_display_equivalent_math_values():
    assert answer_value_key(" $88779$ ") == "88779"
    assert answer_value_key("$$ x + 1 $$") == "x+1"
    assert answer_value_key(r"\dfrac{1}{2}") == r"\frac{1}{2}"


def test_mcq_display_wrapped_distractor_is_recorded_as_distractor():
    task = SimpleNamespace(
        correct_answer="$2$",
        answer_type="mcq",
        distractor_meta=[{"value": "1"}],
    )

    assert AnswerEvaluator().evaluate(task, "$1$") == (0.0, "distractor")


LATEX = r"$y = 2 \pm \sqrt{x - 1}$, $x \in [1; +\infty)$"


def test_display_answer_unwraps_a_python_repr_dict_with_escaped_backslashes():
    stored = repr({"text": LATEX, "is_correct": False})                    # backslashes doubled, quotes single
    assert "\\\\pm" in stored and stored.startswith("{'text'")
    assert display_student_answer(stored) == LATEX
    assert display_student_answer("  " + stored + "\n") == LATEX              # surrounding blanks


def test_display_answer_unwraps_a_json_dict():
    import json
    assert display_student_answer(json.dumps({"text": LATEX, "is_correct": True})) == LATEX
    assert display_student_answer('{"text": "x = 5"}') == "x = 5"


@pytest.mark.parametrize("raw", [
    "x = 5", "$\\frac{1}{2}$", "", "   ", "{1; 2}", "{x | x>0}", "{1, 2, 3}", "{}", "{-3; 5}", "{x \\in R}",
    "{'text': 'unterminated", "{'text': }", "{'a': 1}", "{'text': 5}", "{'text': ''}", "{'text': None}",
    '{"text": 7}', "[{'text': 'x'}]", "x {'text': 'y'}",
    "{'text': __import__('os').getcwd()}",                           # never evaluated
    "{'text': 'a'} + {'text': 'b'}",
])
def test_display_answer_leaves_everything_else_unchanged(raw):
    assert display_student_answer(raw) == raw


def test_display_answer_passes_non_strings_through_and_caps_the_input():
    assert display_student_answer(None) is None and display_student_answer(5) == 5
    long_dict = repr({"text": "x" * 3000, "is_correct": False})
    assert len(long_dict) > 2000 and display_student_answer(long_dict) == long_dict
    nested = "{'text': " + "[" * 500 + "1" + "]" * 500 + "}"                 # deep nesting must not raise
    assert display_student_answer(nested) == nested
