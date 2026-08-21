#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK Resolve Tool — resolve a local path or http(s) URL to a local APK path.

Usage:
    python apk_resolve.py <apk_path>

    apk_path: a local file path, or an http(s) URL to download.

Prints a single-line JSON object to stdout and exits 0 on success:
    {"apk_path": "<absolute path>"}

Exits non-zero (1) only for a hard error (download failure / missing local
file), printing the reason to stderr.
"""

import json
import os
import sys
import urllib.request
from urllib.parse import urlparse


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: apk_resolve.py <apk_path>", file=sys.stderr)
        return 1

    apk_path = sys.argv[1]

    if apk_path.startswith("http://") or apk_path.startswith("https://"):
        cache_dir = os.path.join(os.getcwd(), "apk_cache")
        os.makedirs(cache_dir, exist_ok=True)

        basename = os.path.basename(urlparse(apk_path).path)
        if not basename:
            basename = "apk_download.apk"

        target = os.path.abspath(os.path.join(cache_dir, basename))
        try:
            urllib.request.urlretrieve(apk_path, target)
        except Exception as exc:
            print(f"download failed: {exc}", file=sys.stderr)
            return 1

        print(json.dumps({"apk_path": target}))
        return 0

    target = os.path.abspath(apk_path)
    if os.path.isfile(target):
        print(json.dumps({"apk_path": target}))
        return 0

    print(f"file not found: {apk_path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
