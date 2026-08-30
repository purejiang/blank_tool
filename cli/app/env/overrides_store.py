#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OverridesStore: the single owner of ``<output_dir>/registry/overrides.json`` IO.

Callers manage individual keys (``custom_paths``, ``env_overrides``, ...);
this class only loads the whole file and persists the whole dict.  Load/save
only — no per-key helpers (YAGNI).
"""

import json
import os
from pathlib import Path

from app.env import get_output_dir


class OverridesStore:
    """Read/write the process-wide overrides dict at ``<output>/registry/overrides.json``."""

    def __init__(self, root_dir: str = "") -> None:
        """Resolve the registry root.

        Args:
            root_dir: explicit registry root (test injection).  When empty,
                ``<output_dir>/registry`` is resolved via :func:`get_output_dir`.
        """
        self._root_dir = root_dir

    def _path(self) -> Path:
        root = self._root_dir or os.path.join(get_output_dir(), "registry")
        return Path(root) / "overrides.json"

    def load(self) -> dict:
        """Return the overrides dict, or ``{}`` when the file is absent/malformed."""
        path = self._path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def save(self, overrides: dict) -> None:
        """Persist *overrides* to ``overrides.json`` (dir created lazily)."""
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(overrides, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
