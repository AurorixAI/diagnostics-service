"""N03b-2 R3: the bank budget and the stop after the first failure (M1), the model's numbers (M2), the plan texts (m1-m3), a cut-off answer (m5),
the real state adapter over HTTP (m6), a journal row without a topic.  No database, no real bank, no paid model."""
import json
import logging
from types import SimpleNamespace as NS

import httpx
import pytest

from src.core import gemini_client
from src.domain import report_generator as rg
from src.domain import report_plan as rp
from tests.fake_content import Response
from tests.test_n03b2_report_content import (  # noqa: F401  (fixtures)
    Bank, SKILLS, _errors_in_many_skills, _valid_answer, a, bank, gen, wrongs,
)

# captured at import: the conftest fixture replaces the module attribute for every test, these are the real functions
REAL_IS_ACTIVE = rp.bank_task_is_active


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(rp, "_now", c)
    return c


# ── M1: the budget, the stop after the first failure, the cache ────────────────

def test_a_hanging_bank_costs_one_read_not_one_per_task(clock):
    calls = []

    def hang(task_id):
        calls.append(task_id)
        clock.t += 33                       # a read that times out after the client's retries
        raise httpx.ReadTimeout("hung")

    reader = rp.BankReader(is_active=hang, unused=lambda *a, **k: calls.append("tasks") or [])
    withdrawn, unread = rp.find_withdrawn_tasks([f"T{i}" for i in range(20)], reader)
    assert calls == ["T0"] and reader.failure == "unreachable" and reader.reads == 1
    assert withdrawn == set() and len(unread) == 20                   # all unread, none "withdrawn"
    assert reader.unused_tasks("S", []) is None and calls == ["T0"]   # no read of any kind after the first failure
    assert clock.t == 33


def test_a_slow_bank_is_cut_by_the_budget_of_the_whole_report(clock):
    calls = []

    def slow(task_id):
        calls.append(task_id)
        clock.t += 25
        return True

    reader = rp.BankReader(is_active=slow, budget_s=60)
    withdrawn, unread = rp.find_withdrawn_tasks([f"T{i}" for i in range(10)], reader)
    assert len(calls) == 3 and reader.failure == "budget"             # reads at 0, 25, 50 s; the one at 75 s is refused
    assert len(unread) == 7 and clock.t == 75
    assert rp.BANK_BUDGET_S < 600                                      # well below report_jobs.STALE_GENERATING_AFTER (10 min)


def test_identical_reads_are_made_once():
    calls = []
    reader = rp.BankReader(is_active=lambda t: calls.append(t) or True,
                           unused=lambda skill, exclude, hardest_first=False: calls.append(skill) or [{"task_id": "x"}])
    assert reader.task_is_active("a") and reader.task_is_active("a")
    assert reader.unused_tasks("S", ["b", "a"]) == reader.unused_tasks("S", ["a", "b"])
    assert calls == ["a", "S"]


def test_report_build_with_a_hanging_bank_stays_in_the_budget_and_builds_no_material(gen, bank, clock):
    bank.on_status = lambda: setattr(clock, "t", clock.t + 30)
    bank.down_status = True
    report = gen(_errors_in_many_skills())                             # 8 wrong answers on 7 skills
    rj = report.report_json
    assert bank.status_calls == 1 and bank.asked == []                 # the first failure stopped everything
    assert clock.t == 30
    assert rj["report_meta"]["degraded"] == ["task_status"] and report.report_schema_version == 0
    assert gen.calls == []                                             # nothing to word, nothing paid
    for step in rj["action_plan"]:
        assert step["evidence"] and step["material"] is None and step["check"] is None   # not "a task at the lesson"


def test_a_bank_that_fails_on_the_first_task_read_stops_the_other_reads(gen, bank):
    bank.down_tasks = True
    bank.add("G8_T1_K1", 5).add("G8_T1_K2", 5)
    rj = gen(wrongs("G8_T1_K1", 1) + wrongs("G8_T1_K2", 1)).report_json
    assert bank.asked == [] and rj["report_meta"]["degraded"] == ["bank_tasks"]    # the 1st read raised; the 2nd skill was not asked
    assert all(s["material"] is None for s in rj["action_plan"])


# ── M2: the numbers of the model ────────────────────────────────────────────────

def _worded(gen, descriptions):
    """Report of two skills (G8_T1_K1: 2 errors = journal №1, №2; G8_T2_K1: 1 error = №3); the model words each step with ``descriptions``."""
    answers = wrongs("G8_T1_K1", 2) + wrongs("G8_T2_K1", 1)
    base = gen(answers, narrative=None).report_json
    ok = _valid_answer({"G8_T1_K1": "Навык 1.1", "G8_T2_K1": "Навык 2.1"})
    ok["overall"]["score_percent"], ok["overall"]["status"] = base["overall"]["score_percent"], base["overall"]["status"]
    for item, text in zip(ok["action_plan"], descriptions):
        item["action_title"], item["full_description"] = "Тема", text
    before = len(gen.calls)
    rj = gen(answers, narrative=json.dumps(ok, ensure_ascii=False)).report_json
    assert len(gen.calls) == before + 1                                  # ONE paid call: a rejected step text is not asked again
    return base, rj


@pytest.mark.parametrize("bad,reason", [
    ("Решить 3 из 4 заданий подряд.", "N-of-M"),
    ("Решить 3/4 заданий подряд.", "N-of-M"),
    ("Освоено на 85 % и выше.", "percent"),
    ("Разобрать ошибку в задании №9.", "№9"),                           # the skill has rows №1 and №2
    ("Решить 40 заданий.", "numbers that are not in the data"),
    ("Доля верных около 0,6.", "numbers that are not in the data"),
])
def test_a_step_text_with_an_invented_number_keeps_the_wording_of_the_data(gen, caplog, bad, reason):
    caplog.set_level(logging.WARNING)
    base, rj = _worded(gen, [bad, "Разобрать ошибки и закрепить правило."])
    first, second = rj["action_plan"]
    assert first["source"] == "deterministic_fallback" and first["full_description"] == base["action_plan"][0]["full_description"]
    assert second["source"] == "ai" and second["full_description"] == "Разобрать ошибки и закрепить правило."   # the rest of the answer is used
    assert rj["report_meta"]["narrative_source"] == "ai"
    assert any("is not used" in r.getMessage() and reason in r.getMessage() for r in caplog.records)         # the reason is in the log
    assert first["evidence"] == base["action_plan"][0]["evidence"]


def test_numbers_that_are_in_the_data_of_the_step_are_allowed(gen):
    # journal rows №1 and №2 of the skill, its two errors, the number in its name
    _, rj = _worded(gen, ["Разобрать ошибки в заданиях №1 и №2 (всего 2 ошибки) и навык 1.1.", "Разобрать №3."])
    assert [s["source"] for s in rj["action_plan"]] == ["ai", "ai"]


def test_a_hostile_answer_for_every_step_gives_the_plan_of_the_data_without_the_model_text(gen):
    base, rj = _worded(gen, ["освоено на 85 %", "решить 3 из 4"])
    assert rj["action_plan"] == base["action_plan"]
    assert not any("85" in s or "3 из 4" in s for s in rg._all_strings(rj["action_plan"]))


# ── m5: a cut-off answer is not asked again ─────────────────────────────────────

def test_a_cut_off_answer_is_not_repeated_and_the_wording_stays_with_the_data(gen, caplog):
    caplog.set_level(logging.WARNING)
    answers = wrongs("G8_T1_K1", 2)
    base = gen(answers, narrative=None).report_json
    before = len(gen.calls)
    cut = gemini_client.TruncatedText('{"overall": {"status": "below_level", "student_su')
    rj = gen(answers, narrative=cut).report_json
    assert len(gen.calls) == before + 1                                   # one call, not two
    assert rj["report_meta"]["narrative_source"] == "ai_failed" and rj["action_plan"] == base["action_plan"]
    assert any("cut off at max_tokens" in r.getMessage() and str(rg.NARRATIVE_MAX_TOKENS) in r.getMessage() for r in caplog.records)


def test_the_azure_client_marks_an_answer_that_hit_the_ceiling(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    settings = NS(report_narrative_enabled="true", azure_deepseek_api_key="k", azure_deepseek_endpoint="http://azure.invalid",
                  azure_deepseek_model="m", gemini_api_key="")
    monkeypatch.setattr(gemini_client, "get_settings", lambda: settings)
    body = {"choices": [{"message": {"content": '{"a": "cut'}, "finish_reason": "length"}], "usage": {"completion_tokens": 6000}}
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: NS(status_code=200, json=lambda: body, text=""))
    text = gemini_client.call_gemini("p", max_tokens=6000)
    assert text == '{"a": "cut' and getattr(text, "truncated", False) is True
    assert any("completion_tokens=6000" in r.getMessage() for r in caplog.records)
    body["choices"][0]["finish_reason"] = "stop"
    assert getattr(gemini_client.call_gemini("p", max_tokens=6000), "truncated", False) is False


# ── m6: the real state adapter over HTTP ────────────────────────────────────────

@pytest.fixture
def http(monkeypatch):
    """What content-service answers to GET /tasks/{id}; the conftest substitute of the adapter does not apply to REAL_IS_ACTIVE."""
    from src.repositories import knowledge_repo

    answer = {}

    def get_task(task_id):
        what = answer["what"]
        if isinstance(what, Exception):
            raise what
        return what

    monkeypatch.setattr(knowledge_repo.content_client, "get_task", get_task)
    return answer


def test_the_real_state_adapter_reads_404_inactive_active_5xx_and_timeouts(http):
    http["what"] = Response({"detail": "nf"}, 404)
    assert REAL_IS_ACTIVE("T") is False                                    # gone from the bank = withdrawn
    http["what"] = Response({"task_id": "T", "is_active": False})
    assert REAL_IS_ACTIVE("T") is False
    http["what"] = Response({"task_id": "T", "is_active": True})
    assert REAL_IS_ACTIVE("T") is True
    http["what"] = Response({"detail": "boom"}, 503)
    with pytest.raises(Exception):
        REAL_IS_ACTIVE("T")                                                # unknown, not withdrawn
    http["what"] = httpx.ReadTimeout("hung")
    with pytest.raises(httpx.ReadTimeout):
        REAL_IS_ACTIVE("T")


def test_a_5xx_or_a_timeout_of_the_real_adapter_is_unread_not_withdrawn(http):
    for failure in (Response({}, 500), httpx.ConnectTimeout("t")):
        http["what"] = failure
        withdrawn, unread = rp.find_withdrawn_tasks(["A", "B"], rp.BankReader(is_active=REAL_IS_ACTIVE))
        assert withdrawn == set() and unread == ["A", "B"]


# ── the map: a row without a topic ──────────────────────────────────────────────

def test_an_answer_without_a_topic_goes_to_the_bucket_without_topic_not_into_the_void():
    rows = [NS(topic_id=None, skill_id=None, outcome=0, is_deep_scan=False), NS(topic_id="G8_T1", skill_id="x", outcome=1, is_deep_scan=False),
            NS(topic_id="", skill_id="G8_T1_K1", outcome=0, is_deep_scan=False)]
    got = rp.build_checked_topics(rows, {"G8_T1": {"name_ru": "Тема 1"}, "G8_T1_K1": {"name_ru": "Навык"}})
    assert [(t["topic_name_ru"], t["checked"], t["errors"]) for t in got] == [("Без темы", 1, 1), ("Тема 1", 1, 0), ("Навык", 1, 1)]
    assert sum(t["checked"] for t in got) == 3 and got[0]["topic_id"] is None


# ── m1-m3: the texts and the basis ──────────────────────────────────────────────

def _item(kind):
    return {"skill_id": "R", "skill_name_ru": "Корень", "errors": 1, "rows": [{"journal_no": 1}], "evidence_kind": kind, "prerequisite_of": "S"}


def test_start_here_is_said_of_the_first_step_only():
    names = {"S": "Исходный"}
    first = rp.deterministic_description(_item(rp.KIND_CONFIRMED_PREREQUISITE), names, first=True)
    later = rp.deterministic_description(_item(rp.KIND_CONFIRMED_PREREQUISITE), names, first=False)
    assert "с него следует начать" in first and "с него следует начать" not in later
    assert "подтверждённый пререквизит навыка «Исходный»" in later


def test_more_than_five_wrong_answers_keep_the_count_and_quote_five(gen):
    rj = gen(wrongs("G8_T1_K1", 7)).report_json
    (step,) = rj["action_plan"]
    assert step["errors_count"] == 7 and len(step["evidence"]) == rp.EVIDENCE_MAX == 5
