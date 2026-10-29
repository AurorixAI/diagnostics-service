"""#160: nothing that identifies a person reaches an outside model.

No database, no network: the model client is replaced by a recorder (``gen`` fixture), and a source guard checks that
no other module can open a connection to a model (LESSONS_LEARNED 51: every path, one test each).
"""
from __future__ import annotations

import hashlib
import inspect
import pathlib
import re

import pytest

from src.domain import report_generator as rg
from tests.test_n03a_report import _gap_answers, gen  # noqa: F401  (gen is a fixture)

NAME = "Айбек Тестов"
PHONE_ANSWERS = [
    ("+998 90 123 45 67", "[телефон]"),
    ("мой номер 90-123-45-67, звоните", "мой номер [телефон], звоните"),
    ("998901234567", "[телефон]"),
    ("8 (999) 123-45-67", "[телефон]"),
    ("пишите на aibek.testov@mail.ru пожалуйста", "пишите на [email] пожалуйста"),
]
MATHS_UNTOUCHED = ["12", "3.14", "1000000", "12.03.2024", "10 12 14 16 18", "1 000 000 000", "x=5, y=7", "-3/4"]


# ── the name never enters the prompt ─────────────────────────────────────────────────────────────────

def test_prompt_of_a_named_student_has_no_name(gen):
    gen(_gap_answers(), weak=["G7_T9_K1"], student_name=NAME)
    assert gen.llm_calls, "the prompt was not built"
    for prompt in gen.llm_calls:
        assert "Айбек" not in prompt and "Тестов" not in prompt and NAME not in prompt
        assert "Ученик: Ученик | Заявленный класс: 8 | Код теста: T" in prompt


def test_prompt_builder_has_no_slot_for_a_name_or_other_person_identifiers():
    params = set(inspect.signature(rg._build_prompt).parameters)
    assert not {p for p in params if re.search(r"name|phone|email|contact|student_id|school|org", p)}


def test_the_user_visible_report_keeps_the_name_where_it_was(gen):
    report = gen(_gap_answers(), weak=["G7_T9_K1"], student_name=NAME)
    assert report.report_json["report_meta"]["student_name"] == NAME
    default = gen(_gap_answers(), weak=["G7_T9_K1"])
    assert default.report_json["report_meta"]["student_name"] == "Ученик"


# ── the cache key does not depend on the name, and equals the key of the unchanged prompt ───────────

def test_cache_key_is_the_same_for_any_name_and_for_the_old_default_prompt(gen):
    gen(_gap_answers(), weak=["G7_T9_K1"], student_name=NAME)
    gen(_gap_answers(), weak=["G7_T9_K1"])
    named, default = gen.llm_calls[0], gen.llm_calls[-1]
    assert named == default
    # the line the report job always produced before #160 (it never passed a name): same bytes -> same key,
    # so a paid answer stored before the change is still found
    legacy_line = "Ученик: Ученик | Заявленный класс: 8 | Код теста: T"
    assert legacy_line in named
    assert hashlib.sha256(named.encode()).hexdigest() == hashlib.sha256(default.encode()).hexdigest()


# ── free text of the student: obvious phones and e-mails are masked ─────────────────────────────────

@pytest.mark.parametrize("typed,expected", PHONE_ANSWERS)
def test_prompt_answer_masks_phones_and_emails(typed, expected):
    assert rg._prompt_answer(typed) == expected


@pytest.mark.parametrize("typed", MATHS_UNTOUCHED)
def test_prompt_answer_leaves_maths_alone(typed):
    assert rg._prompt_answer(typed) == typed


def test_phone_cut_by_the_200_char_limit_leaves_no_digits():
    out = rg._prompt_answer("а" * 195 + "+998901234567")
    assert len(out) == 200 and out.endswith("…") and not re.search(r"\d", out)


def test_masked_answers_reach_the_prompt_but_the_report_keeps_what_was_typed(gen):
    answers = _gap_answers()
    answers[0].student_answer = "мой телефон +998 90 123 45 67"
    answers[3].student_answer = "aibek@mail.ru"
    report = gen(answers, weak=["G7_T9_K1"])
    prompt = "\n".join(gen.llm_calls)
    assert "998" not in prompt and "123 45 67" not in prompt and "aibek" not in prompt and "mail.ru" not in prompt
    assert "[телефон]" in prompt and "[email]" in prompt
    shown = str([p["student_answer"] for p in report.report_json["error_patterns"]])
    assert "+998 90 123 45 67" in shown                       # the report is what the student typed


# ── source guard: the only code that can talk to a model is src/core/gemini_client.py ───────────────

def test_only_the_model_client_can_reach_an_outside_model():
    root = pathlib.Path(rg.__file__).resolve().parents[1]
    pattern = re.compile(r"import\s+(?:openai|anthropic|requests)|from\s+(?:openai|anthropic|requests)|generativeai|requests\.post|urlopen|azure_deepseek", re.I)
    hits = sorted(
        str(p.relative_to(root)) for p in root.rglob("*.py")
        if pattern.search(p.read_text(encoding="utf-8")) and p.name not in {"gemini_client.py", "config.py"}
    )
    assert hits == [], f"a new path to a model: {hits}"
    callers = sorted(
        str(p.relative_to(root)) for p in root.rglob("*.py")
        if "call_gemini(" in p.read_text(encoding="utf-8") and p.name != "gemini_client.py"
    )
    assert callers == ["domain/report_generator.py"]
