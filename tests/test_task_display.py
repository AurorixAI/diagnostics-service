"""Tests for diagnostic task display (MCQ vs open)."""
from types import SimpleNamespace

from src.domain.task_display import (
    build_diag_answer_options,
    diag_answer_type_for_display,
    should_show_diag_mcq,
)
from src.domain.proof_answer import extract_proof_expression, format_proof_answer


def _task(**kwargs):
    base = {
        "answer_type": "exact_number",
        "correct_answer": "4",
        "correct_answer_latex": "$4$",
        "question_text": "",
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


def test_legacy_text_distractors_are_rendered_as_mcq_without_data_mutation():
    t = _task(
        correct_answer="2",
        correct_answer_latex="$2$",
        distractor_meta=[
            {"text": "1", "text_latex": "$1$"},
            {"text": "3", "text_latex": "$3$"},
        ],
    )

    opts, latex = build_diag_answer_options(t)

    assert opts is not None and set(opts) == {"1", "2", "3"}
    assert latex is not None
    assert latex[opts.index("1")] == "$1$"
    assert t.distractor_meta[0]["text"] == "1"


def test_dict_options_keep_canonical_value_and_parallel_latex():
    t = _task(
        correct_answer="1/2",
        correct_answer_latex=r"$\dfrac{1}{2}$",
        answer_options=[
            {"value": "1/2", "value_latex": r"$\dfrac{1}{2}$"},
            {"value": "2", "value_latex": "$2$"},
        ],
    )

    options, options_latex = build_diag_answer_options(t)

    assert options == ["1/2", "2"]
    assert options_latex == [r"$\dfrac{1}{2}$", "$2$"]


def test_parallel_answer_options_latex_overrides_legacy_raw_option_formatting():
    t = _task(
        correct_answer="x / 2",
        correct_answer_latex=r"$\dfrac{x}{2}$",
        answer_options=[
            {"text": "x / 2"},
            {"text": "x / 3"},
        ],
        answer_options_latex=[r"$\dfrac{x}{2}$", r"$\dfrac{x}{3}$"],
    )

    options, options_latex = build_diag_answer_options(t)

    assert options == ["x / 2", "x / 3"]
    assert options_latex == [r"$\dfrac{x}{2}$", r"$\dfrac{x}{3}$"]


def test_stored_options_remain_the_ui_source_even_when_distractors_differ():
    t = _task(
        answer_options=["1", "2"],
        distractor_meta=[
            {"value": "3", "value_latex": "$3$"},
            {"value": "5", "value_latex": "$5$"},
        ],
    )

    options, latex = build_diag_answer_options(t)

    assert options is not None and options == ["1", "2", "4"]
    assert latex is not None and latex[options.index("4")] == "$4$"


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


def test_proof_placeholder_extracts_tight_inequality():
    question = (
        "Известно, что числа x_1 и x_2 являются нулями функции y = ax^2 + bx + c. "
        "Докажите, что если число x_0 заключено между x_1 и x_2, то выполняется неравенство "
        "a(ax_0^2 + bx_0 + c) < 0."
    )
    assert extract_proof_expression(question) == "a(ax_0^2 + bx_0 + c) < 0"
    assert format_proof_answer(question) == "$a(ax_0^2 + bx_0 + c) < 0$"


def test_proof_placeholder_normalizes_sqrt_notation():
    question = "Докажите, что sqrt(6) + √(9) < 0."
    assert extract_proof_expression(question) == r"\sqrt{6} + \sqrt{9} < 0"
