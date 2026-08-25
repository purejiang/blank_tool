"""Shared fixtures for workflow unit tests.

The engine's retry backoff (``WorkflowEngine._sleep_before_retry``) sleeps
for real seconds — that would make every retry-semantics test slow.  Retry
tests assert attempt COUNTS, not timing, so the backoff is neutralized here
for the whole directory.  The backoff policy itself is unit-tested directly
in ``test_retry_backoff.py`` (which re-patches the method where needed).
"""

import pytest

from app.workflow.engine import WorkflowEngine


@pytest.fixture(autouse=True)
def _no_retry_backoff(monkeypatch):
    """Replace the retry backoff sleep with a no-op for all workflow tests."""
    monkeypatch.setattr(
        WorkflowEngine,
        "_sleep_before_retry",
        lambda self, attempt, context: None,
    )
