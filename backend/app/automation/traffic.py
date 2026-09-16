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
import json
import os
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from app.automation.adb import run_adb
from app.utils.env import get_cache_dir, get_runtime_dir
from app.utils.logger import Logger

logger = Logger.get_logger("TrafficCapture")

# device_id -> {"proc": Popen, "port": int, "jsonl": str, "log": str}
_ACTIVE: Dict[str, Dict[str, Any]] = {}

DEFAULT_PORT = 18888

# On-disk mirror of `_ACTIVE`, so a LATER backend process can self-heal.
#
# `_ACTIVE` dies with the process, but the device-side wiring does NOT: the
# device keeps `global http_proxy 127.0.0.1:<port>` and the `adb reverse`
# entry pointing at a proxy that no longer exists — i.e. a device with no
# network. This cannot be handled by a graceful-exit hook alone: on Windows
# the Electron main process kills the backend with TerminateProcess
# (`src/main/main.ts` before-quit), so no signal handler runs. The registry
# is therefore written while a capture is live and consumed by
# `recover_stale_capture()` on the NEXT backend start.
_REGISTRY_NAME = "traffic_active.json"


def _registry_path() -> str:
    # create=False: reading the registry (status / recovery probe) must not
    # have a mkdir side effect. `_set_registry` creates the dir when writing.
    return os.path.join(get_cache_dir(create=False), _REGISTRY_NAME)


def _active_entries() -> Dict[str, Dict[str, Any]]:
    """Serializable view of `_ACTIVE` (no Popen objects)."""
    out: Dict[str, Dict[str, Any]] = {}
    for device_id, state in _ACTIVE.items():
        proc = state.get("proc")
        out[str(device_id)] = {
            "port": state.get("port"),
            "jsonl": state.get("jsonl") or "",
            "pid": getattr(proc, "pid", None),
        }
    return out


def _set_registry(entries: Dict[str, Dict[str, Any]]) -> None:
    """Overwrite the registry, or remove it when nothing is active.

    Atomic (`tmp` + `os.replace`): a reader must never see a half-written
    file and conclude there is nothing to heal. Never raises — a registry
    write failure must not fail a capture.
    """
    path = _registry_path()
    if not entries:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning(f"failed to write traffic registry '{path}': {e}")


def _write_registry() -> None:
    _set_registry(_active_entries())


# ----------------------------------------------------------------------
# mitmdump location / environment
# ----------------------------------------------------------------------

def _mitmproxy_lib() -> str:
    return os.path.join(get_runtime_dir(), "mitmproxy", "lib")


def _mitmproxy_conf() -> str:
    d = os.path.join(get_runtime_dir(), "mitmproxy", "conf")
    os.makedirs(d, exist_ok=True)
    return d


def any_capture_active() -> bool:
    """True while any capture runs — refuse reinstall then (Windows locks mitmdump's .pyd/.dll)."""
    return bool(_ACTIVE)


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


def status() -> Dict[str, Any]:
    """One-shot capability report for the settings UI / preflight checks.

    ``ready`` is what the automation page hints on; ``installed`` alone only
    means the package directory exists — compiled wheels can still mismatch
    the running interpreter (see :func:`mitmdump_python_compatible`).
    """
    installed = mitmdump_available()
    mismatch = mitmdump_python_compatible()
    return {
        "installed": installed,
        "ready": installed and mismatch is None,
        "lib_path": _mitmproxy_lib(),
        "python_mismatch": mismatch,
        # Pure read probe — must never create directories (review M2).
        "ca_cert_exists": os.path.isfile(ca_cert_path()),
    }


def ca_cert_path(*, create: bool = False) -> str:
    """Path of the mitmproxy CA cert in the runtime conf dir.

    ``create=False`` (default) only builds the path — read-side callers
    (status probes) must never create directories. Pass ``create=True``
    where the conf dir is genuinely needed, e.g. when handing the path to
    mitmdump, so the dir gets created via :func:`_mitmproxy_conf`.
    """
    if create:
        conf = _mitmproxy_conf()
    else:
        conf = os.path.join(get_runtime_dir(), "mitmproxy", "conf")
    return os.path.join(conf, "mitmproxy-ca-cert.pem")


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
    cert = ca_cert_path(create=True)
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
        # Capture tool: do NOT verify the upstream (real server) certificate.
        # Default verification caused silent misses — e.g. HMS grs.dbankcloud.*
        # failed with "unable to get local issuer certificate" (chain the
        # bundled trust store lacks), the flow errored out and the addon's
        # response() hook never fired, so those requests vanished from the
        # jsonl. Client-side trust is what matters for decryption and is
        # handled by the device CA (install_ca); upstream verification only
        # decides whether we can READ the response.
        "--set", "ssl_insecure=true",
        "--set", "termlog_verbosity=warn",
        "-s", _addon_path(),
    ]
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        argv, env=env, stdout=log_fh, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
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
    # Persist the device-side wiring BEFORE anyone can observe the capture as
    # running: if this process dies now, the next backend start must be able
    # to find and undo it.
    _write_registry()
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
    proxy_restored = False
    try:
        r = run_adb(device_id, ["shell", "settings", "put", "global", "http_proxy", ":0"])
        proxy_restored = r.get("returncode", 1) == 0
        if state:
            run_adb(device_id, ["reverse", "--remove", f"tcp:{state['port']}"])
    except Exception as e:
        logger.warning(f"proxy restore issue for {device_id}: {e}")

    if not state:
        _write_registry()
        return {"success": True, "requests": 0, "proxy_restored": proxy_restored}

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
    _write_registry()
    logger.info(f"traffic capture stopped on {device_id}: {requests} requests")
    return {
        "success": True,
        "jsonl": state["jsonl"],
        "requests": requests,
        "proxy_restored": proxy_restored,
    }


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
    """Best-effort cleanup for graceful backend shutdown (proxy restore everywhere)."""
    for device_id in list(_ACTIVE.keys()):
        try:
            stop_capture(device_id)
        except Exception:
            pass


# ----------------------------------------------------------------------
# stale-capture recovery (next backend start after a hard kill / crash)
# ----------------------------------------------------------------------

def _port_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _port_owner_pid(port: int) -> Optional[int]:
    """pid owning ``127.0.0.1:<port>`` in LISTENING state (Windows only)."""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except Exception:
        return None
    needle = f"127.0.0.1:{port}"
    for line in (out or "").splitlines():
        if "LISTENING" not in line.upper():
            continue
        parts = line.split()
        # proto  local  foreign  state  pid
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[1] == needle:
            try:
                return int(parts[-1])
            except ValueError:
                return None
    return None


def _image_name_for_pid(pid: int) -> str:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except Exception:
        return ""
    first = (out or "").strip().splitlines()
    if not first:
        return ""
    return first[0].split(",")[0].strip().strip('"').lower()


def _free_port(port: int) -> Optional[bool]:
    """Terminate an ORPHANED mitmdump still holding ``port``.

    A hard-killed parent does not take its children down on Windows, so a
    stale mitmdump keeps 18888 bound and every later capture fails with
    "port already in use". Deliberately conservative: only a Windows
    listener whose image is python (mitmdump is run as
    ``<python> -c ...``) and which is NOT this process is signalled, so a
    reused pid cannot take down an unrelated app. Returns ``None`` when
    nothing was listening, ``True``/``False`` when it was (and is/is not
    gone afterwards).
    """
    if not _port_listening(port):
        return None
    pid = _port_owner_pid(port)
    if not pid or pid == os.getpid():
        return False
    if not _image_name_for_pid(pid).startswith("python"):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        logger.warning(f"failed to terminate stale mitmdump pid {pid}: {e}")
        return False
    deadline = time.time() + 3.0
    while time.time() < deadline and _port_listening(port):
        time.sleep(0.2)
    freed = not _port_listening(port)
    logger.info(f"stale mitmdump pid {pid} on port {port}: freed={freed}")
    return freed


def _port_in_use_by_us(port: int) -> bool:
    """True when a LIVE capture in this process already owns ``port``.

    Guards ``_free_port``: a stale registry entry for device A must never
    make us kill the mitmdump that device B is legitimately using right now.
    """
    return any(state.get("port") == port for state in _ACTIVE.values())


def recover_stale_capture(device_id: Optional[str] = None) -> Dict[str, Any]:
    """Undo device-side capture wiring left behind by a previous process.

    Called at backend start (``backend/main.py``) and from the
    ``automation.traffic_reset`` handler. Captures still alive in THIS
    process are never touched. Entries are consumed whether or not the
    device answered (an unplugged device must not make the next start
    re-run the same recovery forever) — per-device success is reported.

    Returns ``{"success": True, "restored": [{device_id, proxy_restored,
    reverse_removed, port_freed, error?}]}``.
    """
    try:
        with open(_registry_path(), "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, ValueError):
        entries = {}
    if not isinstance(entries, dict):
        entries = {}

    wanted = str(device_id) if device_id else ""
    targets = {
        str(dev): info
        for dev, info in entries.items()
        if str(dev) not in _ACTIVE and (not wanted or str(dev) == wanted)
    }

    restored = []
    for dev, info in targets.items():
        info = info if isinstance(info, dict) else {}
        port = info.get("port")
        rec: Dict[str, Any] = {
            "device_id": dev,
            "proxy_restored": False,
            "reverse_removed": False,
            "port_freed": None,
        }
        try:
            r = run_adb(dev, ["shell", "settings", "put", "global", "http_proxy", ":0"])
            rec["proxy_restored"] = r.get("returncode", 1) == 0
            if port:
                rr = run_adb(dev, ["reverse", "--remove", f"tcp:{int(port)}"])
                rec["reverse_removed"] = rr.get("returncode", 1) == 0
        except Exception as e:  # offline device / adb failure — report, do not raise
            rec["error"] = str(e)
        if port and not _port_in_use_by_us(int(port)):
            try:
                rec["port_freed"] = _free_port(int(port))
            except Exception as e:
                rec["port_freed"] = False
                rec["error"] = rec.get("error") or str(e)
        restored.append(rec)

    # Keep live entries and any stale entry the caller did not ask about.
    remaining = {
        str(dev): info
        for dev, info in entries.items()
        if str(dev) in _ACTIVE or str(dev) not in targets
    }
    _set_registry(remaining)
    if restored:
        logger.info(f"recovered stale traffic capture: {restored}")
    return {"success": True, "restored": restored}
