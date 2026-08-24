#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK Signature Tool — extract signer certificate fingerprints.

Strategy:
    1. ``keytool -printcert -jarfile <apk>`` — covers v1 (JAR) signatures.
    2. Fallback: ``apksigner verify --print-certs <apk>`` — covers v2/v3-only
       APKs that keytool cannot read.  apksigner is located as a jar under
       ``BT_RUNTIME_DIR`` (e.g. ``<BT_RUNTIME_DIR>/android/apksigner.jar``)
       or next to this script's ``runtime/`` checkout, and run with the
       resolved java binary.

Usage:
    python apk_signature.py <apk_path>

Prints a single-line JSON object to stdout and ALWAYS exits 0 (degrade
gracefully, never crash the workflow):

    {"signature_md5": "...", "signature_sha1": "...", "signature_sha256": "..."}

On a missing keytool AND apksigner / failed commands it prints:
    {"signature_md5": "", "error": "<short reason>"}
"""

import json
import os
import re
import shutil
import subprocess
import sys


def _find_java_bin():
    """Locate the java executable: BT_JAVA_BIN, then JAVA_HOME/bin, then PATH."""
    env = os.environ.get("BT_JAVA_BIN", "")
    if env and os.path.isfile(env):
        return env

    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        java_name = "java.exe" if os.name == "nt" else "java"
        candidate = os.path.join(java_home, "bin", java_name)
        if os.path.isfile(candidate):
            return candidate

    return shutil.which("java")


def _find_keytool(java_bin):
    """Locate keytool, preferring the sibling of java_bin, else PATH."""
    if java_bin:
        java_dir = os.path.dirname(java_bin)
        keytool_name = "keytool.exe" if os.name == "nt" else "keytool"
        candidate = os.path.join(java_dir, keytool_name)
        if os.path.isfile(candidate):
            return candidate

    return shutil.which("keytool")


def _find_apksigner_jar():
    """Locate apksigner.jar under BT_RUNTIME_DIR or a sibling runtime/ dir.

    Mirrors the ``apksigner`` descriptor layout (``android/apksigner.jar``
    relative to the runtime root); a couple of common alternative layouts
    are accepted as well.
    """
    roots = []
    runtime_dir = os.environ.get("BT_RUNTIME_DIR", "")
    if runtime_dir:
        roots.append(runtime_dir)
    # <repo>/runtime relative to this script (examples/tools/android/...).
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
    roots.append(os.path.join(repo_root, "runtime"))

    relatives = [
        os.path.join("android", "apksigner.jar"),
        os.path.join("apksigner", "apksigner.jar"),
        "apksigner.jar",
    ]
    for root in roots:
        for relative in relatives:
            candidate = os.path.join(root, relative)
            if os.path.isfile(candidate):
                return candidate
    return ""


def _parse_fingerprints(output, style):
    """Parse MD5/SHA1/SHA256 fingerprints from tool output.

    ``style`` is ``"keytool"`` (``MD5: AA:BB:...``) or ``"apksigner"``
    (``Signer #1 certificate MD5 digest: aabb...``).
    """
    if style == "keytool":
        patterns = {
            "md5": r"MD5\s*:\s*([0-9A-Fa-f:]+)",
            "sha1": r"SHA1\s*:\s*([0-9A-Fa-f:]+)",
            "sha256": r"SHA256\s*:\s*([0-9A-Fa-f:]+)",
        }
    else:
        patterns = {
            "md5": r"certificate MD5 digest:\s*([0-9A-Fa-f]+)",
            "sha1": r"certificate SHA-1 digest:\s*([0-9A-Fa-f]+)",
            "sha256": r"certificate SHA-256 digest:\s*([0-9A-Fa-f]+)",
        }

    result = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        result[key] = match.group(1) if match else ""
    return result


def _run(cmd):
    """Run a command, returning (returncode, combined_output) or raising."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")


def _via_keytool(apk_path, keytool):
    """v1 (JAR) signature fingerprints via keytool; '' md5 on failure."""
    returncode, output = _run([keytool, "-printcert", "-jarfile", apk_path])
    fingerprints = _parse_fingerprints(output, "keytool")
    if returncode != 0 or not fingerprints["md5"]:
        return None
    return fingerprints


def _via_apksigner(apk_path, java_bin, apksigner_jar):
    """v2/v3 signature fingerprints via apksigner; None on failure."""
    returncode, output = _run(
        [java_bin, "-jar", apksigner_jar, "verify", "--print-certs", apk_path]
    )
    fingerprints = _parse_fingerprints(output, "apksigner")
    if not fingerprints["md5"]:
        return None
    return fingerprints


def _emit(payload):
    print(json.dumps(payload))


def main() -> int:
    if len(sys.argv) < 2:
        _emit({"signature_md5": "", "error": "usage: apk_signature.py <apk_path>"})
        return 0

    apk_path = sys.argv[1]
    java_bin = _find_java_bin()
    keytool = _find_keytool(java_bin)

    if keytool:
        try:
            fingerprints = _via_keytool(apk_path, keytool)
        except Exception:
            fingerprints = None
        if fingerprints:
            _emit(
                {
                    "signature_md5": fingerprints["md5"],
                    "signature_sha1": fingerprints["sha1"],
                    "signature_sha256": fingerprints["sha256"],
                    "source": "keytool",
                }
            )
            return 0

    # keytool missing or produced no fingerprint — try apksigner (v2/v3).
    apksigner_jar = _find_apksigner_jar()
    if java_bin and apksigner_jar:
        try:
            fingerprints = _via_apksigner(apk_path, java_bin, apksigner_jar)
        except Exception:
            fingerprints = None
        if fingerprints:
            _emit(
                {
                    "signature_md5": fingerprints["md5"],
                    "signature_sha1": fingerprints["sha1"],
                    "signature_sha256": fingerprints["sha256"],
                    "source": "apksigner",
                }
            )
            return 0

    if not keytool and not apksigner_jar:
        reason = "neither keytool nor apksigner found"
    elif not apksigner_jar:
        reason = "keytool found no v1 signature and apksigner.jar not found (v2/v3-only apk?)"
    else:
        reason = "no certificate fingerprint in keytool/apksigner output"
    _emit({"signature_md5": "", "error": reason})
    return 0


if __name__ == "__main__":
    sys.exit(main())
