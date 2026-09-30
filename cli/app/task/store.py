#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task-definition storage.

A **task definition** is a reusable execution configuration: a saved workflow
plus the input values to run it with (and an optional working directory).  It is
what the renderer's task pages and the headless CLI's ``run --task`` both
operate on — deliberately a different thing from:

- a *saved workflow* (``app.workflow.store``), which stores the workflow graph
  but never the values it is run with;
- a *run* (``app.history.store``), which is one execution of a workflow with
  the inputs it happened to use; run records are pruned by the retention
  policy, task definitions are user data and are never pruned.

Storage: one JSON file per task, ``<id>.json`` under a WRITABLE directory
resolved from ``BT_TASK_DEFS_DIR``, falling back to ``<output_dir>/task_defs``
(``get_output_dir()`` is writable in both dev and packaged builds).  It is
deliberately NOT ``<output_dir>/tasks``: that tree is the per-run scratch space
(``get_tasks_root()``, wiped by ``tasks.clear``), keyed by a run identity — a
task definition is neither.

Identity vs. display name:
    Like saved workflows, a task definition is identified by an auto-generated
    ASCII id (``tk-`` + 12 hex chars, see :mod:`app.ids`) which is also its
    file name.  Its **display name** lives inside the file and may be any
    script, including characters that are illegal in a file name.  References
    may use either form: the store resolves an id first and falls back to a
    name lookup.

JSON file layout (one file per task, ``<id>.json``)::

    {
        "name": "nightly-audit",
        "workflow_id": "wf-3f9a2b1c4d5e",
        "workflow": "apk-audit",
        "inputs": {"apk_path": "D:/x.apk", "deep": true},
        "work_dir": "",
        "description": "...",
        "created_at": "2026-08-03T12:00:00.000000",
        "updated_at": "2026-08-03T12:00:00.000000"
    }

``workflow_id`` binds a saved workflow BY ID, so renaming the workflow (or the
task) never breaks the binding; ``workflow`` is the display-name snapshot it
was saved under, kept as a fallback for task files written before ids existed.
The definition is never embedded, so editing the workflow keeps every task
pointing at the current graph; a task whose workflow was deleted is reported as
dangling by the handler (``workflow_exists: false``) instead of silently
disappearing.  ``inputs`` is an opaque snapshot: it is stored as given and
validated at run time by the engine's port checks — the store never interprets
values.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.env import get_env, get_output_dir
from app.ids import (
    MAX_ID_ATTEMPTS,
    TASK_ID_RE,
    WORKFLOW_ID_RE,
    id_file_path,
    is_plain_stem,
    is_task_id,
    new_task_id,
)
from app.utils.atomic_json import atomic_write_json

logger = logging.getLogger(__name__)


@dataclass
class TaskDefinitionInfo:
    """A stored task definition (``list`` / ``load`` result).

    Attributes:
        id: storage identity — also the ``<id>.json`` file name stem.
        name: human-facing display name; may repeat and may contain any
            characters.
        workflow_id: storage id of the saved workflow this task runs, or
            ``None`` for a task saved before ids existed (binding then falls
            back to ``workflow``).
        workflow: display-name snapshot of that workflow, used as the binding
            fallback and for display when the id cannot be resolved.
        inputs: stored input values, exactly as submitted (never interpreted
            here).
        work_dir: optional working directory; ``""`` means "use the
            workflow's own directory / the run's artifact directory".
        description: human-facing one-liner.
        created_at: ISO-8601 timestamp of the first save.
        updated_at: ISO-8601 timestamp of the last save.
    """

    name: str
    workflow: str
    id: str = ""
    workflow_id: Optional[str] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    work_dir: str = ""
    description: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to the on-disk/wire shape (``inputs`` included)."""
        return {
            "name": self.name,
            "workflow_id": self.workflow_id,
            "workflow": self.workflow,
            "inputs": dict(self.inputs),
            "work_dir": self.work_dir,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskNotFoundError(Exception):
    """Raised when ``load``/``delete`` targets a task that does not exist."""


class AmbiguousTaskNameError(Exception):
    """Raised when a task display name matches more than one stored task.

    Ids are unique, names are not: once two tasks share a name, only an id can
    identify one of them, so name-based lookups fail loudly instead of silently
    picking a winner.
    """

    def __init__(self, name: str, ids: List[str]) -> None:
        self.name = name
        self.ids = list(ids)
        super().__init__(
            f"task name {name!r} matches {len(self.ids)} tasks "
            f"({', '.join(self.ids)}); refer to one by id"
        )


class TaskStore(ABC):
    """Abstract task-definition storage.

    The surface mirrors :class:`app.workflow.store.WorkflowStore` (small, and
    addressed by id with a name fallback) so a future database-backed store can
    drop in without touching the handler or the CLI.
    """

    @abstractmethod
    def save(
        self,
        name: str,
        workflow: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        work_dir: str = "",
        description: str = "",
        *,
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> TaskDefinitionInfo:
        """Persist a task definition (create or overwrite)."""
        raise NotImplementedError

    @abstractmethod
    def load(self, ref: str) -> TaskDefinitionInfo:
        """Return the task definition *ref* points at.

        Raises:
            TaskNotFoundError: if no task matches *ref*.
            AmbiguousTaskNameError: if *ref* is a name matching several.
        """
        raise NotImplementedError

    @abstractmethod
    def list(self) -> List[TaskDefinitionInfo]:
        """Return every stored task definition, sorted by display name."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, ref: str) -> None:
        """Remove the task definition *ref* points at.

        Raises:
            TaskNotFoundError: if no task matches *ref*.
            AmbiguousTaskNameError: if *ref* is a name matching several.
        """
        raise NotImplementedError

    @abstractmethod
    def exists(self, ref: str) -> bool:
        """Return True when *ref* matches a stored task definition."""
        raise NotImplementedError


def _iso_now() -> str:
    return datetime.now().isoformat()


def _info_from_data(task_id: str, data: Dict[str, Any]) -> TaskDefinitionInfo:
    """Build a :class:`TaskDefinitionInfo` from parsed JSON *data*.

    Tolerant about the optional fields (missing ``inputs`` / ``work_dir`` /
    ``description`` / timestamps fall back to their empty values).  The display
    name falls back to *task_id* for files written before names were stored
    (their file name WAS the name).  Strict about the binding: a task needs
    either a ``workflow_id`` or a ``workflow`` name, since one with neither
    cannot be executed.

    Raises:
        ValueError: *data* is not a dict, or the binding is missing.
    """
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")

    raw_name = data.get("name")
    name = raw_name if isinstance(raw_name, str) and raw_name.strip() else task_id

    raw_workflow_id = data.get("workflow_id")
    workflow_id = (
        raw_workflow_id
        if isinstance(raw_workflow_id, str) and WORKFLOW_ID_RE.match(raw_workflow_id)
        else None
    )

    workflow = data.get("workflow")
    if not isinstance(workflow, str):
        workflow = ""
    if not workflow.strip() and workflow_id is None:
        raise ValueError("missing 'workflow_id'/'workflow' field")

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
        id=task_id,
        name=name,
        workflow_id=workflow_id,
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
    the bundled resources.  The directory is created on construction, which also
    runs the one-time legacy-name migration.
    """

    def __init__(self, task_defs_dir: Optional[str] = None) -> None:
        """Resolve and prepare the writable task-definitions directory.

        Args:
            task_defs_dir: explicit writable directory.  When omitted,
                resolves ``BT_TASK_DEFS_DIR``, falling back to
                ``<output_dir>/task_defs``.

        The directory is created (``exist_ok=True``) if missing, then any
        surviving pre-id files are migrated to ids (idempotent).
        """
        if task_defs_dir:
            self._task_defs_dir = task_defs_dir
        else:
            self._task_defs_dir = get_env(
                "BT_TASK_DEFS_DIR",
                os.path.join(get_output_dir(), "task_defs"),
            )
        os.makedirs(self._task_defs_dir, exist_ok=True)
        self._migrate_legacy_names()

    @property
    def task_defs_dir(self) -> str:
        """The writable directory task files are stored in."""
        return self._task_defs_dir

    # ── identity ─────────────────────────────────────────────────────────

    def _path_for_stem(self, stem: str) -> str:
        """Return the file path for a *stem* already known to live in this dir.

        Used for stems that came out of :meth:`resolve` — either a validated id
        or a file name discovered by scanning the directory — so it never needs
        to re-validate.  Caller-supplied ids go through :meth:`path_for_id`.
        """
        return os.path.join(self._task_defs_dir, f"{stem}.json")

    def path_for_id(self, task_id: str) -> str:
        """Return the file path for *task_id*.

        Rejects anything that is not id-shaped with :class:`ValueError`, so a
        crafted reference cannot escape ``self._task_defs_dir``.
        """
        return id_file_path(
            self._task_defs_dir, task_id, TASK_ID_RE, "task"
        )

    def _allocate_id(self) -> Optional[str]:
        """Return an unused task id, or ``None`` if none could be drawn."""
        for _ in range(MAX_ID_ATTEMPTS):
            candidate = new_task_id()
            if not os.path.exists(self.path_for_id(candidate)):
                return candidate
        return None

    def find_id_by_name(self, name: str) -> Optional[str]:
        """Return the id of the task whose display name is *name*.

        An exact match wins; a case-insensitive pass follows.  A name matching
        several tasks raises :class:`AmbiguousTaskNameError`.
        """
        if not isinstance(name, str) or not name:
            return None
        infos = self.list()
        matches = [info.id for info in infos if info.name == name]
        if not matches:
            folded = name.casefold()
            matches = [info.id for info in infos if info.name.casefold() == folded]
        if len(matches) > 1:
            raise AmbiguousTaskNameError(name, matches)
        if matches:
            return matches[0]
        if not is_plain_stem(name):
            return None
        return name if os.path.isfile(self._path_for_stem(name)) else None

    def resolve(self, ref: str) -> Optional[str]:
        """Return the id *ref* points at: an existing id, else a name lookup.

        Returns ``None`` when nothing matches, so callers can raise their own
        not-found error with the right context.
        """
        if not isinstance(ref, str) or not ref:
            return None
        if is_task_id(ref):
            return ref if os.path.isfile(self.path_for_id(ref)) else None
        return self.find_id_by_name(ref)

    # ── write / read ─────────────────────────────────────────────────────

    def _read_data(self, path: str) -> Dict[str, Any]:
        """Read one task file as a JSON dict.

        Raises:
            ValueError: unreadable/invalid JSON, or not a JSON object.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in task file {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"task file {path} is not a valid task: expected a JSON object")
        return data

    def _read(self, ref: str) -> TaskDefinitionInfo:
        """Read and parse the task *ref* points at.

        Raises:
            TaskNotFoundError: no task matches *ref*.
            AmbiguousTaskNameError: *ref* is a name matching several.
            ValueError: unreadable/invalid JSON, or a schema-invalid document.
        """
        task_id = self.resolve(ref)
        if task_id is None:
            raise TaskNotFoundError(ref)
        path = self._path_for_stem(task_id)
        if not os.path.isfile(path):
            raise TaskNotFoundError(ref)
        data = self._read_data(path)
        try:
            return _info_from_data(task_id, data)
        except ValueError as exc:
            raise ValueError(f"task file {path} is not a valid task: {exc}") from exc

    def save(
        self,
        name: str,
        workflow: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        work_dir: str = "",
        description: str = "",
        *,
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> TaskDefinitionInfo:
        """Persist a task definition (create or overwrite).

        ``created_at`` is set on the first save and preserved on overwrite;
        ``updated_at`` is refreshed on every save.  ``inputs`` is stored as
        given (a copy of the mapping, never interpreted).

        Args:
            name: display name (free-form; may repeat).
            workflow: display-name snapshot of the bound workflow, kept as the
                binding fallback when *workflow_id* is not given.
            workflow_id: storage id of the bound workflow (preferred binding).
            task_id: id to overwrite; ``None`` allocates a fresh one.

        Raises:
            ValueError: *name* is blank, neither binding is usable, or
                *task_id* is not id-shaped.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("task name must be a non-empty string")

        if workflow_id is not None and not WORKFLOW_ID_RE.match(str(workflow_id)):
            raise ValueError(f"invalid workflow id: {workflow_id!r}")
        if workflow_id is None and (
            not isinstance(workflow, str) or not workflow.strip()
        ):
            raise ValueError(
                "task needs a 'workflow_id' or a non-empty 'workflow' name"
            )

        if task_id is None:
            allocated = self._allocate_id()
            if allocated is None:
                raise RuntimeError("could not allocate a free task id")
            task_id = allocated
        else:
            # Validates the id shape before any path is built.
            self.path_for_id(task_id)

        path = self.path_for_id(task_id)
        now = _iso_now()

        created_at = now
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    created_at = json.load(f).get("created_at") or now
            except (OSError, TypeError, AttributeError, json.JSONDecodeError):
                # Unreadable/corrupt existing file: treat as a fresh save.
                created_at = now

        info = TaskDefinitionInfo(
            id=task_id,
            name=name,
            workflow_id=workflow_id,
            workflow=workflow if isinstance(workflow, str) else "",
            inputs=dict(inputs or {}),
            work_dir=work_dir if isinstance(work_dir, str) else "",
            description=description if isinstance(description, str) else "",
            created_at=created_at,
            updated_at=now,
        )
        atomic_write_json(path, info.to_dict())
        return info

    def load(self, ref: str) -> TaskDefinitionInfo:
        """Return the task definition *ref* points at.

        Raises:
            TaskNotFoundError: if no task matches *ref*.
            AmbiguousTaskNameError: if *ref* is a name matching several.
            ValueError: if the stored file is not a valid task document.
        """
        return self._read(ref)

    def list(self) -> List[TaskDefinitionInfo]:
        """Return every ``*.json`` task definition, sorted by display name.

        Corrupt or schema-invalid files are skipped — a single broken task must
        not crash the listing (same tolerance as the workflow store).  The
        display name is read from the file, never derived from the file name
        (which is the opaque id).
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
            task_id = filename[: -len(".json")]
            try:
                data = self._read_data(path)
                infos.append(_info_from_data(task_id, data))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                logger.warning(
                    f"Skipping corrupted task file: {filename} — {exc}"
                )
                continue

        return sorted(infos, key=lambda info: info.name)

    def delete(self, ref: str) -> None:
        """Remove the task definition *ref* points at.

        Raises:
            TaskNotFoundError: if no task matches *ref*.
            AmbiguousTaskNameError: if *ref* is a name matching several.
        """
        task_id = self.resolve(ref)
        if task_id is None:
            raise TaskNotFoundError(ref)
        path = self._path_for_stem(task_id)
        if not os.path.isfile(path):
            raise TaskNotFoundError(ref)
        os.remove(path)

    def exists(self, ref: str) -> bool:
        """Return True when *ref* matches a stored task definition."""
        try:
            return self.resolve(ref) is not None
        except AmbiguousTaskNameError:
            # Several tasks share the name — for an existence check that is a
            # yes, not an error.
            return True

    # ── one-time migration / backfill ────────────────────────────────────

    def _migrate_legacy_names(self) -> None:
        """Rename pre-id ``<name>.json`` files to ``<id>.json``.

        Idempotent and best-effort: an id-shaped name is skipped, an
        unreadable/invalid file is left exactly where it is, and any failure is
        logged instead of breaking construction.

        Pre-id task files derived their display name from the file name and did
        not store it, so a file without a ``name`` field has the old stem
        written into it before the rename — otherwise the rename would destroy
        the only copy of the name.  Files that already carry a ``name`` are
        renamed in place (a pure ``os.replace``, no content rewrite).
        """
        if not os.path.isdir(self._task_defs_dir):
            return
        try:
            filenames = os.listdir(self._task_defs_dir)
        except OSError as exc:
            logger.warning(
                "could not read task dir %s during id migration: %s",
                self._task_defs_dir,
                exc,
            )
            return

        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            stem = filename[: -len(".json")]
            if is_task_id(stem):
                continue
            source = os.path.join(self._task_defs_dir, filename)
            if not os.path.isfile(source):
                continue

            try:
                data = self._read_data(source)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                logger.warning(
                    "leaving unreadable file %s in place during id migration: %s",
                    filename,
                    exc,
                )
                continue

            target_id = self._allocate_id()
            if target_id is None:
                logger.warning(
                    "could not allocate an id for %s; leaving it in place", filename
                )
                continue
            target = self.path_for_id(target_id)

            raw_name = data.get("name")
            if isinstance(raw_name, str) and raw_name.strip():
                try:
                    os.replace(source, target)
                except FileNotFoundError:
                    # A concurrent constructor already migrated this file.
                    continue
                except OSError as exc:
                    logger.warning(
                        "could not migrate task file %s to an id: %s", filename, exc
                    )
                    continue
            else:
                # The old file name was the display name — write it in before
                # the rename can lose it.
                data["name"] = stem
                try:
                    atomic_write_json(target, data)
                except OSError as exc:
                    logger.warning(
                        "could not migrate task file %s to an id: %s", filename, exc
                    )
                    continue
                try:
                    os.remove(source)
                except OSError as exc:
                    logger.warning(
                        "migrated task file %s but could not remove the old copy: %s",
                        filename,
                        exc,
                    )
            logger.info(
                "migrated task file %s -> %s", filename, os.path.basename(target)
            )

    def backfill_workflow_ids(self, resolve_name: Callable[[str], Optional[str]]) -> int:
        """Fill in a missing ``workflow_id`` from the bound workflow's name.

        Pre-id task files bound their workflow by display name only.  This
        resolves those names to ids once, so a later rename of the workflow no
        longer breaks the binding.  Idempotent; returns the number of files
        updated.

        Args:
            resolve_name: maps a workflow display name to its id, or ``None``
                when the name is unknown (dangling) or ambiguous.  May raise
                ``Exception`` for an ambiguous name — that is treated as
                "leave the name-based binding alone" rather than as a failure.
        """
        updated = 0
        if not os.path.isdir(self._task_defs_dir):
            return updated
        try:
            filenames = os.listdir(self._task_defs_dir)
        except OSError as exc:
            logger.warning(
                "could not read task dir %s during workflow-id backfill: %s",
                self._task_defs_dir,
                exc,
            )
            return updated

        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self._task_defs_dir, filename)
            if not os.path.isfile(path):
                continue
            try:
                data = self._read_data(path)
                info = _info_from_data(filename[: -len(".json")], data)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                logger.warning(
                    "skipping unreadable task file %s during backfill: %s",
                    filename,
                    exc,
                )
                continue

            if info.workflow_id:
                continue
            if not info.workflow:
                continue
            try:
                workflow_id = resolve_name(info.workflow)
            except Exception:
                # Ambiguous name: keeping the name-based binding is safer than
                # guessing which workflow this task meant.
                continue
            if not workflow_id:
                # Dangling binding — leave it, so the task still reports
                # workflow_exists: false instead of silently losing its target.
                continue

            data["workflow_id"] = workflow_id
            try:
                atomic_write_json(path, data)
            except OSError as exc:
                logger.warning(
                    "could not backfill workflow_id in %s: %s", filename, exc
                )
                continue
            updated += 1
        if updated:
            logger.info("backfilled workflow_id in %d task file(s)", updated)
        return updated
