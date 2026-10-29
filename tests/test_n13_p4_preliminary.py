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
import time

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
        plan_min_items=1, plan_max_items=1, root_cause_confirmed=False, test_code="T1",
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


REST = "Решено 7 из 12. {} Опорные навыки: Сложение."
KEPT_AFTER = "Решено 7 из 12. Опорные навыки: Сложение."


@pytest.mark.parametrize("sentence", [
    # R3 leaks (17.10): each states that the assessment is preliminary or limited
    "Итоги диагностики носят предварительный характер.",
    "Выводы предварительные.",
    "Диагностика даёт предварительную картину.",
    "Данные носят предварительный характер.",
    "Точность оценки пока ограничена.",
    "Удалось лишь предварительно оценить уровень.",
    "Оценка, к сожалению, лишь предварительная.",
    "Результат … можно считать лишь предварительным.",
    "Результат диагностики можно считать лишь предварительным.",
    # the same family: more nouns, either order, up to three words apart
    "Заключение пока носит предварительный характер.",
    "Это лишь предварительный анализ.",
    "Диагноз поставлен предварительно.",
    "Итоги предварительно подведены.",            # «итоги» ends in -и but is the noun, not an imperative
    "Уровень определён предварительно, дроби вызывают затруднения.",   # the comma: «дроби» is another clause
    "Измерение пока ограничено.",
    "Оценка ограничена.",
    # each exception to the advice rule on its own: a restricting word with a verb that does not assess ...
    "Можно лишь предварительно сравнить уровень с нормой.",
    # ... and an assessing verb without a restricting word
    "Предварительно удалось определить уровень ученика.",
    # only the ADVERB opens advice: the adjective next to an infinitive still calls the level preliminary
    "Предварительный уровень учитывать при выборе группы.",
    "Предварительный результат уточнить после теста.",
    # hedges: the verb says «we state», not «you do» (one case per verb of the list)
    "Предварительно стоит отметить, что уровень ученика ниже нормы.",
    "Предварительно можно утверждать, что результат ниже нормы.",
    "Можно предварительно заключить, что уровень знаний ниже нормы.",
    "Можно предварительно предположить, что результат ниже нормы.",
    "Следует предварительно констатировать, что уровень ниже нормы.",
    "Можно предварительно полагать, что уровень ниже нормы.",
    "Следует предварительно ожидать, что результат улучшится.",
    # «лишь / только / пока / всего» right before the word: a statement, however far the noun is
    "Уровень знаний ученика определён лишь предварительно.",
    "Результат работы ученика над темой «Дроби» оценён только предварительно.",
    "Итоги по группе за прошлую четверть подведены всего лишь предварительно.",
    "Данные по ученику за последнюю неделю получены пока предварительно.",
    "Оценка знаний ученика по итогам первой четверти дана лишь предварительная.",
])
def test_every_way_of_calling_the_assessment_preliminary_or_limited_is_dropped(sentence):
    assert rg.drop_preliminary_sentences(REST.format(sentence)) == KEPT_AFTER


@pytest.mark.parametrize("text", [
    # advice: «предварительно» and an imperative / infinitive next to it, whatever nouns stand around
    "Чтобы улучшить результат, предварительно повторите дроби.",
    "Для роста уровня предварительно повторите дроби.",
    "Данные задания решите предварительно на черновике.",       # the imperative right BEFORE the adverb
    "Чтобы поднять уровень, предварительно ещё повторите дроби.",   # one word between the adverb and the verb
    "Для оценки результата предварительно изучить тему.",       # an infinitive
    "Для роста уровня предварительно повтори дроби.",           # -й / -и as a word of its own
    "- Для роста уровня предварительно повторите дроби.",
    # reflexive forms and the imperative in -ь
    "Предварительно ознакомьтесь с итогами прошлого урока.",
    "Рекомендуется предварительно ознакомиться с результатами предыдущей работы.",
    "Предварительно проверь результат вычислений.",
    "Для проверки результата предварительно найти ответ.",          # -ти
    "Для проверки результата предварительно повторяй материал.",    # -й
    "Для сравнения результатов предварительно подготовьтесь.",
    "Для сравнения результатов предварительно сойтись во мнениях.",   # -тись
    "Для оценки результата предварительно оставь условие рядом.",    # -ь after a consonant
    # the verbs of «анализ» / «вывод» are verbs, not the nouns
    "Предварительно анализируйте условие и записывайте вывод.",
    "Для проверки результата предварительно выводите формулу.",
    "Для оценки уровня предварительно анализировать условие.",
])
def test_advice_with_the_adverb_is_kept(text):
    assert rg.drop_preliminary_sentences(text) == text
    assert rg.drop_preliminary_sentences(f"Решено 7 из 12. {text} Далее.") == f"Решено 7 из 12. {text} Далее."


@pytest.mark.parametrize("text", [
    # N5: a quoted name is not judged by its words, even when the word and a noun stand side by side
    "Уровень «Предварительная оценка» ниже нормы.",
    "Тема «Предварительные сведения» показала уровень ниже нормы.",
    # the names the deterministic summary lists, with or without a bullet in front
    "Подтверждены навыки: Предварительная оценка результатов.",
    "- Опорные навыки: Предварительная оценка результатов.",
    "• Зафиксированы ключевые затруднения: Предварительные итоги, Анализ данных.",
])
def test_quoted_names_and_listed_names_are_not_judged_by_their_words(text):
    assert rg.drop_preliminary_sentences(text) == text


@pytest.mark.parametrize("text,expected", [
    # «см.» after a number is a unit: it may end a sentence, the neighbour before it stays
    ("Рост 10 см. Оценка предварительная. Далее.", "Рост 10 см. Далее."),
    ("Рост 10см. Оценка предварительная. Далее.", "Рост 10см. Далее."),
    # «см.» as «смотри» does not end a sentence
    ("Подробности см. Рис. 3. Оценка предварительная.", "Подробности см. Рис. 3."),
    ("Уровень ниже нормы, см. Оценка предварительная. Далее.", "Далее."),
])
def test_cm_after_a_number_is_a_unit_not_an_abbreviation(text, expected):
    assert rg.drop_preliminary_sentences(text) == expected


@pytest.mark.parametrize("text,expected", [
    # a bullet or a number at the start of a line opens a sentence: the items of a list never merge
    ("Опорные навыки: Сложение\n- Оценка предварительная\n- Выводы по теме без точки",
     "Опорные навыки: Сложение\n- Выводы по теме без точки"),
    ("• Оценка предварительная\n• Опорные навыки: Сложение", "• Опорные навыки: Сложение"),
    ("* Оценка предварительная\n* Опорные навыки: Сложение", "* Опорные навыки: Сложение"),
    ("1) Оценка предварительная\n2) Опорные навыки: Сложение", "2) Опорные навыки: Сложение"),
    ("Решено 7 из 12\n1) Опорные навыки: Сложение\n2) Оценка предварительная", "Решено 7 из 12\n1) Опорные навыки: Сложение"),
    # a number before the full stop belongs to its sentence: no orphan «1.» is left when the item goes
    ("1. Оценка предварительная.\n2. Решено 7 из 12.", "2. Решено 7 из 12."),
    ("Итоги.\n1. Оценка предварительная.\n2. Решено 7 из 12.\n3. Опорные навыки: Сложение.", "Итоги.\n2. Решено 7 из 12.\n3. Опорные навыки: Сложение."),
])
def test_a_bullet_or_a_number_opens_a_new_sentence(text, expected):
    assert rg.drop_preliminary_sentences(text) == expected


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


# ── speed: an abbreviation, a unit or a line number is read from the last few characters, never the whole prefix ──

def test_a_long_run_of_initials_is_split_in_linear_time():
    text = "А. " * 7000 + "Оценка предварительная. Опорные навыки: Сложение."
    started = time.perf_counter()
    cleaned = rg.drop_preliminary_sentences(text)
    elapsed = time.perf_counter() - started
    assert cleaned == "А. " * 7000 + "Опорные навыки: Сложение."
    assert elapsed < 0.5, f"{elapsed:.3f}s for {len(text)} characters (the target is well under 0.1s)"


def test_long_numbered_and_abbreviated_text_is_cut_in_linear_time_too():
    lines = "".join(f"{n}. Тема {n}, т.е. дроби, 10 см. Далее.\n" for n in range(1, 2500))
    text = lines + "Оценка предварительная."
    started = time.perf_counter()
    cleaned = rg.drop_preliminary_sentences(text)
    elapsed = time.perf_counter() - started
    assert cleaned == lines.rstrip("\n")
    assert elapsed < 0.5, f"{elapsed:.3f}s"


def test_a_very_long_run_of_initials_does_not_turn_quadratic():
    text = "А. " * 150000 + "Оценка предварительная."
    started = time.perf_counter()
    cleaned = rg.drop_preliminary_sentences(text)
    elapsed = time.perf_counter() - started
    assert cleaned == ("А. " * 150000).rstrip()
    assert elapsed < 1.5, f"{elapsed:.3f}s for {len(text)} characters"
