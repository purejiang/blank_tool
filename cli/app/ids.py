#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generated identity strings for stored workflows and task definitions.

Storage identity used to *be* the display name: a saved workflow lived at
``<name>.json`` and every reference to it — task bindings, sub-workflow
``template`` parameters, editor URLs, run history — carried that name.  Two
consequences followed: a non-ASCII name became a non-ASCII file name, and
renaming a workflow broke every reference to it.

Both stores now key their files by an opaque, auto-generated ASCII id:

- ``<output_dir>/workflows/wf-<12 hex>.json``  — a saved workflow;
- ``<output_dir>/task_defs/tk-<12 hex>.json``  — a saved task definition.

The display name stays free-form (any script, arbitrary punctuation, and it may
even repeat) and is stored *inside* the file.  The file name stem IS the id —
there is no redundant ``id`` field to drift out of sync.

The ids are short and prefixed on purpose: they show up in logs, CLI output and
URLs, and a regex must be able to tell an id from a name (both stores keep
accepting a name as a fallback reference).
"""

import os
import re
import uuid

#: Stored workflow id: ``wf-`` + 12 lowercase hex chars (48 bits).
WORKFLOW_ID_RE = re.compile(r"^wf-[0-9a-f]{12}$")

#: Stored task-definition id: ``tk-`` + 12 lowercase hex chars (48 bits).
TASK_ID_RE = re.compile(r"^tk-[0-9a-f]{12}$")

#: How many times a colliding id is redrawn before the store gives up.  A
#: collision needs two identical 48-bit draws, so this is paranoia rather than
#: a real limit — but it guarantees a generated id can never overwrite a file
#: that already belongs to something else.
MAX_ID_ATTEMPTS = 10


def new_workflow_id() -> str:
    """Return a fresh workflow id (``wf-`` + 12 hex chars)."""
    return "wf-" + uuid.uuid4().hex[:12]


def new_task_id() -> str:
    """Return a fresh task-definition id (``tk-`` + 12 hex chars)."""
    return "tk-" + uuid.uuid4().hex[:12]


def is_workflow_id(value) -> bool:
    """Return True when *value* is shaped like a workflow id."""
    return isinstance(value, str) and bool(WORKFLOW_ID_RE.match(value))


def is_task_id(value) -> bool:
    """Return True when *value* is shaped like a task-definition id."""
    return isinstance(value, str) and bool(TASK_ID_RE.match(value))


def is_plain_stem(value) -> bool:
    """Return True when *value* can only name a file directly inside one dir.

    Used for the last-resort "the file name is the name" lookup that keeps a
    hand-placed or unparsable file addressable.  Rejecting separators, ``..``
    and blanks is what stops that fallback from becoming a path-traversal hole.
    """
    if not isinstance(value, str) or not value:
        return False
    if os.sep in value or "/" in value or "\\" in value:
        return False
    if ".." in value:
        return False
    return True


def id_file_path(directory: str, value, pattern, label: str) -> str:
    """Return ``<directory>/<value>.json`` for an id-shaped *value*.

    Shared by both stores so their path-safety rules cannot drift apart.  The
    *pattern* check is what makes a crafted reference unable to escape
    *directory*: an id only ever contains ``[a-z0-9-]``, so separators, ``..``
    and drive letters are rejected before a path is built.

    Args:
        directory: the writable store directory.
        value: the candidate id.
        pattern: compiled regex the id must fully match.
        label: noun used in error messages (``"workflow"`` / ``"task"``).

    Raises:
        ValueError: if *value* is not a non-empty string, or does not match
            *pattern*.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} id must be a non-empty string")
    if not pattern.match(value):
        raise ValueError(f"invalid {label} id: {value!r}")
    return os.path.join(directory, f"{value}.json")
