#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Builtin archive tools (``archive.*`` prefix): extraction and creation of
zip, tar, and tar.gz archives with path-traversal protection.

Both tools are stdlib-only ``BuiltinTool`` subclasses that declare a
typed port contract (``ports``) and implement :meth:`execute`.

Security note: archive extraction validates every member path before
writing anything to disk to mitigate CVE-2007-4559 (zip/tar path
traversal).  On Python >= 3.12 tarfile's ``filter="data"`` is used; on
older interpreters members are validated manually by ``_ensure_within``.
"""

import os
import shutil
import sys
import tarfile
import zipfile

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
