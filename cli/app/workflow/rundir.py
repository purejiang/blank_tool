#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Per-run artifact directory.

Files the ENGINE produces while a workflow runs (today: ``flow.foreach``'s
per-item results file) must not be dropped into the workflow's own directory:
that directory can be a source tree or the template store, and polluting it
confuses git and ``template.list()``.

Every run therefore gets ``<output_dir>/runs/<run-id>/``.  The directory is
created once per run and exposed to workflow params as ``$rundir`` /
``${rundir}``, so an author has an obvious, writable place for their own
outputs too::

    "path": "${rundir}/evidence-${inputs.path | basename}.txt"

The run's *working* directory (``$workdir``) keeps its own meaning — it is
where relative input paths resolve.
"""

import os
import re

from app.utils.env import get_output_dir

#: Characters kept when turning a run id into a directory name.
_UNSAFE_SLUG_RE = re.compile(r"[^A-Za-z0-9_-]+")

#: Directory name under the output dir holding one subdirectory per run.
RUNS_DIRNAME = "runs"

#: Slug used when a run has no identifier at all.
FALLBACK_SLUG = "adhoc"


def safe_slug(value) -> str:
    """Reduce *value* to characters that are safe in a file/directory name."""
    slug = _UNSAFE_SLUG_RE.sub("_", str(value or ""))
    return slug.strip("_") or FALLBACK_SLUG


def runs_root() -> str:
    """Return the parent directory of every run directory."""
    return os.path.join(get_output_dir(), RUNS_DIRNAME)


def run_dir_for(run_id) -> str:
    """Return the artifact directory for *run_id*, creating it if needed.

    Raises:
        OSError: when the directory cannot be created (unwritable output
            dir) — callers degrade to "no per-run directory" instead of
            failing the run.
    """
    path = os.path.join(runs_root(), safe_slug(run_id))
    os.makedirs(path, exist_ok=True)
    return path
