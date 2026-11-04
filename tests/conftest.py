"""Shared pytest fixtures."""
import pytest


@pytest.fixture(autouse=True)
def _fresh_abuse_limits():
    """Invite-lookup counters are process-wide: every test starts (and leaves) them empty."""
    from src.core.abuse_limit import counters

    counters.reset()
    yield
    counters.reset()


@pytest.fixture(autouse=True)
def _fresh_hierarchy_cache():
    """The knowledge-hierarchy cache is process-wide (WC-B P-01): every test starts and leaves it empty."""
    from src.repositories.knowledge_repo import clear_hierarchy_cache

    clear_hierarchy_cache()
    yield
    clear_hierarchy_cache()


@pytest.fixture(autouse=True)
def _report_plan_without_a_bank(monkeypatch):
    """N03b-2: a report reads the bank (is a task still active; which active tasks a skill has).  No test talks to content-service by accident:
    by default every task is active and every skill has no free task.  A test that needs a bank replaces these two functions itself."""
    from src.domain import report_plan

    monkeypatch.setattr(report_plan, "bank_task_is_active", lambda task_id: True)
    monkeypatch.setattr(report_plan, "bank_unused_tasks", lambda skill_id, exclude_ids, hardest_first=False: [])
    yield
