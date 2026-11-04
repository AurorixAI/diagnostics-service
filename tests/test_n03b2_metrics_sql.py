"""N03b-2: the acceptance metrics (``tools/n03b2_metrics_after.sql``, the copy of artifacts/analysis/n03b2_metrics_after.sql) measure what they say.

The query runs against a temporary ``diag_reports`` table that holds synthetic reports - one built by the generator (schema 8), one in the
shape of the stage report before the package (the "before" row of the acceptance table), one with a task taken out of the bank - and the
numbers are the expected ones.  A report of the old shape measures 0 on every new line, so the same file gives the honest "before" and "after".

Requires A2_TEST_DATABASE_URL (the disposable PostgreSQL) like the other DB tests.
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest
from sqlalchemy import create_engine

from tests.test_n03b2_report_content import (  # noqa: F401  (fixtures)
    Bank, SKILLS, _errors_in_many_skills, a, bank, gen, wrongs,
)

DB_URL = os.getenv("A2_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="Requires disposable A2 PostgreSQL")

SQL = pathlib.Path(__file__).resolve().parents[1] / "tools" / "n03b2_metrics_after.sql"


def measure(reports):
    assert DB_URL and DB_URL.endswith("/a2_diagnostic"), "Use only the disposable a2_diagnostic database"
    engine = create_engine(DB_URL)
    text = "\n".join(line for line in SQL.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--"))
    first, second = [s.strip() for s in text.split(";") if s.strip()]
    with engine.connect() as connection:
        connection.exec_driver_sql("create temp table diag_reports (id serial primary key, report_json jsonb, generation_status text)")
        for report in reports:
            connection.exec_driver_sql(
                "insert into diag_reports (report_json, generation_status) values (%s::jsonb, 'ready')", (json.dumps(report),),
            )
        line = connection.exec_driver_sql(first).scalar()
        categories = connection.exec_driver_sql(second).scalar()
    engine.dispose()
    return dict(part.split("=", 1) for part in line.split(" ")), categories


def old_report():
    """The shape of a stage report before N03b-2: a template step per skill, a string code as evidence, thinking clusters, no map."""
    return {
        "report_meta": {"report_schema_version": 7, "total_questions": 10, "questions_correct": 4},
        "cognitive_error_types": [{"category": "signs_and_powers", "count": 2}],
        "recommended_start": {"skill_id": "A", "evidence": "observed_error"},
        "action_plan": [
            {"priority": 1, "skill_id": "A", "skill_name_ru": "A", "full_description": "Шаблон.", "evidence": "observed_error"},
            {"priority": 2, "skill_id": "B", "skill_name_ru": "B", "full_description": "Шаблон.", "evidence": "observed_error"},
        ],
        "error_patterns": [{"skill_id": s, "eval_category": "wrong", "answer_id": f"o{i}"} for i, s in enumerate("ABCD")],
    }


def test_the_metrics_measure_schema_8_only_and_count_the_old_reports_apart(gen, bank):
    for skill in SKILLS:
        bank.add(skill, 6)
    new = gen(_errors_in_many_skills()).report_json
    got, categories = measure([new, old_report()])
    # the slice: one report of schema 8; the old one (the "before" shape) is only counted, not measured
    assert got["отчётов"] == "1" and got["отчётов_других_схем_ready_не_в_срезе"] == "1"
    assert got["шагов"] == "5" and got["шагов_коррекции"] == "5"
    assert got["шагов_с_основанием"] == "5" and got["шагов_коррекции_с_основанием_из_журнала_попытки"] == "5"
    assert got["шагов_с_материалом_из_банка"] == "5" and got["шагов_материал_на_занятии"] == "0" and got["шагов_без_материала_банк_не_прочитан"] == "0"
    assert got["шагов_с_проверкой_заданием_банка"] == "5" and got["шагов_проверка_на_занятии"] == "0"
    assert got["разных_описаний"] == "5" and got["отчётов_с_кластерами"] == "0"
    assert got["навыков_с_ошибками"] == "7" and got["из_них_нигде_не_названо"] == "0"      # 5 steps + 2 in "more difficulties"
    assert got["карта_тем_есть"] == "1" and got["карта_сходится_с_шапкой"] == "1" and got["первый_шаг_равен_старту"] == "1"
    assert got["шагов_с_основанием_из_снятых"] == "0"
    assert "wrong=" in categories
    # the old report alone: nothing is measured (it is outside the slice), exactly one report waits for the rebuild
    only_old, _ = measure([old_report()])
    assert only_old["отчётов"] == "0" and only_old["шагов"] == "0" and only_old["отчётов_других_схем_ready_не_в_срезе"] == "1"


def test_material_is_counted_as_bank_tasks_and_as_at_the_lesson_apart(gen, bank):
    bank.add("G8_T1_K1", 5)                      # the first skill has tasks, the second has none, the third was never read
    report = gen(wrongs("G8_T1_K1", 2) + wrongs("G8_T2_K1", 1) + wrongs("G8_T3_K1", 1)).report_json
    got = measure([report])[0]
    assert (got["шагов_с_материалом_из_банка"], got["шагов_материал_на_занятии"]) == ("1", "2")
    assert (got["шагов_с_проверкой_заданием_банка"], got["шагов_проверка_на_занятии"]) == ("1", "2")
    unread = json.loads(json.dumps(report))
    for step in unread["action_plan"]:
        step["material"] = step["check"] = None
    got = measure([unread])[0]
    assert got["шагов_без_материала_банк_не_прочитан"] == "3" and got["шагов_с_материалом_из_банка"] == "0" and got["шагов_материал_на_занятии"] == "0"


def test_the_basis_must_be_rows_of_this_attempts_journal(gen, bank):
    report = gen(wrongs("G8_T1_K1", 2)).report_json
    assert measure([report])[0]["шагов_коррекции_с_основанием_из_журнала_попытки"] == "1"
    forged = json.loads(json.dumps(report))
    forged["action_plan"][0]["evidence"][0]["answer_id"] = "not-in-this-journal"
    got = measure([forged])[0]
    assert got["шагов_коррекции"] == "1" and got["шагов_коррекции_с_основанием_из_журнала_попытки"] == "0"


def test_a_step_that_rests_on_a_withdrawn_task_and_a_skill_named_nowhere_are_counted(gen, bank):
    bank.add("G8_T1_K1", 5)
    report = gen(wrongs("G8_T1_K1", 2) + [a("G8_T2_K1", 1)]).report_json
    assert measure([report])[0]["шагов_с_основанием_из_снятых"] == "0"
    # a task is withdrawn in the journal while a step still quotes it: the metric catches it (the generator never does this)
    forged = json.loads(json.dumps(report))
    forged["error_patterns"][0]["task_withdrawn"] = True
    assert measure([forged])[0]["шагов_с_основанием_из_снятых"] == "1"
    # a skill with errors that no step and no "more difficulties" names
    forged = json.loads(json.dumps(report))
    forged["error_patterns"].append({"skill_id": "NOWHERE", "eval_category": "wrong", "answer_id": "x"})
    got = measure([forged])[0]
    assert got["навыков_с_ошибками"] == "2" and got["из_них_нигде_не_названо"] == "1"
    # ... but not when its task is withdrawn: it is marked in the journal and is no difficulty
    forged["error_patterns"][-1]["task_withdrawn"] = True
    got = measure([forged])[0]
    assert got["навыков_с_ошибками"] == "1" and got["из_них_нигде_не_названо"] == "0"
