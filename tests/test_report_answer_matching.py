"""A stored student answer is matched to the current distractors / options of a repaired task (report side only)."""
from types import SimpleNamespace as NS

import pytest

from src.domain import report_generator as rg

EXPLANATION = "Ученик возвёл обе части в куб, не сменив знак неравенства"


def distractors(value):
    return [{"value": value, "error_logic": EXPLANATION}, {"value": "x^3 > y^3", "error_logic": "Другое"}]


def test_find_matching_distractor_after_the_braces_were_added_by_a_content_wave():
    found = rg._find_matching_distractor(distractors("$x^{3} < y^{3}$"), "x^3 < y^3")
    assert found is not None and found["error_logic"] == EXPLANATION
    assert rg._find_matching_distractor(distractors("x^3 < y^3"), "$x^{3} < y^{3}$")["error_logic"] == EXPLANATION


@pytest.mark.parametrize("stored, current", [
    ("x^{13} < y^{13}", "x^13 < y^13"), ("x^{13} < y^{13}", "x^1 3 < y^1 3"), ("x^3 < y^3", "$x^{13} < y^{13}$"),
])
def test_find_matching_distractor_does_not_unwrap_multi_character_groups(stored, current):
    assert rg._find_matching_distractor(distractors(current), stored) is None


def test_student_answer_is_mapped_to_the_repaired_option_display():
    pairs = [("$x^{3} < y^{3}$", r"$x^{3} < y^{3}$"), ("x^3 > y^3", "$x^3 > y^3$")]
    assert rg._student_answer_latex("x^3 < y^3", pairs) == r"$x^{3} < y^{3}$"
    assert rg._student_answer_latex("x^{13} < y^{13}", pairs) is None


def test_rebuilt_report_attaches_the_explanation_of_the_repaired_distractor(monkeypatch):
    """Session b5b3e418: answered `x^3 < y^3`; after wave w35 the distractor value is `$x^{3} < y^{3}$`."""
    task = {
        "id": "ds_llm_c93d5c1c9ba6", "question_text": "Сравните куб", "question_latex": None,
        "correct_answer": "x^3 > y^3", "correct_answer_latex": None, "distractor_meta": distractors("$x^{3} < y^{3}$"),
        "_option_pairs": [("x^3 > y^3", "$x^{3} > y^{3}$"), ("$x^{3} < y^{3}$", "$x^{3} < y^{3}$")], "_answer_type": "mcq",
    }
    monkeypatch.setattr(rg, "_load_task_context", lambda answer: (dict(task), "snapshot"))
    answer = NS(
        id="a1", session_id=None, task_id="ds_llm_c93d5c1c9ba6", skill_id="S1", topic_id="T1", outcome=0,
        eval_category="distractor", student_answer="x^3 < y^3", task_snapshot=None, answered_at=None, time_ms=1, phase="navigation",
        is_deep_scan=False,
    )
    patterns = rg._build_error_patterns([answer], {"S1": {"name_ru": "Неравенства"}})
    assert len(patterns) == 1
    assert patterns[0]["distractor_explanation"] == EXPLANATION
    assert patterns[0]["student_answer"] == "x^3 < y^3"                     # the stored answer is shown as it was
    assert patterns[0]["student_answer_latex"] == "$x^{3} < y^{3}$"          # the option the student chose, as repaired

    task["distractor_meta"] = distractors("$x^{13} < y^{13}$")
    patterns = rg._build_error_patterns([answer], {"S1": {"name_ru": "Неравенства"}})
    assert patterns[0]["distractor_explanation"] is None                    # a different value gets no explanation


def test_rehydrate_script_key_agrees_on_single_tokens_and_not_on_groups():
    from scripts import rehydrate_reports as script
    assert script.are_answers_equivalent("x^3 < y^3", "$x^{3} < y^{3}$")
    assert script.are_answers_equivalent("a_2", "a_{2}")
    assert not script.are_answers_equivalent("x^{13}", "x^13")
    assert not script.are_answers_equivalent("x^{13}", "x^1 3")
