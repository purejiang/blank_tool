"""Tests for the module-level EnvironmentRegistry singleton (T16).

Asserts that ``app.env.registry.get_env_registry`` returns ONE process-wide
instance, that ``discover()`` is idempotent, and that the singleton is
initialized WITH the writable overlay (``<output_dir>/registry``).
"""

import os

import pytest

import app.env.registry as registry_module
from app.env.registry import get_env_registry


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """Reset the module-level singleton before each test."""
    monkeypatch.setattr(registry_module, "_default_registry", None)


def test_get_env_registry_returns_same_instance():
    """Two calls return the identical object (lazy singleton)."""
    a = get_env_registry()
    b = get_env_registry()
    assert a is b


def test_discover_is_idempotent():
    """Calling discover() repeatedly does not duplicate descriptors."""
    reg = get_env_registry()
    before = {resolved.name for resolved in reg.list_all()}
    reg.discover()
    after = {resolved.name for resolved in reg.list_all()}
    assert after == before


def test_singleton_uses_writable_overlay(tmp_path, monkeypatch):
    """The singleton is initialized with overlay_dir=<output_dir>/registry."""
    import app.utils.env as env_utils

    monkeypatch.setattr(env_utils, "get_output_dir", lambda: str(tmp_path))
    reg = get_env_registry()
    assert reg._overlay_dir == os.path.join(str(tmp_path), "registry")
