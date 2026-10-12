"""N02 against a disposable PostgreSQL: numbers agree across report, payload and script.

Requires A2_TEST_DATABASE_URL (database a2_diagnostic) like the other DB tests.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.domain import auth_sync_jobs as sync_jobs
from src.domain import report_generator as rg
from src.domain.report_generator import REPORT_SCHEMA_VERSION
from src.models.base import Base
from src.models.diag_models import DiagAnswer, DiagReport, DiagSession

DB_URL = os.getenv("A2_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="Requires disposable A2 PostgreSQL")

# L2 topic T1 has one wrong answer; T2 only correct answers.  L4 K1 belongs to T1.
NODES = {
    "G8_T1": NS(id="G8_T1", level="L2", parent_id="G8_S", name_ru="Дроби"),
    "G8_T2": NS(id="G8_T2", level="L2", parent_id="G8_S", name_ru="Степени"),
    "G8_T1_P1": NS(id="G8_T1_P1", level="L3", parent_id="G8_T1", name_ru="Параграф"),
    "G8_T1_K1": NS(id="G8_T1_K1", level="L4", parent_id="G8_T1_P1", name_ru="Сложение дробей"),
    "G7_T9_K1": NS(id="G7_T9_K1", level="L4", parent_id=None, name_ru="Сравнение дробей"),
    "G8_S": NS(id="G8_S", level="L1", parent_id=None, name_ru="Алгебра"),
}


@pytest.fixture
def db(monkeypatch):
    assert DB_URL and DB_URL.endswith("/a2_diagnostic"), "Use only the disposable a2_diagnostic database"
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine, tables=[DiagSession.__table__, DiagAnswer.__table__, DiagReport.__table__])
    with engine.begin() as connection:
        for table in [DiagReport.__table__, DiagAnswer.__table__, DiagSession.__table__]:
            connection.execute(table.delete())
    factory = sessionmaker(engine)

    class FakeKnowledge:
        def get_by_id(self, node_id):
            return NODES.get(node_id)

    monkeypatch.setattr(rg, "KnowledgeRepository", FakeKnowledge)
    monkeypatch.setattr(rg, "call_gemini", lambda *a, **k: None)
    monkeypatch.setattr(rg, "_load_task_context", lambda answer: (None, "unavailable"))
    with factory() as session:
        yield session
    engine.dispose()


def make_session(db, *, theta=0.48, se=0.25, grade=8, invite="N02TEST001"):
    sid = uuid.uuid4()
    session = DiagSession(
        id=sid, student_id=uuid.uuid4(), grade_level=grade, invite_code=invite, phase="completed",
        theta=theta, theta_se=se, overall_level="at_grade", items_answered=13,
        weak_skills=["G8_T1_K1"], completed_at=datetime.now(timezone.utc),
        topic_breakdown={"G8_T1": {"alpha": -0.2, "level": "below_grade", "observations": 5},
                         "G8_T2": {"alpha": 0.2, "level": "at_grade", "observations": 5}},
    )
    db.add(session)
    db.flush()
    t0 = datetime(2026, 10, 1, 10, 0, 0)
    rows = []
    # 10 adaptive answers: 2 correct (both in T2, which therefore has only correct answers), 8 wrong in T1
    spec = [("G8_T2", "G8_T2_K1", 1), ("G8_T2", "G8_T2_K1", 1)] + [("G8_T1", "G8_T1_K1", 0)] * 8
    for i, (topic, skill, outcome) in enumerate(spec):
        rows.append(DiagAnswer(session_id=sid, task_id=f"t{i}", skill_id=skill, topic_id=topic,
                               student_answer="1", outcome=outcome, eval_category="correct" if outcome else "wrong",
                               phase="navigation", is_deep_scan=False, answered_at=t0 + timedelta(minutes=i)))
    # deep scan probes (not part of "solved N of M"); one legacy 0.5 on a CAT item is "not correct"
    rows.append(DiagAnswer(session_id=sid, task_id="d1", skill_id="G7_T9_K1", topic_id="G8_T1",
                           student_answer="1", outcome=0, eval_category="wrong", phase="deep_scan",
                           is_deep_scan=True, deep_scan_origin_skill_id="G8_T1_K1", deep_scan_step=1,
                           answered_at=t0 + timedelta(minutes=20)))
    rows.append(DiagAnswer(session_id=sid, task_id="d2", skill_id="G7_T9_K1", topic_id="G8_T1",
                           student_answer="1", outcome=1, eval_category="correct", phase="deep_scan",
                           is_deep_scan=True, deep_scan_origin_skill_id="G8_T1_K1", deep_scan_step=2,
                           answered_at=t0 + timedelta(minutes=21)))
    rows.append(DiagAnswer(session_id=sid, task_id="h1", skill_id="G8_T1_K1", topic_id="G8_T1",
                           student_answer="1", outcome=0.5, eval_category="distractor", phase="navigation",
                           is_deep_scan=False, answered_at=t0 + timedelta(minutes=22)))
    db.add_all(rows)
    db.commit()
    return session


def build_report(db, session):
    return rg.generate_and_save_report(
        db, session_id=session.id, student_id=session.student_id, grade_level=session.grade_level,
        theta=float(session.theta), theta_se=float(session.theta_se), overall_level=session.overall_level,
        topic_breakdown=session.topic_breakdown, weak_skills=session.weak_skills,
        items_total=session.items_answered, force=True,
    )


def test_payload_and_report_use_the_same_numbers_and_rule(db):
    session = make_session(db)
    report = build_report(db, session)
    assert report is not None and report.generation_status == "ready"
    rj = report.report_json
    payload = sync_jobs._completion_payload(db, session)

    level = rj["level"]
    # same answer set (CAT only), same rule (legacy 0.5 is not correct)
    assert (level["solved"], level["total"]) == (2, 11)
    assert payload["correct_answers"] == level["solved"]
    assert payload["total_items"] == level["total"]
    assert rj["report_meta"]["questions_correct"] == level["solved"]
    assert rj["report_meta"]["total_questions"] == level["total"]
    assert rj["overall"]["score_percent"] == round(2 / 11 * 100)
    assert payload["accuracy"] == round(2 / 11, 4)
    assert rj["report_meta"]["prerequisite_questions"] == 2

    # level fields agree everywhere and come from theta only (18% correct, theta +0.48)
    assert level["category"] == payload["overall_level"] == "at_grade"
    assert level["status"] == payload["level_status"] == "on_level"
    # N03a: no class equivalent anywhere, no reliability percentage
    assert "class_equivalent" not in level and "class_equivalent" not in payload
    assert "class_equivalent" not in rj["overall"] and "confidence_of_diagnosis" not in rj["overall"]
    assert level["provisional"] is payload["level_provisional"] is False
    assert rj["overall"]["status"] == "on_level" and rj["overall"]["status_label_ru"] == "Соответствует уровню"
    assert report.report_schema_version == REPORT_SCHEMA_VERSION


def test_provisional_when_se_is_large(db):
    session = make_session(db, se=0.55, invite="N02TEST002")
    payload = sync_jobs._completion_payload(db, session)
    assert payload["level_provisional"] is True
    assert build_report(db, session).report_json["level"]["provisional"] is True


def test_report_weak_topics_are_evidence_based_and_deduplicated(db):
    session = make_session(db)
    rj = build_report(db, session).report_json
    weak_ids = [w["skill_id"] for w in rj["weak_skills"] + rj["critical_gaps"]]
    assert weak_ids == ["G8_T1"]                                  # T2: only correct answers -> never weak
    item = (rj["weak_skills"] + rj["critical_gaps"])[0]
    assert item["confirmed_by_deep_scan"] is True
    assert [d["skill_id"] for d in item["detail_skills"]] == ["G8_T1_K1"]
    plan_ids = [p["skill_id"] for p in rj["action_plan"]]
    assert "G8_T1" in plan_ids and "G8_T1_K1" not in plan_ids      # L4 is a detail of its L2, not a second item
    assert "G8_T2" not in plan_ids


def test_report_chain_uses_the_stored_origin_link(db):
    session = make_session(db)
    rj = build_report(db, session).report_json
    chains = rj["root_cause_chains"]
    assert len(chains) == 1
    assert chains[0]["source_skill_id"] == "G8_T1_K1" and chains[0]["root_gap_skill_id"] == "G7_T9_K1"
    assert chains[0]["evidence_source"] == "stored_link"
    assert "без углублённой проверки" not in rj["overall"]["student_summary"]


def test_report_without_prerequisite_gap_but_with_deep_scan_says_not_confirmed(db):
    session = make_session(db)
    db.query(DiagAnswer).filter(DiagAnswer.task_id == "d1").update({"outcome": 1, "eval_category": "correct"})
    db.commit()
    summary = build_report(db, session).report_json["overall"]["student_summary"]
    assert "углублённая проверка не подтвердила единую первопричину" in summary
    assert "без углублённой проверки" not in summary


# ── backfill script ───────────────────────────────────────────────────────────

def test_resync_script_is_dry_run_by_default_and_idempotent(db, monkeypatch):
    from scripts import resync_auth_levels as script

    fresh = make_session(db)                     # completed, report not yet regenerated
    stale_before = script.run(execute=False, limit=None, session_ids=None, allow_stale_report=False, db=db)
    assert stale_before["selected"] == 0         # needs a current-schema report first

    build_report(db, fresh)
    db.refresh(fresh)
    fresh.auth_sync_status = "synced"
    fresh.auth_sync_completed_at = datetime.utcnow() - timedelta(days=3)   # synced long before the new report
    db.commit()

    dry = script.run(execute=False, limit=None, session_ids=None, allow_stale_report=False, db=db)
    assert dry["mode"] == "dry-run" and dry["selected"] == 1 and dry["queued"] == 0
    db.refresh(fresh)
    assert fresh.auth_sync_status == "synced"    # dry-run wrote nothing

    done = script.run(execute=True, limit=None, session_ids=None, allow_stale_report=False, db=db)
    assert done["queued"] == 1
    db.refresh(fresh)
    assert fresh.auth_sync_status == "pending" and fresh.auth_sync_attempts == 0
    # already queued -> nothing more to select
    assert script.run(execute=True, limit=None, session_ids=None, allow_stale_report=False, db=db)["selected"] == 0

    # the existing worker delivers it (HTTP boundary stubbed), carrying the level fields
    sent = []
    monkeypatch.setattr(sync_jobs.auth_client, "notify_complete", lambda code, sid, payload: sent.append(payload) or True)
    assert sync_jobs.process_next_auth_completion_sync() is True
    assert sent and sent[0]["level_status"] == "on_level" and sent[0]["overall_level"] == "at_grade"
    assert "class_equivalent" not in sent[0] and sent[0]["level_provisional"] is False

    # after delivery a re-run is a no-op (idempotent)
    assert script.run(execute=True, limit=None, session_ids=None, allow_stale_report=False, db=db)["selected"] == 0


# ── content-service down: degraded reports are never current ─────────────────

def test_hierarchy_outage_is_not_stamped_current_and_falls_back_to_own_l2(db, monkeypatch):
    from src.domain.report_jobs import enqueue_report_generation

    class Down:
        def get_by_id(self, node_id):
            raise ConnectionError("content-service down")

    monkeypatch.setattr(rg, "KnowledgeRepository", Down)
    session = make_session(db)
    enqueue_report_generation(db, session.id)

    # retries left: nothing is written, the job is reported failed so report_jobs re-queues it
    first = build_report(db, session)
    assert first.generation_status == "failed" and first.report_schema_version == 0
    assert first.report_json is None and "content-service unavailable" in first.generation_error

    # last attempt: degraded content is kept for display but is still not current
    first.generation_attempts = 3
    db.commit()
    last = build_report(db, session)
    assert last.report_schema_version == 0 and last.generation_status == "failed"
    meta = last.report_json["report_meta"]
    assert "knowledge_hierarchy" in meta["degraded"]
    # a skill id that is a topic_breakdown key is its own L2 even with the hierarchy down
    assert [w["skill_id"] for w in last.report_json["weak_skills"] + last.report_json["critical_gaps"]] == ["G8_T1"]
    # and a stale-report scan lists it again
    from src.domain.report_jobs import list_stale_report_sessions
    assert [sid for sid, *_ in list_stale_report_sessions(db)] == [session.id]


def test_worker_requeues_a_failed_degraded_report(db, monkeypatch):
    from src.domain import report_jobs
    from src.models.diag_models import DiagReport as R

    class Down:
        def get_by_id(self, node_id):
            raise ConnectionError("down")

    monkeypatch.setattr(rg, "KnowledgeRepository", Down)
    session = make_session(db)
    report_jobs.enqueue_report_generation(db, session.id)
    assert report_jobs.process_next_report_job() is False
    db.expire_all()
    row = db.query(R).one()
    assert row.generation_status == "pending" and row.generation_stage == "retry_queued"
    assert row.report_schema_version == 0


# ── regenerate_reports: stale listing, deterministic marker, no LLM ──────────

def test_regenerate_script_dry_run_then_deterministic_rebuild_without_llm(db, monkeypatch):
    from scripts import regenerate_reports as script
    from src.domain import report_jobs
    from src.models.diag_models import DiagReport as R

    session = make_session(db)
    calls = []
    monkeypatch.setattr(rg, "call_gemini", lambda *a, **k: calls.append(1) or None)

    dry = script.run(execute=False)
    assert dry["mode"] == "dry-run" and dry["stale"] == 1 and dry["queued"] == 0
    assert dry["narrative"] == "deterministic"
    assert db.query(R).count() == 0                      # dry-run wrote nothing

    done = script.run(execute=True)
    assert done["queued"] == 1
    db.expire_all()
    row = db.query(R).one()
    assert row.generation_status == "pending" and row.generation_requested_at is not None
    assert report_jobs.is_deterministic_job(row)

    assert report_jobs.process_next_report_job() is True
    db.expire_all()
    row = db.query(R).one()
    assert row.generation_status == "ready" and row.report_schema_version == REPORT_SCHEMA_VERSION
    assert calls == []                                    # the paid model was never called
    assert row.report_json["report_meta"]["narrative_status"] == "deterministic_fallback"
    assert report_jobs.REGENERATION_KEY not in row.report_json   # marker disappeared with the new report
    assert row.report_json["level"]["status"] == "on_level"

    again = script.run(execute=True)                      # idempotent
    assert again["stale"] == 0 and again["queued"] == 0


def test_with_narrative_is_the_explicit_opt_in_and_other_jobs_keep_the_narrative(db, monkeypatch):
    from scripts import regenerate_reports as script
    from src.domain import report_jobs
    from src.models.diag_models import DiagReport as R

    session = make_session(db)
    calls = []
    monkeypatch.setattr(rg, "call_gemini", lambda *a, **k: calls.append(1) or None)
    assert script.run(execute=True, with_narrative=True)["queued"] == 1
    db.expire_all()
    assert not report_jobs.is_deterministic_job(db.query(R).one())
    assert report_jobs.process_next_report_job() is True
    assert calls                                          # narrative attempted only on opt-in


def test_resync_force_requeues_sessions_already_synced_after_the_report(db):
    from scripts import resync_auth_levels as script

    session = make_session(db)
    build_report(db, session)
    db.refresh(session)
    session.auth_sync_status = "synced"
    session.auth_sync_completed_at = datetime.utcnow() + timedelta(minutes=5)   # synced AFTER the report
    db.commit()
    kw = dict(limit=None, session_ids=None, allow_stale_report=False, db=db)

    assert script.run(execute=True, **kw)["selected"] == 0            # normal mode: nothing to do
    dry = script.run(execute=False, force=True, **kw)
    assert dry["selected"] == 1 and dry["queued"] == 0                 # --force is still a dry run by default
    db.refresh(session)
    assert session.auth_sync_status == "synced"
    assert script.run(execute=True, force=True, **kw)["queued"] == 1
    db.refresh(session)
    assert session.auth_sync_status == "pending"
    assert script.run(execute=True, force=True, **kw)["selected"] == 0   # already queued
