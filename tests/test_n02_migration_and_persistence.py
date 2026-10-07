"""N02: migration 010 (up/down/up, lock_timeout) and persistence of the Deep Scan link."""
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.models.diag_models import DiagAnswer
from tests.test_completion_lifecycle import CODE, PAYLOAD, scenario, submit  # noqa: F401  (fixture)

DB_URL = os.environ.get("A2_TEST_DATABASE_URL")
ROOT = Path(__file__).parents[1]
NEW = ("deep_scan_origin_skill_id", "deep_scan_step")


def test_migration_010_sets_lock_timeout_before_alter_and_has_downgrade():
    source = (ROOT / "alembic" / "versions" / "010_deep_scan_origin_link.py").read_text()
    up = source.split("def upgrade")[1].split("def downgrade")[0]
    assert "SET LOCAL lock_timeout = '5s'" in up and up.index("lock_timeout") < up.index("add_column")
    down = source.split("def downgrade")[1]
    assert "SET LOCAL lock_timeout = '5s'" in down and down.index("lock_timeout") < down.index("drop_column")
    assert "down_revision = '009_answer_task_evidence'" in source


@pytest.mark.skipif(not DB_URL, reason="Requires disposable PostgreSQL")
def test_migration_010_up_down_up_keeps_legacy_rows_and_fails_fast_under_lock():
    assert make_url(DB_URL).database == "a2_diagnostic", "Require isolated CI database"
    name = "a2_n02_" + uuid.uuid4().hex[:12]
    admin = create_engine(make_url(DB_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    test_url = make_url(DB_URL).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(test_url)
    env = {**os.environ, "DATABASE_URL": test_url}

    def alembic(*args):
        return subprocess.run(["alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)

    def columns():
        with engine.connect() as conn:
            return {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='diag_answers'"))}

    try:
        assert alembic("upgrade", "009_answer_task_evidence").returncode == 0
        session_id, answer_id = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO diag_sessions(id,student_id,grade_level,phase) VALUES (:i,:s,9,'completed')"),
                         {"i": session_id, "s": uuid.uuid4()})
            conn.execute(text("INSERT INTO diag_answers(id,session_id,task_id,skill_id,topic_id,student_answer,outcome,is_deep_scan)"
                              " VALUES (:i,:s,'legacy','skill','topic','old',0,true)"), {"i": answer_id, "s": session_id})
        assert not set(NEW) & columns()

        # lock held -> migration fails fast, leaves the schema untouched
        blocker = engine.connect()
        tx = blocker.begin()
        blocker.execute(text("LOCK TABLE diag_answers IN ACCESS EXCLUSIVE MODE"))
        try:
            locked = alembic("upgrade", "head")
        finally:
            tx.rollback()
            blocker.close()
        assert locked.returncode != 0 and "lock timeout" in locked.stderr.lower()
        assert not set(NEW) & columns()

        assert alembic("upgrade", "head").returncode == 0 and set(NEW) <= columns()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT task_id, student_answer, deep_scan_origin_skill_id, deep_scan_step FROM diag_answers")).one()
            assert tuple(row) == ("legacy", "old", None, None)          # old answers: link unknown, not invented
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "010_deep_scan_origin_link"
        assert alembic("downgrade", "009_answer_task_evidence").returncode == 0 and not set(NEW) & columns()
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM diag_answers")) == 1
        assert alembic("upgrade", "head").returncode == 0 and set(NEW) <= columns()
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
        admin.dispose()


@pytest.mark.skipif(not DB_URL, reason="Requires disposable PostgreSQL/Redis")
def test_deep_scan_answer_records_origin_and_step(scenario):
    client, session_id, invite, factory, redis = scenario
    state = redis.load(str(session_id))
    state.phase, state.is_in_deep_scan = "deep_scan", True
    state.deep_scan = {"origin_skill_id": "A2_ORIGIN", "queue": [], "tested": ["P1", "P2"], "gaps": [],
                       "current_skill_id": "A2_SKILL", "max_items": 6, "items_used": 2, "completed": False}
    redis.save(state)
    assert submit(client, session_id).status_code == 200
    with factory() as db:
        row = db.query(DiagAnswer).one()
        assert row.is_deep_scan is True
        assert (row.deep_scan_origin_skill_id, row.deep_scan_step) == ("A2_ORIGIN", 3)
