"""Tests for diagnostic task display (MCQ vs open)."""
from types import SimpleNamespace

from src.domain.task_display import (
    build_diag_answer_options,
    diag_answer_type_for_display,
    should_show_diag_mcq,
)


def _task(**kwargs):
    base = {
        "answer_type": "exact_number",
        "correct_answer": "4",
        "correct_answer_latex": "$4$",
        "answer_options": None,
        "distractor_meta": None,
        "tags": {},
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_no_distractors_stays_open():
    t = _task()
    assert should_show_diag_mcq(t) is False
    opts, _ = build_diag_answer_options(t)
    assert opts is None


def test_exact_number_with_distractors_is_mcq():
    t = _task(
        distractor_meta=[
            {"value": "3", "value_latex": "$3$"},
            {"value": "5", "value_latex": "$5$"},
        ],
    )
    assert should_show_diag_mcq(t) is True
    opts, _ = build_diag_answer_options(t)
    assert opts is not None
    assert len(opts) == 3
    assert "4" in opts
    assert diag_answer_type_for_display(t, opts) == "mcq"


def test_inequality_with_distractors_is_mcq():
    t = _task(
        answer_type="inequality",
        correct_answer=r"\sqrt{24} = \frac{1}{3}\sqrt{216}",
        correct_answer_latex=r"$\sqrt{24} = \frac{1}{3}\sqrt{216}$",
        distractor_meta=[
            {"value": r"\sqrt{24} > \frac{1}{3}\sqrt{216}"},
            {"value": r"\sqrt{24} < \frac{1}{3}\sqrt{216}"},
        ],
    )
    assert should_show_diag_mcq(t) is True
    opts, _ = build_diag_answer_options(t)
    assert opts is not None
    assert t.correct_answer in opts


def test_expression_with_distractors_is_mcq():
    t = _task(
        answer_type="expression",
        correct_answer="2x+1",
        distractor_meta=[{"value": "x+1"}, {"value": "2x"}],
    )
    assert should_show_diag_mcq(t) is True
    opts, _ = build_diag_answer_options(t)
    assert opts is not None


def test_coordinate_with_distractors_is_mcq():
    t = _task(
        answer_type="coordinate",
        correct_answer="(5; 4)",
        distractor_meta=[{"value": "(5; 0)"}, {"value": "(2.33; 4)"}],
    )
    assert should_show_diag_mcq(t) is True
    opts, _ = build_diag_answer_options(t)
    assert opts is not None
    assert "(5; 4)" in opts
    assert diag_answer_type_for_display(t, opts) == "mcq"
