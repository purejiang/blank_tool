#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File tail helpers.

``tail_file`` returns the last N lines of a UTF-8 text file (``logs.tail``);
``tail_bytes`` returns the last N bytes of a log file (``task.read_log``).
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class TailResult:
    lines: list[str]
    truncated: bool
    size: int
    log_path: str


@dataclass
class TailBytesResult:
    content: str
    truncated: bool
    size: int
    log_path: str


def tail_file(path: str, max_lines: int = 200) -> TailResult:
    """Return the last ``max_lines`` lines of a UTF-8 text file."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    truncated = len(all_lines) > max_lines
    tail = all_lines[-max_lines:] if truncated else all_lines
    # Strip trailing newline characters
    tail = [line.rstrip("\n") for line in tail]
    return TailResult(lines=tail, truncated=truncated, size=os.path.getsize(path), log_path=path)


def tail_bytes(path: str, max_bytes: Optional[int] = None) -> TailBytesResult:
    """Read a log file, keeping only the last ``max_bytes`` bytes when given."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if max_bytes is not None and size > max_bytes:
            f.seek(size - max_bytes)
            truncated = True
        else:
            f.seek(0)
            truncated = False
        content = f.read().decode("utf-8", errors="replace")
    return TailBytesResult(content=content, truncated=truncated, size=size, log_path=path)
