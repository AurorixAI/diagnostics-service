"""N13 P4 #102 (owner decision 17.10): a report never says «предварительно».

The internal ``provisional`` flag (se above PROVISIONAL_SE) stays in the stored data for calibration, but it
is never worded: not in the deterministic summary, not in what the narrative model is given, and a sentence
like that is dropped from the summary before it is stored and when a stored report is served.
"""
from __future__ import annotations

import inspect
import os

import pytest

from src.domain import report_generator as rg

WORDING = ("предварительн", "точность измерения пока ограничена", "provisional")
LEGACY = "Оценка предварительная: точность измерения пока ограничена."


def _summary(**over):
    args = dict(
        status_label="Ниже уровня класса", grade_level=8, score_pct=40, solved=7, total=12,
        boundary={"breakpoint_skills": ["Дроби"]}, strong_skills=[{"skill_name_ru": "Сложение"}], chains=[],
    )
    args.update(over)
    return rg._build_deterministic_summary(**args)


def test_the_deterministic_summary_has_no_preliminary_sentence_and_no_flag_to_ask_for_one():
    assert "provisional" not in inspect.signature(rg._build_deterministic_summary).parameters
    with pytest.raises(TypeError):
        _summary(provisional=True)
    for args in (
        {}, {"chains": [{"root_gap_skill_name": "Дроби"}]}, {"boundary": {"breakpoint_skills": []}, "strong_skills": []},
        {"boundary": {"breakpoint_skills": []}, "development_focus": "Степени", "achievements": [{"skill_name_ru": "Степени"}]},
        {"solved": None, "total": None},
    ):
        text = _summary(**args).lower()
        for word in WORDING:
            assert word not in text, (args, word)
    # the rest of the sentence flow is untouched: result, level, evidence, anchors, closing
    text = _summary()
    assert text.startswith("Решено 7 из 12 заданий адаптивного теста. Результат измерения: «Ниже уровня класса» (заявленный класс — 8). Зафиксированы")


def test_the_prompt_for_the_model_has_no_slot_for_the_flag_and_no_such_wording():
    assert "provisional" not in " ".join(inspect.signature(rg._build_prompt).parameters)
    args = dict(
        grade_level=8, overall_level="at_grade", score_pct=40, correct=7, total=12, computed_status="below_level",
        status_label="Ниже уровня класса", topics_block="  Дроби", wrong_block="  (нет)", chains_block="  (нет)",
        boundary_block="  (нет)", cognitive_block="  (нет)", anchor_block="  (нет)", plan_candidates_block="  1. G8_T1 — Дроби (x)",
        plan_min_items=1, plan_max_items=1, root_cause_confirmed=False, student_name="Ученик", test_code="T1",
    )
    prompt = rg._build_prompt(**args).lower()
    for word in WORDING:
        assert word not in prompt, word


@pytest.mark.parametrize("text,expected", [
    (f"Решено 7 из 12. Результат: «Ниже». {LEGACY} Зафиксированы затруднения: Дроби.",
     "Решено 7 из 12. Результат: «Ниже». Зафиксированы затруднения: Дроби."),
    (f"{LEGACY} Решено 7 из 12. Результат: «Ниже».", "Решено 7 из 12. Результат: «Ниже»."),
    (f"Решено 7 из 12. Результат: «Ниже». {LEGACY}", "Решено 7 из 12. Результат: «Ниже»."),
    ("Решено 7 из 12. Оценка носит предварительный характер. Опорные навыки: Сложение.", "Решено 7 из 12. Опорные навыки: Сложение."),
    ("Решено 7 из 12. Точность измерения пока ограничена. Опорные навыки: Сложение.", "Решено 7 из 12. Опорные навыки: Сложение."),
    (LEGACY, ""),
    ("Решено 7 из 12. Опорные навыки: Сложение.", "Решено 7 из 12. Опорные навыки: Сложение."),
    ("", ""),
])
def test_a_preliminary_sentence_is_dropped_and_only_that_sentence(text, expected):
    assert rg.drop_preliminary_sentences(text) == expected


def test_not_a_string_comes_back_unchanged():
    for value in (None, 5, ["Оценка предварительная."], {"a": 1}):
        assert rg.drop_preliminary_sentences(value) is value


def test_a_stored_legacy_report_is_served_without_the_sentence_and_keeps_the_flag_for_calibration():
    stored = {
        "overall": {"student_summary": f"Решено 7 из 12. Результат: «Ниже». {LEGACY} Зафиксированы затруднения: Дроби.",
                    "provisional": True, "status": "below_level"},
        "level": {"category": "below_grade", "status": "below", "provisional": True, "solved": 7, "total": 12},
        "action_plan": [{"skill_id": "G8_T1", "skill_name_ru": "Дроби", "priority": 1, "action_title": "Дроби",
                         "full_description": "Предварительно повторите сложение дробей. Затем решите три задачи."}],
    }
    served = rg.strip_retired_report_fields(stored)
    assert served["overall"]["student_summary"] == "Решено 7 из 12. Результат: «Ниже». Зафиксированы затруднения: Дроби."
    assert served["overall"]["provisional"] is True and served["level"]["provisional"] is True
    # «предварительно повторите» is a different meaning of the word in a plan step: left alone
    assert served["action_plan"][0]["full_description"] == stored["action_plan"][0]["full_description"]
    # the stored copy is not modified in place
    assert LEGACY in stored["overall"]["student_summary"]
    # a summary that was only the sentence is withheld (the front hides an empty block), not shown as ""
    only = rg.strip_retired_report_fields({"overall": {"student_summary": LEGACY}})
    assert only["overall"]["student_summary"] is None
    # an untouched summary (and an empty one) stays as it is
    assert rg.strip_retired_report_fields({"overall": {"student_summary": ""}})["overall"]["student_summary"] == ""


# ── against a disposable PostgreSQL (like tests/test_n02_db.py): the whole report, the model's input ──

DB_URL = os.getenv("A2_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="Requires disposable A2 PostgreSQL")

if DB_URL:  # the fixtures live with the N02 tests
    from tests.test_n02_db import build_report, db, make_session  # noqa: F401


@needs_db
def test_the_model_gets_the_same_prompt_whatever_the_flag_says_and_the_stored_summary_never_words_it(db, monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(rg, "call_gemini", lambda prompt, *a, **k: prompts.append(prompt))   # None: the narrative is not written

    precise = make_session(db, se=0.25, invite="P4TEST0001")
    report_precise = build_report(db, precise)
    precise_prompts, prompts[:] = list(prompts), []

    loose = make_session(db, se=0.55, invite="P4TEST0002")
    report_loose = build_report(db, loose)
    loose_prompts = list(prompts)

    assert report_precise.report_json["level"]["provisional"] is False
    assert report_loose.report_json["level"]["provisional"] is True            # kept for calibration
    assert report_loose.report_json["overall"]["provisional"] is True
    assert precise_prompts and loose_prompts
    assert precise_prompts == loose_prompts                                     # nothing about precision reaches the model
    for prompt in loose_prompts:
        for word in WORDING:
            assert word not in prompt.lower(), word
    summary = report_loose.report_json["overall"]["student_summary"].lower()
    for word in WORDING:
        assert word not in summary, word
