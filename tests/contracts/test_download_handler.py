"""
Contract tests for the Download handler (``download.file``).

The handler streams a remote file with retry-with-backoff and an explicit
``use_proxy`` switch. OFF means always connect directly (matching browser
behaviour, avoiding the classic ``[WinError 10061]`` proxy-refused failure);
ON means the first attempt uses the env proxy and later attempts fall back
to a direct connection on transient failures.

Tests call ``download_file`` directly with ``(params, stream_handler)`` to
mirror how the framework dispatches it (same style as test_task_handler.py).
"""
import socket
from unittest.mock import MagicMock
from urllib.error import URLError

import pytest

from app.handlers.download_handler import download_file, API_MAP, _friendly_reason


@pytest.fixture(autouse=True)
def _no_real_task_dir(tmp_path, monkeypatch):
    """Keep the fallback downloads dir inside tmp_path; never touch real dirs."""
    monkeypatch.setattr(
        "app.handlers.download_handler.get_tasks_root",
        lambda: str(tmp_path / "tasks"),
    )


class _FakeResp:
    """Minimal urllib response: headers + one EOF read."""

    def __init__(self, content_length=0):
        self.headers = {"Content-Length": str(content_length)}
        self._read = False

    def read(self, _n):
        if self._read:
            return b""
        self._read = True
        return b""

    def close(self):
        pass


def _patch_net(monkeypatch):
    """Patch urlopen/build_opener; return (urlopen_mock, build_opener_mock)
    with build_opener().open() returning a fake successful response."""
    uo = MagicMock()
    bo = MagicMock()
    bo.return_value.open.return_value = _FakeResp()
    monkeypatch.setattr("app.handlers.download_handler.urlopen", uo)
    monkeypatch.setattr("app.handlers.download_handler.build_opener", bo)
    return uo, bo


class TestApiMap:
    def test_download_file_registered(self):
        assert "download.file" in API_MAP
        assert API_MAP["download.file"] is download_file


class TestUseProxySwitch:
    def test_off_always_direct(self, tmp_path, monkeypatch):
        """use_proxy=False must never touch module-level urlopen: always build
        a ProxyHandler({}) opener (i.e. a direct connection)."""
        events = []
        uo, bo = _patch_net(monkeypatch)
        download_file(
            {"url": "http://example.com/a.bin", "filename": "a.bin", "use_proxy": False},
            lambda e: events.append(e),
        )
        bo.assert_called_once()
        proxy_handler = bo.call_args[0][0]
        assert proxy_handler.proxies == {}
        uo.assert_not_called()
        assert events[-1]["type"] == "complete"

    def test_on_uses_proxy_first_then_direct_retry(self, tmp_path, monkeypatch):
        """use_proxy=True: attempt 1 goes through urlopen (env proxy); after a
        transient URLError the retry bypasses the proxy via ProxyHandler({})."""
        events = []
        uo, bo = _patch_net(monkeypatch)
        uo.side_effect = [URLError(ConnectionRefusedError("[WinError 10061] refused")), _FakeResp()]
        download_file(
            {"url": "http://example.com/a.bin", "filename": "a.bin", "use_proxy": True},
            lambda e: events.append(e),
        )
        # First attempt hit urlopen (proxy) and failed; second attempt built a direct opener.
        assert uo.call_count == 1
        bo.assert_called_once()
        proxy_handler = bo.call_args[0][0]
        assert proxy_handler.proxies == {}
        assert events[-1]["type"] == "complete"

    def test_default_direct_when_no_env_proxy(self, tmp_path, monkeypatch):
        """No explicit switch and no env proxy -> behaves like OFF (direct)."""
        events = []
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        uo, bo = _patch_net(monkeypatch)
        download_file(
            {"url": "http://example.com/a.bin", "filename": "a.bin"},
            lambda e: events.append(e),
        )
        bo.assert_called_once()
        uo.assert_not_called()
        assert events[-1]["type"] == "complete"


class TestFriendlyReason:
    def test_10061_with_proxy_hint(self, monkeypatch):
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
        msg = _friendly_reason(ConnectionRefusedError("[WinError 10061] 拒绝"), use_proxy=True)
        assert "代理" in msg
        assert "127.0.0.1:7897" in msg

    def test_10061_direct_no_proxy_hint(self):
        msg = _friendly_reason(ConnectionRefusedError("[WinError 10061] 拒绝"), use_proxy=False)
        assert "代理" not in msg
        assert "未监听" in msg

    def test_timeout_hint(self):
        msg = _friendly_reason(socket.timeout("timed out"), use_proxy=False)
        assert "超时" in msg
