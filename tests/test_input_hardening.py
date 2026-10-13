"""DIAG-6: one hostile or oversized answer must not block the service or fail grading / the report.

The diagnostic is open through a public link and grading is synchronous inside an async endpoint, so a slow comparison
stalls every session.  Before this change ``"." * 40000 + "x"`` took ~3 s in ``answers_equivalent``, ``"√(" * 20000``
~5 s in the evaluator, ``"1/" + "1" * 4301`` raised ``ValueError`` (``int`` digit limit) and ``"1" * 400 + "/1"`` raised
``OverflowError`` in the evaluator.
"""
import hashlib
import json
import logging
import pathlib
import random
import re
import sys
import time
from fractions import Fraction
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.router as api_router
from src.core.database import get_db
from src.domain import answer_evaluator, answer_value, report_generator
from src.domain.answer_evaluator import AnswerEvaluator
from src.domain.answer_value import (
    MAX_ANSWER_CHARS,
    answer_value_key,
    answers_equivalent,
    display_student_answer,
    exact_number,
    report_answer_key,
)
from src.domain.task_evidence import integrity_flags
from src.schemas.diag_schemas import SubmitAnswerRequest

# The longest choice a student can click in the bank of 12.10.2026 (a served option is sent as its full text).
LONGEST_BANK_OPTION = 1283
SLOW = 0.25                      # seconds; the quadratic cases took 0.7 s ... 24 s, linear ones need milliseconds
EV = AnswerEvaluator()
OPEN_TASK = SimpleNamespace(id="open", correct_answer="1/2", answer_type="exact_number",
                            distractor_meta=[{"value": "0.3"}], sympy_solution=None)
MCQ_TASK = SimpleNamespace(id="mcq", correct_answer=r"$x \in [1; 2]$", answer_type="mcq",
                           distractor_meta=[{"value": "3"}, {"value": "4"}], sympy_solution=None)


def pathologies(n: int) -> dict:
    return {
        "dots": "." * n + "x",
        "spaced dots": " ." * (n // 2) + "x",
        "digits": "1" * n,
        "open parens": "(" * n,
        r"\frac{": "\\frac{" * n,
        "minus": "-" * n,
        "1/": "1/" * (n // 2),
        "root signs": "√" * n,
        "pi": "π" * n,
        "spaces": "-" + " " * n + "x",
        "digit, spaces": "1" + " " * n + "x",
        "root paren": "√(" * (n // 2),
        "root paren closed": "√(" * (n // 2) + ")",
        "digits over 1": "1" * n + "/1",
        "operatorname": "\\operatorname{" + "a" * n,
        "sin subscripts": "\\sin" + "_{a}" * (n // 4),
        "caret spaces": "^" + " " * n + "x",
        "semicolons": ";" * n + "x",
        "tilde gap": "1" + "~" * n + "x",
        "latex fraction gap": "-" + " " * n + "\\frac{1}{2",
        "root spaces": "√" + " " * n + "x",
        "sqrt spaces": "\\sqrt" + " " * n + "(",
        "in spaces": "∈" + " " * n,
        "list commas": "1, " * (n // 3),
        "backslashes": "\\" * n,
        "signs": "+-" * (n // 2) + "1/2",
        "json braces": '{"a":' * (n // 5),
        "braces deep": "{" + "[" * (n - 1),
        "dollars": "$" * n,
        "braced single": "^{ " * (n // 3),
        "mixed number": "1 " * (n // 2) + "/",
    }


def public_calls() -> dict:
    return {
        "answer_value_key": answer_value_key,
        "report_answer_key": report_answer_key,
        "exact_number": exact_number,
        "answers_equivalent": lambda s: answers_equivalent(s, "1/2"),
        "answers_equivalent (wrapped)": lambda s: answers_equivalent("$" + s + "$", s),
        "display_student_answer": display_student_answer,
        "evaluate (open task)": lambda s: EV.evaluate(OPEN_TASK, s),
        "evaluate (mcq task)": lambda s: EV.evaluate(MCQ_TASK, s),
    }


def internal_calls() -> dict:
    return {
        **public_calls(),
        "_notation_key": answer_value._notation_key,
        "_normalize_number": answer_evaluator._normalize_number,
        "_preprocess_for_sympy": answer_evaluator._preprocess_for_sympy,
    }


def timed(fn, value):
    best = None
    for _ in range(2):
        started = time.perf_counter()
        fn(value)                          # must not raise either
        elapsed = time.perf_counter() - started
        best = elapsed if best is None else min(best, elapsed)
    return best


# ── the request: 422 instead of work ────────────────────────────────────────────────────────────────────────────

class _Db:
    """Stands in for the session: a request that passes validation finds no session and gets a 404."""
    def __init__(self):
        self.queries = 0

    def query(self, *_args, **_kwargs):
        self.queries += 1
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return None


@pytest.fixture
def client():
    db = _Db()
    app = FastAPI()
    app.include_router(api_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[api_router._service] = lambda: object()
    with TestClient(app) as test_client:
        test_client.db = db
        yield test_client


def post_answer(client, **body):
    payload = {"task_id": "T1", "student_answer": "1", "time_ms": 100, **body}
    return client.post("/api/v1/diagnostic/sessions/00000000-0000-0000-0000-000000000001/answer", json=payload,
                       headers={"X-Diagnostic-Invite-Code": "CODE0001"})


def test_limit_is_above_the_longest_bank_option():
    assert MAX_ANSWER_CHARS >= LONGEST_BANK_OPTION
    assert SubmitAnswerRequest.model_fields["student_answer"].metadata[0].max_length == MAX_ANSWER_CHARS


@pytest.mark.parametrize("answer", [
    "x" * (MAX_ANSWER_CHARS + 1),
    "1" * 4301,                                   # the int digit limit used to turn this into a 500
    "." * 40000 + "x",
    "√(" * 200000,
    "1" * 5_000_000,
])
def test_answer_over_the_limit_is_422_and_never_reaches_the_grader(client, answer):
    response = post_answer(client, student_answer=answer)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "student_answer"]
    assert client.db.queries == 0


def test_task_id_is_bounded_too(client):
    assert post_answer(client, task_id="T" * 129).status_code == 422
    assert client.db.queries == 0


@pytest.mark.parametrize("answer", ["", "1/2", "$x \\in [1; 2]$", "я" * LONGEST_BANK_OPTION, "x" * MAX_ANSWER_CHARS])
def test_answer_within_the_limit_is_accepted_by_validation(client, answer):
    response = post_answer(client, student_answer=answer)
    assert response.status_code == 404                 # got past validation to the handler: no such session
    assert client.db.queries == 1


# ── total functions: no ValueError / OverflowError, any length ────────────────────────────────────────────────────

@pytest.fixture
def small_int_limit():
    """Python 3.11 refuses int(str) of more than 4300 digits; 640 is the lowest limit it allows."""
    if not hasattr(sys, "set_int_max_str_digits"):
        pytest.skip("needs Python >= 3.11")
    old = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(old)


DIGIT_BOMBS = [
    "1" * 1000,
    "1" * 1000 + "/1",
    "1/" + "1" * 1000,
    "-" + "1" * 700 + " / " + "3" * 700,
    "1 " + "1" * 700 + "/" + "7",
    "0." + "1" * 1000,
    "0," + "1" * 1000,
    "1" + " 000" * 400,
    "\\frac{" + "1" * 1000 + "}{2}",
    "\\frac{1}{" + "2" * 1000 + "}",
    "3\\frac{" + "1" * 1000 + "}{2}",
]


@pytest.mark.parametrize("text", DIGIT_BOMBS)
def test_digits_beyond_the_int_limit_are_not_a_number(small_int_limit, text):
    with pytest.raises(ValueError):                    # the conversion this hardening guards against really fails here
        int("1" * 1000)
    assert exact_number(text) is None
    assert exact_number("$" + text + "$") is None
    assert answers_equivalent(text, "1/2") is False
    assert answers_equivalent("1/2", text) is False
    assert answers_equivalent(text, text) is True      # the same text is still the same answer (keys, no conversion)
    assert report_answer_key(text) == report_answer_key(text)
    assert EV.evaluate(OPEN_TASK, text) == (0.0, "wrong")
    assert EV.evaluate(MCQ_TASK, text) == (0.0, "wrong")


@pytest.mark.parametrize("text", ["1" * 4301, "1/" + "1" * 4301, "-" + "9" * 4400 + "/3", "1" * 400 + "/1", "1" * 309 + "/1"])
def test_default_limits_digit_cases_cannot_raise(text):
    """4301+ digits (ValueError in ``Fraction`` / ``int``) and a 400 digit ratio (OverflowError in ``num / den``)."""
    assert answers_equivalent(text, "1/2") is False
    assert EV.evaluate(OPEN_TASK, text) == (0.0, "wrong")
    assert EV.evaluate(MCQ_TASK, text) == (0.0, "wrong")
    assert exact_number(text) is None or len(text) <= MAX_ANSWER_CHARS


def test_ratio_that_overflows_a_float_is_not_a_number_but_ordinary_ratios_grade():
    assert answer_evaluator._normalize_number("1" * 400 + "/1") is None
    assert answer_evaluator._normalize_number("10/4") == 2.5
    task = SimpleNamespace(id="n", correct_answer="2,5", answer_type="exact_number", distractor_meta=None, sympy_solution=None)
    assert EV.evaluate(task, "10/4") == (1.0, "correct")


def test_deeply_nested_transport_dict_is_returned_unchanged():
    for text in ("{" + "[" * 1998, '{"a":' * 399, "{'a':" * 399, "{" + "(" * 1998):
        assert display_student_answer(text) == text
    assert display_student_answer("{'text': '$x$', 'is_correct': False}") == "$x$"


# ── over the limit: only ever equal to itself ───────────────────────────────────────────────────────────────────────

def test_text_over_the_limit_has_a_safe_key():
    long = "1/2" * MAX_ANSWER_CHARS
    other = long + "."
    assert answer_value_key(long) == answer_value_key(long)
    assert answer_value_key(long) != answer_value_key(other)
    assert answer_value_key(long) != answer_value_key("1/2")
    assert report_answer_key(long) == report_answer_key(long)
    assert report_answer_key(long) != report_answer_key(other)
    assert answers_equivalent(long, other) is False
    assert answers_equivalent(long, "1/2") is False
    assert exact_number("1" * (MAX_ANSWER_CHARS + 1)) is None
    # the limit itself is still an ordinary answer
    assert answer_value_key("A" * MAX_ANSWER_CHARS) == "a" * MAX_ANSWER_CHARS
    assert exact_number("1" * 1000) == Fraction(int("1" * 1000))


def test_oversize_key_survives_lone_surrogates():
    assert answer_value_key("\ud800" * (MAX_ANSWER_CHARS + 1)) == answer_value_key("\ud800" * (MAX_ANSWER_CHARS + 1))


def test_evaluator_calls_an_answer_over_the_limit_wrong_without_looking_at_it(monkeypatch, caplog):
    def not_reached(*_args):
        raise AssertionError("an oversized answer must not be compared")
    monkeypatch.setattr(answer_evaluator, "answer_value_key", not_reached)
    with caplog.at_level(logging.WARNING, logger=answer_evaluator.log.name):
        assert EV.evaluate(OPEN_TASK, "x" * (MAX_ANSWER_CHARS + 1)) == (0.0, "wrong")
    assert "answer_too_long" in caplog.text and "xxxx" not in caplog.text


# ── one failing comparison is a wrong answer, never a failed request or a failed report ──────────────────────────────

def test_exception_while_grading_is_wrong_and_the_log_has_no_answer_text(monkeypatch, caplog):
    def boom(value):
        raise ValueError(f"invalid literal for int(): {value!r}")
    monkeypatch.setattr(answer_evaluator, "_normalize_number", boom)
    with caplog.at_level(logging.WARNING, logger=answer_evaluator.log.name):
        assert EV.evaluate(OPEN_TASK, "SECRET-ANSWER 7") == (0.0, "wrong")
    assert "answer_evaluation_failed" in caplog.text
    assert "task_id=open" in caplog.text and "error_type=ValueError" in caplog.text
    assert "SECRET" not in caplog.text


def test_report_matching_survives_a_failing_comparison(monkeypatch, caplog):
    def boom(value):
        raise ValueError(f"cannot read {value!r}")
    monkeypatch.setattr(report_generator, "report_answer_key", boom)
    with caplog.at_level(logging.WARNING, logger=report_generator.log.name):
        assert report_generator._find_matching_distractor([{"value": "1"}], "SECRET-ANSWER") is None
        assert report_generator._student_answer_latex("SECRET-ANSWER", [("1", "$1$")]) is None
    assert caplog.text.count("report_answer_compare_failed") == 2
    assert "SECRET" not in caplog.text


def test_integrity_flags_ignore_an_unreadable_stored_answer(monkeypatch):
    old = {"correct_answer": "2", "display_options": ["1", "2"], "question_text": "q"}
    new = {"correct_answer": "2", "question_text": "q"}
    calls = []

    real = answer_value.report_answer_key

    def boom(value):
        calls.append(value)
        if value == "SECRET-ANSWER":
            raise RecursionError("boom")
        return real(value)
    monkeypatch.setattr("src.domain.answer_value.report_answer_key", boom)
    assert integrity_flags(old, new, "SECRET-ANSWER", 0.0) == []
    assert "SECRET-ANSWER" in calls


@pytest.mark.parametrize("stored", ["." * 40000 + "x", "1" * 5000, "{" + "[" * 1998, "√(" * 20000, "1/" + "1" * 4301])
def test_report_builds_with_a_hostile_stored_answer(monkeypatch, stored):
    """Journal rows written before the limit may hold anything; the report still gets its context."""
    task_payload = {
        "question_text": "Решите x/2 = 1", "question_latex": None, "answer_type": "mcq", "correct_answer": "2",
        "correct_answer_latex": "$2$", "answer_options": ["2", "1"],
        "distractor_meta": [{"value": "1", "value_latex": "$1$", "error_logic": "Не умножили."}],
    }
    from src.clients import content_client
    from src.domain.task_evidence import capture_task
    monkeypatch.setattr(content_client, "get", lambda _: SimpleNamespace(status_code=200, json=lambda: task_payload))
    answer = SimpleNamespace(task_id="task-1", skill_id="skill-1", student_answer=stored, outcome=0.0,
                             eval_category="wrong", answered_at=None, id=1)
    pairs = report_generator._task_option_pairs(task_payload, "2", "$2$")
    answer.task_snapshot = capture_task(SimpleNamespace(id="task-1", **task_payload), [p[0] for p in pairs],
                                        [p[1] for p in pairs], "mcq")
    started = time.perf_counter()
    pattern = report_generator._build_error_patterns([answer], {"skill-1": {"name_ru": "Навык"}})[0]
    assert time.perf_counter() - started < SLOW
    assert pattern["answer_options"] == ["2", "1"]            # the context was not thrown away
    assert pattern["correct_answer"] == "2"
    assert pattern["distractor_explanation"] is None and pattern["student_answer_latex"] is None


# ── timing: every text-matching helper stays fast and linear on the pathological shapes ────────────────────────────

@pytest.mark.parametrize("size", [20000, 40000])
def test_public_helpers_return_quickly_on_pathological_answers(size):
    slow = []
    for pname, text in pathologies(size).items():
        for fname, fn in public_calls().items():
            elapsed = timed(fn, text)
            if elapsed > SLOW:
                slow.append((fname, pname, round(elapsed, 3)))
    assert not slow


@pytest.mark.parametrize("size", [20000, 40000])
def test_regexes_are_linear_even_without_the_length_limit(monkeypatch, size):
    """The limit is a bound, not the fix: with it lifted every helper must still be linear on these shapes."""
    monkeypatch.setattr(answer_value, "MAX_ANSWER_CHARS", 10 ** 9)
    monkeypatch.setattr(answer_evaluator, "MAX_ANSWER_CHARS", 10 ** 9)
    slow = []
    for pname, text in pathologies(size).items():
        for fname, fn in internal_calls().items():
            elapsed = timed(fn, text)
            if elapsed > SLOW:
                slow.append((fname, pname, round(elapsed, 3)))
    assert not slow


def test_answers_at_the_limit_stay_fast():
    slow = []
    for pname, text in pathologies(MAX_ANSWER_CHARS).items():
        text = text[:MAX_ANSWER_CHARS]
        for fname, fn in public_calls().items():
            elapsed = timed(fn, text)
            if elapsed > 0.05:
                slow.append((fname, pname, round(elapsed, 3)))
    assert not slow


# ── the rewritten pieces equal the regexes they replace ───────────────────────────────────────────────────────────

def test_trailing_punctuation_strip_equals_the_old_regex():
    old = re.compile(r"[\s.;]+$")
    assert [c for c in range(sys.maxunicode + 1) if bool(re.match(r"\s", chr(c))) != chr(c).isspace()] == []
    rnd = random.Random(1)
    alphabet = [" ", ".", ";", "\n", "a", "1", " ", "\t", "\x1c", " ", "$"]
    for _ in range(20000):
        text = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 9)))
        assert answer_value._strip_trailing_punct(text) == old.sub("", text), repr(text)


def test_mixed_latex_regex_matches_what_the_old_one_matched():
    old = re.compile(r"(-?)\s*(\d+)?\s*\\frac\{\s*(-?\d+)\s*\}\{\s*(\d+)\s*\}")
    rnd = random.Random(2)
    tokens = ["-", " ", "1", "23", "\\frac{", "}", "{", "-4", "x", "\\", "frac", "5", "\t", "\n", " "]
    for _ in range(30000):
        text = "".join(rnd.choice(tokens) for _ in range(rnd.randint(0, 12)))
        for method in ("fullmatch", "search"):
            before, after = getattr(old, method)(text), getattr(answer_value._MIXED_LATEX_RE, method)(text)
            assert (before is None) == (after is None), repr(text)
            if before:
                assert before.groups() == after.groups() and before.span() == after.span(), repr(text)


def test_sqrt_parentheses_rewrite_equals_the_old_regex():
    rnd = random.Random(3)
    tokens = ["√(", "√", "(", ")", "a", "1", "x+1", "\n", "√()", "((", "))", " "]
    for _ in range(30000):
        text = "".join(rnd.choice(tokens) for _ in range(rnd.randint(0, 10)))
        assert answer_evaluator._sqrt_parentheses_to_call(text) == re.sub(r"√\(([^)]+)\)", r"sqrt(\1)", text), repr(text)


# ── regression: the verdicts of the bank do not move ──────────────────────────────────────────────────────────────

GOLDEN = json.loads((pathlib.Path(__file__).parent / "fixtures" / "answer_value_golden.json").read_text(encoding="utf-8"))


def short(key: str) -> str:
    return key if len(key) <= 40 else "sha1:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


@pytest.mark.parametrize("case", GOLDEN["tasks"], ids=[t["id"] for t in GOLDEN["tasks"]])
def test_bank_verdicts_equal_those_before_the_hardening(case):
    """The key, every distractor and every served choice (with and without ``$``) of 79 bank tasks.

    ``answer_value_golden.json`` was produced by the code of 119700c (before DIAG-6) from the active bank of
    12.10.2026; the whole bank (34 606 tasks, 397 103 answers, 2.1 M pairs) was compared the same way, 0 differences.
    """
    task = SimpleNamespace(id=case["id"], correct_answer=case["correct_answer"], answer_type=case["answer_type"],
                           sympy_solution=case["sympy_solution"],
                           distractor_meta=[{"value": v} for v in case["distractor_values"]])
    variants = case["variants"]
    equal_pairs = set()
    for index, text in enumerate(variants):
        assert list(EV.evaluate(task, text)) == case["eval"][index], text
        assert short(answer_value_key(text)) == case["key"][index], text
        assert short(report_answer_key(text)) == case["rkey"][index], text
        number = exact_number(text)
        assert (None if number is None else str(number)) == case["num"][index], text
    for i in range(len(variants)):
        for j in range(i + 1, len(variants)):
            if answers_equivalent(variants[i], variants[j]):
                equal_pairs.add((i, j))
    assert equal_pairs == {tuple(pair) for pair in case["equal_pairs"]}
