"""Backfill script: dry-run writes nothing, execute fills, re-run is a no-op, missing task stays NULL."""
import os
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from scripts import backfill_task_snapshots as bf
from src.domain.task_evidence import read_task
from src.core.db_timezone import utc_connect_args

ROOT = Path(__file__).parents[1]
BANK = {
    't-ok': NS(id='t-ok', skill_id='G7_S', question_text='Q', question_latex='$x=2$', question_image_url=None,
               correct_answer='2', correct_answer_latex='$2$', answer_type='mcq', sympy_solution=None,
               answer_options=['2', '1'], answer_options_latex=['$2$', '$1$'],
               distractor_meta=[{'value': '1', 'value_latex': '$1$', 'error_logic': 'why'}],
               irt_discrimination=1., irt_difficulty=0., irt_guessing=.25),
}


class Repo:
    def __init__(self, bank=BANK, broken=()):
        self.bank, self.broken, self.calls = bank, set(broken), []

    def get_by_id(self, task_id):
        self.calls.append(task_id)
        if task_id in self.broken:
            raise RuntimeError('content-service down')
        return self.bank.get(task_id)


@pytest.fixture(scope='module')
def engine():
    url = os.environ.get('A2_TEST_DATABASE_URL')
    assert url and make_url(url).database == 'a2_diagnostic', 'Require isolated CI database'
    name = 'a2_backfill_' + uuid.uuid4().hex[:12]
    admin = create_engine(make_url(url).set(database='postgres'), isolation_level='AUTOCOMMIT', connect_args=utc_connect_args(url))
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE {name}'))
    test_url = make_url(url).set(database=name).render_as_string(hide_password=False)
    result = subprocess.run(['alembic', 'upgrade', 'head'], cwd=ROOT, env={**os.environ, 'DATABASE_URL': test_url},
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-3000:]
    eng = create_engine(test_url, connect_args=utc_connect_args(test_url))
    yield eng
    eng.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE {name} WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def db(engine):
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM diag_answers'))
        conn.execute(text('DELETE FROM diag_sessions'))
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def seed(engine):
    """3 legacy rows (known task x2, missing task) + 1 row that already has a snapshot."""
    sid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO diag_sessions(id,student_id,grade_level,phase) VALUES (:i,:s,7,'completed')"),
                     {'i': sid, 's': uuid.uuid4()})
        for task_id, snap in (('t-ok', None), ('t-ok', None), ('t-gone', None), ('t-ok', '{"keep":"me"}')):
            conn.execute(text(
                "INSERT INTO diag_answers(id,session_id,task_id,skill_id,topic_id,student_answer,outcome,task_snapshot) "
                "VALUES (:i,:s,:t,'k','p','1',0,CAST(:snap AS jsonb))"),
                {'i': uuid.uuid4(), 's': sid, 't': task_id, 'snap': snap})
    return sid


def null_count(engine):
    with engine.connect() as conn:
        return conn.scalar(text('SELECT count(*) FROM diag_answers WHERE task_snapshot IS NULL'))


def test_dry_run_writes_nothing(engine, db):
    seed(engine)
    stats = bf.run(db, Repo(), execute=False)
    assert stats['examined'] == 3 and stats['would_fill'] == 2 and stats['missing_task'] == 1 and stats['filled'] == 0
    assert null_count(engine) == 3


def test_execute_fills_rerun_is_noop_and_missing_stays_null(engine, db):
    sid = seed(engine)
    stats = bf.run(db, Repo(), execute=True, batch_size=1)   # forces several batches/commits
    assert stats['filled'] == 2 and stats['missing_task'] == 1
    assert null_count(engine) == 1
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT task_id, task_snapshot FROM diag_answers WHERE task_snapshot IS NOT NULL")).all()
        assert any(r.task_snapshot == {'keep': 'me'} for r in rows)       # existing snapshot untouched
        filled = [r for r in rows if r.task_snapshot.get('provenance')]
    assert len(filled) == 2
    for row in filled:
        snap = row.task_snapshot
        assert snap['provenance'] == 'legacy_bank_backfill' and snap['backfill_source'] == bf.BACKFILL_SOURCE
        assert snap['backfilled_at']
        payload = read_task(snap, 't-ok')                                  # hash + envelope validate
        assert payload['correct_answer'] == '2' and sorted(payload['display_options']) == ['1', '2']
        # same deterministic shuffle the live service would use for this session/task
        options, _ = bf.build_diag_answer_options(BANK['t-ok'], seed=f'{sid}:t-ok')
        assert payload['display_options'] == options
    with engine.connect() as conn:
        before = conn.execute(text('SELECT id, task_snapshot FROM diag_answers ORDER BY id')).all()
    again = bf.run(db, Repo(), execute=True)
    assert again['filled'] == 0 and again['examined'] == 1 and again['missing_task'] == 1
    with engine.connect() as conn:
        assert conn.execute(text('SELECT id, task_snapshot FROM diag_answers ORDER BY id')).all() == before


def test_unreachable_content_service_leaves_null_and_is_counted(engine, db):
    seed(engine)
    stats = bf.run(db, Repo(broken={'t-ok'}), execute=True)
    assert stats['fetch_errors'] == 2 and stats['filled'] == 0 and stats['missing_task'] == 1
    assert null_count(engine) == 3


def test_task_is_fetched_once_per_run_and_limit_is_respected(engine, db):
    seed(engine)
    repo = Repo()
    bf.run(db, repo, execute=False)
    assert sorted(repo.calls) == ['t-gone', 't-ok']
    assert bf.run(db, Repo(), execute=False, limit=1)['examined'] == 1
