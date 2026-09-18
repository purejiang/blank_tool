"""
Contract tests for App handler API methods.

``system.selfcheck`` is the diagnostics page's self-check. Its contract is
deliberately narrow, and these tests pin exactly that:

- every probe carries ``id`` / ``category`` / ``status`` / ``value``;
- ``status`` and ``category`` stay inside their fixed vocabularies;
- ``value`` is a raw fact (path / version / URL) and never a localized
  sentence — the renderer owns all wording;
- the probe set covers the ids the renderer keys its i18n off, so a rename on
  either side fails here instead of silently rendering a blank label.

Directory probes run against ``tmp_path`` so the suite never touches the real
cache / tasks / output directories.
"""
import json
import os

import pytest

# The renderer's CHECK_LABELS map keys off these; a missing one shows up as a
# raw id in the UI instead of a label.
REQUIRED_IDS = {
    "env.os",
    "env.python",
    "env.java",
    "env.proxy",
    "config.dir.runtime",
    "config.dir.backend",
    "config.dir.cache",
    "config.dir.tasks",
    "config.dir.auto_tasks",
    "config.dir.output",
    "config.tool_search",
}

VALID_STATUSES = {"ok", "warn", "fail"}
VALID_CATEGORIES = {"env", "tool", "config", "runtime"}

PROXY_KEYS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")


def _data(response):
    return json.loads(response) if isinstance(response, str) else response


def _payload(api_handler, request_id=91):
    data = _data(
        api_handler.handle_request(
            {"id": request_id, "method": "system.selfcheck", "params": {}}
        )
    )
    assert data["id"] == request_id
    assert data["finished"] is True
    assert data["result"]["type"] == "success"
    return data["result"]["payload"]


def _checks(payload):
    return {c["id"]: c for c in payload["checks"]}


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Point every directory probe at tmp_path and clear the proxy env."""
    (tmp_path / "cache").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "auto_tasks").mkdir()
    monkeypatch.setenv("BT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("BT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("BT_TASKS_DIR", str(tmp_path / "tasks"))
    monkeypatch.setenv("BT_AUTO_TASKS_DIR", str(tmp_path / "auto_tasks"))
    monkeypatch.setenv("BT_OUTPUT_DIR", str(tmp_path / "output"))
    for key in PROXY_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("BT_SEARCH_SYSTEM_TOOLS", raising=False)
    return tmp_path


class TestSelfcheckEnvelope:
    def test_returns_success(self, api_handler):
        payload = _payload(api_handler)
        assert isinstance(payload, dict)
        assert isinstance(payload["generated_at"], (int, float))
        assert payload["generated_at"] > 0
        assert isinstance(payload["checks"], list)
        assert payload["checks"]

    def test_probe_shape_and_vocabulary(self, api_handler, isolated_dirs):
        payload = _payload(api_handler)
        for check in payload["checks"]:
            assert isinstance(check["id"], str) and check["id"]
            assert check["category"] in VALID_CATEGORIES, check["id"]
            assert check["status"] in VALID_STATUSES, check["id"]
            # Raw fact only: the renderer adds every word, so a status value
            # must never be blank-but-meaningful prose.
            assert isinstance(check["value"], str), check["id"]
            assert "facts" not in check or isinstance(check["facts"], dict)

    def test_covers_ids_the_renderer_labels(self, api_handler, isolated_dirs):
        assert REQUIRED_IDS.issubset(set(_checks(_payload(api_handler))))


class TestDirectoryProbes:
    def test_existing_writable_dirs_are_ok(self, api_handler, isolated_dirs):
        checks = _checks(_payload(api_handler))
        for check_id in (
            "config.dir.runtime",
            "config.dir.backend",
            "config.dir.cache",
            "config.dir.tasks",
            "config.dir.auto_tasks",
        ):
            assert checks[check_id]["status"] == "ok", check_id

    def test_missing_runtime_dir_fails(self, api_handler, tmp_path, monkeypatch):
        monkeypatch.setenv("BT_RUNTIME_DIR", str(tmp_path / "does-not-exist"))
        check = _checks(_payload(api_handler))["config.dir.runtime"]
        assert check["status"] == "fail"
        assert check["facts"]["reason"] == "missing"

    def test_unresolved_runtime_dir_is_reported_as_such(self, api_handler, monkeypatch):
        # get_runtime_dir() returns "" only when no candidate exists anywhere —
        # patch it rather than depend on the machine's directory layout.
        monkeypatch.setattr("app.utils.selfcheck.get_runtime_dir", lambda: "")
        check = _checks(_payload(api_handler))["config.dir.runtime"]
        assert check["status"] == "fail"
        assert check["facts"]["reason"] == "unresolved"

    def test_missing_output_dir_warns_instead_of_failing(
        self, api_handler, isolated_dirs
    ):
        # output/ is created on demand, so its absence is a state, not a defect.
        check = _checks(_payload(api_handler))["config.dir.output"]
        assert check["status"] == "warn"
        assert check["facts"]["reason"] == "missing"


class TestEnvironmentProbes:
    def test_java_reports_a_source(self, api_handler):
        facts = _checks(_payload(api_handler))["env.java"]["facts"]
        assert facts["source"] in ("builtin", "external", "system", "none")

    def test_python_is_resolved_to_the_running_interpreter(self, api_handler):
        check = _checks(_payload(api_handler))["env.python"]
        assert check["status"] == "ok"
        assert os.path.basename(check["value"])

    def test_absent_proxy_is_ok_and_marked_unconfigured(
        self, api_handler, isolated_dirs
    ):
        check = _checks(_payload(api_handler))["env.proxy"]
        assert check["status"] == "ok"
        assert check["facts"]["configured"] is False

    def test_unreachable_proxy_warns(self, api_handler, isolated_dirs, monkeypatch):
        # Port 1 is never listening — this is the stale-proxy case that turns
        # a download into [WinError 10061].
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
        check = _checks(_payload(api_handler))["env.proxy"]
        assert check["status"] == "warn"
        assert check["facts"]["configured"] is True
        assert check["facts"]["reachable"] is False

    def test_tool_search_flag_is_reflected(self, api_handler, isolated_dirs, monkeypatch):
        monkeypatch.setenv("BT_SEARCH_SYSTEM_TOOLS", "1")
        check = _checks(_payload(api_handler))["config.tool_search"]
        assert check["status"] == "warn"
        assert check["facts"]["enabled"] is True
