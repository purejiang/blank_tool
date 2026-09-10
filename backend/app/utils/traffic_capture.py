#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Traffic capture for adb automation — mitmdump orchestration (stdlib only).

The actual interception is done by ``mitmdump`` (installed under
``<runtime>/mitmproxy/lib``, imported via PYTHONPATH) driven by the addon in
``traffic_addon.py`` which appends one JSON object per completed exchange to
a JSONL file.

Device-side wiring:
  * ``adb reverse tcp:<port> tcp:<port>`` — the device reaches the PC-side
    proxy through its own ``127.0.0.1:<port>`` (no LAN IP discovery, works
    over USB and TCP adb alike).
  * ``settings put global http_proxy 127.0.0.1:<port>`` routes the device's
    HTTP(S) traffic through the proxy.
  * On rooted devices (MuMu) the mitmproxy CA is pushed into the system cert
    store so HTTPS can be decrypted; without it only plain HTTP is readable.

Every ``start_capture`` MUST be paired with ``stop_capture`` — the proxy
restores ``http_proxy :0`` (a device left pointing at a dead proxy loses all
connectivity) and terminates the mitmdump process.
"""

import base64
import hashlib
import os
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from app.utils.env import get_runtime_dir
from app.utils.logger import Logger

logger = Logger.get_logger("TrafficCapture")

# device_id -> {"proc": Popen, "port": int, "jsonl": str, "log": str}
_ACTIVE: Dict[str, Dict[str, Any]] = {}

DEFAULT_PORT = 18888


# ----------------------------------------------------------------------
# mitmdump location / environment
# ----------------------------------------------------------------------

def _mitmproxy_lib() -> str:
    return os.path.join(get_runtime_dir(), "mitmproxy", "lib")


def _mitmproxy_conf() -> str:
    d = os.path.join(get_runtime_dir(), "mitmproxy", "conf")
    os.makedirs(d, exist_ok=True)
    return d


def mitmdump_available() -> bool:
    """mitmdump is importable when runtime/mitmproxy/lib holds the package."""
    return os.path.isdir(os.path.join(_mitmproxy_lib(), "mitmproxy"))


def mitmdump_python_compatible() -> Optional[str]:
    """Error string when the installed wheels don't match this interpreter.

    ``runtime/mitmproxy/PYTHON_MARKER`` records the ``X.Y`` used at install
    time (compiled deps like cryptography ship cpXY wheels). Empty marker →
    assume compatible.
    """
    marker = os.path.join(get_runtime_dir(), "mitmproxy", "PYTHON_MARKER")
    try:
        with open(marker, "r", encoding="utf-8") as f:
            want = f.read().strip()
    except OSError:
        return None
    cur = f"{sys.version_info[0]}.{sys.version_info[1]}"
    if want and want != cur:
        return (
            f"mitmproxy installed for Python {want} but backend runs {cur} — "
            f"reinstall with: pip install --target {os.path.dirname(marker)}/lib mitmproxy"
        )
    return None


def ca_cert_path() -> str:
    return os.path.join(_mitmproxy_conf(), "mitmproxy-ca-cert.pem")


def _addon_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "traffic_addon.py")


# ----------------------------------------------------------------------
# CA subject hash (openssl x509 -subject_hash_old equivalent)
# ----------------------------------------------------------------------

def _der_read_len(data: bytes, pos: int):
    """Read a DER length at pos. Returns (length, next_pos)."""
    b = data[pos]
    pos += 1
    if b < 0x80:
        return b, pos
    n = b & 0x7F
    return int.from_bytes(data[pos:pos + n], "big"), pos + n


def _der_children(data: bytes):
    """Yield (tag, elem_start, content_start, end) for children of the DER
    CONTENT of a constructed element (tag+length already stripped)."""
    pos = 0
    while pos < len(data):
        elem_start = pos
        tag = data[pos]
        content_start = pos + 1
        length, content_start = _der_read_len(data, content_start)
        end = content_start + length
        yield tag, elem_start, content_start, end
        pos = end


def subject_hash_old(cert_pem_path: str) -> str:
    """openssl ``subject_hash_old``: first 4 bytes of MD5(DER subject Name),
    rendered little-endian. Android names system CAs ``<hash>.0``.

    Minimal DER walk: Certificate → tbsCertificate → children — the two
    ``SEQUENCE`` Names sit between sigAlg and validity (issuer) / after
    validity (subject).
    """
    with open(cert_pem_path, "rb") as f:
        pem = f.read()
    b64 = b"".join(
        line for line in pem.splitlines()
        if b"-----" not in line
    )
    der = base64.b64decode(b64)

    # top: SEQUENCE (cert) → first child = tbsCertificate SEQUENCE.
    # All offsets below are relative to ``body`` (der with the outer
    # SEQUENCE header stripped) — never mix them with ``der`` indexes.
    body = der[1 + _len_size(der, 1):]
    _, _, tbs_start, tbs_end = list(_der_children(body))[0]
    tbs_body = body[tbs_start:tbs_end]

    subject_der = None
    seq_seen = 0
    for tag, elem_start, _, end in _der_children(tbs_body):
        if tag == 0x30:
            seq_seen += 1
            if seq_seen == 4:  # 1=sigAlg, 2=issuer, 3=validity, 4=subject
                # hash the full Name DER (tag+len+content), like openssl
                subject_der = bytes(tbs_body[elem_start:end])
                break
        elif tag in (0x02, 0xA0):
            continue
    if subject_der is None:
        raise ValueError("could not locate subject Name in certificate DER")
    h = hashlib.md5(subject_der).digest()[:4]
    return "".join(f"{b:02x}" for b in reversed(h))


def _len_size(data: bytes, pos: int) -> int:
    """Size of the DER length field at pos (after the tag byte)."""
    b = data[pos]
    return 1 if b < 0x80 else 1 + (b & 0x7F)


# ----------------------------------------------------------------------
# device-side CA install (root required — MuMu)
# ----------------------------------------------------------------------

def _su(device_id: str, script: str) -> Dict[str, Any]:
    """Run a multi-word shell script as root.

    ``run_adb`` joins argv with spaces and sends it through the device
    shell WITHOUT re-quoting, so ``su -c`` would only see the first word of
    an unquoted script. Wrap the whole script in single quotes (scripts
    here must therefore not contain single quotes themselves).
    """
    from app.utils.adb_auto_core import run_adb
    return run_adb(device_id, ["shell", "su", "-c", "'" + script + "'"])


def _ca_installed(device_id: str, hash_name: str) -> bool:
    r = _su(device_id, f"test -f /system/etc/security/cacerts/{hash_name}.0")
    return r.get("returncode", 1) == 0


def install_ca(device_id: str) -> Dict[str, Any]:
    """Push the mitmproxy CA into the system cert store (needs root).

    Returns ``{"success": bool, "already_installed": bool, "error": str}``.
    A failure here only means HTTPS stays encrypted — plain HTTP capture
    still works, so callers should degrade gracefully.
    """
    from app.utils.adb_auto_core import run_adb

    cert = ca_cert_path()
    if not os.path.isfile(cert):
        return {"success": False, "error": f"CA cert not generated yet: {cert}"}
    try:
        hash_name = subject_hash_old(cert)
    except Exception as e:
        return {"success": False, "error": f"subject hash failed: {e}"}

    if _ca_installed(device_id, hash_name):
        return {"success": True, "already_installed": True}

    tmp = f"/data/local/tmp/{hash_name}.0"
    r = run_adb(device_id, ["push", cert, tmp])
    if r.get("returncode", 1) != 0:
        return {"success": False, "error": "adb push CA failed"}

    # MuMu (Android 12, systemless root): try both remount spellings, then
    # copy + chmod. The whole script is single-quoted for `su -c` (see _su).
    script = (
        "mount -o rw,remount / 2>/dev/null; "
        "mount -o rw,remount /system 2>/dev/null; "
        f"cp {tmp} /system/etc/security/cacerts/{hash_name}.0 && "
        f"chmod 644 /system/etc/security/cacerts/{hash_name}.0"
    )
    r = _su(device_id, script)
    if r.get("returncode", 1) != 0 or not _ca_installed(device_id, hash_name):
        return {
            "success": False,
            "error": "CA install failed (no root or read-only /system)",
        }
    logger.info(f"mitmproxy CA installed on {device_id} ({hash_name}.0)")
    return {"success": True, "already_installed": False}


# ----------------------------------------------------------------------
# start / stop
# ----------------------------------------------------------------------

def start_capture(
    device_id: str,
    jsonl_path: str,
    port: int = DEFAULT_PORT,
    host_filter: str = "",
    install_root_ca: bool = True,
) -> Dict[str, Any]:
    """Start mitmdump + wire the device to it.

    Returns ``{"success", "error", "jsonl", "port", "https_ready"}``.
    ``https_ready=False`` means the CA could not be installed — HTTPS
    traffic will appear as CONNECT failures / TLS errors only.
    """
    if device_id in _ACTIVE:
        return {"success": False, "error": "capture already running on this device"}
    if not mitmdump_available():
        return {
            "success": False,
            "error": "mitmproxy not found in runtime/mitmproxy/lib",
        }
    mismatch = mitmdump_python_compatible()
    if mismatch:
        return {"success": False, "error": mismatch}

    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    log_path = jsonl_path + ".mitmdump.log"

    # Pre-flight: if the port is already taken (by OUR mitmdump or another
    # process — Clash UIs love 8888), bind fails and the ready-probe below
    # would falsely connect to the squatter. Fail fast with a clear error.
    try:
        probe = socket.socket()
        probe.bind(("127.0.0.1", port))
        probe.close()
    except OSError:
        return {
            "success": False,
            "error": f"port {port} already in use by another process",
        }

    env = os.environ.copy()
    lib = _mitmproxy_lib()
    env["PYTHONPATH"] = lib + os.pathsep + env.get("PYTHONPATH", "")
    env["TRAFFIC_JSONL"] = jsonl_path
    env["TRAFFIC_HOST_FILTER"] = host_filter or ""

    # Run mitmdump via an inline entry (pip --target installs have no
    # console scripts). argv is rebuilt before calling so mitmdump parses
    # our CLI flags.
    code = (
        "import sys;"
        "from mitmproxy.tools.main import mitmdump;"
        "sys.exit(mitmdump())"
    )
    argv = [
        sys.executable, "-c", code,
        "--listen-host", "127.0.0.1",
        "--listen-port", str(port),
        "--set", f"confdir={_mitmproxy_conf()}",
        "--set", "termlog_verbosity=warn",
        "-s", _addon_path(),
    ]
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        argv, env=env, stdout=log_fh, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    # wait for the proxy port to accept connections (CA generation happens
    # on first start and can take a couple of seconds)
    deadline = time.time() + 20.0
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            log_fh.close()
            return {
                "success": False,
                "error": f"mitmdump exited early (code {proc.returncode}), see {log_path}",
            }
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                ready = True
                break
        except OSError:
            time.sleep(0.2)
    # The connect may have hit a squatter that grabbed the port between our
    # probe and mitmdump's bind — make sure OUR process is still alive.
    if not ready or proc.poll() is not None:
        _terminate(proc)
        log_fh.close()
        return {
            "success": False,
            "error": f"mitmdump not ready on port {port} (bind failed or exited), see {log_path}",
        }

    https_ready = False
    if install_root_ca:
        ca = install_ca(device_id)
        https_ready = bool(ca.get("success"))

    from app.utils.adb_auto_core import run_adb
    r = run_adb(device_id, ["reverse", f"tcp:{port}", f"tcp:{port}"])
    if r.get("returncode", 1) != 0:
        _terminate(proc)
        log_fh.close()
        return {"success": False, "error": "adb reverse failed"}

    r = run_adb(device_id, ["shell", "settings", "put", "global", "http_proxy",
                            f"127.0.0.1:{port}"])
    if r.get("returncode", 1) != 0:
        run_adb(device_id, ["reverse", "--remove", f"tcp:{port}"])
        _terminate(proc)
        log_fh.close()
        return {"success": False, "error": "settings put http_proxy failed"}

    _ACTIVE[device_id] = {
        "proc": proc, "log_fh": log_fh, "port": port,
        "jsonl": jsonl_path, "log": log_path,
    }
    logger.info(
        f"traffic capture started on {device_id}: port={port}, "
        f"https_ready={https_ready}, jsonl={jsonl_path}"
    )
    return {
        "success": True, "jsonl": jsonl_path, "port": port,
        "https_ready": https_ready,
    }


def stop_capture(device_id: str) -> Dict[str, Any]:
    """Restore device proxy, remove reverse, stop mitmdump.

    Safe to call even when nothing is running (all steps best-effort).
    Returns ``{"success", "jsonl", "requests", "error"}`` — ``requests`` is
    the number of JSONL records written (0 when unknown).
    """
    state = _ACTIVE.pop(device_id, None)

    # proxy restore first — a device pointing at a dead proxy is offline
    try:
        from app.utils.adb_auto_core import run_adb
        run_adb(device_id, ["shell", "settings", "put", "global", "http_proxy", ":0"])
        if state:
            run_adb(device_id, ["reverse", "--remove", f"tcp:{state['port']}"])
    except Exception as e:
        logger.warning(f"proxy restore issue for {device_id}: {e}")

    if not state:
        return {"success": True, "requests": 0}

    proc: subprocess.Popen = state["proc"]
    _terminate(proc)
    try:
        state["log_fh"].close()
    except Exception:
        pass

    requests = 0
    try:
        with open(state["jsonl"], "rb") as f:
            requests = sum(1 for line in f if line.strip())
    except OSError:
        pass
    logger.info(f"traffic capture stopped on {device_id}: {requests} requests")
    return {"success": True, "jsonl": state["jsonl"], "requests": requests}


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def stop_all() -> None:
    """Best-effort cleanup for backend shutdown (proxy restore everywhere)."""
    for device_id in list(_ACTIVE.keys()):
        try:
            stop_capture(device_id)
        except Exception:
            pass
