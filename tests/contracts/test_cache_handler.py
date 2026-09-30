"""
Contract tests for Cache handler API methods.

Every test runs against tmp_path storage roots (autouse ``storage_roots``
fixture): these handlers delete directories, so pointing them at the real
output/cache/logs trees would destroy the developer's data.
"""
import json
import os

import pytest

from app.handlers import cache_handler

#: Managed output/ subdirs — user data that bulk clears must never touch.
#: ``task_defs`` holds saved task definitions (workflow + inputs).
MANAGED = ("workflows", "task_defs", "history", "runs", "registry")

#: Managed output/ plain file — the user plugin manifest (also user data).
PROTECTED_FILE = "plugins.json"


@pytest.fixture(autouse=True)
def storage_roots(tmp_path, monkeypatch):
    """Redirect every storage root at tmp_path."""
    output = tmp_path / "output"
    cache = tmp_path / "cache"
    logs = tmp_path / "logs"
    for directory in (output, cache, logs):
        directory.mkdir()
    monkeypatch.setenv("BT_OUTPUT_DIR", str(output))
    monkeypatch.setenv("BT_CACHE_DIR", str(cache))
    monkeypatch.delenv("BT_TASKS_DIR", raising=False)
    monkeypatch.setattr(cache_handler, "_logs_root", lambda: str(logs))
    return {"output": output, "cache": cache, "logs": logs}


def _seed_managed(roots, names=MANAGED, payload=b"userdata"):
    """Create each managed subdir with one file inside, plus plugins.json."""
    for name in names:
        subdir = roots["output"] / name
        subdir.mkdir(parents=True, exist_ok=True)
        (subdir / "keep.txt").write_bytes(payload)
    (roots["output"] / PROTECTED_FILE).write_text(
        json.dumps([{"module": "my_plugin", "kind": "native"}]),
        encoding="utf-8",
    )


def _call(api_handler, method, params=None, request_id=99):
    request = {"id": request_id, "method": method, "params": params or {}}
    response = api_handler.handle_request(request)
    data = json.loads(response) if isinstance(response, str) else response
    assert data["result"]["type"] == "success", data
    return data["result"]["payload"]


class TestCacheInfo:
    def test_valid_request_returns_success(self, api_handler):
        request = {"id": 51, "method": "cache.get_info", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 51
        assert "result" in data
        assert data["finished"] is True
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert "tasks" in payload
        assert "output" in payload
        assert "logs" in payload
        assert "total" in payload
        assert {"path", "size", "files"} <= set(payload["tasks"])
        assert {"path", "size", "files"} <= set(payload["output"])
        assert {"path", "size", "files"} <= set(payload["logs"])
        assert {"size", "files"} <= set(payload["total"])

    def test_cache_info_alias_works(self, api_handler):
        """cache.info should be the same as cache.get_info."""
        request = {"id": 52, "method": "cache.info", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 52
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert "tasks" in payload
        assert "output" in payload
        assert "logs" in payload
        assert "total" in payload

    def test_managed_blocks_report_the_managed_subdirs(self, api_handler, storage_roots):
        _seed_managed(storage_roots, payload=b"0123456789")

        payload = _call(api_handler, "cache.info")

        assert set(payload["managed"]) == set(MANAGED)
        for name in MANAGED:
            block = payload["managed"][name]
            assert {"path", "size", "files"} <= set(block)
            assert os.path.normcase(block["path"]) == os.path.normcase(
                str(storage_roots["output"] / name)
            )
            assert block["files"] == 1
            assert block["size"] == 10

    def test_managed_blocks_are_zero_when_missing(self, api_handler, storage_roots):
        payload = _call(api_handler, "cache.info")

        for name in MANAGED:
            assert payload["managed"][name]["size"] == 0
            assert payload["managed"][name]["files"] == 0


# cache.clear alias retired — storage.clear/output.clear/tasks.clear/logs.clear cover all use cases; zero renderer callers


class TestOutputClear:
    def test_valid_request_returns_success(self, api_handler):
        request = {"id": 54, "method": "output.clear", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 54
        result = data["result"]
        assert result["type"] == "success"

    def test_output_clear_keeps_managed_subdirs(self, api_handler, storage_roots):
        _seed_managed(storage_roots)
        loose = storage_roots["output"] / "loose.txt"
        loose.write_text("export", encoding="utf-8")

        payload = _call(api_handler, "output.clear")

        assert set(payload) == {"path", "size", "files"}
        assert not loose.exists(), "a plain export must still be cleared"
        assert (storage_roots["output"] / PROTECTED_FILE).exists(), (
            "the user plugin manifest must survive output.clear"
        )
        for name in MANAGED:
            assert (storage_roots["output"] / name / "keep.txt").exists()


class TestStorageClear:
    def test_clear_all_returns_success(self, api_handler):
        request = {
            "id": 55,
            "method": "storage.clear",
            "params": {"target": "all"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 55
        result = data["result"]
        assert result["type"] == "success"
        payload = result["payload"]
        assert payload["success"] is True
        assert "cleared_paths" in payload

    def test_clear_cache_only_returns_success(self, api_handler):
        request = {
            "id": 56,
            "method": "storage.clear",
            "params": {"target": "cache"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "success"

    def test_clear_all_defaults_to_skipping_managed_data(
        self, api_handler, storage_roots
    ):
        """#6: target:"all" must not wipe saved workflows / history / runs."""
        _seed_managed(storage_roots)
        loose = storage_roots["output"] / "loose.txt"
        loose.write_text("export", encoding="utf-8")
        (storage_roots["cache"] / "tasks").mkdir()
        task_file = storage_roots["cache"] / "tasks" / "t.bin"
        task_file.write_text("task", encoding="utf-8")
        log_file = storage_roots["logs"] / "backend.log"
        log_file.write_text("log", encoding="utf-8")

        payload = _call(api_handler, "storage.clear", {"target": "all"})

        assert payload["success"] is True
        assert not loose.exists()
        assert not task_file.exists()
        assert not log_file.exists()
        for name in MANAGED:
            assert (storage_roots["output"] / name).is_dir(), f"{name}/ was deleted"
            assert (storage_roots["output"] / name / "keep.txt").exists()
        assert (storage_roots["output"] / PROTECTED_FILE).exists(), (
            "target:all must not drop the user plugin manifest"
        )

    def test_clear_output_target_skips_managed_data(self, api_handler, storage_roots):
        _seed_managed(storage_roots)
        loose = storage_roots["output"] / "loose.txt"
        loose.write_text("export", encoding="utf-8")

        payload = _call(api_handler, "storage.clear", {"target": "output"})

        assert payload["success"] is True
        assert not loose.exists()
        assert (storage_roots["output"] / PROTECTED_FILE).exists()
        for name in MANAGED:
            assert (storage_roots["output"] / name / "keep.txt").exists()

    @pytest.mark.parametrize(
        "target", ["workflows", "task_defs", "history", "runs", "registry"]
    )
    def test_single_managed_target_clears_exactly_that_dir(
        self, api_handler, storage_roots, target
    ):
        _seed_managed(storage_roots)

        payload = _call(api_handler, "storage.clear", {"target": target})

        assert payload["success"] is True
        assert os.path.normcase(str(storage_roots["output"] / target)) in {
            os.path.normcase(p) for p in payload["cleared_paths"]
        }
        assert (storage_roots["output"] / target).is_dir()
        assert list((storage_roots["output"] / target).iterdir()) == []
        for other in MANAGED:
            if other == target:
                continue
            assert (storage_roots["output"] / other / "keep.txt").exists(), (
                f"target={target} also cleared {other}/"
            )

    def test_include_managed_true_restores_the_old_full_wipe(
        self, api_handler, storage_roots
    ):
        _seed_managed(storage_roots)

        payload = _call(
            api_handler, "storage.clear", {"target": "all", "include_managed": True}
        )

        assert payload["success"] is True
        for name in MANAGED:
            assert not (storage_roots["output"] / name).exists(), (
                f"{name}/ survived include_managed:true"
            )
        assert not (storage_roots["output"] / PROTECTED_FILE).exists(), (
            "include_managed:true must restore the old full wipe"
        )

    def test_include_managed_false_is_the_default(self, api_handler, storage_roots):
        _seed_managed(storage_roots, names=("history",))

        _call(api_handler, "storage.clear", {"target": "all", "include_managed": False})

        assert (storage_roots["output"] / "history" / "keep.txt").exists()


class TestResponseShape:
    METHODS = [
        "cache.get_info",
        "cache.info",
        "output.clear",
        "storage.clear",
    ]

    def test_all_methods_produce_valid_response_shape(self, api_handler):
        for method in self.METHODS:
            request = {"id": 500, "method": method, "params": {}}
            resp = api_handler.handle_request(request)
            data = json.loads(resp) if isinstance(resp, str) else resp
            assert "id" in data, f"{method}: missing id"
            assert "result" in data, f"{method}: missing result"
            assert "finished" in data, f"{method}: missing finished"
