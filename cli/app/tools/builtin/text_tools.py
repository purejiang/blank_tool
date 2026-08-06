#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin text tools (``text.*`` prefix): regex search and replacement on files.

Both tools are stdlib-only ``BuiltinTool`` subclasses that declare a
typed port contract (``ports``) and implement :meth:`execute`.
"""

import os
import re
from pathlib import PurePath

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext


def _error(message: str) -> dict:
    """Return the uniform error payload used by every tool on failure."""
    return {"error": message}


class TextGrep(BuiltinTool):
    """Search a file or directory tree for lines matching a regular expression."""

    name = "text.grep"
    description = (
        "Search a file or a directory tree for lines matching a regular "
        "expression pattern."
    )

    ports = PortSet(
        inputs=[
            Port("path", TypeAnnotation(BaseType.TEXT), True, "File or directory to search."),
            Port("pattern", TypeAnnotation(BaseType.TEXT), True, "Regular expression to match against each line."),
            Port("include", TypeAnnotation(BaseType.TEXT), False, "Shell-style glob to filter file names (default '*')."),
            Port("recursive", TypeAnnotation(BaseType.BOOLEAN), False, "Search subdirectories recursively (default True)."),
        ],
        outputs=[
            Port("matches", TypeAnnotation(BaseType.JSON), True, "List of {file, line, content} matches."),
            Port("count", TypeAnnotation(BaseType.NUMBER), True, "Number of matched lines."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        if not (os.path.isfile(path) or os.path.isdir(path)):
            return _error(f"path does not exist: {path}")
        try:
            regex = re.compile(inputs["pattern"])
        except re.error as exc:
            return _error(f"invalid regex {inputs['pattern']!r}: {exc}")
        include = inputs.get("include", "*")
        recursive = bool(inputs.get("recursive", True))
        matches = []

        def _search_file(file_path: str) -> None:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        if regex.search(line):
                            matches.append(
                                {
                                    "file": os.path.normpath(file_path),
                                    "line": lineno,
                                    "content": line.rstrip("\r\n"),
                                }
                            )
            except OSError:
                return

        if os.path.isfile(path):
            _search_file(path)
        else:
            for root, _dirs, files in os.walk(path):
                for name in files:
                    full = os.path.join(root, name)
                    if PurePath(full).match(include):
                        _search_file(full)
                if not recursive:
                    break
        return {"matches": matches, "count": len(matches)}


class TextReplace(BuiltinTool):
    """Replace text in a file using regex pattern substitution (re.sub)."""

    name = "text.replace"
    description = (
        "Replace text in a file using a regular expression pattern. "
        "Reads the entire file, applies re.sub(pattern, replacement) "
        "and writes the result back. Supports backreferences (\\1 etc.)."
    )

    ports = PortSet(
        inputs=[
            Port("path", TypeAnnotation(BaseType.FILE), True, "File to modify in-place."),
            Port("pattern", TypeAnnotation(BaseType.TEXT), True, "Python regex pattern (re.sub compatible)."),
            Port("replacement", TypeAnnotation(BaseType.TEXT), True, "Replacement text; supports backreferences."),
        ],
        outputs=[
            Port("path", TypeAnnotation(BaseType.FILE), True, "The modified file path."),
            Port("count", TypeAnnotation(BaseType.NUMBER), True, "Number of replacements made."),
            Port("changed", TypeAnnotation(BaseType.BOOLEAN), True, "True when at least one replacement was made."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        if not os.path.isfile(path):
            return _error(f"file does not exist: {path}")
        try:
            regex = re.compile(inputs["pattern"])
        except re.error as exc:
            return _error(f"invalid regex {inputs['pattern']!r}: {exc}")
        replacement = inputs["replacement"]
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                original = fh.read()
        except OSError as exc:
            return _error(f"cannot read {path}: {exc}")
        modified, count = regex.subn(replacement, original)
        if count == 0:
            return {"path": os.path.normpath(path), "count": 0, "changed": False}
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(modified)
        except OSError as exc:
            return _error(f"cannot write {path}: {exc}")
        return {"path": os.path.normpath(path), "count": count, "changed": True}
