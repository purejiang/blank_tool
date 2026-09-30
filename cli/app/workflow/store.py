#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Saved-workflow storage.

D3 storage layer for saved workflows: :class:`WorkflowStore` is the abstract
interface, :class:`FileWorkflowStore` persists one workflow per
``<id>.json`` file under a WRITABLE directory.

Identity vs. display name:
    A stored workflow is identified by an **auto-generated ASCII id**
    (``wf-`` + 12 hex chars, see :mod:`app.ids`) which is also its file name.
    Its **display name** lives inside the file (``definition.name``), is free
    to be any script, and may even repeat.  References may use either: the
    store resolves an id first and falls back to a name lookup
    (:meth:`FileWorkflowStore.resolve`), so pre-id references — saved task
    bindings, ``workflow.run`` ``template`` parameters, bookmarks — keep
    working.

Writable-path requirement (Oracle finding #2):
    In packaged builds the ``cli/`` tree is copied to
    ``process.resourcesPath`` (electron-builder ``extraResources``, see
    ``package.json``) and is READ-ONLY.  The storage directory resolves via
    ``BT_WORKFLOWS_DIR`` (falling back to the legacy ``BT_TEMPLATES_DIR``),
    else ``<output_dir>/workflows`` (``get_output_dir()`` returns a writable
    path), and is created on construction.  No workflows are pre-installed —
    users import them separately (e.g. from ``examples/``).

Directory layout (one file per workflow, ``<id>.json``)::

    {
        "definition": { ... WorkflowDefinition.to_dict() ... },
        "created_at": "2026-08-03T12:00:00.000000",
        "updated_at": "2026-08-03T12:00:00.000000",
        "description": "...",
        "tags": ["android", "install"]
    }

    A raw (bare-definition) file is still accepted on read: when there is no
    ``definition`` key the whole file IS the definition, which is exactly the
    import format used by ``examples/``.

One-time migrations (idempotent, best-effort, never fatal):
    Construction adopts any surviving ``<output_dir>/templates/`` files into
    the new ``workflows/`` directory, then renames every file whose name is
    not already an id (``<display name>.json`` from the pre-id era) to a fresh
    id.  A file that does not parse as a workflow is left exactly where it is,
    so an unrelated or corrupt JSON is never relabelled as a workflow.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.env import get_env, get_output_dir
from app.ids import (
    MAX_ID_ATTEMPTS,
    WORKFLOW_ID_RE,
    id_file_path,
    is_plain_stem,
    is_workflow_id,
    new_workflow_id,
)
from app.utils.atomic_json import atomic_write_json
from app.workflow.definition import WorkflowDefinition

logger = logging.getLogger(__name__)

#: Historical module-local name for
#: :func:`app.utils.atomic_json.atomic_write_json` — the helper moved to
#: ``app.utils`` when the task-definition store needed the same temp-file +
#: ``os.replace`` write.  Kept as an alias so the write path stays a single
#: implementation and module-local references keep working.
_atomic_write_json = atomic_write_json

#: Directory name (under the output dir) holding saved workflows.
WORKFLOWS_DIRNAME = "workflows"

#: Pre-rename directory name whose contents are adopted on construction.
LEGACY_WORKFLOWS_DIRNAME = "templates"


def _file_mtime_iso(path: str) -> Optional[str]:
    """Return *path*'s modification time as an ISO-8601 string, or ``None``.

    Used as the timestamp fallback for raw (bare definition) workflow files,
    which carry no wrapper ``created_at``/``updated_at``.  Never raises: an
    unreadable/unstatable file simply yields ``None``.
    """
    try:
        return datetime.fromtimestamp(os.stat(path).st_mtime).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


@dataclass
class WorkflowInfo:
    """Read-only metadata about a stored workflow (returned by ``list``).

    Attributes:
        id: storage identity — also the ``<id>.json`` file name stem.
        name: human-facing display name (``definition.name``); may repeat
            across workflows and may contain any characters.
        description: human-facing explanation of the workflow.
        created_at: ISO-8601 timestamp of the first save, or ``None``.
        updated_at: ISO-8601 timestamp of the last save, or ``None``.
        tags: free-form keyword list attached by the caller.
        node_count: number of nodes in the stored definition.
    """

    id: str
    name: str
    description: str
    created_at: Optional[str]
    updated_at: Optional[str]
    tags: List[str]
    node_count: int


class WorkflowNotFoundError(Exception):
    """Raised when ``load``/``delete`` targets a workflow that does not exist."""


class AmbiguousWorkflowNameError(Exception):
    """Raised when a display name matches more than one stored workflow.

    Ids are unique, names are not: once two workflows share a name, only an id
    can identify one of them, so name-based lookups fail loudly instead of
    silently picking a winner.
    """

    def __init__(self, name: str, ids: List[str]) -> None:
        self.name = name
        self.ids = list(ids)
        super().__init__(
            f"workflow name {name!r} matches {len(self.ids)} workflows "
            f"({', '.join(self.ids)}); refer to one by id"
        )


class WorkflowStore(ABC):
    """Abstract saved-workflow storage.

    Implementations persist :class:`WorkflowDefinition` objects under a
    generated ASCII id.  The abstract surface is deliberately small so a
    future SQLite-backed store can drop in without touching callers (D3).
    """

    @abstractmethod
    def save(
        self,
        definition: WorkflowDefinition,
        metadata: dict,
        workflow_id: Optional[str] = None,
    ) -> WorkflowInfo:
        """Persist *definition* (create or overwrite).

        Args:
            definition: the workflow schema to store; its ``name`` is the
                display name.
            metadata: caller-supplied dict; the ``description`` and ``tags``
                keys are stored with the workflow.
            workflow_id: id to overwrite; ``None`` allocates a fresh one.

        Returns:
            The stored :class:`WorkflowInfo`, including the effective id.
        """
        raise NotImplementedError

    @abstractmethod
    def load_with_meta(
        self, ref: str
    ) -> Tuple[WorkflowDefinition, Dict[str, Any]]:
        """Load the workflow *ref* points at, plus its wrapper metadata.

        Args:
            ref: a workflow id, or a display name to look up.

        Returns:
            ``(definition, metadata)`` where *metadata* carries ``id``,
            ``name``, ``description`` (str), ``tags`` (list of str),
            ``created_at`` and ``updated_at`` (ISO-8601 strings, or ``None``
            when unknown).  Missing metadata keys never raise — each falls
            back to its default.

        Raises:
            WorkflowNotFoundError: if no workflow matches *ref*.
            AmbiguousWorkflowNameError: if *ref* is a name matching several.
        """
        raise NotImplementedError

    @abstractmethod
    def load(self, ref: str) -> WorkflowDefinition:
        """Load the workflow definition *ref* points at.

        Raises:
            WorkflowNotFoundError: if no workflow matches *ref*.
            AmbiguousWorkflowNameError: if *ref* is a name matching several.
        """
        raise NotImplementedError

    @abstractmethod
    def list(self) -> List[WorkflowInfo]:
        """Return metadata for every stored workflow, sorted by display name."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, ref: str) -> None:
        """Remove the workflow *ref* points at.

        Raises:
            WorkflowNotFoundError: if no workflow matches *ref*.
            AmbiguousWorkflowNameError: if *ref* is a name matching several.
        """
        raise NotImplementedError

    @abstractmethod
    def exists(self, ref: str) -> bool:
        """Return True when *ref* matches a stored workflow."""
        raise NotImplementedError


class FileWorkflowStore(WorkflowStore):
    """File-backed :class:`WorkflowStore` storing one JSON file per workflow.

    All workflows live under ``self._workflows_dir`` — a WRITABLE directory
    outside the bundled resources (see the module docstring, Oracle finding
    #2).  The directory is created on construction, which also runs the
    one-time legacy migrations.
    """

    def __init__(self, workflows_dir: Optional[str] = None) -> None:
        """Resolve and prepare the writable workflows directory.

        Args:
            workflows_dir: explicit writable directory.  When omitted,
                resolves ``BT_WORKFLOWS_DIR`` (or the legacy
                ``BT_TEMPLATES_DIR``) and falls back to
                ``<output_dir>/workflows`` (``get_output_dir()`` is a writable
                path in both dev and packaged builds).  The legacy
                ``<output_dir>/templates/`` directory is only adopted when the
                default was used — an explicit directory is never second-guessed.

        The directory is created (``exist_ok=True``) if missing, then any
        surviving pre-id files are migrated to ids (idempotent).
        """
        legacy_dir = None
        if workflows_dir:
            self._workflows_dir = workflows_dir
        else:
            env_dir = get_env("BT_WORKFLOWS_DIR") or get_env("BT_TEMPLATES_DIR")
            if env_dir:
                self._workflows_dir = env_dir
            else:
                self._workflows_dir = os.path.join(
                    get_output_dir(), WORKFLOWS_DIRNAME
                )
                legacy_dir = os.path.join(
                    get_output_dir(), LEGACY_WORKFLOWS_DIRNAME
                )
        os.makedirs(self._workflows_dir, exist_ok=True)
        if legacy_dir:
            self._adopt_legacy_dir(legacy_dir)
        self._migrate_legacy_names()

    @property
    def workflows_dir(self) -> str:
        """The writable directory workflow files are stored in."""
        return self._workflows_dir

    # ── identity ─────────────────────────────────────────────────────────

    def _path_for_stem(self, stem: str) -> str:
        """Return the file path for a *stem* already known to live in this dir.

        Used for stems that came out of :meth:`resolve` — either a validated id
        or a file name discovered by scanning the directory — so it never needs
        to re-validate.  Caller-supplied ids go through :meth:`path_for_id`.
        """
        return os.path.join(self._workflows_dir, f"{stem}.json")

    def path_for_id(self, workflow_id: str) -> str:
        """Return the file path for *workflow_id*.

        Rejects anything that is not id-shaped with :class:`ValueError`, so a
        crafted reference cannot escape ``self._workflows_dir``.
        """
        return id_file_path(
            self._workflows_dir, workflow_id, WORKFLOW_ID_RE, "workflow"
        )

    def _allocate_id(self) -> Optional[str]:
        """Return an unused workflow id, or ``None`` if none could be drawn."""
        for _ in range(MAX_ID_ATTEMPTS):
            candidate = new_workflow_id()
            if not os.path.exists(self.path_for_id(candidate)):
                return candidate
        return None

    def find_id_by_name(self, name: str) -> Optional[str]:
        """Return the id of the workflow whose display name is *name*.

        An exact match wins; a case-insensitive pass follows, because the
        pre-id store compared names through the file system (case-insensitive
        on Windows and on macOS default volumes) and references written back
        then rely on it.  A name matching several workflows raises
        :class:`AmbiguousWorkflowNameError` rather than picking one.

        When nothing matches, a file literally named ``<name>.json`` is still
        accepted as that workflow: that is how a hand-placed file — or a
        corrupt one, whose display name cannot be read — stays addressable, and
        it is what turns such a reference into a parse error instead of a
        confusing "not found".
        """
        if not isinstance(name, str) or not name:
            return None
        infos = self.list()
        matches = [info.id for info in infos if info.name == name]
        if not matches:
            folded = name.casefold()
            matches = [info.id for info in infos if info.name.casefold() == folded]
        if len(matches) > 1:
            raise AmbiguousWorkflowNameError(name, matches)
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
        if is_workflow_id(ref):
            return ref if os.path.isfile(self.path_for_id(ref)) else None
        return self.find_id_by_name(ref)

    # ── write / read ─────────────────────────────────────────────────────

    def save(
        self,
        definition: WorkflowDefinition,
        metadata: dict,
        workflow_id: Optional[str] = None,
    ) -> WorkflowInfo:
        """Persist *definition* under *workflow_id* (create or overwrite).

        ``created_at`` is set on first save and preserved on overwrite;
        ``updated_at`` is refreshed on every save.  The file is written as
        UTF-8 JSON with 2-space indent.
        """
        name = getattr(definition, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("workflow definition must carry a non-empty name")

        if workflow_id is None:
            allocated = self._allocate_id()
            if allocated is None:
                raise RuntimeError("could not allocate a free workflow id")
            workflow_id = allocated
        else:
            # Validates the id shape before any path is built.
            self.path_for_id(workflow_id)

        path = self.path_for_id(workflow_id)
        now = datetime.now().isoformat()

        created_at = now
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    created_at = json.load(f).get("created_at") or now
            except (OSError, TypeError, AttributeError, json.JSONDecodeError):
                # Unreadable/corrupt existing file: treat as a fresh save.
                created_at = now

        description = metadata.get("description", "")
        tags = list(metadata.get("tags", []))
        data = {
            "definition": definition.to_dict(),
            "created_at": created_at,
            "updated_at": now,
            "description": description,
            "tags": tags,
        }
        _atomic_write_json(path, data)

        return WorkflowInfo(
            id=workflow_id,
            name=name,
            description=description if isinstance(description, str) else "",
            created_at=created_at,
            updated_at=now,
            tags=tags,
            node_count=len(definition.nodes),
        )

    def _read_definition_and_meta(
        self, path: str
    ) -> Tuple[WorkflowDefinition, Dict[str, Any]]:
        """Parse one workflow file into ``(definition, wrapper metadata)``.

        Two on-disk formats are accepted, mirroring :meth:`save`/:meth:`list`:

        - Wrapped (produced by :meth:`save`): ``{"definition": {...},
          "description": ..., "tags": [...], "created_at": ...,
          "updated_at": ...}`` — the wrapper metadata is returned as stored
          (a missing/blank key falls back to its default).
        - Raw (import format, e.g. a file copied from ``examples/``): a bare
          :class:`WorkflowDefinition` dict with no ``definition`` key — the
          whole file IS the definition.  ``description`` is taken from that
          definition's own top-level field, ``tags`` is ``[]`` and the
          timestamps fall back to the file's modification time (``None`` when
          it cannot be read).

        Raises:
            ValueError: if the file is not valid JSON, not a dict, or fails
                :meth:`WorkflowDefinition.from_dict` validation.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSON in workflow file {path}: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(
                f"workflow file {path} is not a valid workflow: "
                "expected a JSON object"
            )

        definition_data = data.get("definition")
        if definition_data is None:
            # Raw workflow file (import format) — the whole file is the
            # definition and it carries no wrapper metadata.  The description
            # is read from the definition's own top-level field so
            # load_with_meta() agrees with list() (which does the same for raw
            # files); tags have no raw-file equivalent.
            definition_data = data
            mtime = _file_mtime_iso(path)
            raw_description = data.get("description")
            metadata: Dict[str, Any] = {
                "description": (
                    raw_description if isinstance(raw_description, str) else ""
                ),
                "tags": [],
                "created_at": mtime,
                "updated_at": mtime,
            }
        else:
            # Wrapped store format (from save()).
            description = data.get("description")
            raw_tags = data.get("tags")
            metadata = {
                "description": description if isinstance(description, str) else "",
                "tags": list(raw_tags) if isinstance(raw_tags, list) else [],
                "created_at": data.get("created_at") or None,
                "updated_at": data.get("updated_at") or None,
            }

        return WorkflowDefinition.from_dict(definition_data), metadata

    def load_with_meta(
        self, ref: str
    ) -> Tuple[WorkflowDefinition, Dict[str, Any]]:
        """Load the workflow *ref* points at, plus its wrapper metadata.

        Returns:
            ``(definition, metadata)`` where *metadata* carries ``id``,
            ``name``, ``description``, ``tags``, ``created_at`` and
            ``updated_at``.

        Raises:
            WorkflowNotFoundError: if no workflow matches *ref*.
            AmbiguousWorkflowNameError: if *ref* is a name matching several.
            ValueError: if the stored file is not valid JSON, not a dict, or
                fails :meth:`WorkflowDefinition.from_dict` validation.
        """
        workflow_id = self.resolve(ref)
        if workflow_id is None:
            raise WorkflowNotFoundError(ref)

        path = self._path_for_stem(workflow_id)
        if not os.path.isfile(path):
            raise WorkflowNotFoundError(ref)

        definition, metadata = self._read_definition_and_meta(path)
        metadata["id"] = workflow_id
        metadata["name"] = definition.name
        return definition, metadata

    def load(self, ref: str) -> WorkflowDefinition:
        """Load the workflow definition *ref* points at.

        Thin wrapper over :meth:`load_with_meta` (single read path).

        Raises:
            WorkflowNotFoundError: if no workflow matches *ref*.
            AmbiguousWorkflowNameError: if *ref* is a name matching several.
            ValueError: if the stored file is not valid JSON, not a dict, or
                fails :meth:`WorkflowDefinition.from_dict` validation.
        """
        definition, _metadata = self.load_with_meta(ref)
        return definition

    def list(self) -> List[WorkflowInfo]:
        """Return metadata for every ``*.json`` workflow, sorted by name.

        Corrupt or schema-invalid files are skipped (a single broken file must
        not crash the listing); ``node_count`` is derived from the parsed
        definition's ``nodes`` length and ``name`` from ``definition.name``
        (never from the file name, which is the opaque id).
        """
        infos: List[WorkflowInfo] = []
        if not os.path.isdir(self._workflows_dir):
            return infos

        for filename in os.listdir(self._workflows_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self._workflows_dir, filename)
            if not os.path.isfile(path):
                continue

            try:
                definition, metadata = self._read_definition_and_meta(path)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as e:
                logger.warning(
                    f"Skipping corrupted workflow file: {filename} — {e}"
                )
                continue

            infos.append(
                WorkflowInfo(
                    id=filename[: -len(".json")],
                    name=definition.name,
                    description=metadata["description"],
                    created_at=metadata["created_at"],
                    updated_at=metadata["updated_at"],
                    tags=metadata["tags"],
                    node_count=len(definition.nodes),
                )
            )
        return sorted(infos, key=lambda info: info.name)

    def delete(self, ref: str) -> None:
        """Remove the workflow *ref* points at.

        Raises:
            WorkflowNotFoundError: if no workflow matches *ref*.
            AmbiguousWorkflowNameError: if *ref* is a name matching several.
        """
        workflow_id = self.resolve(ref)
        if workflow_id is None:
            raise WorkflowNotFoundError(ref)
        path = self._path_for_stem(workflow_id)
        if not os.path.isfile(path):
            raise WorkflowNotFoundError(ref)
        os.remove(path)

    def exists(self, ref: str) -> bool:
        """Return True when *ref* matches a stored workflow."""
        try:
            return self.resolve(ref) is not None
        except AmbiguousWorkflowNameError:
            # Several workflows share the name — for an existence check that is
            # a yes, not an error.
            return True

    # ── one-time migrations ──────────────────────────────────────────────

    def _adopt_legacy_dir(self, legacy_dir: str) -> None:
        """Move workflow files out of the pre-rename directory.

        Called only when the store resolved the *default* directory, so an
        explicitly configured store never reaches into an unrelated path.
        Idempotent: a file whose target already exists is left alone, and the
        legacy directory is removed only when it ends up empty.
        """
        if os.path.normpath(legacy_dir) == os.path.normpath(self._workflows_dir):
            return
        if not os.path.isdir(legacy_dir):
            return

        moved = 0
        try:
            filenames = os.listdir(legacy_dir)
        except OSError as exc:
            logger.warning("could not read legacy workflow dir %s: %s", legacy_dir, exc)
            return

        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            source = os.path.join(legacy_dir, filename)
            target = os.path.join(self._workflows_dir, filename)
            if not os.path.isfile(source) or os.path.exists(target):
                continue
            try:
                os.replace(source, target)
                moved += 1
            except FileNotFoundError:
                continue
            except OSError as exc:
                logger.warning(
                    "could not adopt legacy workflow file %s: %s", source, exc
                )

        if moved:
            logger.info(
                "adopted %d workflow file(s) from %s into %s",
                moved,
                legacy_dir,
                self._workflows_dir,
            )
        try:
            os.rmdir(legacy_dir)
        except OSError:
            # Non-empty (skipped/unknown files) or in use — harmless.
            pass

    def _migrate_legacy_names(self) -> None:
        """Rename pre-id ``<name>.json`` files to ``<id>.json``.

        Idempotent and best-effort: a file that already has an id-shaped name
        is skipped, a file that does not parse as a workflow is left exactly
        where it is (so an unrelated or corrupt JSON is never relabelled as a
        workflow), and any failure is logged instead of breaking construction.
        The content is not rewritten — only the file name changes.
        """
        if not os.path.isdir(self._workflows_dir):
            return
        try:
            filenames = os.listdir(self._workflows_dir)
        except OSError as exc:
            logger.warning(
                "could not read workflow dir %s during id migration: %s",
                self._workflows_dir,
                exc,
            )
            return

        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            stem = filename[: -len(".json")]
            if is_workflow_id(stem):
                continue
            source = os.path.join(self._workflows_dir, filename)
            if not os.path.isfile(source):
                continue

            try:
                # Parse-and-discard: the rename only happens for a file we can
                # prove is a workflow.
                self._read_definition_and_meta(source)
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
            try:
                os.replace(source, target)
            except FileNotFoundError:
                # A concurrent constructor already migrated this file.
                continue
            except OSError as exc:
                logger.warning(
                    "could not migrate workflow file %s to an id: %s", filename, exc
                )
                continue
            logger.info(
                "migrated workflow file %s -> %s", filename, os.path.basename(target)
            )
