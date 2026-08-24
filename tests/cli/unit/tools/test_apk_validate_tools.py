"""Tests: APK validation example tools (examples/tools/android).

Covers the four python_script tools backing the apk-validate workflow:
apk-resolve, apk-signature, validate-entry and validate-report.  The scripts
are exercised both as subprocesses (their real contract: argv in, single-line
JSON on stdout) and, for apk_signature's pure helpers, via import.
"""

import hashlib
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
TOOLS_DIR = ROOT / "examples" / "tools" / "android"

APK_RESOLVE = TOOLS_DIR / "apk-resolve" / "apk_resolve.py"
APK_SIGNATURE = TOOLS_DIR / "apk-signature" / "apk_signature.py"
VALIDATE_ENTRY = TOOLS_DIR / "validate-entry" / "validate_entry.py"
VALIDATE_REPORT = TOOLS_DIR / "validate-report" / "validate_report.py"


def _run_script(script, *args, cwd=None, env=None):
    """Run a tool script and return (returncode, parsed_stdout_json, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    payload = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            payload = json.loads(line)
    return proc.returncode, payload, proc.stderr


def _md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _md5_file(path) -> str:
    return _md5_bytes(Path(path).read_bytes())


@pytest.fixture
def fixture_apk(tmp_path):
    """A minimal 'APK' (zip) with a binary asset and a properties file."""
    apk_path = tmp_path / "fixture.apk"
    entries = {
        "assets/login.png": b"\x89PNG fake-binary-content",
        "assets/channel.properties": b"# channel config\nchannel=huawei\nversion: 1.2\n",
    }
    with zipfile.ZipFile(apk_path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return apk_path, entries


@pytest.fixture
def http_server(tmp_path):
    """Serve tmp_path over http on an ephemeral localhost port."""
    class _QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(tmp_path), **kwargs)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=5)


# ── apk-resolve ─────────────────────────────────────────────────────────────

class TestApkResolve:
    def test_local_existing_file(self, tmp_path):
        apk = tmp_path / "app.apk"
        apk.write_bytes(b"apk")
        code, payload, _ = _run_script(APK_RESOLVE, apk)
        assert code == 0
        assert payload["apk_path"] == str(apk.resolve())

    def test_local_missing_file_fails(self, tmp_path):
        code, payload, stderr = _run_script(APK_RESOLVE, tmp_path / "nope.apk")
        assert code == 1
        assert payload is None
        assert "file not found" in stderr

    def test_url_download(self, tmp_path, http_server, monkeypatch):
        (tmp_path / "remote.apk").write_bytes(b"remote-apk-bytes")
        # download lands in <cwd>/apk_cache
        work = tmp_path / "work"
        work.mkdir()
        code, payload, _ = _run_script(
            APK_RESOLVE, f"{http_server}/remote.apk", cwd=str(work)
        )
        assert code == 0
        downloaded = Path(payload["apk_path"])
        assert downloaded.is_file()
        assert downloaded.parent.name == "apk_cache"
        assert downloaded.read_bytes() == b"remote-apk-bytes"


# ── validate-entry: file type ───────────────────────────────────────────────

class TestValidateEntryFile:
    def _run(self, *args):
        code, payload, _ = _run_script(VALIDATE_ENTRY, *args)
        assert code == 0, "validate_entry must always exit 0"
        assert payload is not None
        return payload

    def test_local_file_md5_match(self, tmp_path):
        f = tmp_path / "login.png"
        f.write_bytes(b"image-bytes")
        r = self._run("login", "file", f, _md5_file(f), "", "", "", "", "", "")
        assert r["passed"] is True
        assert r["actual"] == _md5_file(f)

    def test_local_file_md5_mismatch(self, tmp_path):
        f = tmp_path / "login.png"
        f.write_bytes(b"image-bytes")
        r = self._run("login", "file", f, "0" * 32, "", "", "", "", "", "")
        assert r["passed"] is False
        assert "mismatch" in r["message"]

    def test_apk_internal_entry_md5_match(self, fixture_apk):
        apk, entries = fixture_apk
        expected = _md5_bytes(entries["assets/login.png"])
        r = self._run(
            "login", "file", "assets/login.png", expected,
            "", "", "", "", apk, "",
        )
        assert r["passed"] is True, r
        assert r["actual"] == expected

    def test_apk_internal_entry_missing_fails(self, fixture_apk):
        apk, _ = fixture_apk
        r = self._run(
            "ghost", "file", "assets/ghost.png", "0" * 32,
            "", "", "", "", apk, "",
        )
        assert r["passed"] is False
        assert "file not found" in r["message"]

    def test_all_match_rejects_one_tampered_source(self, fixture_apk, http_server, tmp_path):
        """apk entry matches the md5 but the URL download is tampered -> FAIL.

        This is the anti-any-match rule: every available source must equal
        the expected md5, otherwise a tampered source hides behind a good one.
        """
        apk, entries = fixture_apk
        expected = _md5_bytes(entries["assets/login.png"])
        (tmp_path / "ref.png").write_bytes(b"tampered-content")
        r = self._run(
            "login", "file", "assets/login.png", expected,
            f"{http_server}/ref.png", "", "", "", apk, "",
        )
        assert r["passed"] is False
        assert "mismatch" in r["message"]

    def test_all_match_accepts_uniform_sources(self, fixture_apk, http_server, tmp_path):
        apk, entries = fixture_apk
        expected = _md5_bytes(entries["assets/login.png"])
        (tmp_path / "ref.png").write_bytes(entries["assets/login.png"])
        r = self._run(
            "login", "file", "assets/login.png", expected,
            f"{http_server}/ref.png", "", "", "", apk, "",
        )
        assert r["passed"] is True

    def test_no_md5_sources_compared_mutually(self, fixture_apk, http_server, tmp_path):
        apk, entries = fixture_apk
        (tmp_path / "ref.png").write_bytes(entries["assets/login.png"])
        r = self._run(
            "login", "file", "assets/login.png", "",
            f"{http_server}/ref.png", "", "", "", apk, "",
        )
        assert r["passed"] is True
        assert r["expected"] == "sources identical"

    def test_no_md5_divergent_sources_fail(self, fixture_apk, http_server, tmp_path):
        apk, _ = fixture_apk
        (tmp_path / "ref.png").write_bytes(b"different")
        r = self._run(
            "login", "file", "assets/login.png", "",
            f"{http_server}/ref.png", "", "", "", apk, "",
        )
        assert r["passed"] is False
        assert "source mismatch" in r["message"]

    def test_single_source_without_md5_fails(self, fixture_apk):
        apk, _ = fixture_apk
        r = self._run(
            "login", "file", "assets/login.png", "",
            "", "", "", "", apk, "",
        )
        assert r["passed"] is False
        assert "no expected md5" in r["message"]

    def test_case_insensitive_ambiguity_fails(self, tmp_path):
        apk = tmp_path / "ambiguous.apk"
        with zipfile.ZipFile(apk, "w") as zf:
            zf.writestr("Assets/Login.png", b"one")
            zf.writestr("assets/login.png", b"two")
        r = self._run(
            "login", "file", "ASSETS/LOGIN.PNG", "0" * 32,
            "", "", "", "", apk, "",
        )
        assert r["passed"] is False
        assert "ambiguous" in r["message"]

    def test_normalized_entry_name_match(self, fixture_apk):
        apk, entries = fixture_apk
        expected = _md5_bytes(entries["assets/login.png"])
        r = self._run(
            "login", "file", "./assets/login.png", expected,
            "", "", "", "", apk, "",
        )
        assert r["passed"] is True


# ── validate-entry: text type ───────────────────────────────────────────────

class TestValidateEntryText:
    def _run(self, *args):
        code, payload, _ = _run_script(VALIDATE_ENTRY, *args)
        assert code == 0
        return payload

    def test_properties_key_equals(self, tmp_path):
        f = tmp_path / "channel.properties"
        f.write_text("channel=huawei\n", encoding="utf-8")
        r = self._run(
            "channel", "text", f, "", "huawei", "equals", "channel", "", "", ""
        )
        assert r["passed"] is True

    def test_properties_key_colon_separator(self, tmp_path):
        f = tmp_path / "app.properties"
        f.write_text("version: 1.2\n", encoding="utf-8")
        r = self._run(
            "version", "text", f, "", "1.2", "equals", "version", "", "", ""
        )
        assert r["passed"] is True

    def test_properties_key_mismatch(self, tmp_path):
        f = tmp_path / "channel.properties"
        f.write_text("channel=xiaomi\n", encoding="utf-8")
        r = self._run(
            "channel", "text", f, "", "huawei", "equals", "channel", "", "", ""
        )
        assert r["passed"] is False
        assert r["actual"] == "xiaomi"

    def test_apk_internal_properties_key(self, fixture_apk):
        apk, _ = fixture_apk
        r = self._run(
            "channel", "text", "assets/channel.properties", "",
            "huawei", "equals", "channel", "", apk, "",
        )
        assert r["passed"] is True, r

    def test_regex_match(self, tmp_path):
        f = tmp_path / "build.txt"
        f.write_text("versionName=1.2.3-beta\n", encoding="utf-8")
        r = self._run(
            "version", "text", f, "", "", "regex", "", r"versionName=\d+\.\d+", "", ""
        )
        assert r["passed"] is True

    def test_absent_match(self, tmp_path):
        f = tmp_path / "config.txt"
        f.write_text("debug=false\n", encoding="utf-8")
        r = self._run(
            "nodebug", "text", f, "", "", "absent", "", r"debug=true", "", ""
        )
        assert r["passed"] is True

    def test_unknown_match_mode(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        r = self._run("a", "text", f, "", "x", "bogus", "", "", "", "")
        assert r["passed"] is False
        assert "unknown match mode" in r["message"]


# ── validate-entry: apk / signature / unknown types ─────────────────────────

class TestValidateEntryApkAndSignature:
    def _run(self, *args):
        code, payload, _ = _run_script(VALIDATE_ENTRY, *args)
        assert code == 0
        return payload

    def test_apk_md5_match(self, fixture_apk):
        apk, _ = fixture_apk
        r = self._run("whole", "apk", "", _md5_file(apk), "", "", "", "", apk, "")
        assert r["passed"] is True

    def test_apk_md5_mismatch(self, fixture_apk):
        apk, _ = fixture_apk
        r = self._run("whole", "apk", "", "0" * 32, "", "", "", "", apk, "")
        assert r["passed"] is False

    def test_signature_match(self):
        md5 = "aa:bb:cc"
        r = self._run("sig", "signature", "", "aabbcc", "", "", "", "", "", md5)
        assert r["passed"] is True

    def test_signature_unavailable(self):
        r = self._run("sig", "signature", "", "aabbcc", "", "", "", "", "", "")
        assert r["passed"] is False
        assert "signature not available" in r["message"]

    def test_unknown_type(self):
        r = self._run("x", "wat", "", "", "", "", "", "", "", "")
        assert r["passed"] is False
        assert "unknown type" in r["message"]


# ── apk-signature ───────────────────────────────────────────────────────────

def _import_apk_signature():
    spec = importlib.util.spec_from_file_location("apk_signature", APK_SIGNATURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestApkSignature:
    def test_degrades_when_no_keytool_and_no_apksigner(self, tmp_path):
        env = dict(os.environ)
        env.pop("JAVA_HOME", None)
        env.pop("BT_JAVA_BIN", None)
        env["PATH"] = str(tmp_path)  # empty dir: no java/keytool on PATH
        env["BT_RUNTIME_DIR"] = str(tmp_path)  # no apksigner.jar either
        code, payload, _ = _run_script(APK_SIGNATURE, "whatever.apk", env=env)
        assert code == 0, "apk_signature must always exit 0"
        assert payload["signature_md5"] == ""
        assert "error" in payload

    def test_find_apksigner_jar_prefers_bt_runtime_dir(self, tmp_path, monkeypatch):
        module = _import_apk_signature()
        jar = tmp_path / "android" / "apksigner.jar"
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b"fake-jar")
        monkeypatch.setenv("BT_RUNTIME_DIR", str(tmp_path))
        assert module._find_apksigner_jar() == str(jar)

    def test_parse_apksigner_style_fingerprints(self):
        module = _import_apk_signature()
        output = (
            "Verified using v1 scheme (JAR signing): false\n"
            "Verified using v2 scheme (APK Signature Scheme v2): true\n"
            "Signer #1 certificate DN: CN=Test\n"
            "Signer #1 certificate SHA-256 digest: 0123abcd\n"
            "Signer #1 certificate SHA-1 digest: 4567efab\n"
            "Signer #1 certificate MD5 digest: 89abcdef\n"
        )
        fingerprints = module._parse_fingerprints(output, "apksigner")
        assert fingerprints["md5"] == "89abcdef"
        assert fingerprints["sha1"] == "4567efab"
        assert fingerprints["sha256"] == "0123abcd"

    def test_parse_keytool_style_fingerprints(self):
        module = _import_apk_signature()
        output = "MD5: AA:BB:CC\nSHA1: 11:22:33\nSHA256: DD:EE:FF\n"
        fingerprints = module._parse_fingerprints(output, "keytool")
        assert fingerprints["md5"] == "AA:BB:CC"
        assert fingerprints["sha1"] == "11:22:33"
        assert fingerprints["sha256"] == "DD:EE:FF"


# ── validate-report ─────────────────────────────────────────────────────────

class TestValidateReport:
    def test_markdown_report(self, tmp_path):
        results_file = tmp_path / "foreach_loop.json"
        results_file.write_text(
            json.dumps(
                {
                    "count": 2,
                    "passed_count": 1,
                    "failed_count": 1,
                    "all_passed": False,
                    "results": [
                        {
                            "item": {"name": "login"},
                            "outputs": {
                                "name": "login",
                                "type": "file",
                                "passed": True,
                                "actual": "abc",
                                "expected": "abc",
                                "message": "md5 match",
                            },
                            "error": None,
                        },
                        {
                            "item": {"name": "channel"},
                            "outputs": {},
                            "error": "boom",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        out = tmp_path / "report.md"
        code, payload, _ = _run_script(VALIDATE_REPORT, results_file, out)
        assert code == 0
        assert payload["all_passed"] is False
        assert payload["passed_count"] == 1
        assert payload["failed_count"] == 1

        text = out.read_text(encoding="utf-8")
        assert "# APK Validation Report" in text
        assert "| login | file | PASS |" in text
        assert "| channel | ? | FAIL |" in text
        assert "boom" in text
