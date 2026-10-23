"""
Contract tests for the tool probe cache and the probe warm-up.

Why this exists: probing a tool costs up to two subprocess launches (four of
the seven tools are JVM cold starts) and used to run on every launch. The cache
is what makes a warm start free, so its reuse/expiry rules are pinned here —
with no real subprocesses involved.

The counter below sits in ``probe()``, not ``__init__``: a cache hit still
*constructs* the tool (that is the point — it gets its path/version from the
cache) but must never run a probe.
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.tools import probe_cache
from app.tools.base_tool import BaseTool
from app.tools.tool_manager import ToolRegistry


class CountingTool(BaseTool):
    """Minimal tool whose probe cost is observable instead of a real launch."""

    probe_calls = 0

    def probe(self):
        CountingTool.probe_calls += 1
        if not self.tool_path:
            return False, ""
        return True, "9.9.9"

    def _validate_tool(self):  # pragma: no cover - probe() overrides it
        return bool(self.tool_path)

    def _get_possible_tool_names(self):
        return ["counting-tool"]

    def _get_tool_version(self):  # pragma: no cover - probe() overrides it
        return "9.9.9"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated cache dir + runtime dir; a fresh probe counter per test."""
    monkeypatch.setenv("BT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("BT_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("APP_VERSION", "9.9.9-test")
    monkeypatch.delenv("BT_SEARCH_SYSTEM_TOOLS", raising=False)
    monkeypatch.delenv("BT_TOOL_PROBE_TTL", raising=False)
    CountingTool.probe_calls = 0
    return tmp_path


def make_registry(binary_path):
    """A registry with exactly one tool, resolving to *binary_path*."""
    registry = ToolRegistry()
    registry._discovered = {"counting-tool": CountingTool}
    registry._default_tool_path = lambda key: str(binary_path)
    return registry


def write_binary(tmp_path, name="counting-tool.exe", payload="binary"):
    path = tmp_path / "runtime" / "fake" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Reuse rules
# ---------------------------------------------------------------------------

class TestProbeReuse:
    def test_new_registry_reuses_the_cached_verdict(self, env):
        binary = write_binary(env)

        first = make_registry(binary).get("counting-tool")
        assert CountingTool.probe_calls == 1
        assert first.is_valid is True
        assert first.version == "9.9.9"

        # A new registry == a new app launch. Same binary, same cache → free.
        second = make_registry(binary).get("counting-tool")
        assert CountingTool.probe_calls == 1, "a cache hit must not re-probe"
        assert second.is_valid is True
        assert second.version == "9.9.9"
        assert second.tool_path == str(binary)

    def test_replaced_binary_invalidates_the_entry(self, env):
        binary = write_binary(env)
        make_registry(binary).get("counting-tool")
        assert CountingTool.probe_calls == 1

        # Same path, different content (size changes too).
        binary.write_text("binary-v2-much-longer", encoding="utf-8")

        make_registry(binary).get("counting-tool")
        assert CountingTool.probe_calls == 2, "a changed binary must be re-probed"

    def test_removed_binary_is_not_kept_valid(self, env):
        binary = write_binary(env)
        make_registry(binary).get("counting-tool")
        before = CountingTool.probe_calls

        os.remove(binary)

        tool = make_registry(binary).get("counting-tool")
        assert CountingTool.probe_calls > before, "a vanished binary must be re-probed"
        assert tool.is_valid is False

    def test_different_resolution_is_not_a_hit(self, env):
        binary = write_binary(env)
        make_registry(binary).get("counting-tool")
        assert CountingTool.probe_calls == 1

        other = write_binary(env, name="other.exe")

        # Same tool, different path → different key → must probe again.
        make_registry(other).get("counting-tool")
        assert CountingTool.probe_calls == 2

    def test_custom_path_override_is_not_confused_with_the_default(self, env):
        binary = write_binary(env)
        registry = make_registry(binary)
        registry.get("counting-tool")
        assert CountingTool.probe_calls == 1

        override = write_binary(env, name="custom.exe", payload="custom")
        registry.set_custom_path("counting-tool", str(override))
        assert CountingTool.probe_calls == 2, "an override must be re-validated"

        assert registry.get("counting-tool").tool_path == str(override)
        assert CountingTool.probe_calls == 2, "the resolved instance is reused"

        # A fresh launch resolving the default path must never pick up the
        # custom-path verdict. The document keeps one entry slot per tool, so
        # the override evicted the default verdict and this costs one probe —
        # that is the intended trade: switching resolution is a user action,
        # and re-probing once is cheaper than tracking one entry per key.
        fresh = make_registry(binary).get("counting-tool")
        assert fresh.tool_path == str(binary)
        assert fresh.is_valid is True
        assert CountingTool.probe_calls == 3


class TestNegativeEntries:
    def test_unresolved_tool_is_cached_briefly(self, env):
        missing = env / "runtime" / "fake" / "nope.exe"

        tool = make_registry(missing).get("counting-tool")
        assert tool.is_valid is False
        after_first = CountingTool.probe_calls
        assert after_first > 0

        make_registry(missing).get("counting-tool")
        assert CountingTool.probe_calls == after_first, "a negative result must be reused"

    def test_unresolved_tool_expires_after_its_ttl(self, env, monkeypatch):
        missing = env / "runtime" / "fake" / "nope.exe"
        make_registry(missing).get("counting-tool")
        after_first = CountingTool.probe_calls

        monkeypatch.setenv("BT_TOOL_PROBE_TTL", "0")

        make_registry(missing).get("counting-tool")
        assert CountingTool.probe_calls > after_first, "an expired negative entry must re-probe"


class TestEnvironmentFingerprint:
    def test_changed_app_version_drops_every_entry(self, env, monkeypatch):
        binary = write_binary(env)
        make_registry(binary).get("counting-tool")
        assert CountingTool.probe_calls == 1
        assert probe_cache.load()["tools"], "expected a stored entry"

        monkeypatch.setenv("APP_VERSION", "9.9.10-test")
        assert probe_cache.load()["tools"] == {}, "a new build must not reuse verdicts"

        make_registry(binary).get("counting-tool")
        assert CountingTool.probe_calls == 2


# ---------------------------------------------------------------------------
# Document handling
# ---------------------------------------------------------------------------

class TestDocumentHandling:
    def test_corrupt_json_is_a_cache_miss_not_a_crash(self, env):
        path = probe_cache.cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json at all")

        assert probe_cache.load()["tools"] == {}

    def test_wrong_schema_is_a_cache_miss(self, env):
        path = probe_cache.cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"schema": probe_cache.SCHEMA_VERSION + 1, "tools": {"x": {}}}, f)

        assert probe_cache.load()["tools"] == {}

    def test_store_then_lookup_round_trip(self, env):
        binary = write_binary(env)
        doc = probe_cache.new_doc()
        key = probe_cache.make_key(
            "counting-tool", search_system=False, default_path=str(binary)
        )
        probe_cache.store(doc, key, path=str(binary), is_valid=True, version="1.2.3")

        entry = probe_cache.get_entry(doc, key)
        assert entry is not None
        assert entry["version"] == "1.2.3"
        assert entry["mtime_ns"] == os.stat(binary).st_mtime_ns

        probe_cache.invalidate(doc, "counting-tool")
        assert probe_cache.get_entry(doc, key) is None

    def test_save_and_load_survive_a_round_trip(self, env):
        binary = write_binary(env)
        doc = probe_cache.new_doc()
        key = probe_cache.make_key(
            "counting-tool", search_system=False, default_path=str(binary)
        )
        probe_cache.store(doc, key, path=str(binary), is_valid=True, version="1.2.3")
        probe_cache.save(doc)

        assert probe_cache.get_entry(probe_cache.load(), key)["version"] == "1.2.3"

    def test_probe_failure_does_not_write_a_verdict(self, env):
        """An exception while probing is not a result — nothing to cache."""
        binary = write_binary(env)

        class Exploding(CountingTool):
            def probe(self):
                raise RuntimeError("boom")

        registry = make_registry(binary)
        registry._discovered = {"counting-tool": Exploding}

        assert registry.probe_all() == {"counting-tool": None}
        assert probe_cache.load()["tools"] == {}


# ---------------------------------------------------------------------------
# Handler wiring
# ---------------------------------------------------------------------------

class TestGetToolsWiring:
    """`tool.get_tools` must warm the registry before building its report."""

    @pytest.fixture
    def manager(self, monkeypatch):
        from app.handlers import tool_handler

        stub = MagicMock()
        stub.last_probe_ms = 12
        stub.get_tool.side_effect = lambda name: (
            None if name == "nonexistent" else SimpleNamespace(
                is_valid=True, version="1.0", tool_path=f"/fake/{name}"
            )
        )
        monkeypatch.setattr(tool_handler, "manager", stub)
        return tool_handler, stub

    def test_warms_every_tool_once(self, manager):
        tool_handler, stub = manager

        report = tool_handler.get_tools({}, None)

        stub.ensure_all_probed.assert_called_once()
        assert set(report) == {
            "adb", "apktool", "apksigner", "zipalign", "aapt",
            "bundletool", "jarsigner",
        }
        for item in report.values():
            assert set(item) == {"is_valid", "version", "path", "source", "status"}
            assert item["status"] == "available"

    def test_refresh_invalidates_before_reporting(self, manager):
        tool_handler, stub = manager

        tool_handler.get_tools({"refresh": True}, None)

        stub.refresh_tools.assert_called_once()
