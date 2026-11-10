#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pack a plugin directory into an importable zip.

Usage:
    python scripts/pack_plugin.py [plugin_dir] [-o output.zip]

The zip root is the package root (manifest.json / main.py / ui/...), matching
``plugin.import`` in the backend.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plugin_dir", nargs="?", default="plugins-dist/white-label-packer")
    ap.add_argument("-o", "--output", default="")
    args = ap.parse_args()

    src = Path(args.plugin_dir).resolve()
    manifest = src / "manifest.json"
    if not manifest.is_file():
        print(f"missing manifest: {manifest}", file=sys.stderr)
        return 2
    data = json.loads(manifest.read_text(encoding="utf-8"))
    version = str(data.get("version") or "0.0.0")
    out = Path(args.output).resolve() if args.output else \
        src.parent / f"{data.get('id') or src.name}-{version}.zip"

    entries = []
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.suffix.lower() in SKIP_SUFFIXES or p.name in SKIP_NAMES:
            continue
        entries.append((p, rel.as_posix()))

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in entries:
            zf.write(path, arcname)
    print(f"packed {len(entries)} files -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
