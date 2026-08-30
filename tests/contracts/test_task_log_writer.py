"""
Contract tests for ``app.utils.task_log_writer``.

Verifies thread-safe per-task log appending and the soft 50 MB → 20 MB
truncation behaviour.
"""

import io
import os
import re
import threading
import sys
from unittest.mock import patch, MagicMock

import pytest

# Ensure backend package is importable (conftest does this too, but be safe)
backend_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "cli")
)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Smaller caps so the truncation test runs quickly while still exercising
# the exact same code path.
TEST_SIZE_CAP = 2 * 1024 * 1024      # 2 MB
TEST_TAIL_SIZE = 512 * 1024          # 512 KB


@pytest.fixture
def task_id():
    """Unique task id per test to avoid cross-test interference."""
    pid = os.getpid()
    tid = threading.get_ident()
    return f"test_{pid}_{tid}"


@pytest.fixture(autouse=True)
def _small_caps():
    """Replace the real constants with small test values for every test."""
    with (
        patch("app.utils.task_log_writer._SIZE_CAP", TEST_SIZE_CAP),
        patch("app.utils.task_log_writer._TAIL_SIZE", TEST_TAIL_SIZE),
    ):
        yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAppendCreatesFile:
    """Appending twice then flushing should produce a file with exactly two lines."""

    def test_append_creates_file(self, task_id):
        from app.utils.task_log_writer import append_task_log, flush_task_log
        from app.env import get_task_subdir

        log_path = os.path.join(get_task_subdir(task_id, "logs"), "task_exec.log")

        # Remove any leftover from earlier runs
        if os.path.exists(log_path):
            os.remove(log_path)

        append_task_log(task_id, "hello")
        append_task_log(task_id, "world")
        flush_task_log(task_id)

        assert os.path.exists(log_path)
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 2
        assert lines[0].rstrip("\n") == "hello"
        assert lines[1].rstrip("\n") == "world"


class TestAppendConcurrentSafe:
    """10 threads writing 10 lines each → 100 total lines, no garbled lines."""

    def test_append_concurrent_safe(self, task_id):
        from app.utils.task_log_writer import append_task_log, flush_task_log
        from app.env import get_task_subdir

        log_path = os.path.join(get_task_subdir(task_id, "logs"), "task_exec.log")
        if os.path.exists(log_path):
            os.remove(log_path)

        THREADS = 10
        LINES_PER_THREAD = 10
        errors = []

        def worker(thread_no: int):
            for i in range(LINES_PER_THREAD):
                try:
                    append_task_log(task_id, f"t{thread_no}-{i}")
                except Exception as exc:
                    errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(n,))
            for n in range(THREADS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unexpected exceptions: {errors}"

        flush_task_log(task_id)
        assert os.path.exists(log_path)

        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = [l for l in content.split("\n") if l]
        assert len(lines) == THREADS * LINES_PER_THREAD, (
            f"Expected {THREADS * LINES_PER_THREAD} lines, got {len(lines)}"
        )

        # Every line must match the ``t<thread>-<index>`` pattern
        pattern = re.compile(r"^t\d+-\d+$")
        for line in lines:
            assert pattern.match(line), f"Garbled line: {line!r}"


class TestAppendTruncatesOver50mb:
    """Writing past the cap should truncate the file to the tail size."""

    def test_append_truncates_over_50mb(self, task_id):
        from app.utils.task_log_writer import append_task_log, flush_task_log
        from app.env import get_task_subdir

        log_path = os.path.join(get_task_subdir(task_id, "logs"), "task_exec.log")
        if os.path.exists(log_path):
            os.remove(log_path)

        # Generate ~500KB of unique data per call — after 5 calls we exceed
        # TEST_SIZE_CAP (2 MB).  After truncation only TEST_TAIL_SIZE (512 KB)
        # should remain.
        chunk = "X" * 511_000  # ~0.5 MB per line
        total_written = 0

        for i in range(6):
            append_task_log(task_id, f"{i:04d}-{chunk}")
            total_written += len(chunk) + 6  # line + newline

        flush_task_log(task_id)
        assert os.path.exists(log_path)
        size = os.path.getsize(log_path)

        # After truncation, file should be roughly TEST_TAIL_SIZE (plus
        # a small margin for the last append that triggered the cap check).
        assert size <= TEST_TAIL_SIZE + 600_000, (
            f"Expected ≤ {TEST_TAIL_SIZE + 600_000} bytes, got {size}"
        )
        # It should also be at least half of the tail size (sanity).
        assert size >= TEST_TAIL_SIZE * 0.5, (
            f"Expected ≥ {TEST_TAIL_SIZE * 0.5} bytes, got {size}"
        )


class TestGracefulFailure:
    """flush_task_log must never raise, even when the filesystem misbehaves."""

    def test_graceful_on_bad_path(self, task_id):
        """Pass a task_id that would trigger a path error at flush → stderr + no raise."""
        from app.utils.task_log_writer import flush_task_log

        captured = io.StringIO()
        with patch.object(sys, "stderr", captured):
            # Empty task_id → ValueError from get_task_subdir during flush → caught
            flush_task_log("")

        output = captured.getvalue()
        assert "Failed to flush log" in output


# ---------------------------------------------------------------------------
# Tool output capture via CommandExecutor
# ---------------------------------------------------------------------------


class TestToolOutputCapture:
    """CommandExecutor writes stdout/stderr to per-task log when task_id is set."""

    def test_executor_writes_to_task_log(self, task_id, monkeypatch):
        """Mock ProcessExecutor, create context with task_id, verify task log."""
        from app.common.base_executor import CommandExecutionContext, CommandExecutor
        from app.common import base_executor as be_module

        # Mock ProcessExecutor to return known stdout/stderr
        mock_stdout = "hello from tool\nline two"
        mock_stderr = "some warning"

        def mock_run(self, cmd=None, **kwargs):
            return (0, mock_stdout, mock_stderr)

        monkeypatch.setattr(
            "app.common.executor.ProcessExecutor.run", mock_run
        )

        # Capture calls to the imported append_task_log in base_executor
        captured_lines = []
        def fake_append(task_id_val: str, line: str):
            captured_lines.append((task_id_val, line))
        monkeypatch.setattr(be_module, "append_task_log", fake_append)

        task_id_val = "t-test-capture"
        context = CommandExecutionContext(task_id=task_id_val, log_output=True)
        executor = CommandExecutor()
        result = executor.execute(["echo", "hello"], context)

        assert result["success"] is True
        assert result["stdout"] == mock_stdout
        assert result["stderr"] == mock_stderr

        # Verify append_task_log was called with the right task_id and content
        task_lines = [line for tid, line in captured_lines if tid == task_id_val]
        assert len(task_lines) > 0, "Expected at least one log line for the task"

        # Should contain header line
        assert any("[TOOL]" in l for l in task_lines), "Missing [TOOL] header"
        # Should contain stdout content
        assert any("hello from tool" in l for l in task_lines), (
            "Missing stdout content in task log"
        )
        assert any("line two" in l for l in task_lines), (
            "Missing stdout line two in task log"
        )
        # Should contain stderr content
        assert any("some warning" in l for l in task_lines), (
            "Missing stderr content in task log"
        )

    def test_executor_no_task_id_does_not_write(self, monkeypatch):
        """Without task_id, append_task_log should NOT be called."""
        from app.common.base_executor import CommandExecutionContext, CommandExecutor
        from app.common import base_executor as be_module

        def mock_run(self, cmd=None, **kwargs):
            return (0, "output", "")

        monkeypatch.setattr(
            "app.common.executor.ProcessExecutor.run", mock_run
        )

        captured_lines = []
        def fake_append(task_id_val: str, line: str):
            captured_lines.append((task_id_val, line))
        monkeypatch.setattr(be_module, "append_task_log", fake_append)

        context = CommandExecutionContext(task_id=None, log_output=True)
        executor = CommandExecutor()
        result = executor.execute(["echo", "hello"], context)

        assert result["success"] is True
        assert len(captured_lines) == 0, (
            f"append_task_log should not be called when task_id is None, "
            f"got {captured_lines}"
        )

    def test_executor_log_output_false_skips(self, monkeypatch):
        """When log_output is False, task log should NOT be written even with task_id."""
        from app.common.base_executor import CommandExecutionContext, CommandExecutor
        from app.common import base_executor as be_module

        def mock_run(self, cmd=None, **kwargs):
            return (0, "output", "")

        monkeypatch.setattr(
            "app.common.executor.ProcessExecutor.run", mock_run
        )

        captured_lines = []
        def fake_append(task_id_val: str, line: str):
            captured_lines.append((task_id_val, line))
        monkeypatch.setattr(be_module, "append_task_log", fake_append)

        context = CommandExecutionContext(
            task_id="t-test", log_output=False
        )
        executor = CommandExecutor()
        executor.execute(["echo", "hello"], context)

        assert len(captured_lines) == 0, (
            "append_task_log should not be called when log_output is False"
        )
