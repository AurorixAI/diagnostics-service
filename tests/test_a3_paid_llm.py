"""A3: the paid narrative model - emergency switch, no wasted calls, cache between retries.

The model client is ALWAYS replaced here: ``requests.post`` and ``google.generativeai`` are
swapped for recorders in an autouse fixture, so no test can reach the network or cost money.
The generator tests need no database; the job tests need A2_TEST_DATABASE_URL (a2_diagnostic).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import types
import uuid

import pytest

from src.core import gemini_client
from src.core.config import Settings, get_settings
from src.domain import report_generator as rg
from tests.test_n03a_report import _gap_answers, ans, gen  # noqa: F401  (gen is a fixture)

DB_URL = os.getenv("A2_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="Requires disposable A2 PostgreSQL")

SECRET_PROMPT = "PROMPT-WITH-STUDENT-ANSWERS-12345"


# ── no test can reach the network ────────────────────────────────────────────

class Wire:
    """Records every request that WOULD have been paid for."""

    def __init__(self):
        self.azure = []
        self.gemini = []
        self.azure_status = 200
        self.azure_text = "azure answer"
        self.gemini_text = "gemini answer"


@pytest.fixture(autouse=True)
def wire(monkeypatch):
    w = Wire()

    def fake_post(url, json=None, headers=None, timeout=None):
        w.azure.append({"url": url, "timeout": timeout})
        return types.SimpleNamespace(
            status_code=w.azure_status, text="x",
            json=lambda: {"choices": [{"message": {"content": w.azure_text}}]},
        )

    import requests
    monkeypatch.setattr(requests, "post", fake_post)

    class FakeModel:
        def __init__(self, model_name=None, generation_config=None):
            pass

        def generate_content(self, prompt):
            w.gemini.append(1)
            return types.SimpleNamespace(text=w.gemini_text)

    fake_genai = types.ModuleType("google.generativeai")
    fake_genai.configure = lambda **k: None
    fake_genai.GenerativeModel = FakeModel
    google = sys.modules.get("google") or types.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    monkeypatch.setattr(google, "generativeai", fake_genai, raising=False)
    yield w


def set_env(monkeypatch, *, flag=None, azure=False, gemini=False):
    for name in ("REPORT_NARRATIVE_ENABLED", "AZURE_DEEPSEEK_API_KEY", "AZURE_DEEPSEEK_ENDPOINT", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    if flag is not None:
        monkeypatch.setenv("REPORT_NARRATIVE_ENABLED", flag)
    if azure:
        monkeypatch.setenv("AZURE_DEEPSEEK_API_KEY", "k")
        monkeypatch.setenv("AZURE_DEEPSEEK_ENDPOINT", "https://azure.invalid/v1")
    if gemini:
        monkeypatch.setenv("GEMINI_API_KEY", "g")
    get_settings.cache_clear()
    return lambda: get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── B-01 / T-04: the switch, in the one place ────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (None, True), ("true", True), ("1", True), ("yes", True), ("", True), ("garbage", True),
    ("false", False), ("False", False), ("0", False), ("no", False), ("NO", False), ("off", False), (" false ", False),
])
def test_switch_parsing_default_on(monkeypatch, value, expected):
    set_env(monkeypatch, flag=value)
    assert gemini_client.narrative_enabled() is expected


def test_setting_reads_env_name():
    s = Settings(_env_file=None)
    assert s.report_narrative_enabled == "true"


@pytest.mark.parametrize("flag,azure,gemini,paid", [
    (None, True, False, ("azure", 1)),
    ("true", True, False, ("azure", 1)),
    ("false", True, False, (None, 0)),         # switch off + key present  -> 0 paid calls
    ("false", False, True, (None, 0)),
    ("0", True, True, (None, 0)),
    ("no", True, True, (None, 0)),
    ("true", False, False, (None, 0)),         # switch on + no key        -> nothing to call
    (None, False, True, ("gemini", 1)),        # Gemini fallback only
])
def test_call_gemini_flag_times_key(monkeypatch, wire, flag, azure, gemini, paid):
    set_env(monkeypatch, flag=flag, azure=azure, gemini=gemini)
    out = gemini_client.call_gemini(SECRET_PROMPT)
    kind, count = paid
    assert len(wire.azure) + len(wire.gemini) == count
    if kind == "azure":
        assert out == "azure answer" and len(wire.azure) == 1
    elif kind == "gemini":
        assert out == "gemini answer" and len(wire.gemini) == 1
    else:
        assert out is None


def test_every_paid_call_is_logged_without_prompt_or_answer(monkeypatch, wire, caplog):
    set_env(monkeypatch, azure=True, gemini=True)
    wire.azure_status = 500                              # Azure fails -> Gemini is a SECOND paid call
    with caplog.at_level(logging.INFO, logger="src.core.gemini_client"):
        gemini_client.call_gemini(SECRET_PROMPT, purpose="report_narrative")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("paid_llm_call ")]
    assert len(lines) == 2 and len(wire.azure) == 1 and len(wire.gemini) == 1
    assert "provider=azure" in lines[0] and "ok=false" in lines[0]
    assert "provider=gemini" in lines[1] and "ok=true" in lines[1]
    for line in lines:
        assert "service=diagnostic" in line and "purpose=report_narrative" in line and "model=" in line
        assert re.search(r"duration_ms=\d+", line)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert SECRET_PROMPT not in text and "gemini answer" not in text


def test_switch_off_logs_no_paid_call(monkeypatch, wire, caplog):
    set_env(monkeypatch, flag="false", azure=True)
    with caplog.at_level(logging.INFO, logger="src.core.gemini_client"):
        assert gemini_client.call_gemini(SECRET_PROMPT) is None
    assert not [r for r in caplog.records if r.getMessage().startswith("paid_llm_call service")]


# ── B-08: '//' inside a string is content ────────────────────────────────────

def test_extract_json_keeps_double_slash_inside_strings():
    raw = '{"a": "см. https://example.org/x и/или//y", "b": 1}'
    assert rg._extract_json(raw) == {"a": "см. https://example.org/x и/или//y", "b": 1}
    fenced = "```json\n" + raw + "\n```"
    assert rg._extract_json(fenced)["a"].startswith("см. https://")


def test_extract_json_still_tolerates_comments_outside_strings():
    raw = '{\n  "a": "x//y", // comment\n  "b": 2 // tail\n}'
    assert rg._extract_json(raw) == {"a": "x//y", "b": 2}
    assert rg._extract_json("not json") is None and rg._extract_json("") is None


# ── generator: valid model output, helpers ───────────────────────────────────

def valid_model_factory(calls, *, summary="Решено 2 из 11 заданий. Зафиксированы затруднения."):
    def model(prompt, *args, **kwargs):
        calls.append(1)
        status = re.search(r'СКОПИРУЙ ТОЧНО: "(\w+)"', prompt).group(1)
        score = int(re.search(r"\((\d+)%; это факт", prompt).group(1))
        goals_block = prompt.split("ДОПУСТИМЫЕ ЦЕЛИ ПЛАНА", 1)[1].split("ВЕРНИ ТОЛЬКО JSON", 1)[0]
        goals = re.findall(r"^\s+\d+\. (\S+) — (.+?) \(", goals_block, re.M)
        return json.dumps({
            "overall": {"score_percent": score, "status": status, "status_label_ru": "Уровень", "student_summary": summary},
            "action_plan": [
                {"priority": i + 1, "skill_id": sid, "skill_name_ru": name, "action_title": "Отработать тему",
                 "full_description": "Решите несколько заданий и проверьте усвоение."}
                for i, (sid, name) in enumerate(goals[:5])
            ],
        }, ensure_ascii=False)
    return model


def test_generator_flag_on_calls_the_model_and_flag_off_does_not(monkeypatch, gen):
    set_env(monkeypatch, flag=None)
    on = gen(_gap_answers(), narrative=None)
    on_calls = len(gen.llm_calls)
    assert on_calls == 2                                  # two attempts when the model returns nothing
    assert on.report_json["report_meta"]["narrative_status"] == "deterministic_fallback"

    gen.llm_calls.clear()
    set_env(monkeypatch, flag="false")
    off = gen(_gap_answers(), narrative=None)
    assert gen.llm_calls == []                            # 0 calls: the switch
    assert off.report_json["report_meta"]["narrative_status"] == "deterministic_fallback"
    assert off.report_json["action_plan"] and off.report_json["overall"]["student_summary"]
    assert off.narrative_generated is False


def test_generator_flag_off_ignores_even_a_perfect_model(monkeypatch, gen):
    calls: list = []
    set_env(monkeypatch, flag="0")
    report = gen(_gap_answers(), narrative=valid_model_factory(calls))
    assert gen.llm_calls == [] and calls == []
    assert report.narrative_generated is False


def test_generator_valid_model_marks_narrative_generated(monkeypatch, gen):
    set_env(monkeypatch)
    calls: list = []
    report = gen(_gap_answers(), narrative=valid_model_factory(calls))
    assert calls == [1]
    assert report.narrative_generated is True
    assert report.report_json["report_meta"]["narrative_status"] == "ready"


def test_double_slash_in_the_narrative_costs_one_call_not_two(monkeypatch, gen):
    set_env(monkeypatch)
    calls: list = []
    summary = "Решено 2 из 11 заданий. Подробнее https://example.org/a и/или//b."
    report = gen(_gap_answers(), narrative=valid_model_factory(calls, summary=summary))
    assert calls == [1]                                   # B-08: used to be cut, invalid JSON, a second paid call
    assert "https://example.org/a" in report.report_json["overall"]["student_summary"]


def test_degradation_is_decided_before_the_model_zero_paid_calls(monkeypatch, gen):
    set_env(monkeypatch)

    class Down:
        def get_by_id(self, node_id):
            raise ConnectionError("content-service down")

    monkeypatch.setattr(rg, "KnowledgeRepository", Down)
    report = gen(_gap_answers(), narrative=None)
    assert gen.llm_calls == []                            # B-02: 0 paid calls on degradation
    assert report.report_json["report_meta"]["degraded"]


def test_session_without_answers_makes_no_paid_call(monkeypatch, gen):
    set_env(monkeypatch)
    report = gen([], narrative=None, breakdown={"G8_T1": {"alpha": 0.0, "observations": 0}})
    assert gen.llm_calls == []
    assert report.narrative_generated is False


def test_narrative_skip_reason_priority():
    f = rg._narrative_skip_reason
    ok = dict(skip_narrative=False, error_free=False, has_answers=True, degraded=False)
    assert f(**ok) is None
    assert f(**{**ok, "skip_narrative": True}) == "deterministic_job"
    assert f(**{**ok, "error_free": True}) == "error_free"
    assert f(**{**ok, "has_answers": False}) == "no_answers"
    assert f(**{**ok, "degraded": True}) == "degraded_evidence"


# ── jobs against a disposable PostgreSQL ─────────────────────────────────────

if DB_URL:
    from tests.test_n02_db import build_report, db, make_session  # noqa: F401


@needs_db
def test_job_degraded_zero_calls_and_requeued(db, monkeypatch):
    from src.domain import report_jobs
    from src.models.diag_models import DiagReport as R

    set_env(monkeypatch)
    calls: list = []
    monkeypatch.setattr(rg, "call_gemini", lambda *a, **k: calls.append(1) or None)

    class Down:
        def get_by_id(self, node_id):
            raise ConnectionError("down")

    monkeypatch.setattr(rg, "KnowledgeRepository", Down)
    session = make_session(db)
    report_jobs.enqueue_report_generation(db, session.id)
    assert report_jobs.process_next_report_job() is False
    db.expire_all()
    row = db.query(R).one()
    assert calls == []                                    # before: 2 paid calls per attempt, up to 6 per session
    assert row.generation_status == "pending" and row.generation_stage == "retry_queued"
    assert row.narrative_cache is None


@needs_db
def test_retry_of_the_same_job_reuses_the_paid_answer(db, monkeypatch):
    from src.domain import report_jobs
    from src.models.diag_models import DiagReport as R

    set_env(monkeypatch)
    calls: list = []
    monkeypatch.setattr(rg, "call_gemini", valid_model_factory(calls))
    real = rg._finalize_action_plan
    boom = {"left": 1}

    def flaky(*a, **k):
        if boom["left"]:
            boom["left"] -= 1
            raise RuntimeError("bug after the model call")
        return real(*a, **k)

    monkeypatch.setattr(rg, "_finalize_action_plan", flaky)
    session = make_session(db)
    report_jobs.enqueue_report_generation(db, session.id)

    assert report_jobs.process_next_report_job() is False          # attempt 1: paid once, then fails
    db.expire_all()
    row = db.query(R).one()
    assert len(calls) == 1
    assert row.generation_status == "pending" and row.generation_stage == "retry_queued"
    assert row.narrative_cache and row.narrative_cache["ai_data"]["overall"]["student_summary"]
    assert "key" in row.narrative_cache and SECRET_PROMPT not in json.dumps(row.narrative_cache)

    assert report_jobs.process_next_report_job() is True           # attempt 2: cache, no new paid call
    db.expire_all()
    row = db.query(R).one()
    assert len(calls) == 1
    assert row.generation_status == "ready" and row.narrative_generated is True
    assert row.report_json["report_meta"]["narrative_status"] == "ready"
    assert row.narrative_cache is None                             # cleared once the report is current
    from sqlalchemy import text
    assert db.execute(text("SELECT narrative_cache IS NULL FROM diag_reports")).scalar() is True   # SQL NULL, not JSON null


@needs_db
def test_cache_is_ignored_when_the_inputs_changed(db, monkeypatch):
    from src.models.diag_models import DiagReport as R

    set_env(monkeypatch)
    calls: list = []
    monkeypatch.setattr(rg, "call_gemini", valid_model_factory(calls))
    session = make_session(db)
    first = build_report(db, session)
    assert len(calls) == 1 and first.narrative_cache is None
    first.narrative_cache = {"key": "0" * 64, "ai_data": {"overall": {}}}   # a cache of some other prompt
    first.report_schema_version = 0
    db.commit()
    build_report(db, session)
    assert len(calls) == 2                                         # key mismatch -> a fresh paid call


@needs_db
def test_switch_off_job_makes_zero_calls_and_still_finishes(db, monkeypatch):
    from src.domain import report_jobs
    from src.models.diag_models import DiagReport as R

    set_env(monkeypatch, flag="false", azure=True)
    calls: list = []
    monkeypatch.setattr(rg, "call_gemini", valid_model_factory(calls))
    session = make_session(db)
    report_jobs.enqueue_report_generation(db, session.id)
    assert report_jobs.process_next_report_job() is True
    db.expire_all()
    row = db.query(R).one()
    assert calls == [] and row.generation_status == "ready" and row.narrative_generated is False


def test_startup_warns_about_an_unrecognised_switch_value_and_stays_on(monkeypatch, caplog):
    set_env(monkeypatch, flag="flase")
    with caplog.at_level(logging.WARNING, logger="src.core.gemini_client"):
        assert gemini_client.warn_if_switch_unrecognised() is True
    assert any("unrecognised" in r.getMessage() and "flase" in r.getMessage() for r in caplog.records)
    assert gemini_client.narrative_enabled() is True          # still fail-open
    for ok in (None, "true", "false", "0", "no", ""):
        set_env(monkeypatch, flag=ok)
        assert gemini_client.warn_if_switch_unrecognised() is False


def test_the_paid_one_off_script_with_a_hard_coded_password_is_gone():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    assert not (root / "scripts" / "backfill_distractor_explanation.py").exists()
