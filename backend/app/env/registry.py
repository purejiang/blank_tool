#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Environment registry: resolves declared environments to concrete runtime paths.

This is the counterpart of :mod:`app.env.descriptor`. Where
:class:`~app.env.descriptor.EnvironmentDescriptor` declares *what* an
environment is (as data), :class:`EnvironmentRegistry` decides *where* it
actually lives on this machine.

Resolution follows the exact priority used by the legacy hardcoded
``app.utils.env`` helpers (behaviour parity):

1. ``env_var_override`` from the descriptor (e.g. ``BT_JAVA_BIN``), when the
   variable is set and the path exists;
2. bundled runtimes under the runtime directory (``runtime/<search_path>/``),
   probed via the descriptor's ``search_paths``;
3. well-known system env vars per type (``JAVA_HOME``/``JRE_HOME`` for ``jre``,
   ``PYTHONHOME`` for ``python``, ``NODE_HOME``/``NODEJS_HOME`` for ``node``);
4. ``shutil.which()`` over ``PATH`` using the binary file name.

Results are cached until :meth:`EnvironmentRegistry.refresh` is called.
"""

import logging
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.env.descriptor import EnvironmentDescriptor

logger = logging.getLogger(__name__)

# backend/ (env -> app -> backend). Note: registry.py lives at backend/app/env/.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# Default descriptor directory: backend/registry/environments/
_DEFAULT_DESCRIPTOR_DIR = _BACKEND_ROOT / "registry" / "environments"

# Well-known system env vars probed per environment type (resolution level 3).
# ``custom`` types declare no mapping and skip level 3.
_SYSTEM_ENV_VARS_BY_TYPE: Dict[str, List[str]] = {
    "jre": ["JAVA_HOME", "JRE_HOME"],
    "python": ["PYTHONHOME"],
    "node": ["NODE_HOME", "NODEJS_HOME"],
    "custom": [],
}

# Upper bound for the version probe subprocess.
_VERSION_TIMEOUT_SECONDS = 15.0


class EnvironmentNotFoundError(Exception):
    """
    Strict alternative for a missing/unknown environment.

    ``EnvironmentRegistry.resolve`` deliberately does **not** raise this — it
    returns an invalid :class:`ResolvedEnvironment` instead (graceful handling).
    The class exists for callers that want an exception.
    """


@dataclass
class ResolvedEnvironment:
    """
    The concrete result of resolving one environment descriptor.

    Attributes:
        name: environment identifier (same as the descriptor's name).
        root_path: absolute path of the environment root; empty if unresolved.
        binary_path: absolute path to the resolved binary; empty if unresolved.
        version: version string extracted via ``version_regex``; empty when it
            could not be determined.
        is_valid: ``True`` only when a binary exists **and** its ``version_cmd``
            probe exited with status 0.
    """

    name: str
    root_path: str
    binary_path: str
    version: str
    is_valid: bool


def _resolve_path(path_str: str) -> str:
    """Resolve *path_str* to an absolute path (relative paths anchor to backend/)."""
    if not path_str:
        return ""
    if os.path.isabs(path_str):
        return os.path.normpath(path_str)
    return os.path.normpath(os.path.join(str(_BACKEND_ROOT), path_str))


def _runtime_dir() -> str:
    """
    Return the runtime base directory, mirroring ``app.utils.env.get_runtime_dir``.

    Priority: ``BT_RUNTIME_DIR`` env var (resolved against backend/), then
    ``backend/runtime``, then the project-root ``runtime/``. Implemented
    locally to avoid an import cycle with ``app.utils.env``.
    """
    override = os.environ.get("BT_RUNTIME_DIR")
    if override:
        return _resolve_path(override)
    local = _BACKEND_ROOT / "runtime"
    if local.is_dir():
        return str(local)
    up = _BACKEND_ROOT.parent / "runtime"
    if up.is_dir():
        return str(up)
    return ""


class EnvironmentRegistry:
    """
    Loads environment descriptors and resolves them to concrete paths.

    The registry is the single source of truth for "where is environment X on
    this machine". It is thread-safe: descriptors and the resolution cache are
    guarded by a :class:`threading.Lock`.
    """

    def __init__(self) -> None:
        """Start with no descriptors and an empty resolution cache."""
        self._descriptors: Dict[str, EnvironmentDescriptor] = {}
        self._cache: Dict[str, ResolvedEnvironment] = {}
        self._lock = threading.Lock()

    def discover(
        self,
        descriptor_dir: Optional[str] = None,
        overlay_descriptor_dir: Optional[str] = None,
    ) -> None:
        """
        Load every ``*.json`` descriptor from *descriptor_dir* (bundled)
        and *overlay_descriptor_dir* (writable per-user overlay).

        Args:
            descriptor_dir: directory containing JSON descriptors. Defaults to
                ``backend/registry/environments/`` (derived from this file).
            overlay_descriptor_dir: writable overlay directory whose same-named
                descriptors win over bundled ones.  Omitted/absent directories
                are silently ignored.

        A missing directory is a no-op (warned, not raised), so the registry
        stays usable before the descriptor directory exists. Malformed files
        are skipped with a warning; duplicates keep the first (sorted order),
        and loading replaces all descriptors and drops the cache.
        """
        dir_path = Path(descriptor_dir) if descriptor_dir else _DEFAULT_DESCRIPTOR_DIR

        discovered: Dict[str, EnvironmentDescriptor] = {}

        def _load_from(dir_path_to_load: Path) -> None:
            if not dir_path_to_load.is_dir():
                logger.warning(
                    "descriptor directory %s does not exist; no environments discovered",
                    dir_path_to_load,
                )
                return
            for file_path in sorted(dir_path_to_load.glob("*.json")):
                try:
                    descriptor = EnvironmentDescriptor.load_from_file(str(file_path))
                except ValueError as exc:
                    logger.warning(
                        "skipping malformed descriptor %s: %s", file_path.name, exc
                    )
                    continue
                if descriptor.name in discovered:
                    # Late-load wins (overlay replaces bundled)
                    discovered[descriptor.name] = descriptor
                    logger.debug("overlay descriptor %s replaces bundled", descriptor.name)
                else:
                    discovered[descriptor.name] = descriptor

        _load_from(dir_path)
        if overlay_descriptor_dir:
            _load_from(Path(overlay_descriptor_dir))

        with self._lock:
            self._descriptors = discovered
            self._cache.clear()
        logger.info("discovered %d environment(s)", len(discovered))

    def resolve(self, name: str) -> ResolvedEnvironment:
        """
        Resolve the environment named *name* to a concrete instance.

        Unknown names are handled gracefully: an invalid
        :class:`ResolvedEnvironment` with empty paths is returned (never
        :class:`EnvironmentNotFoundError`). Results — negative ones included —
        are cached until :meth:`refresh`.
        """
        with self._lock:
            cached = self._cache.get(name)
            if cached is not None:
                return cached
            descriptor = self._descriptors.get(name)

        if descriptor is None:
            result = ResolvedEnvironment(
                name=name, root_path="", binary_path="", version="", is_valid=False
            )
        else:
            result = self._resolve_descriptor(descriptor)

        with self._lock:
            self._cache[name] = result
        return result

    def list_all(self) -> List[ResolvedEnvironment]:
        """Resolve every discovered descriptor (in discovery order)."""
        with self._lock:
            names = list(self._descriptors.keys())
        return [self.resolve(name) for name in names]

    def is_available(self, name: str) -> bool:
        """Return whether the environment named *name* resolves to a valid one."""
        return self.resolve(name).is_valid

    def refresh(self) -> None:
        """Drop the resolution cache; discovered descriptors stay loaded."""
        with self._lock:
            self._cache.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_descriptor(self, descriptor: EnvironmentDescriptor) -> ResolvedEnvironment:
        binary_path, root_path = _find_binary(descriptor)
        if not binary_path:
            return ResolvedEnvironment(
                name=descriptor.name, root_path="", binary_path="", version="", is_valid=False
            )
        version, probe_ok = _probe_version(binary_path, descriptor)
        return ResolvedEnvironment(
            name=descriptor.name,
            root_path=root_path,
            binary_path=binary_path,
            version=version,
            is_valid=probe_ok,
        )


def _find_binary(descriptor: EnvironmentDescriptor) -> Tuple[str, str]:
    """
    Locate the environment's binary, returning ``(binary_path, root_path)``.

    Levels (first match wins): 1) env var override, 2) bundled runtime search
    paths, 3) well-known system env vars per type, 4) ``PATH``. Returns
    ``("", "")`` when nothing matches.
    """
    # Level 1: env var override — the variable points directly at the binary.
    if descriptor.env_var_override:
        raw = os.environ.get(descriptor.env_var_override)
        if raw:
            override = _resolve_path(raw)
            if os.path.isfile(override):
                return override, os.path.dirname(override)

    # Level 2: bundled runtimes under the runtime directory.
    if descriptor.search_paths:
        runtime_dir = _runtime_dir()
        if runtime_dir:
            for search_path in descriptor.search_paths:
                root = os.path.join(runtime_dir, search_path)
                candidate = os.path.join(root, descriptor.binary)
                if os.path.isfile(candidate):
                    return candidate, root

    # Level 3: well-known system env vars per type.
    for env_var in _SYSTEM_ENV_VARS_BY_TYPE.get(descriptor.type, ()):
        env_value = os.environ.get(env_var)
        if not env_value:
            continue
        # ``binary`` may already carry a bin/ prefix (e.g. bin/java.exe), so
        # try both layouts with the env root (e.g. JAVA_HOME) as the base.
        for candidate in (
            os.path.join(env_value, descriptor.binary),
            os.path.join(env_value, "bin", descriptor.binary),
        ):
            if os.path.isfile(candidate):
                return candidate, env_value

    # Level 4: PATH search using the binary file name only.
    found = shutil.which(os.path.basename(descriptor.binary))
    if found:
        return found, os.path.dirname(found)

    return "", ""


def _probe_version(binary_path: str, descriptor: EnvironmentDescriptor) -> Tuple[str, bool]:
    """
    Run ``version_cmd`` against *binary_path*.

    Returns ``(version, ok)``: *version* is extracted from the combined
    stdout+stderr via ``version_regex`` (empty when undeterminable), and *ok*
    is ``True`` only when the probe exited with status 0.
    """
    try:
        proc = subprocess.run(
            [binary_path] + list(descriptor.version_cmd),
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("version probe failed for %s (%s)", descriptor.name, binary_path)
        return "", False

    if proc.returncode != 0:
        logger.warning(
            "version probe exited %d for %s (%s)",
            proc.returncode,
            descriptor.name,
            binary_path,
        )
        return "", False

    output = (proc.stdout or "") + (proc.stderr or "")
    try:
        match = re.search(descriptor.version_regex, output)
    except re.error as exc:
        logger.warning("invalid version_regex for %s: %s", descriptor.name, exc)
        return "", True
    return (match.group(1) if match else ""), True
