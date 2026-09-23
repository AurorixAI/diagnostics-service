"""How diagnostic answer options are served: one key, no look-alikes, stable shuffle."""
from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.domain import session_service as session_service_module
from src.domain.answer_evaluator import AnswerEvaluator
from src.domain.session_service import SessionService
from src.domain.session_state import SessionState
from src.domain.task_display import build_diag_answer_options, should_show_diag_mcq


def _task(**kwargs):
    base = {
        "id": "task-1",
        "answer_type": "exact_number",
        "correct_answer": "4",
        "correct_answer_latex": "$4$",
        "question_text": "",
        "question_latex": None,
        "question_image_url": None,
        "answer_options": None,
        "answer_options_latex": None,
        "distractor_meta": None,
        "sympy_solution": None,
        "tags": {},
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _graded(task, options):
    evaluator = AnswerEvaluator()
    return [evaluator.evaluate(task, option)[0] == 1.0 for option in options]


# ── one answer in two notations ─────────────────────────────────────────────

def test_key_stored_in_another_notation_is_served_once_and_graded_correct():
    task = _task(
        correct_answer="0.22",
        correct_answer_latex="$0{,}22$",
        answer_options=[r"$\dfrac{11}{50}$", r"$0{,}25$", r"$\dfrac{1}{5}$"],
    )

    options, latex = build_diag_answer_options(task)

    assert len(options) == 3
    assert options.count("0.22") == 1
    assert latex[options.index("0.22")] == r"$\dfrac{11}{50}$"
    assert _graded(task, options) == [option == "0.22" for option in options]


def test_key_split_across_formulas_does_not_add_a_look_alike_option():
    key = "возрастает на $[-4; 2]$ и $[6; 8)$"
    task = _task(
        answer_type="text",
        correct_answer=key,
        correct_answer_latex=key,
        answer_options=["возрастает на $[-4$; $2]$ и $[6$; $8)$", "возрастает на $(-7$; $-4)$"],
    )

    options, latex = build_diag_answer_options(task)

    assert len(options) == 2
    assert sum(_graded(task, options)) == 1
    assert latex[options.index(key)] == "возрастает на $[-4$; $2]$ и $[6$; $8)$"


def test_two_stored_notations_of_the_key_are_merged():
    task = _task(correct_answer=r"$\dfrac{1}{6}$",
                 answer_options=[r"$\dfrac{1}{6}$", r"$\dfrac{1}{3}$", r"$\frac{1}{6}$"])

    options, _ = build_diag_answer_options(task)

    assert options == [r"$\dfrac{1}{6}$", r"$\dfrac{1}{3}$"]


def test_distinct_wrong_options_are_never_merged_with_the_key():
    task = _task(correct_answer="1/3", answer_options=["$0{,}33$", "$1/3$", "$0{,}3$"])

    options, _ = build_diag_answer_options(task)

    assert len(options) == 3
    assert _graded(task, options).count(True) == 1


def test_mixed_number_is_not_confused_with_a_different_fraction():
    task = _task(correct_answer=r"$3\dfrac{4}{9}$", answer_options=["$34/9$", "$3 4/9$", "$4/9$"])

    options, _ = build_diag_answer_options(task)

    assert r"$3\dfrac{4}{9}$" in options and "$34/9$" in options
    assert len(options) == 3


def test_built_options_drop_a_distractor_equal_to_the_key():
    task = _task(correct_answer="1/2", distractor_meta=[{"value": "0,5"}, {"value": "1/3"}, {"value": "2"}])

    options, _ = build_diag_answer_options(task)

    assert sorted(options) == ["1/2", "1/3", "2"]


def test_built_options_fall_back_to_open_input_when_only_the_key_remains():
    task = _task(correct_answer="1/2", distractor_meta=[{"value": "0,5"}, {"value": "$\\dfrac{1}{2}$"}])

    assert build_diag_answer_options(task) == (None, None)


def test_distractor_displayed_like_the_key_is_not_offered_as_a_second_key():
    # Historical row: the distractor's value is "2" but its display is "$20$",
    # identical to the key. A student cannot tell the two buttons apart.
    task = _task(correct_answer="$20$", correct_answer_latex="$20$",
                 distractor_meta=[{"value": "2", "value_latex": "$20$"},
                                  {"value": "200", "value_latex": "$200$"},
                                  {"value": "22", "value_latex": "$22$"}])

    options, latex = build_diag_answer_options(task, seed="s:task-1")

    assert len(latex) == 3 and set(latex) == {"$20$", "$200$", "$22$"}
    assert _graded(task, options).count(True) == 1


def test_stored_option_displayed_exactly_like_the_key_counts_as_the_key():
    key = r"$\sqrt{\dfrac{2}{2}}$"
    task = _task(answer_type="expression", correct_answer=key, correct_answer_latex=key,
                 answer_options=[r"$√\dfrac{2}{2}$", r"$\dfrac{1}{2}$", r"$2$"],
                 answer_options_latex=[key, r"$\dfrac{1}{2}$", r"$2$"])

    options, latex = build_diag_answer_options(task)

    assert options == [key, r"$\dfrac{1}{2}$", r"$2$"]
    assert _graded(task, options) == [True, False, False]


def test_decimal_comma_and_dot_options_are_one_answer():
    key = r"$A(-5{,}8), B(9{,}8); |-5{,}8| = 5{,}8, |9{,}8| = 9{,}8$"
    task = _task(answer_type="text", correct_answer=key, correct_answer_latex=key,
                 answer_options=["$A(-5.8)$, $B(9.8)$; $|-5.8| = 5.8$, $|9.8| = 9.8$",
                                 "$A(5.8)$, $B(-9.8)$; $|5.8| = 5.8$, $|-9.8| = 9.8$"])

    options, _ = build_diag_answer_options(task)

    assert len(options) == 2
    assert _graded(task, options).count(True) == 1


def test_key_repeated_without_its_closing_period_is_one_answer():
    key = "Если $a < -4$, то $x \\in (4; -a]$; если $a > -4$, то $x \\in [-a; 4)$."
    task = _task(answer_type="text", correct_answer=key, correct_answer_latex=key,
                 distractor_meta=[{"value": "Если $a < -4$, то $x \\in [-a; 4)$; если $a > -4$, то $x \\in (4; -a]$"},
                                  {"value": "Если $a < -4$, то $x \\in (4; -a]$; если $a > -4$, то $x \\in [-a; 4)$"},
                                  {"value": "Если $a < -4$, то $x \\in \\varnothing$"}])

    options, _ = build_diag_answer_options(task)

    assert len(options) == 3
    assert _graded(task, options).count(True) == 1


def test_stored_options_whose_display_copies_the_key_become_open_input():
    # Historical row: every option's LaTeX was overwritten with the key's.
    key = r"$x^{6} + 6x^{5}a + a^{6}$"
    task = _task(answer_type="expression", correct_answer=key, correct_answer_latex=key,
                 answer_options=[r"$x^{6} + 6x^{5a} + a^{6}$", r"$x^{6} + 6x^{5a} + a^{5}$",
                                 r"$x^{6} + 6x^{5a} + 6a^{6}$"],
                 answer_options_latex=[key, key, key])

    assert build_diag_answer_options(task, seed="s:task-1") == (None, None)


def test_empty_stored_options_are_never_served():
    task = _task(correct_answer="4", answer_options=["4", "", "5", "  "])

    options, _ = build_diag_answer_options(task)

    assert options == ["4", "5"]


def test_options_that_look_different_are_never_merged():
    task = _task(correct_answer="4", distractor_meta=[{"value": "3", "value_latex": "$3$"},
                                                      {"value": "5", "value_latex": "$5$"},
                                                      {"value": "-4", "value_latex": "$-4$"}])

    options, _ = build_diag_answer_options(task)

    assert sorted(options) == ["-4", "3", "4", "5"]


# ── yes / no ────────────────────────────────────────────────────────────────

def test_yes_no_question_with_one_distractor_is_two_buttons():
    task = _task(answer_type="text", correct_answer="нет", correct_answer_latex="нет",
                 distractor_meta=[{"value": "да"}])

    options, _ = build_diag_answer_options(task, seed="s:task-1")

    assert sorted(options) == ["да", "нет"]
    assert should_show_diag_mcq(task) is True
    assert _graded(task, options) == [option == "нет" for option in options]


def test_other_answers_with_one_distractor_stay_open_input():
    task = _task(correct_answer="4", distractor_meta=[{"value": "5"}])

    assert build_diag_answer_options(task, seed="s:task-1") == (None, None)
    assert should_show_diag_mcq(task) is False


# ── stable per-attempt shuffle ──────────────────────────────────────────────

STORED = _task(correct_answer="4", answer_options=["4", "3", "5", "6"],
               answer_options_latex=["$4$", "$3$", "$5$", "$6$"])
BUILT = _task(correct_answer="4", distractor_meta=[{"value": "3", "value_latex": "$3$"},
                                                   {"value": "5", "value_latex": "$5$"},
                                                   {"value": "6", "value_latex": "$6$"}])


@pytest.mark.parametrize("task", [STORED, BUILT], ids=["stored", "built"])
def test_same_session_always_gets_the_same_order(task):
    first = build_diag_answer_options(task, seed="session-a:task-1")
    for _ in range(10):
        assert build_diag_answer_options(task, seed="session-a:task-1") == first


@pytest.mark.parametrize("task", [STORED, BUILT], ids=["stored", "built"])
def test_correct_position_is_uniform_across_sessions(task):
    positions = Counter()
    for n in range(2000):
        options, _ = build_diag_answer_options(task, seed=f"session-{n}:task-1")
        assert sorted(options) == ["3", "4", "5", "6"]
        positions[options.index("4")] += 1
    assert set(positions) == {0, 1, 2, 3}
    assert all(350 <= count <= 650 for count in positions.values()), positions


@pytest.mark.parametrize("task", [STORED, BUILT], ids=["stored", "built"])
def test_display_latex_travels_with_its_option_after_shuffle(task):
    for n in range(50):
        options, latex = build_diag_answer_options(task, seed=f"session-{n}:task-1")
        assert latex == [f"${value}$" for value in options]


@pytest.mark.parametrize("task", [STORED, BUILT], ids=["stored", "built"])
def test_key_is_graded_correct_in_every_position(task):
    for n in range(200):
        options, _ = build_diag_answer_options(task, seed=f"session-{n}:task-1")
        assert _graded(task, options) == [option == "4" for option in options]


def test_letter_only_options_keep_their_order():
    task = _task(correct_answer="$B$", answer_options=["$A$", "$B$", "$C$", "$D$"])
    for n in range(20):
        options, _ = build_diag_answer_options(task, seed=f"session-{n}:task-1")
        assert options == ["$A$", "$B$", "$C$", "$D$"]


# ── the diagnostic actually passes a per-session seed ──────────────────────

def _served(session_id, task):
    service = object.__new__(SessionService)
    state = SessionState(session_id=session_id, student_id="st", grade_level=9, current_task_id=task.id)
    with patch.object(session_service_module, "settings", SimpleNamespace(max_items=40)):
        return service._task_to_out(task, state).answer_options


def test_session_service_serves_a_stable_per_session_order():
    task = _task(id="task-9", correct_answer="4", answer_options=["4", "3", "5", "6"])

    assert _served("session-x", task) == _served("session-x", task)
    orders = {tuple(_served(f"session-{n}", task)) for n in range(40)}
    assert len(orders) > 1
    first_positions = Counter(order.index("4") for order in orders)
    assert len(first_positions) > 1
