"""
Contract tests for APK handler API methods.
"""
import json
import time
from unittest.mock import patch, MagicMock
from app.handlers.apk_handler import _extract_signature_hashes


def make_fake_proc(stdout_lines=None, returncode=0):
    """Return a fake Popen-like object for streaming execute mocks."""
    lines = list(stdout_lines or [])
    fake_stdout = MagicMock()
    line_iter = iter(lines + ['', '', ''])
    fake_stdout.readline = lambda: next(line_iter)
    fake_proc = MagicMock()
    fake_proc.stdout = fake_stdout
    fake_proc.wait = lambda: None
    fake_proc.returncode = returncode
    fake_proc.kill = lambda: None
    return fake_proc


class TestApkAnalyze:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 11, "method": "apk.analyze", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        # Streaming handler returns stream_id immediately
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"

    def test_nonexistent_apk_path_returns_error(self, api_handler):
        request = {
            "id": 12,
            "method": "apk.analyze",
            "params": {"apk_path": "/nonexistent/path/test.apk"},
        }
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        # Streaming handler returns stream_id immediately
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"


class TestApkGetInfo:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 13, "method": "apk.getInfo", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        # apk.getInfo delegates to apk_analyze (streaming)
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"


class TestApkDecompile:
    def test_missing_file_path_returns_error(self, api_handler):
        request = {"id": 14, "method": "apk.decompile", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        # Streaming handler returns stream_id immediately
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"


class TestApkRecompile:
    def test_missing_project_path_returns_error(self, api_handler):
        request = {"id": 15, "method": "apk.recompile", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        # Streaming handler returns stream_id immediately
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"


class TestApkSign:
    def test_missing_apk_path_returns_error(self, api_handler):
        request = {"id": 16, "method": "apk.sign", "params": {}}
        response = api_handler.handle_request(request)

        data = json.loads(response) if isinstance(response, str) else response
        # Streaming handler returns stream_id immediately
        assert "stream_id" in data.get("result", {})
        assert data["finished"] is False

        # Wait for async stream thread to finish and capture error event
        for _ in range(50):
            if len(api_handler._captured) >= 2:
                break
            time.sleep(0.01)
        assert len(api_handler._captured) >= 2
        error_event = api_handler._captured[0]
        assert error_event["result"]["type"] == "error"


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
        apktool_mock.execute.return_value = make_fake_proc(stdout_lines=[], returncode=0)
        mgr_mock = MagicMock()
        mgr_mock.get_tool.return_value = apktool_mock

        captured_events = []

        def fake_stream_handler(data):
            captured_events.append(data)

        with patch("app.handlers.apk_handler.manager", mgr_mock), \
             patch("app.handlers.apk_handler.os.path.exists", return_value=True), \
             patch("app.handlers.apk_handler.os.makedirs"):
            from app.handlers.apk_handler import apk_decompile
            apk_decompile(
                {"file_path": fake_apk, "options": {"task_id": "my-task-123"}},
                stream_handler=fake_stream_handler,
            )

        assert captured_events[-1]["type"] == "complete"
        output_dir = captured_events[-1]["payload"]["output_dir"]
        assert "tasks" in output_dir
        assert "my-task-123" in output_dir
        assert output_dir.endswith("test")

    def test_decompile_fallback_no_task_id(self):
        """Without task_id, output_dir falls back to Output/decompiled/."""
        from unittest.mock import patch, MagicMock

        fake_apk = "/tmp/test.apk"
        apktool_mock = MagicMock()
        apktool_mock.is_valid = True
        apktool_mock.execute.return_value = make_fake_proc(stdout_lines=[], returncode=0)
        mgr_mock = MagicMock()
        mgr_mock.get_tool.return_value = apktool_mock

        captured_events = []

        def fake_stream_handler(data):
            captured_events.append(data)

        with patch("app.handlers.apk_handler.manager", mgr_mock), \
             patch("app.handlers.apk_handler.os.path.exists", return_value=True), \
             patch("app.handlers.apk_handler.os.makedirs"):
            from app.handlers.apk_handler import apk_decompile
            apk_decompile(
                {"file_path": fake_apk, "options": {}},
                stream_handler=fake_stream_handler,
            )

        assert captured_events[-1]["type"] == "complete"
        output_dir = captured_events[-1]["payload"]["output_dir"]
        assert "tasks" not in output_dir
        assert "decompiled" in output_dir
        assert output_dir.endswith("test")


class TestRecompileUsesTaskDir:
    """apk_recompile should route output to Tasks/{task_id}/output/recompiled/."""

    def test_recompile_uses_task_dir(self):
        """When task_id is provided, output_apk goes under Tasks/{id}/output/recompiled/."""
        from unittest.mock import patch, MagicMock

        fake_project = "/tmp/my_project"
        apktool_mock = MagicMock()
        apktool_mock.is_valid = True
        apktool_mock.execute.return_value = make_fake_proc(stdout_lines=[], returncode=0)
        mgr_mock = MagicMock()
        mgr_mock.get_tool.return_value = apktool_mock

        captured_events = []

        def fake_stream_handler(data):
            captured_events.append(data)

        with patch("app.handlers.apk_handler.manager", mgr_mock), \
             patch("app.handlers.apk_handler.os.path.exists", return_value=True), \
             patch("app.handlers.apk_handler.os.makedirs"):
            from app.handlers.apk_handler import apk_recompile
            apk_recompile(
                {
                    "project_path": fake_project,
                    "options": {"task_id": "task-rcl-42"},
                },
                stream_handler=fake_stream_handler,
            )

        assert captured_events[-1]["type"] == "complete"
        output_apk = captured_events[-1]["payload"]["output_apk"]
        assert "tasks" in output_apk
        assert "task-rcl-42" in output_apk
        assert "recompiled" in output_apk


class TestSignUsesTaskDir:
    """apk_sign should route output to Tasks/{task_id}/output/."""

    def test_sign_uses_task_dir(self):
        """When task_id is provided, signed APK goes under Tasks/{id}/output/."""
        from unittest.mock import patch, MagicMock

        fake_apk = "/tmp/original.apk"
        apksigner_mock = MagicMock()
        apksigner_mock.is_valid = True
        apksigner_mock.execute.return_value = make_fake_proc(stdout_lines=[], returncode=0)
        mgr_mock = MagicMock()
        mgr_mock.get_tool.return_value = apksigner_mock

        captured_events = []

        def fake_stream_handler(data):
            captured_events.append(data)

        with patch("app.handlers.apk_handler.manager", mgr_mock), \
             patch("app.handlers.apk_handler.os.path.exists", return_value=True), \
             patch("app.handlers.apk_handler.os.makedirs"):
            from app.handlers.apk_handler import apk_sign
            apk_sign(
                {
                    "apk_path": fake_apk,
                    "keystore": {
                        "path": "/tmp/ks.jks",
                        "alias": "mykey",
                        "storepass": "pass",
                        "task_id": "sign-task-99",
                    },
                },
                stream_handler=fake_stream_handler,
            )

        assert captured_events[-1]["type"] == "complete"
        apk_path = captured_events[-1]["payload"]["apk_path"]
        assert "tasks" in apk_path
        assert "sign-task-99" in apk_path
        assert apk_path.endswith("original-signed.apk")


# ---------------------------------------------------------------------------
# _extract_signature_hashes contract tests
# ---------------------------------------------------------------------------

def test_extract_signature_hashes_returns_dashes_when_apksigner_missing():
    with patch("app.handlers.apk_handler.manager.get_tool", return_value=None):
        result = _extract_signature_hashes("/nonexistent.apk")
        assert result["sig_md5"] == "-"
        assert result["sig_sha1"] == "-"
        assert result["sig_sha256"] == "-"
        assert "sig_warning" in result


def test_extract_signature_hashes_parses_certs():
    fake_output = (
        "Signer #1 certificate DN: CN=Test\n"
        "Signer #1 certificate SHA-256 digest: ab:12:cd:34\n"
        "Signer #1 certificate SHA-1 digest: ef:56:78:90\n"
        "Signer #1 certificate MD5 digest: 12:34:56:78:90\n"
    )
    with patch("app.handlers.apk_handler.manager.get_tool") as mock_get:
        mock_tool = MagicMock()
        mock_tool.is_valid = True
        mock_tool.execute.return_value = {
            "stdout": fake_output, "stderr": "", "returncode": 0,
        }
        mock_get.return_value = mock_tool
        result = _extract_signature_hashes("/fake.apk")
        assert result["sig_md5"] == "1234567890"
        assert result["sig_sha1"] == "ef567890"
        assert result["sig_sha256"] == "ab12cd34"


def test_extract_signature_hashes_handles_unsigned():
    with patch("app.handlers.apk_handler.manager.get_tool") as mock_get:
        mock_tool = MagicMock()
        mock_tool.is_valid = True
        mock_tool.execute.return_value = {
            "stdout": "Verifies\n", "stderr": "", "returncode": 1,
        }
        mock_get.return_value = mock_tool
        result = _extract_signature_hashes("/fake.apk")
        assert result["sig_md5"] == "-"
        assert "sig_warning" in result
