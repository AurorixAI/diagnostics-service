"""Targeted report regeneration after content repairs (scripts/regenerate_reports.py + report_jobs).

In-memory SQLite (JSONB rendered as JSON), no content-service, no model call: the selection, the
durable queueing and the snapshot refresh are exercised on real SQL.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from scripts import regenerate_reports as script
from src.domain import report_jobs
from src.domain.report_generator import REPORT_SCHEMA_VERSION
from src.domain.task_display import build_diag_answer_options, diag_answer_type_for_display
from src.domain.task_evidence import capture_task, read_task
from src.models.diag_models import Base, DiagAnswer, DiagReport, DiagSession


@compiles(JSONB, "sqlite")
def _jsonb_as_json(_type, _compiler, **_kw):          # test-only: the models use PostgreSQL JSONB
    return "JSON"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[DiagSession.__table__, DiagAnswer.__table__, DiagReport.__table__])
    factory = sessionmaker(engine)
    monkeypatch.setattr(report_jobs, "SessionLocal", factory)          # the stale-mode enqueue opens its own session
    with factory() as session:
        yield session
    engine.dispose()


def make_task(task_id, *, correct="5", distractors=(("3", "Сложил вместо вычитания"), ("4", "Забыл знак")), question="Найдите x"):
    return NS(
        id=task_id, skill_id="G8_T1_K1", question_text=question, question_latex=None, question_image_url=None,
        answer_type="mcq", correct_answer=correct, correct_answer_latex=None, sympy_solution=None,
        answer_options=None, answer_options_latex=None,
        distractor_meta=[{"value": v, "error_logic": why} for v, why in distractors],
        irt_discrimination=1.0, irt_difficulty=0.0, irt_guessing=0.2,
    )


def snapshot_of(task, session_id, provenance="issued"):
    options, options_latex = build_diag_answer_options(task, seed=f"{session_id}:{task.id}")
    return capture_task(task, options, options_latex, diag_answer_type_for_display(task, options), provenance=provenance)


T0 = datetime(2026, 10, 1, 10, 0, 0)


def add_session(db, *, phase="completed", tasks=("t1",), with_snapshot=True, report=None, minute=0):
    sid = uuid.uuid4()
    db.add(DiagSession(
        id=sid, student_id=uuid.uuid4(), grade_level=8, invite_code=f"I{minute:03d}", phase=phase, theta=0.1,
        theta_se=0.3, overall_level="at_grade", completed_at=T0 + timedelta(minutes=minute) if phase == "completed" else None,
        topic_breakdown={}, weak_skills=[],
    ))
    db.flush()
    for index, task_id in enumerate(tasks):
        db.add(DiagAnswer(
            session_id=sid, task_id=task_id, skill_id="G8_T1_K1", topic_id="G8_T1", student_answer="3", outcome=0,
            eval_category="distractor", phase="navigation", is_deep_scan=False, answered_at=T0 + timedelta(minutes=index),
            task_snapshot=snapshot_of(make_task(task_id), sid) if with_snapshot else None,
        ))
    if report:
        db.add(DiagReport(
            session_id=sid, student_id=uuid.uuid4(), grade_level=8, report_json={"report_meta": {}, "marker": "old"},
            report_schema_version=REPORT_SCHEMA_VERSION if report == "current" else 1,
            generation_status={"current": "ready", "stale": "ready"}.get(report, report),
            generation_stage="done", generation_attempts=0,
            generation_requested_at=datetime.now(timezone.utc) if report in ("pending", "generating") else None,
        ))
    db.commit()
    return sid


def reports(db):
    db.expire_all()
    return {r.session_id: r for r in db.query(DiagReport).all()}


# ── selection ─────────────────────────────────────────────────────────────────

def test_selection_by_session_id_includes_current_reports_and_reports_skips(db):
    current = add_session(db, report="current", minute=1)
    active = add_session(db, phase="active", minute=2)
    ghost = uuid.uuid4()
    targets = {t["session_id"]: t for t in report_jobs.find_regeneration_targets(db, session_ids=[current, active, ghost, current])}
    assert targets[current]["skip"] is None and targets[current]["reasons"] == ["--session-id"]
    assert targets[current]["report_status"] == "ready" and targets[current]["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert "not completed" in targets[active]["skip"] and targets[ghost]["skip"] == "session not found"
    assert len(targets) == 3                                           # the duplicate id is one target


def test_selection_by_tasks_finds_only_completed_sessions_with_those_answers(db):
    hit_a = add_session(db, tasks=("t1", "t2"), report="current", minute=1)
    hit_b = add_session(db, tasks=("t2",), minute=2)
    miss = add_session(db, tasks=("t9",), minute=3)
    active = add_session(db, phase="active", tasks=("t1",), minute=4)
    targets = report_jobs.find_regeneration_targets(db, task_ids=["t1", "t2", " ", "t1"])
    assert [t["session_id"] for t in targets] == [hit_a, hit_b]          # ordered by completion time
    assert targets[0]["reasons"] == ["answered task t1, t2"] and targets[1]["reasons"] == ["answered task t2"]
    assert targets[1]["report_status"] == "missing" and targets[1]["report_schema_version"] is None
    assert miss not in {t["session_id"] for t in targets} and active not in {t["session_id"] for t in targets}


def test_selection_combines_session_ids_and_tasks_with_both_reasons(db):
    both = add_session(db, tasks=("t1",), minute=1)
    only_task = add_session(db, tasks=("t1",), minute=2)
    only_id = add_session(db, tasks=("t9",), minute=3)
    targets = {t["session_id"]: t["reasons"] for t in
               report_jobs.find_regeneration_targets(db, session_ids=[both, only_id], task_ids=["t1"])}
    assert targets[both] == ["--session-id", "answered task t1"]
    assert targets[only_task] == ["answered task t1"] and targets[only_id] == ["--session-id"]


# ── dry-run / queueing ────────────────────────────────────────────────────────

def test_dry_run_lists_sessions_and_reasons_and_writes_nothing(db):
    sid = add_session(db, tasks=("t1",), report="current", minute=1)
    before = reports(db)[sid].generation_status
    result = script.run(execute=False, task_ids=["t1"], db=db)
    assert result["mode"] == "dry-run" and result["targeted"] and result["selected"] == 1 and result["queued"] == 0
    assert result["narrative"] == "deterministic"
    assert result["sessions"] == [(str(sid), "answered task t1", "ready", REPORT_SCHEMA_VERSION, "will queue")]
    row = reports(db)[sid]
    assert row.generation_status == before == "ready" and row.report_json == {"report_meta": {}, "marker": "old"}
    assert row.generation_requested_at is None


def test_execute_queues_a_current_report_deterministically_and_keeps_it_readable(db):
    sid = add_session(db, tasks=("t1",), report="current", minute=1)
    result = script.run(execute=True, session_ids=[sid], db=db)
    assert result["queued"] == 1 and result["already_queued"] == 0
    row = reports(db)[sid]
    assert row.generation_status == "pending" and row.generation_stage == "queued"
    assert row.generation_requested_at is not None and row.generation_attempts == 0
    assert report_jobs.is_deterministic_job(row)                          # no paid model
    assert row.report_json["marker"] == "old"                             # the old report stays until replaced
    assert row.report_schema_version == REPORT_SCHEMA_VERSION


def test_with_narrative_removes_the_deterministic_marker(db):
    sid = add_session(db, report="current", minute=1)
    script.run(execute=True, session_ids=[sid], db=db)
    assert report_jobs.is_deterministic_job(reports(db)[sid])
    row = reports(db)[sid]
    row.generation_status = "ready"
    db.commit()
    script.run(execute=True, session_ids=[sid], with_narrative=True, db=db)
    row = reports(db)[sid]
    assert row.generation_status == "pending" and not report_jobs.is_deterministic_job(row)


def test_a_missing_report_is_created_as_a_claimable_job(db):
    sid = add_session(db, tasks=("t1",), minute=1)
    script.run(execute=True, task_ids=["t1"], db=db)
    row = reports(db)[sid]
    assert row.generation_status == "pending" and row.generation_requested_at is not None
    assert row.report_schema_version == 0 and report_jobs.is_deterministic_job(row)


@pytest.mark.parametrize("status", ["pending", "generating"])
def test_no_double_queue(db, status):
    sid = add_session(db, report=status, minute=1)
    requested_at = reports(db)[sid].generation_requested_at
    result = script.run(execute=True, session_ids=[sid], db=db)
    assert result["queued"] == 0 and result["already_queued"] == 1
    row = reports(db)[sid]
    assert row.generation_status == status and row.generation_requested_at == requested_at
    assert not report_jobs.is_deterministic_job(row)                       # untouched
    dry = script.run(execute=False, session_ids=[sid], db=db)
    assert dry["sessions"][0][4] == "already queued" and dry["already_queued"] == 1


def test_a_second_execute_right_after_the_first_queues_nothing(db):
    sid = add_session(db, report="current", minute=1)
    assert script.run(execute=True, session_ids=[sid], db=db)["queued"] == 1
    again = script.run(execute=True, session_ids=[sid], db=db)
    assert again["queued"] == 0 and again["already_queued"] == 1


def test_skipped_sessions_are_listed_but_never_queued(db):
    active = add_session(db, phase="active", minute=1)
    result = script.run(execute=True, session_ids=[active, uuid.uuid4()], db=db)
    assert result["selected"] == 0 and result["queued"] == 0 and result["skipped"] == 2
    assert reports(db) == {}


# ── stale mode is unchanged ───────────────────────────────────────────────────

def test_without_targeted_flags_the_stale_behaviour_is_unchanged(db):
    current = add_session(db, report="current", minute=1)
    stale = add_session(db, report="stale", minute=2)
    missing = add_session(db, minute=3)
    dry = script.run(execute=False, db=db)
    assert dry["targeted"] is False and dry["stale"] == 2 and dry["queued"] == 0
    assert {sid for sid, _version, _status in dry["sessions"]} == {str(stale), str(missing)}
    done = script.run(execute=True, db=db)
    assert done["queued"] == 2
    rows = reports(db)
    assert rows[stale].generation_status == "pending" and rows[stale].report_schema_version == 0
    assert rows[missing].generation_status == "pending"
    assert rows[current].generation_status == "ready"                      # a current report is never touched
    assert script.run(execute=False, db=db)["stale"] == 2                    # still stale until the worker rebuilds them


def test_refresh_task_content_requires_a_targeted_selection(db):
    with pytest.raises(ValueError):
        script.run(execute=False, refresh_task_content=True, db=db)
    with pytest.raises(SystemExit):
        script.main(["--refresh-task-content"])


# ── input parsing ─────────────────────────────────────────────────────────────

def test_task_id_parsing_accepts_commas_blanks_lines_and_comments(tmp_path):
    assert script.parse_task_ids(["a,b  c\n# comment\nd # tail", "a"]) == ["a", "b", "c", "d"]
    path = tmp_path / "ids.txt"
    path.write_text("ds_llm_1\nds_llm_2, ds_llm_3\n\n# none\n", encoding="utf-8")
    assert script.parse_task_ids([path.read_text(encoding="utf-8")]) == ["ds_llm_1", "ds_llm_2", "ds_llm_3"]


# ── --refresh-task-content ────────────────────────────────────────────────────

class FakeRepo:
    def __init__(self, tasks, broken=()):
        self.tasks, self.broken, self.calls = tasks, set(broken), []

    def get_by_id(self, task_id):
        self.calls.append(task_id)
        if task_id in self.broken:
            raise RuntimeError("content-service down")
        return self.tasks.get(task_id)


def journal(db):
    db.expire_all()
    return {(a.session_id, a.task_id): (a.student_answer, float(a.outcome), a.eval_category) for a in db.query(DiagAnswer).all()}


def test_refresh_dry_run_counts_and_writes_nothing(db):
    sid = add_session(db, tasks=("t1", "t2"), minute=1)
    repo = FakeRepo({"t1": make_task("t1", distractors=(("3", "НОВОЕ объяснение"), ("4", "Забыл знак"))),
                     "t2": make_task("t2")})
    stored = {a.task_id: a.task_snapshot for a in db.query(DiagAnswer).all()}
    result = script.run(execute=False, task_ids=["t1"], refresh_task_content=True, db=db, task_repo=repo)
    assert result["refresh"]["would_refresh"] == 1 and result["refresh"]["refreshed"] == 0
    assert repo.calls == ["t1"]                                            # only the affected task is fetched
    db.expire_all()
    assert {a.task_id: a.task_snapshot for a in db.query(DiagAnswer).all()} == stored


def test_refresh_execute_updates_only_the_snapshot_and_the_rebuild_reads_it(db):
    sid = add_session(db, tasks=("t1", "t2"), minute=1)
    before = journal(db)
    repo = FakeRepo({
        "t1": make_task("t1", correct="6", question="Новое условие",
                        distractors=(("3", "НОВОЕ объяснение"), ("4", "Забыл знак"))),
        "t2": make_task("t2"),
    })
    result = script.run(execute=True, task_ids=["t1"], refresh_task_content=True, db=db, task_repo=repo)
    assert result["refresh"]["refreshed"] == 1 and result["queued"] == 1
    assert journal(db) == before                                          # outcome / student_answer / category untouched
    db.expire_all()
    rows = {a.task_id: a for a in db.query(DiagAnswer).all()}
    payload = read_task(rows["t1"].task_snapshot, "t1")                    # the hash is valid, the envelope readable
    assert rows["t1"].task_snapshot["provenance"] == "bank_refresh"
    assert payload["question_text"] == "Новое условие" and payload["correct_answer"] == "6"
    assert {d["value"]: d["error_logic"] for d in payload["distractor_meta"]}["3"] == "НОВОЕ объяснение"
    info = rows["t1"].task_snapshot["refresh"]
    assert info["previous_provenance"] == "issued" and "distractor_meta" in info["changed_fields"]
    assert rows["t2"].task_snapshot["provenance"] == "issued"              # not an affected task: untouched
    assert payload["irt_difficulty"] == 0.0 and payload["id"] == "t1"      # identity of the issued item kept


def test_refresh_is_idempotent_and_keeps_what_the_student_saw_when_the_options_changed(db):
    sid = add_session(db, tasks=("t1",), minute=1)
    old_options = read_task(db.query(DiagAnswer).one().task_snapshot, "t1")["display_options"]
    repaired = make_task("t1", distractors=(("33", "Новый вариант"), ("4", "Забыл знак")))     # option VALUE changed
    repo = FakeRepo({"t1": repaired})
    first = script.run(execute=True, session_ids=[sid], refresh_task_content=True, db=db, task_repo=repo)
    assert first["refresh"]["refreshed"] == 1 and first["refresh"]["display_options_kept"] == 1
    db.expire_all()
    payload = read_task(db.query(DiagAnswer).one().task_snapshot, "t1")
    assert payload["display_options"] == old_options                         # what the student saw is kept
    assert {d["value"] for d in payload["distractor_meta"]} == {"33", "4"}   # the repaired explanations are in
    reports(db)[sid].generation_status = "ready"
    db.commit()
    second = script.run(execute=True, session_ids=[sid], refresh_task_content=True, db=db, task_repo=repo)
    assert second["refresh"]["refreshed"] == 0 and second["refresh"]["unchanged"] == 1


def test_refresh_counts_null_snapshots_missing_tasks_fetch_errors_and_bad_envelopes(db):
    legacy = add_session(db, tasks=("t1",), with_snapshot=False, minute=1)
    gone = add_session(db, tasks=("t2",), minute=2)
    down = add_session(db, tasks=("t3",), minute=3)
    bad = add_session(db, tasks=("t4",), minute=4)
    row = db.query(DiagAnswer).filter(DiagAnswer.task_id == "t4").one()
    row.task_snapshot = {**row.task_snapshot, "sha256": "0" * 64}
    db.commit()
    repo = FakeRepo({"t4": make_task("t4")}, broken=["t3"])
    result = script.run(execute=True, session_ids=[legacy, gone, down, bad], refresh_task_content=True, db=db, task_repo=repo)
    stats = result["refresh"]
    assert (stats["null_snapshot"], stats["missing_task"], stats["fetch_errors"], stats["invalid_snapshot"]) == (1, 1, 1, 1)
    assert stats["refreshed"] == 0
    assert result["queued"] == 4                                           # the reports are still queued


def test_the_stored_envelope_whitelist_accepts_bank_refresh_only_with_a_valid_hash():
    task = make_task("t1")
    snap = snapshot_of(task, "s")
    assert read_task(snap, "t1")["id"] == "t1"
    refreshed = {**snap, "provenance": "bank_refresh"}
    assert read_task(refreshed, "t1")["id"] == "t1"
    with pytest.raises(ValueError):
        read_task({**snap, "provenance": "made_up"}, "t1")
    with pytest.raises(ValueError):
        read_task({**refreshed, "sha256": "0" * 64}, "t1")
