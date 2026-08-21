#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK Signature Tool — extract signer certificate fingerprints via keytool.

Usage:
    python apk_signature.py <apk_path>

Prints a single-line JSON object to stdout and ALWAYS exits 0 (degrade
gracefully, never crash the workflow):

    {"signature_md5": "...", "signature_sha1": "...", "signature_sha256": "..."}

On a missing keytool / failed command it prints:
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


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"signature_md5": "", "error": "usage: apk_signature.py <apk_path>"}))
        return 0

    apk_path = sys.argv[1]

    java_bin = _find_java_bin()
    keytool = _find_keytool(java_bin)

    if not keytool:
        print(json.dumps({"signature_md5": "", "error": "keytool not found"}))
        return 0

    cmd = [keytool, "-printcert", "-jarfile", apk_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as exc:
        print(json.dumps({"signature_md5": "", "error": f"keytool failed: {exc}"}))
        return 0

    output = (proc.stdout or "") + "\n" + (proc.stderr or "")

    md5_match = re.search(r"MD5\s*:\s*([0-9A-Fa-f:]+)", output)
    sha1_match = re.search(r"SHA1\s*:\s*([0-9A-Fa-f:]+)", output)
    sha256_match = re.search(r"SHA256\s*:\s*([0-9A-Fa-f:]+)", output)

    md5 = md5_match.group(1) if md5_match else ""
    sha1 = sha1_match.group(1) if sha1_match else ""
    sha256 = sha256_match.group(1) if sha256_match else ""

    if proc.returncode != 0 or not md5:
        reason = "keytool failed" if proc.returncode != 0 else "no certificate fingerprint in keytool output"
        print(json.dumps({"signature_md5": "", "error": reason}))
        return 0

    print(json.dumps({
        "signature_md5": md5,
        "signature_sha1": sha1,
        "signature_sha256": sha256,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
