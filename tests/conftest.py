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
