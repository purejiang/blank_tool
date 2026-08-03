#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Template storage abstraction.

D3 storage layer for workflow templates: :class:`TemplateStore` is the
abstract interface, :class:`FileTemplateStore` persists templates as
``<name>.json`` under a WRITABLE directory.

Writable-path requirement (Oracle finding #2):
    In packaged builds the ``backend/`` tree is copied to
    ``process.resourcesPath`` (electron-builder ``extraResources``, see
    ``package.json``) and is READ-ONLY.  Pre-installed defaults ship there
    (``backend/workflows/``) as read-only JSON; user templates MUST live
    outside it.  The storage directory resolves via ``BT_TEMPLATES_DIR``,
    falling back to ``<output_dir>/templates`` (``get_output_dir()`` returns
    a writable path), and is created on construction.
    :meth:`FileTemplateStore.copy_defaults` seeds this writable dir from the
    read-only defaults on first run.

JSON file layout (one file per template, ``<name>.json``)::

    {
        "definition": { ... WorkflowDefinition.to_dict() ... },
        "created_at": "2026-08-03T12:00:00.000000",
        "updated_at": "2026-08-03T12:00:00.000000",
        "description": "...",
        "tags": ["android", "install"]
    }
"""

import json
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.utils.env import get_env, get_output_dir
from app.workflow.definition import WorkflowDefinition


@dataclass
class TemplateInfo:
    """Read-only metadata about a stored template (returned by ``list``).

    Attributes:
        name: template name (matches the ``<name>.json`` filename).
        description: human-facing explanation of the template.
        created_at: ISO-8601 timestamp of first save.
        updated_at: ISO-8601 timestamp of last save.
        tags: free-form keyword list attached by the caller.
        node_count: number of nodes in the stored definition.
    """

    name: str
    description: str
    created_at: str
    updated_at: str
    tags: List[str]
    node_count: int


class TemplateNotFoundError(Exception):
    """Raised when a template ``load``/``delete`` targets does not exist."""


class TemplateStore(ABC):
    """Abstract template storage.

    Implementations persist :class:`WorkflowDefinition` objects under a
    stable, caller-supplied name.  The abstract surface is deliberately
    small so a future SQLite-backed store can drop in without touching
    callers (D3).
    """

    @abstractmethod
    def save(
        self, name: str, definition: WorkflowDefinition, metadata: dict
    ) -> None:
        """Persist *definition* under *name*.

        Args:
            name: unique template name (must be path-safe).
            definition: the workflow schema to store.
            metadata: caller-supplied dict; ``description`` and ``tags``
                keys are stored with the template.
        """
        raise NotImplementedError

    @abstractmethod
    def load(self, name: str) -> WorkflowDefinition:
        """Load the workflow definition stored under *name*.

        Raises:
            TemplateNotFoundError: if no template with *name* exists.
        """
        raise NotImplementedError

    @abstractmethod
    def list(self) -> List[TemplateInfo]:
        """Return metadata for every stored template, sorted by name."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, name: str) -> None:
        """Remove the template stored under *name*.

        Raises:
            TemplateNotFoundError: if no template with *name* exists.
        """
        raise NotImplementedError

    @abstractmethod
    def exists(self, name: str) -> bool:
        """Return True when a template with *name* is stored."""
        raise NotImplementedError


class FileTemplateStore(TemplateStore):
    """File-backed :class:`TemplateStore` storing one JSON file per template.

    All templates live under ``self._templates_dir`` — a WRITABLE directory
    outside the bundled resources (see the module docstring, Oracle finding
    #2).  The directory is created on construction.
    """

    def __init__(self, templates_dir: Optional[str] = None) -> None:
        """Resolve and prepare the writable templates directory.

        Args:
            templates_dir: explicit writable directory.  When omitted,
                resolves ``BT_TEMPLATES_DIR`` env var, falling back to
                ``<output_dir>/templates`` (``get_output_dir()`` is a
                writable path in both dev and packaged builds).

        The directory is created (``exist_ok=True``) if missing.
        """
        if templates_dir:
            self._templates_dir = templates_dir
        else:
            self._templates_dir = get_env(
                "BT_TEMPLATES_DIR",
                os.path.join(get_output_dir(), "templates"),
            )
        os.makedirs(self._templates_dir, exist_ok=True)

    @property
    def templates_dir(self) -> str:
        """The writable directory template files are stored in."""
        return self._templates_dir

    def _path_for(self, name: str) -> str:
        """Return the file path for template *name*.

        Rejects unsafe names (path separators, ``..``, empty/non-string)
        with :class:`ValueError` so a crafted name cannot escape
        ``self._templates_dir``.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("template name must be a non-empty string")

        invalid_chars = os.sep
        if os.sep == "\\":
            # On Windows, "/" is also a valid path separator.
            invalid_chars += "/"
        if any(c in name for c in invalid_chars):
            raise ValueError(
                f"template name contains invalid characters: {name!r}"
            )
        if ".." in name:
            raise ValueError(
                f"template name contains invalid characters: {name!r}"
            )

        return os.path.join(self._templates_dir, f"{name}.json")

    def save(
        self, name: str, definition: WorkflowDefinition, metadata: dict
    ) -> None:
        """Persist *definition* under *name* (create or overwrite).

        ``created_at`` is set on first save and preserved on overwrite;
        ``updated_at`` is refreshed on every save.  The file is written as
        UTF-8 JSON with 2-space indent.
        """
        path = self._path_for(name)
        now = datetime.now().isoformat()

        if os.path.isfile(path):
            created_at = now
            try:
                with open(path, "r", encoding="utf-8") as f:
                    created_at = json.load(f).get("created_at") or now
            except (OSError, json.JSONDecodeError):
                # Unreadable/corrupt existing file: treat as a fresh save.
                created_at = now
        else:
            created_at = now

        data = {
            "definition": definition.to_dict(),
            "created_at": created_at,
            "updated_at": now,
            "description": metadata.get("description", ""),
            "tags": list(metadata.get("tags", [])),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def load(self, name: str) -> WorkflowDefinition:
        """Load the workflow definition stored under *name*.

        Raises:
            TemplateNotFoundError: if no template with *name* exists.
            ValueError: if the stored file is not valid JSON or lacks a
                valid ``definition`` key.
        """
        path = self._path_for(name)
        if not os.path.isfile(path):
            raise TemplateNotFoundError(name)

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in template file {path}: {exc}") from exc

        try:
            definition_data = data["definition"]
        except KeyError:
            raise ValueError(
                f"template file {path} is missing the 'definition' key"
            ) from None
        return WorkflowDefinition.from_dict(definition_data)

    def list(self) -> List[TemplateInfo]:
        """Return metadata for every ``*.json`` template, sorted by name.

        Corrupt or schema-invalid files are skipped (a single broken
        template must not crash the listing); ``node_count`` is derived
        from the parsed definition's ``nodes`` length.
        """
        infos: List[TemplateInfo] = []
        if not os.path.isdir(self._templates_dir):
            return infos

        for filename in os.listdir(self._templates_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self._templates_dir, filename)
            if not os.path.isfile(path):
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                definition = WorkflowDefinition.from_dict(
                    data.get("definition", {})
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue

            infos.append(
                TemplateInfo(
                    name=filename[: -len(".json")],
                    description=data.get("description") or "",
                    created_at=data.get("created_at") or "",
                    updated_at=data.get("updated_at") or "",
                    tags=list(data.get("tags", [])),
                    node_count=len(definition.nodes),
                )
            )
        return sorted(infos, key=lambda info: info.name)

    def delete(self, name: str) -> None:
        """Remove the template stored under *name*.

        Raises:
            TemplateNotFoundError: if no template with *name* exists.
        """
        path = self._path_for(name)
        if not os.path.isfile(path):
            raise TemplateNotFoundError(name)
        os.remove(path)

    def exists(self, name: str) -> bool:
        """Return True when a template with *name* is stored."""
        return os.path.isfile(self._path_for(name))

    def copy_defaults(self, source_dir: str) -> int:
        """Seed the writable dir from read-only pre-installed templates.

        Copies every ``*.json`` in *source_dir* (e.g. ``backend/workflows/``,
        read-only in production) that does not already exist in
        ``self._templates_dir``.  Existing names are never overwritten, so a
        user-edited template survives re-runs.

        Returns:
            Number of templates copied.
        """
        copied = 0
        if not os.path.isdir(source_dir):
            return copied

        for filename in sorted(os.listdir(source_dir)):
            if not filename.endswith(".json"):
                continue
            src = os.path.join(source_dir, filename)
            if not os.path.isfile(src):
                continue
            dest = os.path.join(self._templates_dir, filename)
            if os.path.exists(dest):
                continue
            shutil.copyfile(src, dest)
            copied += 1
        return copied
