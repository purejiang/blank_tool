#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin filesystem tools: directory listing/creation/deletion, text
searching, and archive (zip/tar) creation/extraction.

All six tools are stdlib-only ``BuiltinTool`` subclasses that declare a
typed port contract (``ports``) and implement :meth:`execute`.

Security note: archive extraction validates every member path before
writing anything to disk to mitigate CVE-2007-4559 (zip/tar path
traversal).  On Python >= 3.12 tarfile's ``filter="data"`` is used; on
older interpreters members are validated manually by ``_ensure_within``.
"""

import glob
import os
import re
import shutil
import sys
import tarfile
import zipfile
from pathlib import PurePath

from app.protocol import BaseType, Port, PortSet, TypeAnnotation
from app.tools.builtin.base import BuiltinTool, ToolContext


def _error(message: str) -> dict:
    """Return the uniform error payload used by every tool on failure."""
    return {"error": message}


def _infer_format(path: str) -> str:
    """Infer an archive format from a file path extension (zip fallback)."""
    p = str(path).lower()
    if p.endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    if p.endswith(".tar"):
        return "tar"
    return "zip"


def _ensure_within(dest: str, member_name: str) -> None:
    """Raise ValueError when extracting member_name would escape dest.

    CVE-2007-4559 mitigation: resolve the member's target path and reject
    anything that lands outside the normalized destination directory.
    """
    dest_norm = os.path.normpath(os.path.abspath(dest))
    target = os.path.normpath(os.path.join(dest_norm, member_name))
    if not (target == dest_norm or target.startswith(dest_norm + os.sep)):
        raise ValueError(
            f"path traversal detected in archive member: {member_name!r}"
        )


def _add_to_zip(zf: zipfile.ZipFile, source: str) -> None:
    """Add a file or directory tree to ``zf`` under the source's basename."""
    top = os.path.basename(os.path.abspath(source))
    if os.path.isfile(source):
        zf.write(source, top)
        return
    for root, dirs, files in os.walk(source):
        rel = os.path.relpath(root, source)
        arc_root = top if rel == "." else os.path.join(top, rel).replace("\\", "/")
        for d in sorted(dirs):
            zf.write(os.path.join(root, d), arc_root + "/" + d)
        for f in sorted(files):
            zf.write(os.path.join(root, f), arc_root + "/" + f)


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


class ArchiveExtract(BuiltinTool):
    """Extract a zip or tar archive into a destination directory."""

    name = "archive.extract"
    description = (
        "Extract a zip/tar/tar.gz archive into a destination directory "
        "with path traversal protection."
    )

    ports = PortSet(
        inputs=[
            Port("path", TypeAnnotation(BaseType.FILE), True, "Archive file to extract."),
            Port("dest", TypeAnnotation(BaseType.DIRECTORY), True, "Destination directory."),
            Port("format", TypeAnnotation(BaseType.TEXT), False, "Archive format: zip, tar or tar.gz (default zip)."),
        ],
        outputs=[
            Port("dest", TypeAnnotation(BaseType.DIRECTORY), True, "Destination directory."),
            Port("entries", TypeAnnotation(BaseType.JSON), True, "List of extracted member names."),
            Port("count", TypeAnnotation(BaseType.NUMBER), True, "Number of extracted members."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        path = inputs["path"]
        if not os.path.isfile(path):
            return _error(f"archive file does not exist: {path}")
        dest = inputs["dest"]
        fmt = (inputs.get("format") or "").strip().lower() or _infer_format(path)
        try:
            os.makedirs(dest, exist_ok=True)
            if fmt == "zip":
                with zipfile.ZipFile(path) as zf:
                    for info in zf.infolist():
                        _ensure_within(dest, info.filename)
                    zf.extractall(dest)
                    entries = [info.filename for info in zf.infolist()]
            elif fmt in ("tar", "tar.gz"):
                with tarfile.open(path, mode="r:*") as tf:
                    if sys.version_info >= (3, 12):
                        tf.extractall(dest, filter="data")
                    else:
                        for member in tf.getmembers():
                            _ensure_within(dest, member.name)
                        tf.extractall(dest)
                    entries = [member.name for member in tf.getmembers()]
            else:
                return _error(f"unsupported archive format: {fmt}")
        except (zipfile.BadZipFile, tarfile.TarError, ValueError, OSError) as exc:
            return _error(f"failed to extract archive: {exc}")
        return {"dest": os.path.normpath(dest), "entries": entries, "count": len(entries)}


class ArchiveCreate(BuiltinTool):
    """Create a zip or tar archive from a source file or directory."""

    name = "archive.create"
    description = (
        "Create a zip/tar/tar.gz archive from a source directory or file, "
        "preserving the source's top-level name inside the archive."
    )

    ports = PortSet(
        inputs=[
            Port("source", TypeAnnotation(BaseType.TEXT), True, "Source file or directory to archive."),
            Port("dest", TypeAnnotation(BaseType.FILE), True, "Output archive path."),
            Port("format", TypeAnnotation(BaseType.TEXT), False, "Archive format: zip, tar or tar.gz (default zip)."),
            Port("compression", TypeAnnotation(BaseType.TEXT), False, "Zip compression: deflated or stored (default deflated)."),
        ],
        outputs=[
            Port("path", TypeAnnotation(BaseType.FILE), True, "The created archive path."),
            Port("size", TypeAnnotation(BaseType.NUMBER), True, "Size of the created archive in bytes."),
        ],
    )

    def execute(self, inputs: dict, context: ToolContext) -> dict:
        source = inputs["source"]
        if not (os.path.isfile(source) or os.path.isdir(source)):
            return _error(f"source does not exist: {source}")
        dest = inputs["dest"]
        fmt = (inputs.get("format") or "").strip().lower() or _infer_format(dest)
        compression = (inputs.get("compression") or "deflated").strip().lower()
        try:
            if fmt == "zip":
                if compression not in ("deflated", "stored"):
                    return _error(f"unsupported zip compression: {compression}")
                level = zipfile.ZIP_STORED if compression == "stored" else zipfile.ZIP_DEFLATED
                with zipfile.ZipFile(dest, "w", compression=level) as zf:
                    _add_to_zip(zf, source)
            elif fmt in ("tar", "tar.gz"):
                mode = "w:gz" if fmt == "tar.gz" else "w"
                with tarfile.open(dest, mode) as tf:
                    tf.add(source, arcname=os.path.basename(source).replace("\\", "/"))
            else:
                return _error(f"unsupported archive format: {fmt}")
        except (OSError, ValueError, tarfile.TarError) as exc:
            return _error(f"failed to create archive: {exc}")
        return {"path": os.path.normpath(dest), "size": os.path.getsize(dest)}
