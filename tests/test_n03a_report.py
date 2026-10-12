"""N03a (owner decision O4): what a diagnostic report must NOT claim, and the plan contract.

No database and no model call: the generator runs against a fake session.
Covers: no reliability percentage / class equivalent / invented durations, one
``recommended_start`` equal to the first plan step, the error-free scenario,
attempt date vs build date, and stripping of retired fields from stored reports.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace as NS
import uuid

import pytest

from src.domain import report_generator as rg
from src.models.diag_models import DiagAnswer

T0 = datetime(2026, 10, 1, 10, 0, 0)

NODES = {
    "G8_T1": NS(id="G8_T1", level="L2", parent_id="G8_S", name_ru="Дроби"),
    "G8_T2": NS(id="G8_T2", level="L2", parent_id="G8_S", name_ru="Степени"),
    "G8_T3": NS(id="G8_T3", level="L2", parent_id="G8_S", name_ru="Уравнения"),
    "G8_T1_K1": NS(id="G8_T1_K1", level="L4", parent_id="G8_T1", name_ru="Сложение дробей"),
    "G8_T2_K1": NS(id="G8_T2_K1", level="L4", parent_id="G8_T2", name_ru="Свойства степеней"),
    "G8_T3_K1": NS(id="G8_T3_K1", level="L4", parent_id="G8_T3", name_ru="Линейные уравнения"),
    "G7_T9_K1": NS(id="G7_T9_K1", level="L4", parent_id=None, name_ru="Сравнение дробей"),
    "G8_S": NS(id="G8_S", level="L1", parent_id=None, name_ru="Алгебра"),
}


def ans(skill, topic, outcome, minute, *, deep=False, origin=None, step=None):
    return NS(
        id=f"a{minute:03d}", session_id=None, task_id=f"T{minute}", skill_id=skill, topic_id=topic,
        outcome=outcome, is_deep_scan=deep, phase="deep_scan" if deep else "navigation",
        eval_category="correct" if outcome else "wrong", student_answer="1" if outcome else "0",
        answered_at=T0 + timedelta(minutes=minute), time_ms=1000,
        deep_scan_origin_skill_id=origin, deep_scan_step=step, task_snapshot=None, ai_evaluated=False,
    )


class FakeQuery:
    def __init__(self, rows=(), value=None):
        self.rows, self.value = list(rows), value

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        return self

    def all(self):
        return list(self.rows)

    def scalar(self):
        return self.value


class FakeDB:
    def __init__(self, answers, completed_at=None):
        self.answers, self.completed_at, self.added = answers, completed_at, []

    def query(self, entity):
        return FakeQuery(self.answers) if entity is DiagAnswer else FakeQuery(value=self.completed_at)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, _obj):
        pass

    def rollback(self):
        pass


@pytest.fixture
def gen(monkeypatch):
    calls = []

    class FakeKnowledge:
        def get_by_id(self, node_id):
            return NODES.get(node_id)

    class FakeReports:
        def __init__(self, _db):
            pass

        def get_by_session(self, _sid):
            return None

    monkeypatch.setattr(rg, "KnowledgeRepository", FakeKnowledge)
    monkeypatch.setattr(rg, "DiagReportRepository", FakeReports)
    monkeypatch.setattr(rg, "_load_task_context", lambda answer: (None, "unavailable"))

    def run(answers, *, narrative=None, weak=(), breakdown=None, completed_at=None, theta=0.3, se=0.3, **kw):
        def fake_llm(prompt, **_k):
            calls.append(prompt)
            return narrative(prompt) if callable(narrative) else narrative

        monkeypatch.setattr(rg, "call_gemini", fake_llm)
        topics = breakdown if breakdown is not None else {
            "G8_T1": {"alpha": 0.2, "observations": 3},
            "G8_T2": {"alpha": 0.8, "observations": 3},
            "G8_T3": {"alpha": 0.4, "observations": 3},
        }
        db = FakeDB(answers, completed_at)
        report = rg.generate_and_save_report(
            db, session_id=uuid.uuid4(), student_id=uuid.uuid4(), grade_level=8, theta=theta,
            theta_se=se, overall_level="at_grade", topic_breakdown=topics, weak_skills=list(weak),
            items_total=len(answers), student_name="Ученик", test_code="T", **kw,
        )
        assert report is not None and report.report_json, "report was not built"
        return report

    run.llm_calls = calls
    return run


def _gap_answers():
    """T1: wrong twice (Deep Scan confirms a prerequisite); T2: correct; T3: wrong."""
    return [
        ans("G8_T1_K1", "G8_T1", 0, 1),
        ans("G7_T9_K1", "G8_T1", 0, 2, deep=True, origin="G8_T1_K1", step=1),
        ans("G8_T2_K1", "G8_T2", 1, 3),
        ans("G8_T3_K1", "G8_T3", 0, 4),
        ans("G8_T1_K1", "G8_T1", 0, 5),
    ]


# ── O4: retired claims never appear ───────────────────────────────────────────

def test_schema_version_is_bumped_for_the_contract_change():
    assert rg.REPORT_SCHEMA_VERSION == 5


def test_report_has_no_reliability_percent_no_class_equivalent_no_hours(gen):
    report = gen(_gap_answers(), weak=["G7_T9_K1"])
    rj = report.report_json
    assert "confidence_of_diagnosis" not in rj["overall"]
    assert "class_equivalent" not in rj["overall"] and "class_equivalent" not in rj["level"]
    assert rj["action_plan"] and all("estimated_hours" not in step for step in rj["action_plan"])
    text = str(rj).lower()
    assert not rg._CLASS_EQUIVALENT_RE.search(text)
    assert "надёжност" not in text and "reliab" not in text
    # the level band itself is kept
    assert rj["overall"]["status_label_ru"] and rj["level"]["status"] and rj["level"]["category"]
    assert "Результат измерения: «" in rj["overall"]["student_summary"]


def test_narrative_hours_are_dropped_and_the_plan_starts_at_the_recommended_start(gen):
    answers = _gap_answers()
    first = gen(answers, weak=["G7_T9_K1"], narrative=None).report_json
    candidates = [step["skill_id"] for step in first["action_plan"]]
    assert len(candidates) >= 3, candidates

    # the narrative puts the first target LAST and adds hours: both must be corrected
    shuffled = candidates[1:] + candidates[:1]
    # status/score must match the deterministic values for the narrative to validate
    status, score = first["overall"]["status"], first["overall"]["score_percent"]

    def narrative(_prompt):
        import json
        names = {step["skill_id"]: step["skill_name_ru"] for step in first["action_plan"]}
        return json.dumps({
            "overall": {"status": status, "score_percent": score, "student_summary": "Текст."},
            "action_plan": [
                {"priority": i, "skill_id": sid, "skill_name_ru": names[sid], "action_title": "Тема",
                 "full_description": "Практика. Рекомендуемое количество часов: 4 часа.", "estimated_hours": 4}
                for i, sid in enumerate(shuffled, 1)
            ],
        }, ensure_ascii=False)

    rj = gen(answers, weak=["G7_T9_K1"], narrative=narrative).report_json
    plan = rj["action_plan"]
    assert rj["report_meta"]["narrative_status"] == "ready"
    assert [step["skill_id"] for step in plan][0] == candidates[0]
    assert [step["priority"] for step in plan] == list(range(1, len(plan) + 1))
    assert all("estimated_hours" not in step for step in plan)
    assert all("часов" not in step["full_description"] for step in plan)


def test_finalize_inserts_the_first_target_when_the_narrative_plan_lacks_it():
    candidates = [{"skill_id": f"S{i}", "skill_name_ru": f"Навык {i}", "evidence": "observed_error"}
                  for i in range(1, 6)]

    def step(i, sid):
        return {"priority": i, "skill_id": sid, "skill_name_ru": f"Навык {sid[1:]}", "action_title": "Тема",
                "full_description": "Практика.", "estimated_hours": 2}

    plan = rg._finalize_action_plan([step(1, "S3"), step(2, "S4"), step(3, "S5")], candidates)
    assert [s["skill_id"] for s in plan] == ["S1", "S3", "S4", "S5"]
    assert [s["priority"] for s in plan] == [1, 2, 3, 4]
    assert plan[0]["source"] == "deterministic_fallback" and "estimated_hours" not in plan[1]

    full = rg._finalize_action_plan([step(i, f"S{i}") for i in (2, 3, 4, 5, 6)], candidates)
    assert len(full) == 5 and full[0]["skill_id"] == "S1"            # the compact plan stays compact

    assert rg._finalize_action_plan([], []) == []


def test_one_recommended_start_equals_first_plan_step_and_column(gen):
    report = gen(_gap_answers(), weak=["G7_T9_K1"])
    rj = report.report_json
    start, first = rj["recommended_start"], rj["action_plan"][0]
    assert start["skill_id"] == first["skill_id"] == report.recommended_start
    assert start["skill_name_ru"] == first["skill_name_ru"]
    assert start["evidence"] == "confirmed_prerequisite"
    # a confirmed prerequisite outranks the first Deep Scan id in session.weak_skills order
    assert first["skill_id"] == "G7_T9_K1"


def test_recommended_start_is_not_the_session_weak_skills_head_when_the_plan_ranks_otherwise(gen):
    # weak_skills lists an id that is NOT the best-ranked plan target
    report = gen(_gap_answers(), weak=["G8_T3_K1", "G7_T9_K1"])
    rj = report.report_json
    assert report.recommended_start == rj["action_plan"][0]["skill_id"] == rj["recommended_start"]["skill_id"]


def test_validator_rejects_class_equivalent_and_reliability_in_the_narrative():
    allowed = {"G8_T1": "Дроби"}

    def check(summary):
        data = {
            "overall": {"status": "below_level", "score_percent": 30, "student_summary": summary},
            "action_plan": [{"priority": 1, "skill_id": "G8_T1", "skill_name_ru": "Дроби",
                             "action_title": "Тема", "full_description": "Практика."}],
        }
        return rg._validate_ai_output(data, computed_status="below_level", score_pct=30, allowed_plan_skills=allowed)

    assert check("Ученик работает на уровне, ниже заявленного.")[0]
    for bad in ("Уровень — середина 7 класса.", "Это начало 8 класса.", "В конце 9 класса.",
                "Надёжность диагноза 84%."):
        valid, errors = check(bad)
        assert not valid and errors, bad


def _narrative(summary, *, description="Практика.", label="Ниже уровня класса"):
    return {
        "overall": {"status": "below_level", "score_percent": 30, "status_label_ru": label,
                    "student_summary": summary},
        "action_plan": [{"priority": 1, "skill_id": "G8_T1", "skill_name_ru": "Дроби",
                         "action_title": "Тема", "full_description": description}],
    }


def _validate(data):
    return rg._validate_ai_output(data, computed_status="below_level", score_pct=30,
                                  allowed_plan_skills={"G8_T1": "Дроби"})


@pytest.mark.parametrize("bad", [
    "Уровень — конец седьмого класса.",                    # number word (was missed)
    "Соответствует концу седьмого класса.",
    "Это НАЧАЛО ВОСЬМОГО КЛАССА.",                         # case-insensitive
    "Ориентир: середина девятого класса.",
    "Уровень на конец 10-го класса.",
    "Надёжность 83%.",                                     # without «диагноза» (was missed)
    "Надежность результата составляет 83 %.",
    "Надёжность диагностики — 0,83.",
    "Диагноз с надёжностью 83 процента.",
    "Надёжность диагноза высокая.",
    "Результат подтверждён с 83% надёжностью.",
])
def test_validator_catches_class_equivalent_and_reliability_variants(bad):
    valid, errors = _validate(_narrative(bad))
    assert not valid and errors, bad


@pytest.mark.parametrize("bad_label", ["Конец 7 класса", "Надёжность 83%"])
def test_validator_checks_the_level_label_too(bad_label):
    assert not _validate(_narrative("Текст.", label=bad_label))[0]


@pytest.mark.parametrize("good", [
    "Решено верно 3 из 10 заданий (30%), затруднения в дробях.",
    "Ученик уверенно решает задания на сложение дробей.",
    "Тему изучают в седьмом классе, ученику доступен материал 8 класса.",
    "Уровень диагностики подтверждён тремя заданиями из 10 (30%).",
])
def test_validator_accepts_ordinary_level_prose(good):
    assert _validate(_narrative(good))[0], good


def test_validator_does_not_reject_curriculum_references_in_the_plan():
    # «в конце 7 класса изучают …» is a legitimate reference outside the level statement
    data = _narrative("Ученик допускает ошибки в сложении дробей.",
                      description="Повторите правило: в конце 7 класса изучают сложение дробей; надёжность метода 100%.")
    assert _validate(data) == (True, [])
    data["action_plan"][0]["action_title"] = "Тема 7 класса"
    assert _validate(data)[0]


def test_retired_claim_detector_on_plain_text():
    assert rg.contains_retired_claim("конец 7 класса (заявлен 8)")
    assert rg.contains_retired_claim("Надёжность диагноза 83%")
    assert not rg.contains_retired_claim("Результат измерения: «ниже уровня класса».")
    assert not rg.contains_retired_claim(None) and not rg.contains_retired_claim(5)


# ── Zero-error student ────────────────────────────────────────────────────────

def _clean_answers():
    return [
        ans("G8_T1_K1", "G8_T1", 1, 1), ans("G8_T2_K1", "G8_T2", 1, 2),
        ans("G8_T3_K1", "G8_T3", 1, 3), ans("G8_T2_K1", "G8_T2", 1, 4),
    ]


def test_error_free_report_shows_achievements_and_a_development_step_without_deficit(gen):
    report = gen(_clean_answers(), theta=1.2, se=0.25, narrative="{}")
    rj = report.report_json
    assert rj["report_meta"]["error_free"] is True
    # the correction prompt is never sent for a student with nothing to correct
    assert gen.llm_calls == []
    assert rj["report_meta"]["narrative_status"] == "deterministic_fallback"

    achieved = {a["skill_id"] for a in rj["achievements"]}
    assert achieved == {"G8_T1", "G8_T2", "G8_T3"}
    assert rj["achievements"][0]["skill_id"] == "G8_T2"          # most correct answers first

    # no invented deficit
    assert rj["error_patterns"] == [] and rj["critical_gaps"] == [] and rj["weak_skills"] == []
    assert rj["root_cause_chains"] == []
    assert rj["diagnostic_boundary"]["breakpoint_skills"] == []
    summary = rj["overall"]["student_summary"]
    assert "затруднения не зафиксированы" in summary and "Подтверждены навыки" in summary
    assert "Следующий шаг — развитие" in summary
    assert "коррекц" not in summary.lower() and "первопричин" not in summary.lower()

    # ... but a next development step, which is also the one recommended start
    plan = rj["action_plan"]
    assert len(plan) == 1 and plan[0]["kind"] == "development" and "estimated_hours" not in plan[0]
    assert "дефицит не выявлен" in plan[0]["full_description"]
    assert plan[0]["skill_id"] == "G8_T1"                        # lowest mastery among the verified topics
    assert rj["recommended_start"]["skill_id"] == plan[0]["skill_id"] == report.recommended_start
    assert rj["recommended_start"]["evidence"] == "error_free_development"


def test_an_attempt_with_a_wrong_answer_is_not_error_free(gen):
    answers = _clean_answers() + [ans("G8_T1_K1", "G8_T1", 0, 5)]
    rj = gen(answers).report_json
    assert rj["report_meta"]["error_free"] is False
    assert all(step.get("kind") != "development" for step in rj["action_plan"])
    assert gen.llm_calls, "a student with errors still gets the narrative provider"


def test_topic_with_one_wrong_answer_is_not_an_achievement():
    achievements = rg._build_achievements(
        {"A": {"alpha": 0.4}, "B": {"alpha": 0.4}},
        {"A": {"name_ru": "Тема A"}, "B": {"name_ru": "Тема B"}},
        [NS(topic_id="A", outcome=1), NS(topic_id="A", outcome=0), NS(topic_id="B", outcome=1)],
    )
    assert [a["skill_id"] for a in achievements] == ["B"]


def test_no_answers_means_no_plan_and_no_start(gen):
    rj = gen([], theta=0.0, se=1.0).report_json
    assert rj["action_plan"] == [] and rj["recommended_start"] is None
    assert rj["report_meta"]["error_free"] is False


# ── Authorship / date ─────────────────────────────────────────────────────────

def test_report_date_is_the_attempt_date_and_build_date_is_separate(gen):
    rj = gen(_gap_answers(), completed_at=datetime(2026, 9, 3, 12, 0), weak=["G7_T9_K1"]).report_json
    assert rj["report_meta"]["date"] == "2026-09-03"
    assert rj["report_meta"]["generated_on"] != "2026-09-03"


def test_attempt_date_falls_back_to_the_last_answer(gen):
    rj = gen(_gap_answers(), completed_at=None, weak=["G7_T9_K1"]).report_json
    assert rj["report_meta"]["date"] == "2026-10-01"


@pytest.mark.parametrize("completed_utc, local_date", [
    (datetime(2026, 9, 3, 18, 59), "2026-09-03"),   # 23:59 in Tashkent
    (datetime(2026, 9, 3, 19, 0), "2026-09-04"),    # 00:00 in Tashkent
    (datetime(2026, 9, 3, 20, 30), "2026-09-04"),   # 01:30
    (datetime(2026, 9, 3, 23, 59), "2026-09-04"),   # 04:59
    (datetime(2026, 9, 4, 0, 0), "2026-09-04"),     # 05:00
    (datetime(2026, 9, 4, 12, 0), "2026-09-04"),    # 17:00
])
def test_attempt_date_is_the_tashkent_calendar_day(completed_utc, local_date):
    db = FakeDB([], completed_at=completed_utc)
    assert rg._attempt_date(db, uuid.uuid4(), []) == local_date


def test_attempt_date_of_a_night_attempt_reaches_the_report(gen):
    rj = gen(_gap_answers(), completed_at=datetime(2026, 9, 3, 21, 0), weak=["G7_T9_K1"]).report_json
    assert rj["report_meta"]["date"] == "2026-09-04"


def test_attempt_date_last_answer_fallback_is_also_tashkent_local():
    late = ans("G8_T1_K1", "G8_T1", 1, 0)
    late.answered_at = datetime(2026, 10, 1, 22, 15)           # 03:15 on Oct 2 in Tashkent
    assert rg._attempt_date(FakeDB([late]), uuid.uuid4(), [late]) == "2026-10-02"


def test_failed_completion_query_rolls_back_and_falls_back_to_the_last_answer():
    class BrokenDB(FakeDB):
        rolled_back = 0

        def query(self, entity):
            raise RuntimeError("current transaction is aborted")

        def rollback(self):
            self.rolled_back += 1

    last = ans("G8_T1_K1", "G8_T1", 1, 5)
    db = BrokenDB([last])
    assert rg._attempt_date(db, uuid.uuid4(), [last]) == "2026-10-01"
    assert db.rolled_back == 1                                  # the session stays usable for saving the report


def test_a_failing_rollback_never_fails_the_report_date():
    class WorseDB(FakeDB):
        def query(self, entity):
            raise RuntimeError("boom")

        def rollback(self):
            raise RuntimeError("connection lost")

    last = ans("G8_T1_K1", "G8_T1", 1, 5)
    assert rg._attempt_date(WorseDB([last]), uuid.uuid4(), [last]) == "2026-10-01"


def test_narrative_prompt_forbids_authorship_of_a_teacher_and_class_equivalent(gen):
    gen(_gap_answers(), weak=["G7_T9_K1"], narrative=None)
    prompt = gen.llm_calls[0]
    assert "не от имени педагога" in prompt
    assert "ПЕДАГОГА-ДИАГНОСТА" not in prompt and "ЭКСПЕРТНОЕ ПЕДАГОГИЧЕСКОЕ" not in prompt
    assert "estimated_hours" not in prompt
    assert "ПЕРВАЯ цель списка" in prompt
    assert not rg._CLASS_EQUIVALENT_RE.search(prompt.lower())


# ── Already stored reports ────────────────────────────────────────────────────

def test_stored_pre_schema5_reports_lose_the_retired_fields_when_read():
    stored = {
        "overall": {"status": "on_level", "confidence_of_diagnosis": 0.84, "class_equivalent": "начало 8 класса"},
        "level": {"status": "on_level", "class_equivalent": "начало 8 класса", "solved": 3, "total": 10},
        "action_plan": [{"priority": 1, "skill_id": "A", "estimated_hours": 2}],
    }
    cleaned = rg.strip_retired_report_fields(stored)
    assert cleaned["overall"] == {"status": "on_level"}
    assert cleaned["level"] == {"status": "on_level", "solved": 3, "total": 10}
    assert cleaned["action_plan"] == [{"priority": 1, "skill_id": "A"}]
    assert stored["overall"]["confidence_of_diagnosis"] == 0.84          # the stored row is not mutated
    assert rg.strip_retired_report_fields(None) is None


@pytest.mark.parametrize("prose", [
    "Уровень по результатам измерения — конец 7 класса (заявлен 8 класс). Затруднения в дробях.",
    "Ученик решает на уровне НАЧАЛА 8 КЛАССА.",
    "Надёжность диагноза 83%. Рекомендуется повторить дроби.",
    "Диагностика проведена, надёжность 83%.",
    "Уровень — середина седьмого класса.",
])
def test_stored_schema4_summary_with_retired_prose_is_withheld(prose):
    stored = {"report_meta": {"report_schema_version": 4},
              "overall": {"status": "on_level", "student_summary": prose, "score_percent": 40}}
    cleaned = rg.strip_retired_report_fields(stored)
    assert cleaned["overall"]["student_summary"] is None            # the front hides the block
    assert cleaned["overall"]["status"] == "on_level" and cleaned["overall"]["score_percent"] == 40
    assert stored["overall"]["student_summary"] == prose            # the stored row is not mutated


@pytest.mark.parametrize("prose", [
    "Решено верно 3 из 10 заданий. Основные затруднения — сложение дробей и степени.",
    "Тему изучают в седьмом классе; ученик допускает вычислительные ошибки.",
    "",
    None,
])
def test_stored_summary_without_retired_claims_is_unchanged(prose):
    stored = {"overall": {"status": "on_level", "student_summary": prose}}
    assert rg.strip_retired_report_fields(stored)["overall"]["student_summary"] == prose


def test_stored_report_without_overall_block_is_still_handled():
    assert rg.strip_retired_report_fields({"action_plan": []}) == {"action_plan": []}
    assert rg.strip_retired_report_fields({"overall": None}) == {"overall": None}
