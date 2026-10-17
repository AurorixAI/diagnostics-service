"""N13 P4 #102 (owner decision 17.10): a report never says «предварительно».

The internal ``provisional`` flag (se above PROVISIONAL_SE) stays in the stored data for calibration, but it
is never worded: not in the deterministic summary, not in what the narrative model is given, and a sentence
like that is dropped from the summary before it is stored and when a stored report is served.
"""
from __future__ import annotations

import inspect
import json
import os
import re

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
    ("Решено 7 из 12. Это предварительный результат. Опорные навыки: Сложение.", "Решено 7 из 12. Опорные навыки: Сложение."),
    ("Решено 7 из 12. Предварительная оценка уровня: ниже нормы. Опорные навыки: Сложение.", "Решено 7 из 12. Опорные навыки: Сложение."),
    ("Решено 7 из 12. Уровень определён предварительно. Опорные навыки: Сложение.", "Решено 7 из 12. Опорные навыки: Сложение."),
    ("Решено 7 из 12. Оценка предварительная… Опорные навыки: Сложение.", "Решено 7 из 12. Опорные навыки: Сложение."),
    (LEGACY, ""),
    ("Решено 7 из 12. Опорные навыки: Сложение.", "Решено 7 из 12. Опорные навыки: Сложение."),
    ("", ""),
])
def test_a_preliminary_sentence_is_dropped_and_only_that_sentence(text, expected):
    assert rg.drop_preliminary_sentences(text) == expected


@pytest.mark.parametrize("text", [
    # advice, not a statement about the assessment: «предварительно» without an assessment noun beside it
    "Для начала предварительно повторите дроби.",
    "Решено 7 из 12 заданий. Предварительно повторите дроби. Уровень: «Ниже уровня класса».",
    # the noun is there, but too far from the word: a plan step, not «the assessment is preliminary»
    "Результат решения уравнений: предварительно найдите область определения.",
    # a skill or a topic that happens to carry the word, listed by the deterministic summary
    "Опорные навыки: Предварительные сведения о функциях.",
    "Подтверждены навыки: Предварительная оценка результатов.",
    "Зафиксированы ключевые затруднения: Предварительные сведения, Оценка погрешности.",
    "Углублённая проверка подтвердила первопричину: «Предварительная оценка».",
    "Следующий шаг — развитие: задачи повышенной сложности по теме «Предварительные сведения».",
    # quoted names are not judged by their words
    "Уровень по теме «Предварительные сведения» ниже нормы.",
])
def test_nothing_else_is_touched(text):
    assert rg.drop_preliminary_sentences(text) == text


@pytest.mark.parametrize("text,expected", [
    # «т.е.» / «т.к.» inside a sentence do not end it: no orphan fragment is left behind
    ("Решено 7 из 12, т.е. Оценка предварительная и точность измерения пока ограничена. Опорные навыки: Сложение.",
     "Опорные навыки: Сложение."),
    ("Результат ниже нормы, т.к. Оценка предварительная. Опорные навыки: Сложение.", "Опорные навыки: Сложение."),
    ("Ученик решил задания по дробям, т.е. по теме 5 класса. Оценка предварительная.", "Ученик решил задания по дробям, т.е. по теме 5 класса."),
    ("Темы указаны напр. Дроби и степени. Оценка предварительная. Опорные навыки: Сложение.", "Темы указаны напр. Дроби и степени. Опорные навыки: Сложение."),
    # «и т.д.» / «и др.» often end a sentence: the next capital letter starts a new one, the first stays whole
    ("Решены дроби, степени и т.д. Оценка предварительная. Опорные навыки: Сложение.", "Решены дроби, степени и т.д. Опорные навыки: Сложение."),
    ("Решены дроби, степени и др. Оценка предварительная. Опорные навыки: Сложение.", "Решены дроби, степени и др. Опорные навыки: Сложение."),
    # a full stop inside a number or before a lower-case letter splits nothing
    ("Решено 58.3 процента заданий, т.е. 7 из 12. Оценка предварительная.", "Решено 58.3 процента заданий, т.е. 7 из 12."),
    ("Решено 7 из 12 заданий и т.д., оценка предварительная. Опорные навыки: Сложение.", "Опорные навыки: Сложение."),
])
def test_abbreviations_neither_leak_a_fragment_nor_swallow_a_neighbour(text, expected):
    assert rg.drop_preliminary_sentences(text) == expected
    assert "предварительн" not in rg.drop_preliminary_sentences(text).lower()


def test_separators_survive_a_dropped_sentence():
    text = f"Решено 7 из 12.\n{LEGACY}\n\nОпорные навыки: Сложение."
    assert rg.drop_preliminary_sentences(text) == "Решено 7 из 12.\nОпорные навыки: Сложение."


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


@needs_db
def test_the_write_path_strips_a_preliminary_sentence_the_model_wrote(db, monkeypatch):
    """The model returns a valid narrative whose summary CONTAINS the legacy sentence: it is not stored.

    (Without ``drop_preliminary_sentences`` on the merge of the model's summary this test fails: the sentence would
    be stored and shown.)
    """
    returned: list[str] = []

    def fake_model(prompt, *args, **kwargs):
        status = re.search(r'СКОПИРУЙ ТОЧНО: "(\w+)"', prompt).group(1)
        score = int(re.search(r"\((\d+)%; это факт", prompt).group(1))
        goals_block = prompt.split("ДОПУСТИМЫЕ ЦЕЛИ ПЛАНА", 1)[1].split("ВЕРНИ ТОЛЬКО JSON", 1)[0]
        goals = re.findall(r"^\s+\d+\. (\S+) — (.+?) \(", goals_block, re.M)
        assert goals, goals_block
        summary = f"Решено 2 из 11 заданий адаптивного теста. {LEGACY} Зафиксированы затруднения в сложении дробей."
        answer = json.dumps({
            "overall": {"score_percent": score, "status": status, "status_label_ru": "Уровень", "student_summary": summary},
            "action_plan": [
                {"priority": i + 1, "skill_id": skill_id, "skill_name_ru": name, "action_title": "Отработать тему",
                 "full_description": "Решите несколько заданий на эту тему и проверьте усвоение."}
                for i, (skill_id, name) in enumerate(goals[:5])
            ],
        }, ensure_ascii=False)
        returned.append(answer)
        return answer

    monkeypatch.setattr(rg, "call_gemini", fake_model)
    session = make_session(db, se=0.55, invite="P4TEST0003")
    report = build_report(db, session)

    assert returned and LEGACY in returned[0], "the model really wrote the sentence"
    meta = report.report_json["report_meta"]
    assert meta["narrative_status"] == "ready", "the model's text was accepted, so this is the model's summary"
    stored = report.report_json["overall"]["student_summary"]
    assert stored == "Решено 2 из 11 заданий адаптивного теста. Зафиксированы затруднения в сложении дробей."
    for word in WORDING:
        assert word not in stored.lower(), word
    assert report.report_json["level"]["provisional"] is True      # the flag itself is kept
