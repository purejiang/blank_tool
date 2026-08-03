#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin file tools for the workflow engine.

Six atomic file operations (file.read, file.write, file.copy, file.move,
file.delete, file.hash), each a ``BuiltinTool`` subclass declaring its port
contract and a stdlib-only ``execute`` implementation.

Path safety: every path input goes through :func:`_resolve_path`.  Absolute
paths are trusted as-is (user-provided).  Relative paths resolve against
``context.work_dir`` and are rejected if ``..`` traversal would escape it.
``os.path.realpath`` collapses symlinks so a link pointing outside the work
dir is neutralized instead of silently followed.
"""

import hashlib
import logging
import os
import shutil

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext

logger = logging.getLogger(__name__)

_FILE = TypeAnnotation(BaseType.FILE)
_TEXT = TypeAnnotation(BaseType.TEXT)
_NUMBER = TypeAnnotation(BaseType.NUMBER)
_BOOLEAN = TypeAnnotation(BaseType.BOOLEAN)


class PathOutsideWorkDir(ValueError):
    """Raised when a relative path escapes ``context.work_dir`` via ``..``."""


def _resolve_path(raw_path: str, work_dir: str) -> str:
    """Resolve a user-supplied path against ``work_dir``.

    Absolute paths are returned realpath-resolved as-is.  Relative paths are
    joined onto ``work_dir`` and rejected with :class:`PathOutsideWorkDir`
    when ``..`` traversal escapes it.  Symlink targets are logged and resolved
    via ``os.path.realpath`` rather than followed blindly.
    """
    candidate = raw_path if os.path.isabs(raw_path) else os.path.join(work_dir, raw_path)
    if os.path.islink(candidate):
        logger.warning("symlink detected at %r; resolving to realpath", candidate)
    resolved = os.path.realpath(candidate)

    if not os.path.isabs(raw_path):
        root = os.path.realpath(work_dir)
        try:
            inside = os.path.commonpath([resolved, root]) == root
        except ValueError:  # different drives / mixed abs-rel (Windows)
            inside = False
        if not inside:
            raise PathOutsideWorkDir(
                f"path escapes work dir via '..': {raw_path!r}"
            )
    return resolved


class FileRead(BuiltinTool):
    """Read a text file and return its content and byte size.

    Returns an ``{"error": ...}`` dict (not an exception) when the file is
    missing or unreadable so the workflow engine can route failure handling.
    """

    name = "file.read"
    description = "Read a text file, returning its content and size in bytes."

    ports = PortSet(
        inputs=[
            Port("path", _FILE, required=True, description="Path of the file to read."),
            Port("encoding", _TEXT, required=False, description="Text encoding (default utf-8)."),
        ],
        outputs=[
            Port("content", _TEXT, required=True, description="File contents as text."),
            Port("size", _NUMBER, required=True, description="File size in bytes."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        encoding = inputs.get("encoding", "utf-8")
        try:
            resolved = _resolve_path(path, context.work_dir)
            if not os.path.isfile(resolved):
                return {"error": f"file not found: {path}"}
            with open(resolved, "r", encoding=encoding) as fh:
                content = fh.read()
            return {"content": content, "size": os.path.getsize(resolved)}
        except PathOutsideWorkDir as exc:
            return {"error": str(exc)}
        except (OSError, ValueError) as exc:
            return {"error": f"failed to read {path}: {exc}"}


class FileWrite(BuiltinTool):
    """Write text content to a file, overwriting any existing content."""

    name = "file.write"
    description = "Write text content to a file (overwrites existing content)."

    ports = PortSet(
        inputs=[
            Port("path", _FILE, required=True, description="Destination file path."),
            Port("content", _TEXT, required=True, description="Text content to write."),
            Port("encoding", _TEXT, required=False, description="Text encoding (default utf-8)."),
        ],
        outputs=[
            Port("written", _BOOLEAN, required=True, description="True on success."),
            Port("path", _FILE, required=True, description="Resolved destination path."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        content = inputs["content"]
        encoding = inputs.get("encoding", "utf-8")
        try:
            resolved = _resolve_path(path, context.work_dir)
            with open(resolved, "w", encoding=encoding) as fh:
                fh.write(content)
            return {"written": True, "path": resolved}
        except PathOutsideWorkDir as exc:
            return {"error": str(exc)}
        except (OSError, ValueError) as exc:
            return {"error": f"failed to write {path}: {exc}"}


class FileCopy(BuiltinTool):
    """Copy a file to a destination, optionally refusing to overwrite."""

    name = "file.copy"
    description = "Copy a file to a destination path."

    ports = PortSet(
        inputs=[
            Port("source", _FILE, required=True, description="Source file path."),
            Port("destination", _FILE, required=True, description="Destination file path."),
            Port("overwrite", _BOOLEAN, required=False, description="Overwrite destination if it exists (default True)."),
        ],
        outputs=[
            Port("path", _FILE, required=True, description="Resolved destination path."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        source = inputs["source"]
        destination = inputs["destination"]
        overwrite = bool(inputs.get("overwrite", True))
        try:
            src = _resolve_path(source, context.work_dir)
            dst = _resolve_path(destination, context.work_dir)
            if not os.path.isfile(src):
                return {"error": f"file not found: {source}"}
            if os.path.exists(dst) and not overwrite:
                return {"error": f"destination exists: {destination}"}
            shutil.copy2(src, dst)
            return {"path": dst}
        except PathOutsideWorkDir as exc:
            return {"error": str(exc)}
        except (OSError, shutil.Error) as exc:
            return {"error": f"failed to copy {source} -> {destination}: {exc}"}


class FileMove(BuiltinTool):
    """Move (rename) a file to a destination, optionally refusing to overwrite."""

    name = "file.move"
    description = "Move or rename a file to a destination path."

    ports = PortSet(
        inputs=[
            Port("source", _FILE, required=True, description="Source file path."),
            Port("destination", _FILE, required=True, description="Destination file path."),
            Port("overwrite", _BOOLEAN, required=False, description="Overwrite destination if it exists (default True)."),
        ],
        outputs=[
            Port("path", _FILE, required=True, description="Resolved destination path."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        source = inputs["source"]
        destination = inputs["destination"]
        overwrite = bool(inputs.get("overwrite", True))
        try:
            src = _resolve_path(source, context.work_dir)
            dst = _resolve_path(destination, context.work_dir)
            if not os.path.isfile(src):
                return {"error": f"file not found: {source}"}
            if os.path.exists(dst) and not overwrite:
                return {"error": f"destination exists: {destination}"}
            shutil.move(src, dst)
            return {"path": dst}
        except PathOutsideWorkDir as exc:
            return {"error": str(exc)}
        except (OSError, shutil.Error) as exc:
            return {"error": f"failed to move {source} -> {destination}: {exc}"}


class FileDelete(BuiltinTool):
    """Delete a file.  A missing file is reported as an error dict."""

    name = "file.delete"
    description = "Delete a file at the given path."

    ports = PortSet(
        inputs=[
            Port("path", _FILE, required=True, description="Path of the file to delete."),
        ],
        outputs=[
            Port("deleted", _BOOLEAN, required=True, description="True on success."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        try:
            resolved = _resolve_path(path, context.work_dir)
            if not os.path.exists(resolved):
                return {"error": f"file not found: {path}"}
            if os.path.isdir(resolved):
                return {"error": f"not a file: {path}"}
            os.remove(resolved)
            return {"deleted": True}
        except PathOutsideWorkDir as exc:
            return {"error": str(exc)}
        except OSError as exc:
            return {"error": f"failed to delete {path}: {exc}"}


class FileHash(BuiltinTool):
    """Compute a file's digest with any :mod:`hashlib` algorithm."""

    name = "file.hash"
    description = "Compute the hash digest of a file (sha256, md5, sha1, ...)."

    ports = PortSet(
        inputs=[
            Port("path", _FILE, required=True, description="Path of the file to hash."),
            Port("algorithm", _TEXT, required=False, description="Hash algorithm name (default sha256)."),
        ],
        outputs=[
            Port("hash", _TEXT, required=True, description="Hex digest of the file."),
            Port("algorithm", _TEXT, required=True, description="Algorithm actually used."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        algorithm = inputs.get("algorithm", "sha256")
        try:
            resolved = _resolve_path(path, context.work_dir)
            if not os.path.isfile(resolved):
                return {"error": f"file not found: {path}"}
            hasher = hashlib.new(algorithm)
            with open(resolved, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    hasher.update(chunk)
            return {"hash": hasher.hexdigest(), "algorithm": algorithm}
        except PathOutsideWorkDir as exc:
            return {"error": str(exc)}
        except (OSError, ValueError) as exc:
            return {"error": f"failed to hash {path}: {exc}"}
