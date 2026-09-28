#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task-definition storage.

A **task definition** is a reusable execution configuration: a saved workflow
name plus the input values to run it with (and an optional working directory).
It is what the renderer's task pages and the headless CLI's ``run --task``
both operate on — deliberately a different thing from:

- a *template* (``app.template.store``), which stores the workflow graph but
  never the values it is run with;
- a *run* (``app.history.store``), which is one execution of a workflow with
  the inputs it happened to use; run records are pruned by the retention
  policy, task definitions are user data and are never pruned.

Storage: one JSON file per task, ``<name>.json`` under a WRITABLE directory
resolved from ``BT_TASK_DEFS_DIR``, falling back to
``<output_dir>/task_defs`` (``get_output_dir()`` is writable in both dev and
packaged builds).  It is deliberately NOT ``<output_dir>/tasks``: that tree is
the per-run scratch space (``get_tasks_root()``, wiped by ``tasks.clear``),
keyed by a run identity — a task definition is neither.

JSON file layout (one file per task, ``<name>.json``)::

    {
        "name": "nightly-audit",
        "workflow": "apk-audit",
        "inputs": {"apk_path": "D:/x.apk", "deep": true},
        "work_dir": "",
        "description": "...",
        "created_at": "2026-08-03T12:00:00.000000",
        "updated_at": "2026-08-03T12:00:00.000000"
    }

``workflow`` binds a saved template BY NAME (the definition is never embedded,
so editing the workflow keeps every task pointing at the current graph); a
task whose workflow was renamed or deleted is reported as dangling by the
handler (``workflow_exists: false``) instead of silently disappearing.
``inputs`` is an opaque snapshot: it is stored as given and validated at run
time by the engine's port checks — the store never interprets values.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.env import get_env, get_output_dir
from app.utils.atomic_json import atomic_write_json

logger = logging.getLogger(__name__)


@dataclass
class TaskDefinitionInfo:
    """A stored task definition (``list`` / ``load`` result).

    Attributes:
        name: task name (matches the ``<name>.json`` filename).
        workflow: name of the saved template this task runs.
        inputs: stored input values, exactly as submitted (never interpreted
            here).
        work_dir: optional working directory; ``""`` means "use the
            workflow's own directory".
        description: human-facing one-liner.
        created_at: ISO-8601 timestamp of the first save.
        updated_at: ISO-8601 timestamp of the last save.
    """

    name: str
    workflow: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    work_dir: str = ""
    description: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to the on-disk/wire shape (``inputs`` included)."""
        return {
            "name": self.name,
            "workflow": self.workflow,
            "inputs": dict(self.inputs),
            "work_dir": self.work_dir,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskNotFoundError(Exception):
    """Raised when ``load``/``delete`` targets a task that does not exist."""


class TaskStore(ABC):
    """Abstract task-definition storage.

    The surface mirrors :class:`app.template.store.TemplateStore` (small and
    name-addressed) so a future database-backed store can drop in without
    touching the handler or the CLI.
    """

    @abstractmethod
    def save(
        self,
        name: str,
        workflow: str,
        inputs: Optional[Dict[str, Any]] = None,
        work_dir: str = "",
        description: str = "",
    ) -> TaskDefinitionInfo:
        """Persist a task definition under *name* (create or overwrite)."""
        raise NotImplementedError

    @abstractmethod
    def load(self, name: str) -> TaskDefinitionInfo:
        """Return the task definition stored under *name*.

        Raises:
            TaskNotFoundError: if no task with *name* exists.
        """
        raise NotImplementedError

    @abstractmethod
    def list(self) -> List[TaskDefinitionInfo]:
        """Return every stored task definition, sorted by name."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, name: str) -> None:
        """Remove the task definition stored under *name*.

        Raises:
            TaskNotFoundError: if no task with *name* exists.
        """
        raise NotImplementedError

    @abstractmethod
    def exists(self, name: str) -> bool:
        """Return True when a task definition with *name* is stored."""
        raise NotImplementedError


def _iso_now() -> str:
    return datetime.now().isoformat()


def _info_from_data(name: str, data: Dict[str, Any]) -> TaskDefinitionInfo:
    """Build a :class:`TaskDefinitionInfo` from parsed JSON *data*.

    Tolerant about the optional fields (missing ``inputs`` / ``work_dir`` /
    ``description`` / timestamps fall back to their empty values) but strict
    about ``workflow``: a task with no workflow cannot be executed, so a file
    missing it is treated as corrupt.

    Raises:
        ValueError: *data* is not a dict, or ``workflow`` is missing/blank.
    """
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")

    workflow = data.get("workflow")
    if not isinstance(workflow, str) or not workflow.strip():
        raise ValueError("missing 'workflow' field")

    inputs = data.get("inputs")
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise ValueError("'inputs' must be a JSON object")

    work_dir = data.get("work_dir")
    description = data.get("description")
    created_at = data.get("created_at")
    updated_at = data.get("updated_at")

    return TaskDefinitionInfo(
        name=name,
        workflow=workflow,
        inputs=dict(inputs),
        work_dir=work_dir if isinstance(work_dir, str) else "",
        description=description if isinstance(description, str) else "",
        created_at=created_at if isinstance(created_at, str) else None,
        updated_at=updated_at if isinstance(updated_at, str) else None,
    )


class FileTaskStore(TaskStore):
    """File-backed :class:`TaskStore` storing one JSON file per task.

    All tasks live under ``self._task_defs_dir`` — a WRITABLE directory outside
    the bundled resources.  The directory is created on construction.
    """

    def __init__(self, task_defs_dir: Optional[str] = None) -> None:
        """Resolve and prepare the writable task-definitions directory.

        Args:
            task_defs_dir: explicit writable directory.  When omitted,
                resolves ``BT_TASK_DEFS_DIR``, falling back to
                ``<output_dir>/task_defs``.

        The directory is created (``exist_ok=True``) if missing.
        """
        if task_defs_dir:
            self._task_defs_dir = task_defs_dir
        else:
            self._task_defs_dir = get_env(
                "BT_TASK_DEFS_DIR",
                os.path.join(get_output_dir(), "task_defs"),
            )
        os.makedirs(self._task_defs_dir, exist_ok=True)

    @property
    def task_defs_dir(self) -> str:
        """The writable directory task files are stored in."""
        return self._task_defs_dir

    def _path_for(self, name: str) -> str:
        """Return the file path for task *name*.

        Rejects unsafe names (path separators, ``..``, empty/non-string) with
        :class:`ValueError` so a crafted name cannot escape
        ``self._task_defs_dir``.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("task name must be a non-empty string")

        invalid_chars = os.sep
        if os.sep == "\\":
            # On Windows, "/" is also a valid path separator.
            invalid_chars += "/"
        if any(c in name for c in invalid_chars):
            raise ValueError(f"task name contains invalid characters: {name!r}")
        if ".." in name:
            raise ValueError(f"task name contains invalid characters: {name!r}")

        return os.path.join(self._task_defs_dir, f"{name}.json")

    def _read(self, name: str) -> TaskDefinitionInfo:
        """Read and parse the task file for *name*.

        Raises:
            TaskNotFoundError: no file for *name*.
            ValueError: unreadable/invalid JSON, or a schema-invalid document.
        """
        path = self._path_for(name)
        if not os.path.isfile(path):
            raise TaskNotFoundError(name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in task file {path}: {exc}") from exc
        try:
            return _info_from_data(name, data)
        except ValueError as exc:
            raise ValueError(f"task file {path} is not a valid task: {exc}") from exc

    def save(
        self,
        name: str,
        workflow: str,
        inputs: Optional[Dict[str, Any]] = None,
        work_dir: str = "",
        description: str = "",
    ) -> TaskDefinitionInfo:
        """Persist a task definition under *name* (create or overwrite).

        ``created_at`` is set on the first save and preserved on overwrite;
        ``updated_at`` is refreshed on every save.  ``inputs`` is stored as
        given (a copy of the mapping, never interpreted).

        Raises:
            ValueError: *name* is not path-safe, or *workflow* is blank.
        """
        if not isinstance(workflow, str) or not workflow.strip():
            raise ValueError("task workflow must be a non-empty string")

        path = self._path_for(name)
        now = _iso_now()

        created_at = now
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    created_at = json.load(f).get("created_at") or now
            except (OSError, json.JSONDecodeError, AttributeError):
                # Unreadable/corrupt existing file: treat as a fresh save.
                created_at = now

        info = TaskDefinitionInfo(
            name=name,
            workflow=workflow,
            inputs=dict(inputs or {}),
            work_dir=work_dir if isinstance(work_dir, str) else "",
            description=description if isinstance(description, str) else "",
            created_at=created_at,
            updated_at=now,
        )
        atomic_write_json(path, info.to_dict())
        return info

    def load(self, name: str) -> TaskDefinitionInfo:
        """Return the task definition stored under *name*.

        Raises:
            TaskNotFoundError: if no task with *name* exists.
            ValueError: if the stored file is not a valid task document.
        """
        return self._read(name)

    def list(self) -> List[TaskDefinitionInfo]:
        """Return every ``*.json`` task definition, sorted by name.

        Corrupt or schema-invalid files are skipped — a single broken task
        must not crash the listing (same tolerance as the template store).
        """
        infos: List[TaskDefinitionInfo] = []
        if not os.path.isdir(self._task_defs_dir):
            return infos

        for filename in os.listdir(self._task_defs_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self._task_defs_dir, filename)
            if not os.path.isfile(path):
                continue
            name = filename[: -len(".json")]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                infos.append(_info_from_data(name, data))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                logger.warning(
                    f"Skipping corrupted task file: {filename} — {exc}"
                )
                continue

        return sorted(infos, key=lambda info: info.name)

    def delete(self, name: str) -> None:
        """Remove the task file for *name*.

        Raises:
            TaskNotFoundError: if no task with *name* exists.
        """
        path = self._path_for(name)
        if not os.path.isfile(path):
            raise TaskNotFoundError(name)
        os.remove(path)

    def exists(self, name: str) -> bool:
        """Return True when a task file for *name* is stored."""
        return os.path.isfile(self._path_for(name))
