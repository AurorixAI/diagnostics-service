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


# ── DIAG-3: options shown as Unicode (older snapshots) vs distractor_meta rewritten in LaTeX (prod 13.10) ─────────

def _meta(*pairs):
    return [{"value": value, "error_logic": f"explanation {index}"} for index, value in enumerate(pairs)]


G9_TB_17_2_1 = _meta(r"$45\pi$", r"$\dfrac{\pi}{45}$", r"$\dfrac{\pi}{8}$")
G9_TB_21_252_4 = _meta(
    r"$x = -4\pi + 2\pi k, k \in \mathbb{Z}$", r"$x = -\dfrac{\pi}{2} + 2\pi k, k \in \mathbb{Z}$",
    r"$x = -\dfrac{5\pi}{2} + \pi k, k \in \mathbb{Z}$",
)


@pytest.mark.parametrize("shown_to_student, index", [("$π/45$", 1), ("$π/8$", 2), ("$45π$", 0), ("π/45", 1)])
def test_unicode_option_gets_the_explanation_of_the_latex_distractor_G9_TB_17_2_1(shown_to_student, index):
    found = rg._find_matching_distractor(G9_TB_17_2_1, shown_to_student)
    assert found is not None and found["error_logic"] == f"explanation {index}"


@pytest.mark.parametrize("shown_to_student, index", [
    ("x = -4π + 2πk, k ∈ Z", 0), ("x = -π/2 + 2πk, k ∈ Z", 1), ("x = -5π/2 + πk, k ∈ Z", 2),
    ("$x = -π/2 + 2πk, k ∈ Z$", 1), ("x=-π/2+2πk,k∈Z", 1),
])
def test_every_wrong_unicode_option_gets_its_own_explanation_G9_TB_21_252_4(shown_to_student, index):
    found = rg._find_matching_distractor(G9_TB_21_252_4, shown_to_student)
    assert found is not None and found["error_logic"] == f"explanation {index}"


@pytest.mark.parametrize("answer", [
    "π/4", "$π/4$", "x = -π/2 + 2πk, k ∈ R", "x = π/2 + 2πk, k ∈ Z", "x = -5π/2 + 2πk, k ∈ Z", "x = -π/2 + πk, k ∈ Z",
    "x = -π/2 + 2πk", "π/450", "2π/45", "45/π", "45π/2",
])
def test_a_similar_but_different_answer_still_gets_no_explanation(answer):
    assert rg._find_matching_distractor(G9_TB_17_2_1, answer) is None
    assert rg._find_matching_distractor(G9_TB_21_252_4, answer) is None


def test_unicode_answer_is_mapped_to_the_latex_option_display():
    pairs = [(r"$\dfrac{\pi}{4}$", r"$\dfrac{\pi}{4}$"), (r"$\dfrac{\pi}{45}$", r"$\dfrac{\pi}{45}$")]
    assert rg._student_answer_latex("$π/45$", pairs) == r"$\dfrac{\pi}{45}$"
    assert rg._student_answer_latex("π/450", pairs) is None


def test_rebuilt_report_explains_a_unicode_snapshot_answer_against_latex_distractors(monkeypatch):
    task = {
        "id": "G9_TB_17_2_1", "question_text": "Переведите 45° в радианы", "question_latex": None,
        "correct_answer": r"$\dfrac{\pi}{4}$", "correct_answer_latex": r"$\dfrac{\pi}{4}$", "distractor_meta": G9_TB_17_2_1,
        "_option_pairs": [(r"$\dfrac{\pi}{4}$", r"$\dfrac{\pi}{4}$"), (r"$\dfrac{\pi}{45}$", r"$\dfrac{\pi}{45}$")], "_answer_type": "mcq",
    }
    monkeypatch.setattr(rg, "_load_task_context", lambda answer: (dict(task), "snapshot"))
    answer = NS(
        id="a1", session_id=None, task_id="G9_TB_17_2_1", skill_id="S1", topic_id="T1", outcome=0,
        eval_category="distractor", student_answer="$π/45$", task_snapshot=None, answered_at=None, time_ms=1, phase="navigation",
        is_deep_scan=False,
    )
    patterns = rg._build_error_patterns([answer], {"S1": {"name_ru": "Радианы"}})
    assert len(patterns) == 1
    assert patterns[0]["distractor_explanation"] == "explanation 1"
    assert patterns[0]["student_answer"] == "$π/45$"                                  # the stored answer is shown as it was
    assert patterns[0]["student_answer_latex"] == r"$\dfrac{\pi}{45}$"
