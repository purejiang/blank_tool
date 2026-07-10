"""
Contract tests for APK handler API methods.
"""
import json


class TestApkAnalyze:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 11, "method": "apk.analyze", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 11
        result = data["result"]
        assert result["type"] == "error"

    def test_nonexistent_apk_path_returns_error(self, api_handler):
        request = {
            "id": 12,
            "method": "apk.analyze",
            "params": {"apk_path": "/nonexistent/path/test.apk"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 12
        assert data["finished"] is True
        result = data["result"]
        assert result["type"] == "error"


class TestApkGetInfo:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 13, "method": "apk.getInfo", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestApkDecompile:
    def test_missing_file_path_returns_error(self, api_handler):
        request = {"id": 14, "method": "apk.decompile", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestApkRecompile:
    def test_missing_project_path_returns_error(self, api_handler):
        request = {"id": 15, "method": "apk.recompile", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestApkSign:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 16, "method": "apk.sign", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        result = data["result"]
        assert result["type"] == "error"


class TestApkGetProgress:
    def test_valid_request_returns_success(self, api_handler):
        request = {
            "id": 17,
            "method": "apk.get_progress",
            "params": {"task_id": "task-1", "output_dir": "/tmp"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 17
        assert "result" in data
        assert data["finished"] is True


class TestApkCancelTask:
    def test_valid_request_returns_response(self, api_handler):
        request = {
            "id": 18,
            "method": "apk.cancel_task",
            "params": {"task_id": "task-1"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        assert data["id"] == 18
        assert "result" in data
        assert data["finished"] is True


class TestResponseShape:
    """Verify all APK handler methods produce protocol-compliant responses."""

    METHODS = [
        "apk.analyze",
        "apk.getInfo",
        "apk.decompile",
        "apk.recompile",
        "apk.sign",
        "apk.get_progress",
        "apk.cancel_task",
    ]

    def test_all_methods_produce_valid_response_shape(self, api_handler):
        """Each registered method must return id, result, finished."""
        for method in self.METHODS:
            request = {"id": 100, "method": method, "params": {}}
            resp = api_handler.handle_request(request)
            data = json.loads(resp) if isinstance(resp, str) else resp
            assert "id" in data, f"{method}: missing id"
            assert "result" in data, f"{method}: missing result"
            assert "finished" in data, f"{method}: missing finished"


# ---------------------------------------------------------------------------
# Per-task output directory routing tests
# ---------------------------------------------------------------------------

class TestDecompileUsesTaskDir:
    """apk_decompile should route output to Tasks/{task_id}/output/decompiled/."""

    def test_decompile_uses_task_dir(self):
        """When task_id is provided, output_dir uses get_task_subdir(task_id, 'output')."""
        from unittest.mock import patch, MagicMock

        fake_apk = "/tmp/test.apk"
        apktool_mock = MagicMock()
        apktool_mock.is_valid = True
        apktool_mock.execute.return_value = {"returncode": 0, "stdout": ""}
        mgr_mock = MagicMock()
        mgr_mock.get_tool.return_value = apktool_mock

        with patch("app.handlers.apk_handler.manager", mgr_mock), \
             patch("app.handlers.apk_handler.os.path.exists", return_value=True), \
             patch("app.handlers.apk_handler.os.makedirs"):
            from app.handlers.apk_handler import apk_decompile
            result = apk_decompile(
                {"file_path": fake_apk, "options": {"task_id": "my-task-123"}},
                stream_handler=None,
            )

        assert "tasks" in result["output_dir"]
        assert "my-task-123" in result["output_dir"]
        assert result["output_dir"].endswith("test")

    def test_decompile_fallback_no_task_id(self):
        """Without task_id, output_dir falls back to Output/decompiled/."""
        from unittest.mock import patch, MagicMock

        fake_apk = "/tmp/test.apk"
        apktool_mock = MagicMock()
        apktool_mock.is_valid = True
        apktool_mock.execute.return_value = {"returncode": 0, "stdout": ""}
        mgr_mock = MagicMock()
        mgr_mock.get_tool.return_value = apktool_mock

        with patch("app.handlers.apk_handler.manager", mgr_mock), \
             patch("app.handlers.apk_handler.os.path.exists", return_value=True), \
             patch("app.handlers.apk_handler.os.makedirs"):
            from app.handlers.apk_handler import apk_decompile
            result = apk_decompile(
                {"file_path": fake_apk, "options": {}},
                stream_handler=None,
            )

        assert "tasks" not in result["output_dir"]
        assert "decompiled" in result["output_dir"]
        assert result["output_dir"].endswith("test")


class TestRecompileUsesTaskDir:
    """apk_recompile should route output to Tasks/{task_id}/output/recompiled/."""

    def test_recompile_uses_task_dir(self):
        """When task_id is provided, output_apk goes under Tasks/{id}/output/recompiled/."""
        from unittest.mock import patch, MagicMock

        fake_project = "/tmp/my_project"
        apktool_mock = MagicMock()
        apktool_mock.is_valid = True
        apktool_mock.execute.return_value = {"returncode": 0, "stdout": ""}
        mgr_mock = MagicMock()
        mgr_mock.get_tool.return_value = apktool_mock

        with patch("app.handlers.apk_handler.manager", mgr_mock), \
             patch("app.handlers.apk_handler.os.path.exists", return_value=True), \
             patch("app.handlers.apk_handler.os.makedirs"):
            from app.handlers.apk_handler import apk_recompile
            result = apk_recompile(
                {
                    "project_path": fake_project,
                    "options": {"task_id": "task-rcl-42"},
                },
                stream_handler=None,
            )

        assert "tasks" in result["output_apk"]
        assert "task-rcl-42" in result["output_apk"]
        assert "recompiled" in result["output_apk"]


class TestSignUsesTaskDir:
    """apk_sign should route output to Tasks/{task_id}/output/."""

    def test_sign_uses_task_dir(self):
        """When task_id is provided, signed APK goes under Tasks/{id}/output/."""
        from unittest.mock import patch, MagicMock

        fake_apk = "/tmp/original.apk"
        apksigner_mock = MagicMock()
        apksigner_mock.is_valid = True
        apksigner_mock.execute.return_value = {"returncode": 0, "stdout": ""}
        mgr_mock = MagicMock()
        mgr_mock.get_tool.return_value = apksigner_mock

        with patch("app.handlers.apk_handler.manager", mgr_mock), \
             patch("app.handlers.apk_handler.os.path.exists", return_value=True), \
             patch("app.handlers.apk_handler.os.makedirs"):
            from app.handlers.apk_handler import apk_sign
            result = apk_sign(
                {
                    "apk_path": fake_apk,
                    "keystore": {
                        "path": "/tmp/ks.jks",
                        "alias": "mykey",
                        "storepass": "pass",
                        "task_id": "sign-task-99",
                    },
                },
                stream_handler=None,
            )

        assert "tasks" in result["apk_path"]
        assert "sign-task-99" in result["apk_path"]
        assert result["apk_path"].endswith("original-signed.apk")
