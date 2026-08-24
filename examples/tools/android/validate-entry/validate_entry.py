#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate Entry Tool — validate a single APK validation entry.

Usage:
    python validate_entry.py <name> <type> <path> <md5> <value> <match> \
        <key> <pattern> <apk_path> <signature_md5>

Validation types:
    file       — md5 of a local file, an entry inside the APK zip, or a URL
                 downloaded to a temp file.  Every available source must
                 match the expected md5 (all-match); with no expected md5,
                 multiple sources must be identical to each other.
    text       — file content match (equals / exact / regex / absent), with
                 optional key=value (or key:value) extraction from
                 properties files.  Content is read from disk first, then
                 from inside the APK zip.
    apk        — md5 of the resolved APK file.
    signature  — signer MD5 fingerprint match.

``path`` may point at a local file on disk OR at an entry inside the APK
(e.g. ``assets/login.png``); disk is tried first, then the APK zip.

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
import zipfile

#: Network timeout (seconds) for URL downloads — never hang the workflow.
DOWNLOAD_TIMEOUT = 30

#: Sentinel returned by _apk_entry_bytes when several zip entries match a
#: case-insensitive lookup (the caller cannot know which one was meant).
_AMBIGUOUS = object()


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


def bytes_md5(data):
    """Compute the MD5 hex digest of a bytes object."""
    return hashlib.md5(data).hexdigest()


def download_to_temp(url):
    """Download a URL to a temp file (30s timeout, streamed) and return its path."""
    fd, tmp = tempfile.mkstemp(prefix="validate_entry_", suffix=".bin")
    os.close(fd)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "validate-entry/1.0"})
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
            with open(tmp, "wb") as out:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return tmp


def _entry_name_candidates(entry_name):
    """Return lookup candidates: the exact name, then normalized forms."""
    candidates = [entry_name]
    normalized = entry_name
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    if normalized != entry_name:
        candidates.append(normalized)
    return candidates


def _apk_entry_bytes(apk_path, entry_name):
    """Read an entry from the APK zip.

    Lookup order (per the review decision on ambiguity): exact name, then
    normalized (``./`` / leading ``/`` stripped), then case-insensitive as a
    last resort.  Returns ``(bytes, None)`` on a hit, ``(None, None)`` when
    the entry is absent, ``(_AMBIGUOUS, names)`` when a case-insensitive
    lookup matches several distinct entries, and ``(None, error)`` when the
    APK itself cannot be opened.
    """
    if not apk_path or not os.path.isfile(apk_path):
        return None, f"apk not available: {apk_path or '(not provided)'}"
    try:
        archive = zipfile.ZipFile(apk_path)
    except (zipfile.BadZipFile, OSError) as exc:
        return None, f"cannot open apk as zip: {exc}"

    with archive:
        names = archive.namelist()
        name_set = set(names)

        for candidate in _entry_name_candidates(entry_name):
            if candidate in name_set:
                return archive.read(candidate), None

        # Last resort: case-insensitive match.  Several distinct entries
        # (e.g. ``Assets/Login.png`` vs ``assets/login.png``) make the
        # lookup ambiguous — refuse to guess.
        lowered = entry_name.lstrip("./").lstrip("/").lower()
        hits = [n for n in names if n.lower() == lowered]
        if len(hits) == 1:
            return archive.read(hits[0]), None
        if len(hits) > 1:
            return _AMBIGUOUS, hits

    return None, None


def _read_content_bytes(path, apk_path):
    """Read a file's bytes from disk first, then from inside the APK zip.

    Returns ``(data, source_label, error)``.  ``data`` is ``None`` when the
    file is nowhere to be found; ``_AMBIGUOUS`` when the APK lookup was
    ambiguous (``source_label`` then holds the candidate names).
    """
    if path and os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read(), path, None
    if path and apk_path:
        data, err = _apk_entry_bytes(apk_path, path)
        if data is _AMBIGUOUS:
            # err holds the list of conflicting entry names.
            return _AMBIGUOUS, err, None
        if err:
            return None, None, err
        if data is not None:
            return data, f"apk:{path}", None
    return None, None, None


def _is_url(value):
    return value.startswith("http://") or value.startswith("https://")


def _validate_file(path, md5, value, apk_path):
    """file type: every available source must match the expected md5.

    Sources: the file at ``path`` (disk or APK entry) and, when ``value``
    is a URL, the downloaded reference file.  With an expected ``md5``,
    ALL sources must equal it (any-match would let a tampered source slip
    through when another source still matches).  Without an expected md5,
    two or more sources must be mutually identical; a single source has
    nothing to be checked against and fails.
    """
    expected = normalize_md5(md5)
    sources = []  # list of (label, md5)

    data, label, err = _read_content_bytes(path, apk_path)
    if err:
        return False, "", expected, err
    if data is _AMBIGUOUS:
        return False, "", expected, (
            f"ambiguous apk entry for {path!r}: {', '.join(label)}"
        )
    if data is not None:
        sources.append((label, bytes_md5(data)))

    if value and _is_url(value):
        tmp = download_to_temp(value)  # raises -> caught by __main__ wrapper
        try:
            sources.append((value, file_md5(tmp)))
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    if not sources:
        return False, "", expected, f"file not found: {path}"

    actual = sources[0][1]

    if expected:
        mismatches = [src for src, digest in sources if digest != expected]
        passed = not mismatches
        message = (
            "md5 match"
            if passed
            else "md5 mismatch: " + "; ".join(mismatches)
        )
        return passed, actual, expected, message

    if len(sources) >= 2:
        passed = all(digest == actual for _, digest in sources)
        message = (
            "sources identical"
            if passed
            else "source mismatch: "
            + "; ".join(f"{src}={digest}" for src, digest in sources)
        )
        return passed, actual, "sources identical", message

    return False, actual, "", "no expected md5 given"


def _parse_properties(content):
    """Parse a properties-style body into a dict (``=`` and ``:`` separators)."""
    props = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([^=:]+)[=:](.*)$", stripped)
        if match:
            props[match.group(1).strip()] = match.group(2).strip()
    return props


def _validate_text(path, value, match, key, pattern, apk_path):
    """text type: content match with optional properties key extraction."""
    data, _label, err = _read_content_bytes(path, apk_path)
    if err:
        return False, "", value or pattern, err
    if data is _AMBIGUOUS:
        return False, "", value or pattern, f"ambiguous apk entry for {path!r}"
    if data is None:
        return False, "", value or pattern, f"file not found: {path}"

    content = data.decode("utf-8", errors="replace")

    if key:
        matched_text = _parse_properties(content).get(key, "")
    else:
        matched_text = content

    message = ""
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
    return passed, actual, expected, message


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

    if entry_type == "file":
        passed, actual, expected, message = _validate_file(
            path, md5, value, apk_path
        )

    elif entry_type == "text":
        passed, actual, expected, message = _validate_text(
            path, value, match, key, pattern, apk_path
        )

    elif entry_type == "apk":
        if not apk_path:
            passed, actual, expected = False, "", normalize_md5(md5)
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
            message = "signature not available (keytool/apksigner missing?)"
        else:
            passed = actual == expected
            message = "signature match" if passed else "signature mismatch"

    else:
        passed = False
        actual = ""
        expected = ""
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
