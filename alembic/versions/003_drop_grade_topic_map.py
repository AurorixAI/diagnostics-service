"""Drop grade_topic_map table — data now served from knowledge_hierarchy.

Revision ID: 003_drop_grade_topic_map
Revises: 002_knowledge_tables
"""

from alembic import op
import sqlalchemy as sa

revision = "003_drop_grade_topic_map"
down_revision = "002_knowledge_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_gtm_grade", table_name="grade_topic_map")
    op.drop_table("grade_topic_map")


def downgrade() -> None:
    op.create_table(
        "grade_topic_map",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("grade_level", sa.Integer, nullable=False),
        sa.Column("topic_id", sa.String(30), nullable=False),
        sa.Column("section_id", sa.String(30), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("importance", sa.Integer, nullable=False, server_default="5"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.CheckConstraint("grade_level BETWEEN 5 AND 11", name="ck_gtm_grade"),
        sa.CheckConstraint("importance BETWEEN 1 AND 10", name="ck_gtm_importance"),
    )
    op.create_index("idx_gtm_grade", "grade_topic_map", ["grade_level"])
