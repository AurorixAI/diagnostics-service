"""Targeted report regeneration after content repairs (scripts/regenerate_reports.py + report_jobs).

In-memory SQLite (JSONB rendered as JSON) by default; no content-service, no model call.  Set
``REGEN_TEST_DATABASE_URL`` to a throwaway PostgreSQL database named ``regen_test`` to run the same tests on
real PostgreSQL (JSONB equality guard, FOR UPDATE SKIP LOCKED); tests that need a second connection holding a
row lock run only there.
"""
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from scripts import regenerate_reports as script
from src.domain import report_jobs
from src.domain.report_generator import REPORT_SCHEMA_VERSION
from src.domain.task_display import build_diag_answer_options, diag_answer_type_for_display
from src.domain.task_evidence import capture_task, read_task
from src.models.diag_models import Base, DiagAnswer, DiagReport, DiagSession

PG_URL = os.getenv("REGEN_TEST_DATABASE_URL")
TABLES = [DiagSession.__table__, DiagAnswer.__table__, DiagReport.__table__]


@compiles(JSONB, "sqlite")
def _jsonb_as_json(_type, _compiler, **_kw):          # test-only: the models use PostgreSQL JSONB
    return "JSON"


@pytest.fixture
def engine():
    if PG_URL:
        assert PG_URL.rstrip("/").endswith("/regen_test"), "run only against the throwaway regen_test database"
        eng = create_engine(PG_URL)
        Base.metadata.create_all(eng, tables=TABLES)
        with eng.begin() as connection:
            for table in reversed(TABLES):
                connection.execute(table.delete())
    else:
        eng = create_engine("sqlite://")
        Base.metadata.create_all(eng, tables=TABLES)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine, monkeypatch):
    maker = sessionmaker(engine)
    monkeypatch.setattr(report_jobs, "SessionLocal", maker)           # the stale-mode enqueue opens its own session
    monkeypatch.setattr(script, "SessionLocal", maker)
    return maker


@pytest.fixture
def db(factory):
    with factory() as session:
        yield session


needs_postgres = pytest.mark.skipif(not PG_URL, reason="needs real PostgreSQL row locks (REGEN_TEST_DATABASE_URL)")


def make_task(task_id, *, correct="5", distractors=(("3", "Сложил вместо вычитания"), ("4", "Забыл знак")), question="Найдите x",
              is_active=True, question_latex=None, answer_type="mcq"):
    return NS(
        id=task_id, skill_id="G8_T1_K1", question_text=question, question_latex=question_latex, question_image_url=None,
        is_active=is_active, answer_type=answer_type, correct_answer=correct, correct_answer_latex=None, sympy_solution=None,
        answer_options=None, answer_options_latex=None,
        distractor_meta=[{"value": v, "error_logic": why} for v, why in distractors],
        irt_discrimination=1.0, irt_difficulty=0.0, irt_guessing=0.2,
    )


def snapshot_of(task, session_id, provenance="issued"):
    options, options_latex = build_diag_answer_options(task, seed=f"{session_id}:{task.id}")
    return capture_task(task, options, options_latex, diag_answer_type_for_display(task, options), provenance=provenance)


T0 = datetime(2026, 10, 1, 10, 0, 0)


def add_session(db, *, phase="completed", tasks=("t1",), with_snapshot=True, report=None, minute=0, make=None,
                student_answer="3", outcome=0):
    make = make or make_task
    sid = uuid.uuid4()
    db.add(DiagSession(
        id=sid, student_id=uuid.uuid4(), grade_level=8, invite_code=f"I{minute:03d}", phase=phase, theta=0.1,
        theta_se=0.3, overall_level="at_grade", completed_at=T0 + timedelta(minutes=minute) if phase == "completed" else None,
        topic_breakdown={}, weak_skills=[],
    ))
    db.flush()
    for index, task_id in enumerate(tasks):
        db.add(DiagAnswer(
            session_id=sid, task_id=task_id, skill_id="G8_T1_K1", topic_id="G8_T1", student_answer=student_answer, outcome=outcome,
            eval_category="distractor", phase="navigation", is_deep_scan=False, answered_at=T0 + timedelta(minutes=index),
            task_snapshot=snapshot_of(make(task_id), sid) if with_snapshot else None,
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
    def __init__(self, tasks, broken=(), on_fetch=None):
        self.tasks, self.broken, self.on_fetch, self.calls = tasks, set(broken), on_fetch, []

    def get_by_id(self, task_id):
        self.calls.append(task_id)
        if self.on_fetch:
            self.on_fetch(task_id)
        if task_id in self.broken:
            raise RuntimeError("content-service down")
        return self.tasks.get(task_id)


def journal(db):
    db.expire_all()
    return {(a.session_id, a.task_id): (a.student_answer, float(a.outcome), a.eval_category) for a in db.query(DiagAnswer).all()}


def snapshots(db):
    db.expire_all()
    return {(a.session_id, a.task_id): a.task_snapshot for a in db.query(DiagAnswer).all()}


def repaired(task_id="t1", **kwargs):
    kwargs.setdefault("distractors", (("3", "НОВОЕ объяснение"), ("4", "Забыл знак")))
    return make_task(task_id, **kwargs)


def refresh(db, repo, sessions, tmp_path=None, name="backup.jsonl", **kwargs):
    kwargs.setdefault("execute", True)
    if kwargs["execute"] and tmp_path is not None:
        kwargs.setdefault("backup_path", str(tmp_path / name))
    return script.run(session_ids=sessions, refresh_task_content=True, db=db, task_repo=repo, **kwargs)


def test_refresh_dry_run_lists_changes_and_flags_and_writes_nothing(db, tmp_path):
    sid = add_session(db, tasks=("t1", "t2"), minute=1)
    repo = FakeRepo({"t1": repaired("t1"), "t2": make_task("t2")})
    before = snapshots(db)
    result = refresh(db, repo, [sid], execute=False, task_ids=["t1"])
    stats = result["refresh"]
    assert stats["would_refresh"] == 1 and stats["refreshed"] == 0 and result["exit_code"] == 0
    assert repo.calls == ["t1"]                                            # only the affected task is fetched
    item = [i for i in result["refresh_details"]["items"] if i["status"] == "would_refresh"][0]
    assert item["task_id"] == "t1" and item["changed"] == ["distractor_meta"] and item["flags"] == []
    assert result["refresh_details"]["backup"] is None and list(tmp_path.iterdir()) == []
    assert snapshots(db) == before


def test_execute_writes_the_backup_first_and_only_the_snapshot_column(db, tmp_path):
    sid = add_session(db, tasks=("t1", "t2"), minute=1)
    before_journal, before_snaps = journal(db), snapshots(db)
    repo = FakeRepo({"t1": repaired("t1", question="Найдите x"), "t2": make_task("t2")})
    result = refresh(db, repo, [sid], tmp_path, task_ids=["t1"])
    assert result["refresh"]["refreshed"] == 1 and result["queued"] == 1 and result["exit_code"] == 0
    assert journal(db) == before_journal                                   # outcome / student_answer / category untouched
    info = result["refresh_details"]["backup"]
    assert info["rows"] == 1 and not info["stdout"] and info["sha256"] == hashlib.sha256(open(info["path"], "rb").read()).hexdigest()
    rows = [json.loads(line) for line in open(info["path"], encoding="utf-8")]
    assert len(rows) == 1 and rows[0]["task_id"] == "t1" and rows[0]["task_snapshot"] == before_snaps[(sid, "t1")]
    snaps = snapshots(db)
    new = snaps[(sid, "t1")]
    payload = read_task(new, "t1")                                          # envelope and hash are valid
    assert new["provenance"] == "bank_refresh" and snaps[(sid, "t2")] == before_snaps[(sid, "t2")]
    assert {d["value"]: d["error_logic"] for d in payload["distractor_meta"]}["3"] == "НОВОЕ объяснение"
    old = before_snaps[(sid, "t1")]
    assert new["refresh_history"] == [{
        "at": new["refresh_history"][0]["at"], "source": report_jobs.REFRESH_SOURCE, "previous_sha256": old["sha256"],
        "previous_provenance": "issued", "previous_task": old["task"], "result_sha256": new["sha256"],
        "changed_fields": ["distractor_meta"], "kept_key_and_question": False,
    }]
    assert payload["id"] == "t1" and payload["irt_difficulty"] == 0.0
    assert payload["display_options"] == old["task"]["display_options"]
    assert payload["display_options_latex"] == old["task"]["display_options_latex"]    # what the student saw, never replaced


def test_a_second_refresh_keeps_the_issued_hash_and_the_restore_walks_back(db, tmp_path):
    sid = add_session(db, tasks=("t1",), minute=1)
    original = snapshots(db)[(sid, "t1")]
    first = refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], tmp_path, name="b1.jsonl")
    after_first = snapshots(db)[(sid, "t1")]
    reports(db)[sid].generation_status = "ready"
    db.commit()
    second = refresh(db, FakeRepo({"t1": repaired("t1", distractors=(("3", "СНОВА новое"), ("4", "Забыл знак")))}),
                     [sid], tmp_path, name="b2.jsonl")
    after_second = snapshots(db)[(sid, "t1")]
    assert first["refresh"]["refreshed"] == second["refresh"]["refreshed"] == 1
    history = after_second["refresh_history"]
    assert [h["previous_provenance"] for h in history] == ["issued", "bank_refresh"]
    assert history[0]["previous_sha256"] == original["sha256"] and history[1]["previous_sha256"] == after_first["sha256"]

    # restore: the newest backup first; the older one is "diverged" until then
    b1, b2 = str(tmp_path / "b1.jsonl"), str(tmp_path / "b2.jsonl")
    assert script.run_restore(backup_path=b1, execute=True, db=db)["restore"]["diverged"] == 1
    assert snapshots(db)[(sid, "t1")] == after_second
    dry = script.run_restore(backup_path=b2, execute=False, db=db)
    assert dry["restore"]["would_restore"] == 1 and snapshots(db)[(sid, "t1")] == after_second          # dry-run by default
    assert script.run_restore(backup_path=b2, execute=True, db=db)["restore"]["restored"] == 1
    assert snapshots(db)[(sid, "t1")] == after_first
    assert script.run_restore(backup_path=b1, execute=True, db=db)["restore"]["restored"] == 1
    assert snapshots(db)[(sid, "t1")] == original                           # exactly the issued snapshot again
    again = script.run_restore(backup_path=b1, execute=True, db=db)
    assert again["restore"]["already_restored"] == 1 and again["exit_code"] == 0


def test_restore_reports_missing_answers_and_invalid_rows(db, tmp_path):
    sid = add_session(db, tasks=("t1",), minute=1)
    path = tmp_path / "bad.jsonl"
    path.write_text("not json\n" + json.dumps({"answer_id": str(uuid.uuid4()), "session_id": str(sid), "task_id": "t1",
                                               "task_snapshot": {"sha256": "x"}}) + "\n", encoding="utf-8")
    result = script.run_restore(backup_path=str(path), execute=True, db=db)
    assert result["restore"]["invalid_rows"] == 1 and result["restore"]["missing_answer"] == 1 and result["exit_code"] == 2


def test_open_input_tasks_refresh_without_option_flags(db, tmp_path):
    def open_task(task_id, **kwargs):
        return make_task(task_id, distractors=(), answer_type="open_text", **kwargs)

    sid = add_session(db, tasks=("t1",), minute=1, make=open_task)
    assert read_task(snapshots(db)[(sid, "t1")], "t1")["display_options"] is None
    live = open_task("t1")
    live.sympy_solution = "x = 5"
    result = refresh(db, FakeRepo({"t1": live}), [sid], tmp_path)
    assert result["refresh"]["refreshed"] == 1
    assert read_task(snapshots(db)[(sid, "t1")], "t1")["sympy_solution"] == "x = 5"
    # a changed key of an open-input task raises key_changed only: there are no displayed choices to be outside of
    keyed = open_task("t1")
    keyed.correct_answer = "6"
    items = refresh(db, FakeRepo({"t1": keyed}), [sid], execute=False)["refresh_details"]["items"]
    assert items[0]["flags"] == ["key_changed"]


@pytest.mark.parametrize("live_kwargs, student_answer, flags", [
    ({"correct": "6"}, "3", ["key_changed", "new_key_not_in_display_options"]),
    ({"correct": "3", "distractors": (("5", "Теперь это ошибка"), ("4", "Забыл знак"))}, "3",
     ["key_changed", "student_answer_equals_new_key_but_outcome<1"]),
    ({"question": "Совсем другое условие"}, "3", ["question_changed"]),
    ({"question_latex": "$x+2=7$"}, "3", ["question_changed"]),
])
def test_flagged_answers_are_listed_and_skipped_by_default(db, tmp_path, live_kwargs, student_answer, flags):
    sid = add_session(db, tasks=("t1",), minute=1, student_answer=student_answer)
    before = snapshots(db)
    result = refresh(db, FakeRepo({"t1": repaired("t1", **live_kwargs)}), [sid], tmp_path)
    item = result["refresh_details"]["items"][0]
    assert item["status"] == "flagged_skipped" and item["flags"] == flags
    assert result["refresh"]["flagged_skipped"] == 1 and result["refresh"]["refreshed"] == 0
    assert snapshots(db) == before                                           # the report keeps agreeing with the stored outcome
    assert result["queued"] == 1 and result["exit_code"] == 0                # still rebuilt, from the old snapshot
    assert result["refresh_details"]["backup"] is None                       # nothing to overwrite, no backup file needed


def test_allow_key_change_refreshes_everything_except_key_and_question(db, tmp_path):
    sid = add_session(db, tasks=("t1",), minute=1)
    old = read_task(snapshots(db)[(sid, "t1")], "t1")
    live = repaired("t1", correct="6", question="Совсем другое условие")
    result = refresh(db, FakeRepo({"t1": live}), [sid], tmp_path, allow_key_change=True)
    item = result["refresh_details"]["items"][0]
    assert item["status"] == "refreshed" and "key_changed" in item["flags"]
    new = snapshots(db)[(sid, "t1")]
    payload = read_task(new, "t1")
    assert payload["correct_answer"] == old["correct_answer"] == "5" and payload["question_text"] == old["question_text"]
    assert {d["value"]: d["error_logic"] for d in payload["distractor_meta"]}["3"] == "НОВОЕ объяснение"
    assert new["refresh_history"][0]["kept_key_and_question"] is True
    # only the key / question differ and they are protected: nothing is left to write
    reports(db)[sid].generation_status = "ready"
    db.commit()
    res2 = refresh(db, FakeRepo({"t1": repaired("t1", correct="6", question="Совсем другое условие")}), [sid],
                   tmp_path, name="b2.jsonl", allow_key_change=True)
    assert res2["refresh"]["refreshed"] == 0 and res2["refresh"]["unchanged"] == 1


def test_inactive_and_blanked_live_tasks_are_skipped_and_counted(db, tmp_path):
    inactive = add_session(db, tasks=("t1",), minute=1)
    no_question = add_session(db, tasks=("t2",), minute=2)
    no_key = add_session(db, tasks=("t3",), minute=3)
    fine = add_session(db, tasks=("t4",), minute=4)
    before = snapshots(db)
    live = {
        "t1": repaired("t1", is_active=False),
        "t2": repaired("t2", question="  ", question_latex=None),
        "t3": repaired("t3", correct="  "),
        "t4": repaired("t4"),
    }
    result = refresh(db, FakeRepo(live), [inactive, no_question, no_key, fine], tmp_path)
    stats = result["refresh"]
    assert stats["inactive_task"] == 1 and stats["invalid_live_task"] == 2 and stats["refreshed"] == 1
    assert result["refresh_details"]["inactive_tasks"] == ["t1"]
    assert {f["task_id"] for f in result["refresh_details"]["failed"]} == {"t2", "t3"}
    after = snapshots(db)
    assert after[(inactive, "t1")] == before[(inactive, "t1")] and after[(fine, "t4")] != before[(fine, "t4")]
    assert result["exit_code"] == script.EXIT_FAILURES
    rows = reports(db)
    assert set(rows) == {inactive, fine}                                    # failed sessions are not queued; inactive is not a failure
    assert result["queued"] == 2


def test_a_fetch_error_holds_the_whole_session_back_and_exits_non_zero(db, tmp_path):
    ok = add_session(db, tasks=("t1",), minute=1)
    mixed = add_session(db, tasks=("t2", "t3"), minute=2)
    before = snapshots(db)
    repo = FakeRepo({"t1": repaired("t1"), "t2": repaired("t2")}, broken=["t3"])
    result = refresh(db, repo, [ok, mixed], tmp_path)
    stats = result["refresh"]
    assert stats["fetch_errors"] == 1 and stats["held_back"] == 1 and stats["refreshed"] == 1
    after = snapshots(db)
    assert after[(mixed, "t2")] == before[(mixed, "t2")]                    # even the answer that could be refreshed is untouched
    assert after[(ok, "t1")] != before[(ok, "t1")]
    assert result["exit_code"] == script.EXIT_FAILURES and set(reports(db)) == {ok}
    failed = result["refresh_details"]["failed"]
    assert [(f["task_id"], f["status"]) for f in failed] == [("t3", "fetch_errors")] and failed[0]["session_id"] == str(mixed)
    assert [row[4] for row in result["sessions"] if row[0] == str(mixed)] == ["held back: refresh failed"]


def test_allow_partial_goes_on_but_still_exits_non_zero(db, tmp_path):
    mixed = add_session(db, tasks=("t2", "t3"), minute=1)
    before = snapshots(db)
    result = refresh(db, FakeRepo({"t2": repaired("t2")}, broken=["t3"]), [mixed], tmp_path, allow_partial=True)
    assert result["refresh"]["refreshed"] == 1 and result["queued"] == 1 and result["exit_code"] == script.EXIT_PARTIAL
    assert snapshots(db)[(mixed, "t2")] != before[(mixed, "t2")] and snapshots(db)[(mixed, "t3")] == before[(mixed, "t3")]


def test_invalid_snapshot_and_build_error_are_separate_failures_a_404_is_not_one(db, tmp_path, monkeypatch):
    gone = add_session(db, tasks=("t1",), minute=1)
    bad = add_session(db, tasks=("t2",), minute=2)
    boom = add_session(db, tasks=("t3",), minute=3)
    row = db.query(DiagAnswer).filter(DiagAnswer.task_id == "t2").one()
    row.task_snapshot = {**row.task_snapshot, "sha256": "0" * 64}
    db.commit()
    from src.domain import task_evidence

    real = task_evidence.refresh_snapshot

    def flaky(snapshot, task_id, *args, **kwargs):
        if task_id == "t3":
            raise RuntimeError("cannot merge")
        return real(snapshot, task_id, *args, **kwargs)

    monkeypatch.setattr(task_evidence, "refresh_snapshot", flaky)
    result = refresh(db, FakeRepo({"t2": repaired("t2"), "t3": repaired("t3")}), [gone, bad, boom], execute=False)
    stats = result["refresh"]
    assert (stats["missing_task"], stats["invalid_snapshot"], stats["build_errors"]) == (1, 1, 1)
    # a task deleted from the bank (404) is skipped with a warning like an inactive one: not a failure
    assert {f["status"] for f in result["refresh_details"]["failed"]} == {"invalid_snapshot", "build_errors"}
    assert result["refresh_details"]["missing_tasks"] == ["t1"]
    assert result["exit_code"] == script.EXIT_FAILURES


def test_null_snapshots_are_left_to_the_live_bank_read(db, tmp_path):
    sid = add_session(db, tasks=("t1",), with_snapshot=False, minute=1)
    repo = FakeRepo({"t1": repaired("t1")})
    result = refresh(db, repo, [sid], tmp_path)
    assert result["refresh"]["null_snapshot"] == 1 and result["refresh"]["refreshed"] == 0 and repo.calls == []
    assert result["queued"] == 1 and result["exit_code"] == 0


def test_all_tasks_are_fetched_before_any_write_transaction(db, tmp_path):
    sid = add_session(db, tasks=("t1", "t2"), minute=1)
    states = []
    repo = FakeRepo({"t1": repaired("t1"), "t2": repaired("t2")}, on_fetch=lambda _t: states.append(db.in_transaction()))
    refresh(db, repo, [sid], tmp_path)
    assert states == [False, False]                                         # no transaction held open during the HTTP calls


def test_an_answer_changed_in_the_meantime_makes_the_session_busy_and_nothing_of_it_is_kept(db, factory, tmp_path):
    sid = add_session(db, tasks=("t1", "t2"), minute=1)
    other = add_session(db, tasks=("t3",), minute=2)
    t2_id = db.query(DiagAnswer.id).filter(DiagAnswer.task_id == "t2").scalar()
    before = snapshots(db)

    def concurrent_edit(task_id):
        if task_id != "t2":
            return
        with factory() as second:
            row = second.query(DiagAnswer).filter(DiagAnswer.id == t2_id).one()
            row.task_snapshot = {**row.task_snapshot, "note": "changed by someone else"}
            second.commit()

    repo = FakeRepo({t: repaired(t) for t in ("t1", "t2", "t3")}, on_fetch=concurrent_edit)
    result = refresh(db, repo, [sid, other], tmp_path)
    assert result["refresh"]["skipped_concurrent"] == 2 and result["refresh"]["refreshed"] == 1
    after = snapshots(db)
    assert after[(sid, "t1")] == before[(sid, "t1")]                         # the whole session was rolled back
    assert after[(sid, "t2")]["note"] == "changed by someone else" and after[(sid, "t2")]["provenance"] == "issued"
    assert after[(other, "t3")]["provenance"] == "bank_refresh"              # other sessions are unaffected
    assert result["exit_code"] == script.EXIT_BUSY and result["refresh_details"]["busy_sessions"] == [sid]
    assert set(reports(db)) == {other}                                       # the busy session is not queued
    assert [r[4] for r in result["sessions"] if r[0] == str(sid)] == ["busy (generating): run again when the worker is idle"]


def test_backup_is_mandatory_for_a_write(db, tmp_path):
    sid = add_session(db, tasks=("t1",), minute=1)
    before = snapshots(db)
    with pytest.raises(report_jobs.BackupError, match="mandatory"):
        refresh(db, FakeRepo({"t1": repaired("t1")}), [sid])                  # no backup_path, no default under /app
    assert snapshots(db) == before and reports(db) == {}
    with pytest.raises(SystemExit):
        script.main(["--session-id", str(sid), "--refresh-task-content", "--execute"])


def test_no_backup_no_write(db, tmp_path):
    sid = add_session(db, tasks=("t1",), minute=1)
    before = snapshots(db)
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(report_jobs.BackupError):
        refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], backup_path=str(blocker / "backup.jsonl"))
    assert snapshots(db) == before and reports(db) == {}                    # nothing written, nothing queued
    taken = tmp_path / "exists.jsonl"
    taken.write_text("old", encoding="utf-8")
    with pytest.raises(report_jobs.BackupError):                           # an existing backup is never overwritten
        refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], backup_path=str(taken))
    assert taken.read_text(encoding="utf-8") == "old" and snapshots(db) == before


def test_a_generating_report_is_busy_not_rewritten_and_not_queued(db, tmp_path):
    busy = add_session(db, tasks=("t1",), report="generating", minute=1)
    waiting = add_session(db, tasks=("t2",), report="pending", minute=2)
    free = add_session(db, tasks=("t3",), report="current", minute=3)
    before = snapshots(db)
    repo = FakeRepo({t: repaired(t) for t in ("t1", "t2", "t3")})
    result = refresh(db, repo, [busy, waiting, free], tmp_path)
    after = snapshots(db)
    assert result["refresh"]["busy"] == 1 and result["exit_code"] == script.EXIT_BUSY
    assert after[(busy, "t1")] == before[(busy, "t1")]                      # the worker may be reading it: not rewritten
    assert after[(waiting, "t2")] != before[(waiting, "t2")]                # an unclaimed pending job reads the new snapshot
    assert after[(free, "t3")] != before[(free, "t3")]
    rows = reports(db)
    assert rows[busy].generation_status == "generating" and rows[waiting].generation_status == "pending"
    assert rows[free].generation_status == "pending" and report_jobs.is_deterministic_job(rows[free])
    assert result["refresh_details"]["busy_sessions"] == [busy]
    assert [r[4] for r in result["sessions"] if r[0] == str(busy)] == ["busy (generating): run again when the worker is idle"]
    assert result["queued"] == 1 and result["already_queued"] >= 1


@needs_postgres
def test_a_report_row_locked_by_the_worker_claim_is_busy(db, factory, tmp_path):
    sid = add_session(db, tasks=("t1",), report="pending", minute=1)
    before = snapshots(db)
    with factory() as worker:                                               # what _claim_next_report does: FOR UPDATE
        worker.query(DiagReport).filter(DiagReport.session_id == sid).with_for_update().first()
        result = refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], tmp_path)
        assert result["refresh"]["busy"] == 1 and result["exit_code"] == script.EXIT_BUSY
        worker.rollback()
    assert snapshots(db) == before


def test_pg_or_sqlite_jsonb_guard_matches_the_snapshot_that_was_read(db, tmp_path):
    """The WHERE task_snapshot = <old> guard must match a normal row (non-ASCII text, floats, nulls)."""
    sid = add_session(db, tasks=("t1",), minute=1)
    result = refresh(db, FakeRepo({"t1": repaired("t1", distractors=(("3", "Ёжик: «объяснение» ∑"), ("4", "x")))}), [sid], tmp_path)
    assert result["refresh"]["refreshed"] == 1 and result["refresh"]["skipped_concurrent"] == 0


# ── main() ────────────────────────────────────────────────────────────────────

@pytest.fixture
def repo_in_main(monkeypatch):
    holder = {}

    def install(repo):
        holder["repo"] = repo
        from src.repositories import knowledge_repo
        monkeypatch.setattr(knowledge_repo, "TaskRepository", lambda: repo)

    return install


def test_main_with_a_tasks_file_dry_run_then_execute(db, factory, tmp_path, repo_in_main):
    sid = add_session(db, tasks=("t1", "t2"), minute=1)
    other = add_session(db, tasks=("t9",), minute=2)
    ids = tmp_path / "ids.txt"
    ids.write_text("# repaired in wave w35\nt1, t2\n", encoding="utf-8")
    repo_in_main(FakeRepo({"t1": repaired("t1"), "t2": make_task("t2")}))
    before = snapshots(db)
    assert script.main(["--affected-by-tasks-file", str(ids), "--refresh-task-content"]) == 0
    assert snapshots(db) == before and reports(db) == {}                    # dry-run by default
    backup = tmp_path / "main.jsonl"
    assert script.main(["--affected-by-tasks-file", str(ids), "--refresh-task-content", "--execute",
                        "--backup", str(backup)]) == 0
    assert snapshots(db)[(sid, "t1")]["provenance"] == "bank_refresh" and snapshots(db)[(other, "t9")] == before[(other, "t9")]
    assert set(reports(db)) == {sid} and backup.exists()


def test_main_exit_codes(db, factory, tmp_path, repo_in_main):
    sid = add_session(db, tasks=("t1",), minute=1)
    repo_in_main(FakeRepo({}, broken=["t1"]))
    assert script.main(["--session-id", str(sid), "--refresh-task-content"]) == script.EXIT_FAILURES            # dry-run too
    assert script.main(["--session-id", str(sid), "--refresh-task-content", "--execute",
                        "--backup", str(tmp_path / "x.jsonl")]) == script.EXIT_FAILURES and reports(db) == {}
    repo_in_main(FakeRepo({"t1": repaired("t1")}))
    blocker = tmp_path / "f"
    blocker.write_text("x", encoding="utf-8")
    assert script.main(["--session-id", str(sid), "--refresh-task-content", "--execute",
                        "--backup", str(blocker / "b.jsonl")]) == script.EXIT_BACKUP and reports(db) == {}


def test_main_restore_mode_and_argument_checks(db, factory, tmp_path, repo_in_main):
    sid = add_session(db, tasks=("t1",), minute=1)
    original = snapshots(db)[(sid, "t1")]
    repo_in_main(FakeRepo({"t1": repaired("t1")}))
    backup = tmp_path / "b.jsonl"
    assert script.main(["--session-id", str(sid), "--refresh-task-content", "--execute", "--backup", str(backup)]) == 0
    refreshed = snapshots(db)[(sid, "t1")]
    assert script.main(["--restore-from", str(backup)]) == 0 and snapshots(db)[(sid, "t1")] == refreshed     # dry-run
    assert script.main(["--restore-from", str(backup), "--execute"]) == 0 and snapshots(db)[(sid, "t1")] == original
    for bad in (["--restore-from", str(backup), "--session-id", str(sid)], ["--backup", "x"], ["--allow-partial"],
                ["--refresh-task-content"]):
        with pytest.raises(SystemExit):
            script.main(bad)


# ── durable undo, backup copy-out, consistency ────────────────────────────────

def test_the_pre_image_is_kept_in_the_row_and_verified_against_its_hash(db, tmp_path):
    from src.domain.task_evidence import _digest, restore_previous_snapshot

    sid = add_session(db, tasks=("t1",), minute=1)
    original = snapshots(db)[(sid, "t1")]
    refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], tmp_path)
    refreshed = snapshots(db)[(sid, "t1")]
    last = refreshed["refresh_history"][-1]
    assert last["previous_task"] == original["task"] and _digest(last["previous_task"]) == last["previous_sha256"]
    assert restore_previous_snapshot(refreshed) == original                      # exactly the issued snapshot
    tampered = json.loads(json.dumps(refreshed))
    tampered["refresh_history"][-1]["previous_task"]["correct_answer"] = "999"
    with pytest.raises(ValueError, match="previous_sha256"):
        restore_previous_snapshot(tampered)
    for broken in (original, {**refreshed, "refresh_history": []}):
        with pytest.raises(ValueError):
            restore_previous_snapshot(broken)


def test_restore_last_needs_no_file_walks_back_and_requeues(db, tmp_path):
    sid = add_session(db, tasks=("t1",), minute=1)
    original = snapshots(db)[(sid, "t1")]
    refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], tmp_path, name="b1.jsonl")
    after_first = snapshots(db)[(sid, "t1")]
    reports(db)[sid].generation_status = "ready"
    db.commit()
    refresh(db, FakeRepo({"t1": repaired("t1", distractors=(("3", "СНОВА новое"), ("4", "Забыл знак")))}), [sid],
            tmp_path, name="b2.jsonl")
    after_second = snapshots(db)[(sid, "t1")]
    reports(db)[sid].generation_status = "ready"
    db.commit()

    dry = script.run_restore_last(session_ids=[sid], execute=False, db=db)
    assert dry["restore"]["would_restore"] == 1 and dry["exit_code"] == 0
    assert snapshots(db)[(sid, "t1")] == after_second and reports(db)[sid].generation_status == "ready"   # dry-run: no change
    done = script.run_restore_last(session_ids=[sid], execute=True, db=db)
    assert done["restore"]["restored"] == 1 and done["restore"]["queued"] == 1
    assert snapshots(db)[(sid, "t1")] == after_first
    row = reports(db)[sid]
    assert row.generation_status == "pending" and report_jobs.is_deterministic_job(row)       # re-queued, no LLM
    row.generation_status = "ready"
    db.commit()
    assert script.run_restore_last(session_ids=[sid], execute=True, db=db)["restore"]["restored"] == 1
    assert snapshots(db)[(sid, "t1")] == original
    again = script.run_restore_last(session_ids=[sid], execute=True, db=db)
    assert again["restore"]["not_refreshed"] == 1 and again["restore"]["restored"] == 0


def test_restore_last_selects_by_tasks_and_reports_unverifiable_rows(db, tmp_path):
    sid = add_session(db, tasks=("t1", "t2"), minute=1)
    refresh(db, FakeRepo({"t1": repaired("t1"), "t2": repaired("t2")}), [sid], tmp_path)
    row = db.query(DiagAnswer).filter(DiagAnswer.task_id == "t2").one()
    snap = json.loads(json.dumps(row.task_snapshot))
    snap["refresh_history"][-1]["previous_task"]["correct_answer"] = "999"
    row.task_snapshot = snap
    db.commit()
    result = script.run_restore_last(session_ids=[sid], task_ids=["t1"], execute=True, db=db)
    assert result["restore"]["restored"] == 1 and result["exit_code"] == 0              # only t1 was selected
    bad = script.run_restore_last(session_ids=[sid], task_ids=["t2"], execute=True, db=db)
    assert bad["restore"]["unverifiable"] == 1 and bad["exit_code"] == script.EXIT_FAILURES


def test_restore_takes_the_report_lock_skips_a_generating_session_and_requeues_the_rest(db, tmp_path):
    busy = add_session(db, tasks=("t1",), minute=1)
    free = add_session(db, tasks=("t2",), minute=2)
    refresh(db, FakeRepo({"t1": repaired("t1"), "t2": repaired("t2")}), [busy, free], tmp_path)
    for sid in (busy, free):
        reports(db)[sid].generation_status = "ready"
    db.commit()
    reports(db)[busy].generation_status = "generating"                           # the worker claimed it meanwhile
    db.commit()
    refreshed = snapshots(db)
    result = script.run_restore(backup_path=str(tmp_path / "backup.jsonl"), execute=True, db=db)
    assert result["restore"]["busy"] == 1 and result["restore"]["restored"] == 1 and result["restore"]["queued"] == 1
    assert result["exit_code"] == script.EXIT_BUSY
    after = snapshots(db)
    assert after[(busy, "t1")] == refreshed[(busy, "t1")] and after[(free, "t2")]["provenance"] == "issued"
    assert reports(db)[free].generation_status == "pending" and reports(db)[busy].generation_status == "generating"


def test_backup_to_stdout_keeps_stdout_clean_and_reports_rows_and_sha(db, capsys):
    sid = add_session(db, tasks=("t1", "t2"), minute=1)
    before = snapshots(db)
    result = refresh(db, FakeRepo({"t1": repaired("t1"), "t2": repaired("t2")}), [sid], backup_path="-")
    out = capsys.readouterr().out
    info = result["refresh_details"]["backup"]
    assert info["stdout"] and info["path"] == "-" and info["rows"] == 2
    assert hashlib.sha256(out.encode("utf-8")).hexdigest() == info["sha256"]
    rows = [json.loads(line) for line in out.splitlines()]                      # ONLY the JSONL on stdout
    assert len(rows) == 2 and {r["task_snapshot"]["task"]["id"] for r in rows} == {"t1", "t2"}
    assert {r["task_snapshot"]["sha256"] for r in rows} == {before[(sid, "t1")]["sha256"], before[(sid, "t2")]["sha256"]}


def test_main_prints_the_docker_cp_command_and_logs_to_stderr(db, factory, tmp_path, repo_in_main, caplog, capsys):
    import logging

    sid = add_session(db, tasks=("t1",), minute=1)
    repo_in_main(FakeRepo({"t1": repaired("t1")}))
    backup = tmp_path / "out.jsonl"
    with caplog.at_level(logging.INFO, logger="regenerate_reports"):
        assert script.main(["--session-id", str(sid), "--refresh-task-content", "--execute", "--backup", str(backup)]) == 0
    text = caplog.text
    assert f'docker cp "$HOSTNAME":{backup} ./' in text and "rows=1" in text
    assert hashlib.sha256(backup.read_bytes()).hexdigest() in text
    assert capsys.readouterr().out == ""                                        # nothing but a requested backup goes to stdout
    import inspect
    assert "stream=sys.stderr" in inspect.getsource(script.main)                # --backup - leaves stdout to the JSONL


def test_a_deleted_task_is_skipped_with_a_warning_and_the_session_is_still_queued(db, tmp_path):
    sid = add_session(db, tasks=("t1",), minute=1)
    before = snapshots(db)
    result = refresh(db, FakeRepo({}), [sid], tmp_path)                         # the bank answers 404 for t1
    assert result["refresh"]["missing_task"] == 1 and result["exit_code"] == 0
    assert result["refresh_details"]["missing_tasks"] == ["t1"] and result["refresh_details"]["failed"] == []
    assert snapshots(db) == before and result["queued"] == 1


def test_sessions_without_a_report_row_are_written_consistently_and_queued_afterwards(db, tmp_path):
    no_row = add_session(db, tasks=("t1",), minute=1)
    with_row = add_session(db, tasks=("t2",), report="current", minute=2)
    dry = refresh(db, FakeRepo({"t1": repaired("t1"), "t2": repaired("t2")}), [no_row, with_row], execute=False)
    assert dry["refresh"]["would_refresh"] == 2 and dry["refresh"]["busy"] == 0
    done = refresh(db, FakeRepo({"t1": repaired("t1"), "t2": repaired("t2")}), [no_row, with_row], tmp_path)
    assert done["refresh"]["refreshed"] == 2 and done["queued"] == 2
    assert set(reports(db)) == {no_row, with_row}


def test_dry_run_probes_the_same_busy_state_as_execute(db, tmp_path):
    busy = add_session(db, tasks=("t1",), report="generating", minute=1)
    result = refresh(db, FakeRepo({"t1": repaired("t1")}), [busy], execute=False)
    assert result["refresh"]["busy"] == 1 and result["exit_code"] == script.EXIT_BUSY


@needs_postgres
def test_dry_run_sees_a_report_row_locked_by_the_worker(db, factory):
    sid = add_session(db, tasks=("t1",), report="pending", minute=1)
    with factory() as worker:
        worker.query(DiagReport).filter(DiagReport.session_id == sid).with_for_update().first()
        result = refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], execute=False)
        assert result["refresh"]["busy"] == 1 and result["exit_code"] == script.EXIT_BUSY
        worker.rollback()
    assert refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], execute=False)["refresh"]["would_refresh"] == 1


@needs_postgres
def test_the_documented_plain_sql_fallback_restores_the_previous_snapshot(db, factory, tmp_path):
    import re
    from sqlalchemy import text

    sid = add_session(db, tasks=("t1",), minute=1)
    answer_id = db.query(DiagAnswer.id).scalar()
    original = snapshots(db)[(sid, "t1")]
    refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], tmp_path, name="b1.jsonl")
    reports(db)[sid].generation_status = "ready"
    db.commit()
    refresh(db, FakeRepo({"t1": repaired("t1", distractors=(("3", "СНОВА новое"), ("4", "Забыл знак")))}), [sid],
            tmp_path, name="b2.jsonl")
    sql = re.search(r"(UPDATE diag_answers a SET.*?WHERE a\.id = s\.id;)", script.__doc__, re.S).group(1)
    sql = re.sub(r"^ {9}", "", sql, flags=re.M).replace("<answer uuid>", str(answer_id))
    db.execute(text(sql))
    db.commit()
    step_back = snapshots(db)[(sid, "t1")]
    assert step_back["provenance"] == "bank_refresh" and len(step_back["refresh_history"]) == 1     # one refresh undone
    db.execute(text(sql))
    db.commit()
    assert snapshots(db)[(sid, "t1")] == original                                                  # all of them


# ── restore-last only undoes a row that is still the result of that refresh ───

def _rehash(snapshot):
    from src.domain.task_evidence import _digest
    return {**snapshot, "sha256": _digest(snapshot["task"])}


def test_restore_last_never_resurrects_old_content_over_a_later_change(db, tmp_path):
    sid = add_session(db, tasks=("t1",), minute=1)
    refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], tmp_path)
    row = db.query(DiagAnswer).one()
    edited = json.loads(json.dumps(row.task_snapshot))
    edited["task"]["question_text"] = "Исправлено вручную после обновления"
    row.task_snapshot = _rehash(edited)                                     # a valid, internally consistent newer state
    db.commit()
    kept = snapshots(db)[(sid, "t1")]
    result = script.run_restore_last(session_ids=[sid], execute=True, db=db)
    assert result["restore"]["diverged"] == 1 and result["restore"]["restored"] == 0
    assert result["exit_code"] == script.EXIT_FAILURES and snapshots(db)[(sid, "t1")] == kept

    broken = json.loads(json.dumps(kept))
    broken["task"]["question_text"] = "Правка без пересчёта хеша"
    row = db.query(DiagAnswer).one()
    row.task_snapshot = broken
    db.commit()
    assert script.run_restore_last(session_ids=[sid], execute=True, db=db)["restore"]["diverged"] == 1
    assert snapshots(db)[(sid, "t1")] == broken


def test_history_entries_without_result_sha256_are_unverifiable_unless_forced(db, tmp_path):
    sid = add_session(db, tasks=("t1",), minute=1)
    original = snapshots(db)[(sid, "t1")]
    refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], tmp_path)
    row = db.query(DiagAnswer).one()
    legacy = json.loads(json.dumps(row.task_snapshot))
    del legacy["refresh_history"][-1]["result_sha256"]                      # as written by an earlier build
    row.task_snapshot = legacy
    db.commit()
    refused = script.run_restore_last(session_ids=[sid], execute=True, db=db)
    assert refused["restore"]["unverifiable"] == 1 and refused["restore"]["restored"] == 0
    assert snapshots(db)[(sid, "t1")] == legacy
    forced = script.run_restore_last(session_ids=[sid], execute=True, force_legacy=True, db=db)
    assert forced["restore"]["restored"] == 1 and snapshots(db)[(sid, "t1")] == original
    # --force-legacy still demands an internally consistent row
    refresh(db, FakeRepo({"t1": repaired("t1")}), [sid], tmp_path, name="again.jsonl")
    row = db.query(DiagAnswer).one()
    tampered = json.loads(json.dumps(row.task_snapshot))
    del tampered["refresh_history"][-1]["result_sha256"]
    tampered["task"]["question_text"] = "без хеша"
    row.task_snapshot = tampered
    db.commit()
    assert script.run_restore_last(session_ids=[sid], execute=True, force_legacy=True, db=db)["restore"]["diverged"] == 1


def test_stdout_backup_is_written_as_bytes_independent_of_the_stdout_encoding(db, monkeypatch):
    import io
    import sys

    sid = add_session(db, tasks=("t1",), minute=1)
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="ascii", errors="strict"))   # a C / POSIX locale
    result = refresh(db, FakeRepo({"t1": repaired("t1", distractors=(("3", "Объяснение: ёжик ∑"), ("4", "x")))}), [sid],
                     backup_path="-")
    sys.stdout.flush()
    data = raw.getvalue()
    assert hashlib.sha256(data).hexdigest() == result["refresh_details"]["backup"]["sha256"]
    row = json.loads(data.decode("utf-8"))                                  # always UTF-8
    assert row["task_snapshot"]["task"]["id"] == "t1" and "Сложил вместо вычитания" in json.dumps(row, ensure_ascii=False)


def test_main_refuses_stdout_backup_with_debug_and_force_legacy_outside_restore_last(db, factory, monkeypatch):
    sid = add_session(db, tasks=("t1",), minute=1)
    monkeypatch.setattr(script, "get_settings", lambda: NS(debug=True))
    with pytest.raises(SystemExit):
        script.main(["--session-id", str(sid), "--refresh-task-content", "--execute", "--backup", "-"])
    with pytest.raises(SystemExit):
        script.main(["--session-id", str(sid), "--force-legacy"])
