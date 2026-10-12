"""Regression tests for the evidence boundary of diagnostic reports.

These tests deliberately avoid a database and any model call.  They protect the
methodical contract: normal mistakes are observed gaps, while a primary cause
may only be shown after an actual Deep Scan prerequisite trajectory.
"""
from types import SimpleNamespace

from src.domain import report_generator


def _answer(*, skill_id, task_id, outcome, is_deep_scan=False, phase="navigation"):
    return SimpleNamespace(
        skill_id=skill_id,
        task_id=task_id,
        outcome=outcome,
        is_deep_scan=is_deep_scan,
        phase=phase,
        eval_category="correct" if outcome else "wrong",
        student_answer="1" if outcome else "0",
    )


def _skills(*skill_ids):
    return {skill_id: {"name_ru": f"Навык {skill_id}"} for skill_id in skill_ids}


def test_normal_wrong_answer_does_not_create_a_pseudo_root_cause():
    answers = [_answer(skill_id="G7_ALG_1", task_id=None, outcome=0)]

    chains = report_generator._reconstruct_root_cause_chains(
        answers, _skills("G7_ALG_1"), [], grade_level=7,
    )

    assert chains == []
    boundary = report_generator._build_diagnostic_boundary(
        answers, _skills("G7_ALG_1"), 7, chains,
    )
    assert boundary["breakpoint_evidence"] == "observed"
    assert boundary["breakpoint_skills"] == ["Навык G7_ALG_1"]


def test_deep_scan_prerequisite_descent_creates_confirmed_root_cause():
    answers = [
        _answer(skill_id="G7_ALG_1", task_id=None, outcome=0),
        _answer(
            skill_id="G6_ARITH_2", task_id=None, outcome=0,
            is_deep_scan=True, phase="deep_scan",
        ),
    ]
    skills = _skills("G7_ALG_1", "G6_ARITH_2")

    chains = report_generator._reconstruct_root_cause_chains(
        answers, skills, [], grade_level=7,
    )

    assert len(chains) == 1
    assert chains[0]["source_skill_id"] == "G7_ALG_1"
    assert chains[0]["root_gap_skill_id"] == "G6_ARITH_2"
    boundary = report_generator._build_diagnostic_boundary(answers, skills, 7, chains)
    assert boundary["breakpoint_evidence"] == "confirmed"
    assert boundary["breakpoint_level"] == "6 класс"


def test_ai_plan_must_be_compact_and_use_only_evidence_backed_skills():
    allowed = {
        "G7_A": "Навык A",
        "G7_B": "Навык B",
        "G7_C": "Навык C",
        "G7_D": "Навык D",
        "G7_E": "Навык E",
    }

    too_many = {
        "overall": {"status": "below_level", "score_percent": 30, "student_summary": "Текст."},
        "action_plan": [
            {
                "priority": index,
                "skill_id": skill_id,
                "skill_name_ru": allowed[skill_id],
                "action_title": "Отработка",
                "full_description": "Практика по зафиксированному навыку.",
            }
            for index, skill_id in enumerate(["G7_A", "G7_B", "G7_C", "G7_D", "G7_E", "G7_A"], 1)
        ],
    }
    valid, errors = report_generator._validate_ai_output(
        too_many, computed_status="below_level", score_pct=30, allowed_plan_skills=allowed,
    )
    assert not valid
    assert any("action_plan must contain" in error for error in errors)

    invented = {
        "overall": {"status": "below_level", "score_percent": 30, "student_summary": "Текст."},
        "action_plan": [
            {
                "priority": index,
                "skill_id": skill_id,
                "skill_name_ru": allowed.get(skill_id, "Придуманная тема"),
                "action_title": "Отработка",
                "full_description": "Практика по зафиксированному навыку.",
            }
            for index, skill_id in enumerate(["G7_A", "G7_B", "G7_X"], 1)
        ],
    }
    valid, errors = report_generator._validate_ai_output(
        invented, computed_status="below_level", score_pct=30, allowed_plan_skills=allowed,
    )
    assert not valid
    assert any("not evidence-backed" in error for error in errors)


def test_n03a_contract_no_reliability_equivalent_or_duration_in_the_report_contract():
    """Owner decision O4 + N03a: retired claims are not part of the contract (schema 5)."""
    assert report_generator.REPORT_SCHEMA_VERSION >= 5
    assert "estimated_hours" not in report_generator._AI_SCHEMA
    assert "confidence_of_diagnosis" not in report_generator._AI_SCHEMA
    fallback = report_generator._build_fallback_action_plan([
        {"skill_id": "G7_A", "skill_name_ru": "Навык A", "evidence": "confirmed_prerequisite"},
        {"skill_id": "G7_B", "skill_name_ru": "Навык B", "evidence": "observed_error"},
    ])
    assert [step["priority"] for step in fallback] == [1, 2]
    assert all("estimated_hours" not in step for step in fallback)
    assert fallback[0]["skill_id"] == "G7_A"

    summary = report_generator._build_deterministic_summary(
        status_label="Ниже уровня класса", grade_level=8, score_pct=30, solved=3, total=10,
        boundary={"breakpoint_skills": ["Навык A"]}, strong_skills=[], chains=[],
    )
    assert not report_generator._CLASS_EQUIVALENT_RE.search(summary.lower())
    assert "Ниже уровня класса" in summary
