"""Actual forward migration preserves legacy rows and leaves evidence unknown."""
import os
from pathlib import Path
import subprocess
import uuid
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url


def test_task_evidence_migration_preserves_legacy_answers():
    url=os.environ.get('A2_TEST_DATABASE_URL')
    assert url and make_url(url).database=='a2_diagnostic', 'Require isolated CI database'
    name='a2_evidence_'+uuid.uuid4().hex[:12]
    admin=create_engine(make_url(url).set(database='postgres'),isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:conn.execute(text(f'CREATE DATABASE {name}'))
    test_url=make_url(url).set(database=name).render_as_string(hide_password=False)
    engine=create_engine(test_url)
    root=Path(__file__).parents[1]
    env={**os.environ,'DATABASE_URL':test_url}
    def upgrade(revision):
        result=subprocess.run(['alembic','upgrade',revision],cwd=root,env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr[-3000:]
    try:
        upgrade('008_durable_auth_sync')
        session_id,student_id,answer_id=uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO diag_sessions(id,student_id,grade_level,phase) VALUES (:id,:student,9,'completed')"),{'id':session_id,'student':student_id})
            conn.execute(text("INSERT INTO diag_answers(id,session_id,task_id,skill_id,topic_id,student_answer,outcome) VALUES (:id,:session,'legacy','skill','topic','old',0)"),{'id':answer_id,'session':session_id})
        with engine.connect() as conn:before=conn.execute(text('SELECT id,task_id,student_answer,outcome FROM diag_answers')).all()
        upgrade('head')
        with engine.connect() as conn:
            assert conn.execute(text('SELECT id,task_id,student_answer,outcome FROM diag_answers')).all()==before
            assert conn.scalar(text('SELECT task_snapshot FROM diag_answers')) is None
            assert conn.scalar(text('SELECT version_num FROM alembic_version'))=='009_answer_task_evidence'
    finally:
        engine.dispose()
        with admin.connect() as conn:conn.execute(text(f'DROP DATABASE {name} WITH (FORCE)'))
        admin.dispose()


def test_migration_009_sets_lock_timeout_before_alter():
    source=(Path(__file__).parents[1]/'alembic'/'versions'/'009_answer_task_evidence.py').read_text()
    up=source.split('def upgrade')[1].split('def downgrade')[0]
    assert "SET LOCAL lock_timeout" in up and up.index('lock_timeout')<up.index('add_column')
    down=source.split('def downgrade')[1]
    assert "SET LOCAL lock_timeout" in down and down.index('lock_timeout')<down.index('drop_column')


def test_migration_009_fails_fast_when_diag_answers_is_locked_and_roundtrips():
    url=os.environ.get('A2_TEST_DATABASE_URL')
    assert url and make_url(url).database=='a2_diagnostic', 'Require isolated CI database'
    name='a2_locktimeout_'+uuid.uuid4().hex[:12]
    admin=create_engine(make_url(url).set(database='postgres'),isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:conn.execute(text(f'CREATE DATABASE {name}'))
    test_url=make_url(url).set(database=name).render_as_string(hide_password=False)
    engine=create_engine(test_url)
    root=Path(__file__).parents[1]
    env={**os.environ,'DATABASE_URL':test_url}
    def alembic(*args):
        return subprocess.run(['alembic',*args],cwd=root,env=env,capture_output=True,text=True)
    def has_column():
        with engine.connect() as conn:
            return bool(conn.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_name='diag_answers' AND column_name='task_snapshot'")))
    try:
        assert alembic('upgrade','008_durable_auth_sync').returncode==0
        blocker=engine.connect()
        tx=blocker.begin()
        blocker.execute(text('LOCK TABLE diag_answers IN ACCESS SHARE MODE'))
        blocker.execute(text('LOCK TABLE diag_answers IN ACCESS EXCLUSIVE MODE'))  # held until rollback
        try:
            result=alembic('upgrade','head')
        finally:
            tx.rollback();blocker.close()
        assert result.returncode!=0 and 'lock timeout' in result.stderr.lower()
        assert not has_column()
        # up / down / up
        assert alembic('upgrade','head').returncode==0 and has_column()
        assert alembic('downgrade','008_durable_auth_sync').returncode==0 and not has_column()
        assert alembic('upgrade','head').returncode==0 and has_column()
    finally:
        engine.dispose()
        with admin.connect() as conn:conn.execute(text(f'DROP DATABASE {name} WITH (FORCE)'))
        admin.dispose()
