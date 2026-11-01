"""One answer per task in an attempt: UNIQUE (session_id, task_id) on diag_answers (B-06).

Revision ID: 013_unique_answer_per_task
Revises: 012_auth_sync_backoff

A repeated request after a lost Redis write used to add a second row for the same task (double counting in the
report).  The service now answers a repeat from the stored row; this index is the last barrier.

The migration NEVER deletes or merges answers.  If duplicates exist it stops with a message and the service does
not start; check production first with ``artifacts/code_audit_2410/wb_p2_prod_dupes.sh`` (read-only counts).
"""
from alembic import op
import sqlalchemy as sa

revision = '013_unique_answer_per_task'
down_revision = '012_auth_sync_backoff'
branch_labels = None
depends_on = None

_INDEX = 'uq_diag_answers_session_task'


def upgrade():
    row = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) AS pairs, COUNT(DISTINCT session_id) AS sessions, COALESCE(SUM(n - 1), 0) AS extra_rows "
        "FROM (SELECT session_id, COUNT(*) AS n FROM diag_answers GROUP BY session_id, task_id HAVING COUNT(*) > 1) d"
    )).one()
    if row.pairs:
        sample = [
            str(r[0]) for r in op.get_bind().execute(sa.text(
                "SELECT DISTINCT session_id FROM diag_answers GROUP BY session_id, task_id "
                "HAVING COUNT(*) > 1 LIMIT 5"
            ))
        ]
        raise RuntimeError(
            "Cannot add UNIQUE (session_id, task_id) to diag_answers: "
            f"{row.pairs} task(s) in {row.sessions} session(s) have more than one answer row "
            f"({row.extra_rows} extra rows; sample session ids: {', '.join(sample)}). "
            "Nothing was changed. Review these attempts by hand (the report counts both rows), "
            "remove or merge the duplicates, then start the service again."
        )
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.create_index(_INDEX, 'diag_answers', ['session_id', 'task_id'], unique=True)


def downgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_index(_INDEX, table_name='diag_answers')
