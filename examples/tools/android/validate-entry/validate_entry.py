#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate Entry Tool — validate a single APK validation entry.

Usage:
    python validate_entry.py <name> <type> <path> <md5> <value> <match> \
        <key> <pattern> <apk_path> <signature_md5>

Validation types:
    file       — md5 of a local file (or a URL downloaded to a temp file).
    text       — file content match (equals / exact / regex / absent).
    apk        — md5 of the resolved APK file.
    signature  — signer MD5 fingerprint match.

Always prints a single-line JSON result object to stdout and exits 0 —
validation mismatches are results, not errors:
    {"name": ..., "type": ..., "passed": bool, "actual": ..., "expected": ..., "message": ...}
"""

import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request


def normalize_md5(s):
    """Lowercase and strip all non-hex characters from an MD5 string."""
    return re.sub(r"[^0-9a-f]", "", (s or "").lower())


def file_md5(path):
    """Compute the MD5 hex digest of a file (chunked read)."""
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_to_temp(url):
    """Download a URL to a temp file and return its path."""
    fd, tmp = tempfile.mkstemp(prefix="validate_entry_", suffix=".bin")
    os.close(fd)
    try:
        urllib.request.urlretrieve(url, tmp)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return tmp


def _truncate(text, limit=200):
    """Truncate text to ~limit characters."""
    if len(text) > limit:
        return text[:limit]
    return text


def main(argv):
    name = argv[0] if len(argv) > 0 else ""
    entry_type = argv[1] if len(argv) > 1 else ""
    path = argv[2] if len(argv) > 2 else ""
    md5 = argv[3] if len(argv) > 3 else ""
    value = argv[4] if len(argv) > 4 else ""
    match = argv[5] if len(argv) > 5 else ""
    key = argv[6] if len(argv) > 6 else ""
    pattern = argv[7] if len(argv) > 7 else ""
    apk_path = argv[8] if len(argv) > 8 else ""
    signature_md5 = argv[9] if len(argv) > 9 else ""

    actual = ""
    expected = ""
    message = ""
    passed = False

    if entry_type == "file":
        target = path
        if value.startswith("http://") or value.startswith("https://"):
            target = download_to_temp(value)
        if not target or not os.path.isfile(target):
            passed = False
            message = f"file not found: {path}"
        else:
            actual = file_md5(target)
            expected = normalize_md5(md5)
            passed = actual == expected
            message = "md5 match" if passed else "md5 mismatch"

    elif entry_type == "text":
        if not path or not os.path.isfile(path):
            passed = False
            message = f"file not found: {path}"
        else:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if key:
                props = {}
                for line in content.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    if "=" in stripped:
                        k, v = stripped.split("=", 1)
                        props[k.strip()] = v.strip()
                matched_text = props.get(key, "")
            else:
                matched_text = content

            if match in ("equals", ""):
                passed = matched_text.strip() == (value or "").strip()
            elif match == "exact":
                passed = content.strip() == (value or "").strip()
            elif match == "regex":
                regex = pattern or value
                passed = re.search(regex, matched_text) is not None
            elif match == "absent":
                regex = pattern or value
                passed = re.search(regex, matched_text) is None
            else:
                passed = False
                message = f"unknown match mode: {match}"

            actual = _truncate(matched_text)
            expected = value or pattern
            if not message:
                message = "text match" if passed else "text mismatch"

    elif entry_type == "apk":
        if not apk_path:
            passed = False
            message = "apk_path not resolved"
        else:
            actual = file_md5(apk_path)
            expected = normalize_md5(md5)
            passed = actual == expected
            message = "md5 match" if passed else "md5 mismatch"

    elif entry_type == "signature":
        actual = normalize_md5(signature_md5)
        expected = normalize_md5(md5)
        if actual == "":
            passed = False
            message = "signature not available (keytool missing?)"
        else:
            passed = actual == expected
            message = "signature match" if passed else "signature mismatch"

    else:
        passed = False
        message = f"unknown type: {entry_type}"

    return {
        "name": name,
        "type": entry_type,
        "passed": passed,
        "actual": actual,
        "expected": expected,
        "message": message,
    }


if __name__ == "__main__":
    argv = sys.argv[1:]
    try:
        result = main(argv)
    except Exception as exc:
        result = {
            "name": argv[0] if len(argv) > 0 else "",
            "type": argv[1] if len(argv) > 1 else "",
            "passed": False,
            "actual": "",
            "expected": "",
            "message": f"error: {exc}",
        }
    print(json.dumps(result))
    sys.exit(0)
