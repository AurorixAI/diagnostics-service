"""[SUPERSEDED] Knowledge tables live in content-service (algo_content DB).
Diagnostic service reads them via CONTENT_DB_URL — no local copies needed.

Revision ID: 002_knowledge_tables
Revises: 001_diag_tables
Create Date: 2026-05-06
"""
revision = "002_knowledge_tables"
down_revision = "001_diag_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
