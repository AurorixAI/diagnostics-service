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


def test_the_metrics_see_a_schema_8_report_and_a_report_of_the_old_shape(gen, bank):
    for skill in SKILLS:
        bank.add(skill, 6)
    new = gen(_errors_in_many_skills()).report_json
    got, categories = measure([new, old_report()])
    assert got["отчётов"] == "2" and got["шагов"] == "7"
    # the new report: 5 steps with all four lines; the old one: 2 steps with none
    assert got["шагов_с_основанием"] == "5" and got["шагов_с_материалом"] == "5" and got["шагов_с_проверкой"] == "5"
    assert got["разных_описаний"] == "6"                       # 5 own descriptions + the one template of the old report
    assert got["отчётов_с_кластерами"] == "1"                  # only the old report has «Анализ мышления»
    # 7 skills with errors in the new report (all named: 5 steps + more_difficulties), 4 in the old one (C and D are named nowhere)
    assert got["навыков_с_ошибками"] == "11" and got["из_них_нигде_не_названо"] == "2"
    assert got["карта_тем_есть"] == "1" and got["карта_сходится_с_шапкой"] == "1"
    assert got["первый_шаг_равен_старту"] == "2"
    assert got["шагов_с_основанием_из_снятых"] == "0"
    assert "wrong=" in categories


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
