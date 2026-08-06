#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin directory tools (``dir.*`` prefix): listing, creation, and deletion.

All three tools are stdlib-only ``BuiltinTool`` subclasses that declare a
typed port contract (``ports``) and implement :meth:`execute`.
"""

import glob
import os
import shutil

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext


def _error(message: str) -> dict:
    """Return the uniform error payload used by every tool on failure."""
    return {"error": message}


class DirList(BuiltinTool):
    """List the entries of a directory, optionally filtered by a glob pattern."""

    name = "dir.list"
    description = (
        "List the entries (files and subdirectories) of a directory, "
        "optionally filtered by a glob pattern."
    )

    ports = PortSet(
        inputs=[
            Port("path", TypeAnnotation(BaseType.DIRECTORY), True, "Directory to list."),
            Port("pattern", TypeAnnotation(BaseType.TEXT), False, "Glob pattern relative to path (default '*')."),
            Port("recursive", TypeAnnotation(BaseType.BOOLEAN), False, "Match recursively with '**' (default False)."),
        ],
        outputs=[
            Port("entries", TypeAnnotation(BaseType.JSON), True, "List of {name, path, is_dir} entries."),
            Port("count", TypeAnnotation(BaseType.NUMBER), True, "Number of matched entries."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        if not os.path.isdir(path):
            return _error(f"directory does not exist: {path}")
        pattern = inputs.get("pattern", "*")
        recursive = bool(inputs.get("recursive", False))
        entries = []
        for match in glob.glob(os.path.join(path, pattern), recursive=recursive):
            entries.append(
                {
                    "name": os.path.basename(match),
                    "path": os.path.normpath(match),
                    "is_dir": os.path.isdir(match),
                }
            )
        return {"entries": entries, "count": len(entries)}


class DirCreate(BuiltinTool):
    """Create a directory, optionally creating intermediate parents."""

    name = "dir.create"
    description = (
        "Create a directory at the given path, creating intermediate "
        "parents when requested."
    )

    ports = PortSet(
        inputs=[
            Port("path", TypeAnnotation(BaseType.DIRECTORY), True, "Directory to create."),
            Port("parents", TypeAnnotation(BaseType.BOOLEAN), False, "Create intermediate parents (default True)."),
        ],
        outputs=[
            Port("path", TypeAnnotation(BaseType.DIRECTORY), True, "The created directory path."),
            Port("created", TypeAnnotation(BaseType.BOOLEAN), True, "True when the directory did not exist before."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        parents = bool(inputs.get("parents", True))
        existed = os.path.exists(path)
        if not parents:
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                return _error(f"parent directory does not exist: {parent}")
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            return _error(f"failed to create directory {path}: {exc}")
        return {"path": os.path.normpath(path), "created": not existed}


class DirDelete(BuiltinTool):
    """Recursively delete a directory tree."""

    name = "dir.delete"
    description = "Recursively delete a directory and all of its contents."

    ports = PortSet(
        inputs=[
            Port("path", TypeAnnotation(BaseType.DIRECTORY), True, "Directory to delete."),
        ],
        outputs=[
            Port("deleted", TypeAnnotation(BaseType.BOOLEAN), True, "True when the directory was removed."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        if not os.path.isdir(path):
            return _error(f"directory does not exist: {path}")
        try:
            shutil.rmtree(path)
        except OSError as exc:
            return _error(f"failed to delete directory {path}: {exc}")
        return {"deleted": True}
