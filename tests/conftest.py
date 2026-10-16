"""Shared pytest fixtures."""
import pytest


@pytest.fixture(autouse=True)
def _fresh_abuse_limits():
    """Invite-lookup counters are process-wide: every test starts (and leaves) them empty."""
    from src.core.abuse_limit import counters

    counters.reset()
    yield
    counters.reset()
