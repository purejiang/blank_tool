"""Wave 2 tests: all 18 builtin workflow tools (happy + failure paths).

Every tool under ``backend/app/tools/builtin/`` is exercised through its real
``execute(inputs, ToolContext)`` surface with ``tmp_path``-backed fixtures and
a threaded local ``HTTPServer`` for the two net.* tools (no real network).
"""

import hashlib
import http.server
import io
import logging
import os
import socket
import sys
import tarfile
import threading
import zipfile

import pytest

from app.common.exceptions import ToolException
from app.tools.builtin.base import ToolContext
from app.tools.builtin.exec_tools import CodeExec, ShellExec
from app.tools.builtin.file_tools import (
    FileCopy,
    FileDelete,
    FileHash,
    FileMove,
    FileRead,
    FileWrite,
)
from app.tools.builtin.flow_tools import FlowAssert, FlowLog
from app.tools.builtin.fs_tools import (
    ArchiveCreate,
    ArchiveExtract,
    DirCreate,
    DirDelete,
    DirList,
    TextGrep,
)
from app.tools.builtin.net_tools import NetDownload, NetRequest
from app.utils import task_log_writer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(tmp_path, **overrides) -> ToolContext:
    """Build a ToolContext rooted at tmp_path (work_dir is required)."""
    return ToolContext(work_dir=str(tmp_path), **overrides)


# ---------------------------------------------------------------------------
# Mock HTTP server (threaded, ephemeral port 0) — never touches the network.
# ---------------------------------------------------------------------------

_BIN_BODY = b"x" * 200000  # > one 64 KiB chunk so progress streams multiple events


class _MockHandler(http.server.BaseHTTPRequestHandler):
    """Deterministic routing used by the net.* tests."""

    def log_message(self, *args):  # silence request logging
        pass

    def _respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/json":
            self._respond(200, "application/json", b'{"ok": true, "n": 1}')
        elif self.path == "/text":
            self._respond(200, "text/plain", b"hello world")
        elif self.path == "/data.bin":
            self._respond(200, "application/octet-stream", _BIN_BODY)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/json")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._respond(404, "text/plain", b"not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if self.path == "/json":
            self._respond(200, "application/json", b'{"method": "POST"}')
        else:
            self._respond(404, "text/plain", b"not found")


@pytest.fixture
def http_base_url():
    server = http.server.HTTPServer(("127.0.0.1", 0), _MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def refused_url():
    """A URL on an unused port — connection is refused (no server listening)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}/"


def _python_cmd(code: str) -> str:
    """A shell command line running *code* with the current interpreter."""
    return f'"{sys.executable}" -c "{code}"'


# ---------------------------------------------------------------------------
# file.read
# ---------------------------------------------------------------------------

def test_file_read_existing_file_returns_content_and_size(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("hello builtin", encoding="utf-8")
    result = FileRead().execute({"path": str(target)}, _ctx(tmp_path))
    assert result["content"] == "hello builtin"
    assert result["size"] == len("hello builtin".encode("utf-8"))


def test_file_read_nonexistent_returns_error(tmp_path):
    result = FileRead().execute({"path": str(tmp_path / "missing.txt")}, _ctx(tmp_path))
    assert "error" in result
    assert "file not found" in result["error"]


def test_file_read_custom_encoding(tmp_path):
    target = tmp_path / "utf16.txt"
    target.write_text("héllo wörld", encoding="utf-16")
    result = FileRead().execute(
        {"path": str(target), "encoding": "utf-16"}, _ctx(tmp_path)
    )
    assert result["content"] == "héllo wörld"


# ---------------------------------------------------------------------------
# file.write
# ---------------------------------------------------------------------------

def test_file_write_creates_file_with_content(tmp_path):
    target = tmp_path / "out.txt"
    result = FileWrite().execute(
        {"path": str(target), "content": "written content"}, _ctx(tmp_path)
    )
    assert result["written"] is True
    assert target.read_text(encoding="utf-8") == "written content"


def test_file_write_unwritable_path_returns_error(tmp_path):
    result = FileWrite().execute(
        {"path": str(tmp_path / "no_such_dir" / "f.txt"), "content": "x"},
        _ctx(tmp_path),
    )
    assert "error" in result


# ---------------------------------------------------------------------------
# file.copy
# ---------------------------------------------------------------------------

def test_file_copy_copies_existing_file(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("copy me", encoding="utf-8")
    dst = tmp_path / "dst.txt"
    result = FileCopy().execute(
        {"source": str(src), "destination": str(dst)}, _ctx(tmp_path)
    )
    assert result["path"] == str(dst)
    assert dst.read_text(encoding="utf-8") == "copy me"


def test_file_copy_nonexistent_source_returns_error(tmp_path):
    result = FileCopy().execute(
        {
            "source": str(tmp_path / "ghost.txt"),
            "destination": str(tmp_path / "dst.txt"),
        },
        _ctx(tmp_path),
    )
    assert "error" in result
    assert "file not found" in result["error"]


def test_file_copy_overwrite_false_existing_dest_returns_error(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("a", encoding="utf-8")
    dst = tmp_path / "dst.txt"
    dst.write_text("keep me", encoding="utf-8")
    result = FileCopy().execute(
        {"source": str(src), "destination": str(dst), "overwrite": False},
        _ctx(tmp_path),
    )
    assert "error" in result
    assert "destination exists" in result["error"]
    assert dst.read_text(encoding="utf-8") == "keep me"


# ---------------------------------------------------------------------------
# file.move
# ---------------------------------------------------------------------------

def test_file_move_moves_file(tmp_path):
    src = tmp_path / "move.txt"
    src.write_text("moving", encoding="utf-8")
    dst = tmp_path / "moved.txt"
    result = FileMove().execute(
        {"source": str(src), "destination": str(dst)}, _ctx(tmp_path)
    )
    assert result["path"] == str(dst)
    assert not src.exists()
    assert dst.read_text(encoding="utf-8") == "moving"


def test_file_move_nonexistent_returns_error(tmp_path):
    result = FileMove().execute(
        {
            "source": str(tmp_path / "ghost.txt"),
            "destination": str(tmp_path / "dst.txt"),
        },
        _ctx(tmp_path),
    )
    assert "error" in result
    assert "file not found" in result["error"]


# ---------------------------------------------------------------------------
# file.delete
# ---------------------------------------------------------------------------

def test_file_delete_removes_existing_file(tmp_path):
    target = tmp_path / "del.txt"
    target.write_text("gone soon", encoding="utf-8")
    result = FileDelete().execute({"path": str(target)}, _ctx(tmp_path))
    assert result["deleted"] is True
    assert not target.exists()


def test_file_delete_nonexistent_returns_error(tmp_path):
    result = FileDelete().execute(
        {"path": str(tmp_path / "missing.txt")}, _ctx(tmp_path)
    )
    assert "error" in result
    assert "file not found" in result["error"]


# ---------------------------------------------------------------------------
# file.hash
# ---------------------------------------------------------------------------

def test_file_hash_sha256_of_known_content(tmp_path):
    target = tmp_path / "hash.bin"
    target.write_bytes(b"hello world")
    result = FileHash().execute({"path": str(target)}, _ctx(tmp_path))
    assert result["algorithm"] == "sha256"
    assert result["hash"] == hashlib.sha256(b"hello world").hexdigest()


def test_file_hash_md5_algorithm(tmp_path):
    target = tmp_path / "hash.bin"
    target.write_bytes(b"hello world")
    result = FileHash().execute(
        {"path": str(target), "algorithm": "md5"}, _ctx(tmp_path)
    )
    assert result["algorithm"] == "md5"
    assert result["hash"] == hashlib.md5(b"hello world").hexdigest()


def test_file_hash_nonexistent_returns_error(tmp_path):
    result = FileHash().execute(
        {"path": str(tmp_path / "missing.bin")}, _ctx(tmp_path)
    )
    assert "error" in result
    assert "file not found" in result["error"]


# ---------------------------------------------------------------------------
# dir.list
# ---------------------------------------------------------------------------

def test_dir_list_known_entries(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    result = DirList().execute({"path": str(tmp_path)}, _ctx(tmp_path))
    names = {e["name"] for e in result["entries"]}
    assert names == {"a.txt", "b.txt", "sub"}
    assert result["count"] == 3


def test_dir_list_nonexistent_returns_error(tmp_path):
    result = DirList().execute({"path": str(tmp_path / "nope")}, _ctx(tmp_path))
    assert "error" in result


def test_dir_list_pattern_filter(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "c.log").write_text("c", encoding="utf-8")
    result = DirList().execute(
        {"path": str(tmp_path), "pattern": "*.txt"}, _ctx(tmp_path)
    )
    assert result["count"] == 2
    assert {e["name"] for e in result["entries"]} == {"a.txt", "b.txt"}


# ---------------------------------------------------------------------------
# dir.create
# ---------------------------------------------------------------------------

def test_dir_create_new_directory(tmp_path):
    target = tmp_path / "newdir"
    result = DirCreate().execute({"path": str(target)}, _ctx(tmp_path))
    assert result["created"] is True
    assert result["path"] == str(target)
    assert target.is_dir()


def test_dir_create_with_parents(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    result = DirCreate().execute({"path": str(target), "parents": True}, _ctx(tmp_path))
    assert result["created"] is True
    assert target.is_dir()


def test_dir_create_existing_dir_is_idempotent(tmp_path):
    (tmp_path / "exists").mkdir()
    result = DirCreate().execute({"path": str(tmp_path / "exists")}, _ctx(tmp_path))
    assert result["created"] is False


# ---------------------------------------------------------------------------
# dir.delete
# ---------------------------------------------------------------------------

def test_dir_delete_removes_tree(tmp_path):
    target = tmp_path / "tree"
    (target / "sub").mkdir(parents=True)
    (target / "sub" / "f.txt").write_text("x", encoding="utf-8")
    result = DirDelete().execute({"path": str(target)}, _ctx(tmp_path))
    assert result["deleted"] is True
    assert not target.exists()


def test_dir_delete_nonexistent_returns_error(tmp_path):
    result = DirDelete().execute({"path": str(tmp_path / "nope")}, _ctx(tmp_path))
    assert "error" in result
    assert "directory does not exist" in result["error"]


# ---------------------------------------------------------------------------
# text.grep
# ---------------------------------------------------------------------------

def test_text_grep_finds_pattern_in_file(tmp_path):
    target = tmp_path / "grep.txt"
    target.write_text("alpha\nbeta\nalpha again\n", encoding="utf-8")
    result = TextGrep().execute(
        {"path": str(target), "pattern": "alpha"}, _ctx(tmp_path)
    )
    assert result["count"] == 2
    assert {m["line"] for m in result["matches"]} == {1, 3}


def test_text_grep_recursive_in_directory(tmp_path):
    (tmp_path / "root.txt").write_text("needle in root\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.txt").write_text(
        "needle in nested\nnothing here\n", encoding="utf-8"
    )
    result = TextGrep().execute(
        {"path": str(tmp_path), "pattern": "needle"}, _ctx(tmp_path)
    )
    assert result["count"] == 2
    files = {m["file"] for m in result["matches"]}
    assert any(f.endswith("root.txt") for f in files)
    assert any(f.endswith("nested.txt") for f in files)


def test_text_grep_invalid_regex_returns_error(tmp_path):
    target = tmp_path / "grep.txt"
    target.write_text("alpha\n", encoding="utf-8")
    result = TextGrep().execute(
        {"path": str(target), "pattern": "["}, _ctx(tmp_path)
    )
    assert "error" in result
    assert "invalid regex" in result["error"]


def test_text_grep_no_matches_returns_empty(tmp_path):
    target = tmp_path / "grep.txt"
    target.write_text("alpha\n", encoding="utf-8")
    result = TextGrep().execute(
        {"path": str(target), "pattern": "zzz"}, _ctx(tmp_path)
    )
    assert result["count"] == 0
    assert result["matches"] == []


# ---------------------------------------------------------------------------
# archive.extract
# ---------------------------------------------------------------------------

def test_archive_extract_zip(tmp_path):
    archive = tmp_path / "src.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("one.txt", "one")
        zf.writestr("dir/two.txt", "two")
    dest = tmp_path / "out"
    result = ArchiveExtract().execute(
        {"path": str(archive), "dest": str(dest)}, _ctx(tmp_path)
    )
    assert result["count"] == 2
    assert (dest / "one.txt").read_text(encoding="utf-8") == "one"
    assert (dest / "dir" / "two.txt").read_text(encoding="utf-8") == "two"


def test_archive_extract_tar_gz(tmp_path):
    archive = tmp_path / "src.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        payload = io.BytesIO(b"tar content")
        info = tarfile.TarInfo("three.txt")
        info.size = len(b"tar content")
        tf.addfile(info, payload)
    dest = tmp_path / "out"
    result = ArchiveExtract().execute(
        {"path": str(archive), "dest": str(dest)}, _ctx(tmp_path)
    )
    assert result["count"] == 1
    assert (dest / "three.txt").read_text(encoding="utf-8") == "tar content"


def test_archive_extract_rejects_path_traversal_member(tmp_path):
    """CVE-2007-4559 regression: ../ members must be rejected, not written."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "bad")
    archive = tmp_path / "evil.zip"
    archive.write_bytes(buf.getvalue())
    dest = tmp_path / "out"
    result = ArchiveExtract().execute(
        {"path": str(archive), "dest": str(dest)}, _ctx(tmp_path)
    )
    assert "error" in result
    assert "traversal" in result["error"].lower()
    assert not (tmp_path / "evil.txt").exists()


def test_archive_extract_nonexistent_archive_returns_error(tmp_path):
    result = ArchiveExtract().execute(
        {"path": str(tmp_path / "nope.zip"), "dest": str(tmp_path / "out")},
        _ctx(tmp_path),
    )
    assert "error" in result
    assert "does not exist" in result["error"]


# ---------------------------------------------------------------------------
# archive.create
# ---------------------------------------------------------------------------

def test_archive_create_zip_from_directory(tmp_path):
    src = tmp_path / "src_dir"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text("a", encoding="utf-8")
    (src / "sub" / "b.txt").write_text("b", encoding="utf-8")
    archive = tmp_path / "made.zip"
    result = ArchiveCreate().execute(
        {"source": str(src), "dest": str(archive)}, _ctx(tmp_path)
    )
    assert result["path"] == str(archive)
    assert result["size"] > 0
    assert archive.stat().st_size == result["size"]
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert any(n.endswith("a.txt") for n in names)


def test_archive_create_zip_from_single_file(tmp_path):
    src = tmp_path / "single.txt"
    src.write_text("just me", encoding="utf-8")
    archive = tmp_path / "single.zip"
    result = ArchiveCreate().execute(
        {"source": str(src), "dest": str(archive)}, _ctx(tmp_path)
    )
    assert result["size"] > 0
    with zipfile.ZipFile(archive) as zf:
        assert zf.namelist() == ["single.txt"]


# ---------------------------------------------------------------------------
# net.download
# ---------------------------------------------------------------------------

def test_net_download_http_200_writes_file_with_correct_size(tmp_path, http_base_url):
    dest = tmp_path / "down.bin"
    result = NetDownload().execute(
        {"url": http_base_url + "/text", "dest": str(dest)}, _ctx(tmp_path)
    )
    assert result["status_code"] == 200
    assert result["size"] == len(b"hello world")
    assert dest.read_bytes() == b"hello world"


def test_net_download_http_404_returns_error(tmp_path, http_base_url):
    result = NetDownload().execute(
        {"url": http_base_url + "/missing", "dest": str(tmp_path / "x.bin")},
        _ctx(tmp_path),
    )
    assert "error" in result
    assert "HTTP 404" in result["error"]


def test_net_download_reports_progress_events(tmp_path, http_base_url):
    events = []
    result = NetDownload().execute(
        {"url": http_base_url + "/data.bin", "dest": "down.bin"},
        _ctx(tmp_path, stream_handler=events.append),
    )
    assert result["size"] == len(_BIN_BODY)
    assert result["status_code"] == 200
    assert events, "stream_handler should receive progress events"
    assert events[-1]["type"] == "progress"
    assert events[-1]["downloaded"] == len(_BIN_BODY)
    assert events[-1]["total"] == len(_BIN_BODY)


# ---------------------------------------------------------------------------
# net.request
# ---------------------------------------------------------------------------

def test_net_request_200_json_returns_parsed_json(tmp_path, http_base_url):
    result = NetRequest().execute({"url": http_base_url + "/json"}, _ctx(tmp_path))
    assert result["status_code"] == 200
    assert result["json"] == {"ok": True, "n": 1}
    assert "error" not in result


def test_net_request_404_returns_status_and_body_not_error(tmp_path, http_base_url):
    result = NetRequest().execute({"url": http_base_url + "/missing"}, _ctx(tmp_path))
    assert result["status_code"] == 404
    assert result["body"] == "not found"
    assert "error" not in result


def test_net_request_connection_refused_returns_error(tmp_path, refused_url):
    result = NetRequest().execute({"url": refused_url}, _ctx(tmp_path))
    assert "error" in result
    assert "network error" in result["error"]


# ---------------------------------------------------------------------------
# shell.exec
# ---------------------------------------------------------------------------

def test_shell_exec_echo_returns_stdout(tmp_path):
    result = ShellExec().execute({"command": "echo hello from shell"}, _ctx(tmp_path))
    assert result["success"] is True
    assert result["returncode"] == 0
    assert "hello from shell" in result["stdout"]


def test_shell_exec_nonzero_exit_returns_actual_returncode(tmp_path):
    result = ShellExec().execute(
        {"command": _python_cmd("import sys; sys.exit(3)")}, _ctx(tmp_path)
    )
    assert result["success"] is False
    assert result["returncode"] == 3


def test_shell_exec_timeout_returns_error_shape(tmp_path):
    # sleep(2) with timeout=1: the process cannot finish within the timeout,
    # so the timeout path is deterministic (1s < 2s), and the post-kill pipe
    # drain (which on Windows waits for the child to exit) stays short.
    result = ShellExec().execute(
        {"command": _python_cmd("import time; time.sleep(2)"), "timeout": 1},
        _ctx(tmp_path),
    )
    assert result["success"] is False
    assert result["returncode"] == -1
    assert "timeout" in result["stderr"]


# ---------------------------------------------------------------------------
# code.exec
# ---------------------------------------------------------------------------

def test_code_exec_multiplies_inputs(tmp_path):
    result = CodeExec().execute(
        {"code": 'result = inputs["x"] * 2', "inputs": {"x": 21}}, _ctx(tmp_path)
    )
    assert result["success"] is True
    assert result["result"] == 42


def test_code_exec_syntax_error_returns_failure_with_traceback(tmp_path):
    result = CodeExec().execute({"code": "def broken(:"}, _ctx(tmp_path))
    assert result["success"] is False
    assert "SyntaxError" in result["stderr"]


def test_code_exec_unsupported_language_raises(tmp_path):
    with pytest.raises(NotImplementedError, match="python"):
        CodeExec().execute(
            {"code": "x = 1", "language": "javascript"}, _ctx(tmp_path)
        )


# ---------------------------------------------------------------------------
# flow.assert
# ---------------------------------------------------------------------------

def test_flow_assert_true_returns_passed(tmp_path):
    result = FlowAssert().execute({"condition": True}, _ctx(tmp_path))
    assert result == {"passed": True}


def test_flow_assert_false_raises_tool_exception(tmp_path):
    with pytest.raises(ToolException, match="value must be positive"):
        FlowAssert().execute(
            {"condition": False, "message": "value must be positive"}, _ctx(tmp_path)
        )


# ---------------------------------------------------------------------------
# flow.log
# ---------------------------------------------------------------------------

def test_flow_log_writes_message_via_logging(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    result = FlowLog().execute({"message": "hello flow"}, _ctx(tmp_path))
    assert result["logged"] is True
    assert any("hello flow" in r.getMessage() for r in caplog.records)


def test_flow_log_invalid_level_defaults_to_info(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    FlowLog().execute({"message": "odd level", "level": "banana"}, _ctx(tmp_path))
    matching = [r for r in caplog.records if r.getMessage() == "odd level"]
    assert matching, "message should be logged"
    assert matching[0].levelname == "INFO"


def test_flow_log_with_task_id_appends_to_task_log(tmp_path):
    task_id = "wave2-flowlog-test"
    try:
        result = FlowLog().execute(
            {"message": "task line", "level": "warning"},
            _ctx(tmp_path, task_id=task_id),
        )
        assert result["logged"] is True
        with task_log_writer._get_buffer_lock(task_id):
            buffered = list(task_log_writer._per_task_buffers.get(task_id, []))
        assert any("[warning] task line" in line for line in buffered)
    finally:
        task_log_writer.cleanup_task_log(task_id)
