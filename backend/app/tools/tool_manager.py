#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToolRegistry — lazy-loading tool registry with auto-discovery and dependency injection.
"""

import os
import platform
import pkgutil
import importlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Any, Callable, List

from app.tools.base_tool import BaseTool
from app.tools import probe_cache
from app.utils.logger import Logger
from app.utils.env import get_runtime_dir, get_env
from app.common.exceptions import ToolNotFoundError

# Probing one tool means launching it (up to twice). Serial probing made the
# first paint wait for the sum of all of them; four at a time keeps the JVM
# cold-start tools from contending while still cutting the wall clock several
# fold. Overridable for slow or antivirus-heavy machines.
DEFAULT_PROBE_WORKERS = 4


def _probe_workers() -> int:
    raw = get_env("BT_TOOL_PROBE_WORKERS")
    if raw:
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass
    return DEFAULT_PROBE_WORKERS


class ToolRegistry:
    """Lazy-loading tool registry with dependency injection.

    Discovers BaseTool subclasses at import time but only instantiates
    them on first access via get().
    """

    def __init__(self, search_system: bool = False):
        env_flag = os.environ.get("BT_SEARCH_SYSTEM_TOOLS") == "1"
        self.search_system = search_system or env_flag
        self.logger = Logger.get_logger("ToolRegistry")
        self._tools: Dict[str, BaseTool] = {}
        self._custom_paths: Dict[str, str] = {}
        self._discovered: Dict[str, type] = {}
        self._discover_lock = threading.Lock()
        self._initialized = False
        # One lock per tool: a demand probe (a handler asking for adb) and the
        # startup warm-up must never launch the same binary twice.
        self._tool_locks: Dict[str, threading.Lock] = {}
        self._tool_locks_guard = threading.Lock()
        # Probe verdicts are reused across launches (see app.tools.probe_cache).
        # RLock: the store path re-enters through _cache_doc().
        self._cache_document: Optional[Dict[str, Any]] = None
        self._cache_lock = threading.RLock()
        self._last_probe_ms: int = 0

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, tool_package: str = 'app.tools'):
        """Auto-discover BaseTool subclasses in the given package.

        Scans all modules in *tool_package* for classes that inherit from
        BaseTool (excluding BaseTool itself, CommandTool, and classes
        defined in base_tool.py).
        """
        with self._discover_lock:
            if self._initialized:
                return
            self._initialized = True
            package = importlib.import_module(tool_package)
            for _, name, _ in pkgutil.walk_packages(
                package.__path__, package.__name__ + '.'
            ):
                module = importlib.import_module(name)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseTool)
                        and attr is not BaseTool
                        and attr.__name__ != "CommandTool"
                        and attr.__module__ != "app.tools.base_tool"
                    ):
                        key = self._canonical_tool_name(attr.__name__)
                        default_path = self._default_tool_path(key)
                        self.logger.info(
                            f"Discovered tool: {attr.__name__} -> {default_path}"
                        )
                        self._discovered[key] = attr

    # ------------------------------------------------------------------
    # Lazy access
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseTool:
        """Lazy-instantiate and return a tool by name.

        Raises ToolNotFoundError if the tool class was not discovered.
        """
        if name in self._tools:
            return self._tools[name]

        tool_cls = self._discovered.get(name)
        if not tool_cls:
            raise ToolNotFoundError(name)

        with self._lock_for(name):
            # Another thread may have resolved it while we waited for the lock.
            if name in self._tools:
                return self._tools[name]
            instance = self._build(name, tool_cls)
            self._tools[name] = instance
            return instance

    def _lock_for(self, name: str) -> threading.Lock:
        with self._tool_locks_guard:
            lock = self._tool_locks.get(name)
            if lock is None:
                lock = threading.Lock()
                self._tool_locks[name] = lock
            return lock

    def _cache_doc(self) -> Dict[str, Any]:
        with self._cache_lock:
            if self._cache_document is None:
                self._cache_document = probe_cache.load()
            return self._cache_document

    def _build(self, name: str, tool_cls: type) -> BaseTool:
        """Resolve *name* to an instance, reusing a cached verdict when valid.

        The resolution rules below are the historical ones, unchanged — only
        the ``cached_probe`` shortcut and the cache write are new. A cache hit
        skips every subprocess the construction would otherwise launch.
        """
        custom_path = self._custom_paths.get(name)
        default_path = self._default_tool_path(name)

        doc = self._cache_doc()
        key = probe_cache.make_key(
            name,
            search_system=self.search_system,
            default_path=default_path,
            custom_path=custom_path,
        )
        cached = probe_cache.get_entry(doc, key)
        if cached is not None:
            self.logger.debug(
                f"Tool probe cache hit: {name} -> "
                f"{cached.get('path') or '(unresolved)'}"
            )
            return tool_cls(
                name=name,
                path=cached.get("path") or "",
                search_system=False,
                cached_probe=cached,
            )

        if custom_path:
            instance = tool_cls(name=name, path=custom_path, search_system=False)
        elif self.search_system:
            instance = tool_cls(name=name, path="", search_system=True)
            if not getattr(instance, "is_valid", False):
                if default_path and os.path.exists(default_path):
                    instance = tool_cls(
                        name=name, path=default_path, search_system=True
                    )
                else:
                    instance = tool_cls(name=name, path="", search_system=True)
        else:
            if default_path and os.path.exists(default_path):
                instance = tool_cls(
                    name=name, path=default_path, search_system=False
                )
            else:
                instance = tool_cls(name=name, path="", search_system=False)
            if not getattr(instance, "is_valid", False):
                instance = tool_cls(name=name, path="", search_system=True)

        with self._cache_lock:
            probe_cache.store(
                doc,
                key,
                path=getattr(instance, "tool_path", "") or "",
                is_valid=bool(getattr(instance, "is_valid", False)),
                version=getattr(instance, "version", "") or "",
            )
            probe_cache.save(doc)
        return instance

    def probe_all(
        self,
        progress_cb: Optional[Callable[[str, int, int], None]] = None,
        workers: Optional[int] = None,
    ) -> Dict[str, Optional[BaseTool]]:
        """Resolve every discovered tool concurrently.

        Warm-up entry point: the report shape and the per-tool verdicts are
        identical to resolving them one by one, but the subprocess launches
        overlap instead of adding up. ``progress_cb(name, done, total)`` fires
        as each tool settles. Never raises for a single bad tool.
        """
        names = self.list_all()
        total = len(names)
        if not total:
            return {}

        worker_count = max(1, int(workers if workers is not None else _probe_workers()))
        started = time.time()
        counter = {"done": 0}
        counter_lock = threading.Lock()
        resolved: Dict[str, Optional[BaseTool]] = {}

        def probe_one(tool_name: str) -> None:
            try:
                result = self.get(tool_name)
            except ToolNotFoundError:
                result = None
            except Exception as e:  # noqa: BLE001 — warm-up must not fail startup
                self.logger.warning(f"Probe failed for {tool_name}: {e}")
                result = None
            with counter_lock:
                resolved[tool_name] = result
                counter["done"] += 1
                done = counter["done"]
            if progress_cb:
                try:
                    progress_cb(tool_name, done, total)
                except Exception:  # noqa: BLE001 — a reporter must not break probes
                    pass

        if worker_count <= 1 or total == 1:
            for tool_name in names:
                probe_one(tool_name)
        else:
            with ThreadPoolExecutor(max_workers=min(worker_count, total)) as pool:
                list(pool.map(probe_one, names))

        elapsed_ms = int((time.time() - started) * 1000)
        self._last_probe_ms = elapsed_ms
        self.logger.info(
            f"probe wall time = {elapsed_ms}ms for {total} tools "
            f"({min(worker_count, total)} workers)"
        )
        return resolved

    def ensure_all_probed(self) -> None:
        """Warm every tool once (idempotent — resolved tools are reused)."""
        if all(name in self._tools for name in self._discovered):
            return
        self.probe_all()

    @property
    def last_probe_ms(self) -> int:
        """Wall-clock duration of the last ``probe_all`` (0 if never run)."""
        return self._last_probe_ms

    def list_all(self) -> list[str]:
        """Return names of all discovered tool classes."""
        return list(self._discovered.keys())

    def get_available_tools(self) -> Dict[str, BaseTool]:
        """Return all tools that are currently valid/available."""
        result: Dict[str, BaseTool] = {}
        for name in self.list_all():
            try:
                tool = self.get(name)
                if getattr(tool, "is_valid", False):
                    result[name] = tool
            except ToolNotFoundError:
                pass
        return result

    def refresh(self):
        """Clear cached instances so the next get() re-instantiates.

        Cached probe *verdicts* survive: they are keyed by the resolved path
        and validated against the file's mtime/size, so an unchanged binary is
        not re-launched just because someone asked for a refresh.
        """
        self._tools.clear()

    def _invalidate_cached(self, name: str) -> None:
        """Drop one tool's cached verdict (its resolution is about to change)."""
        with self._cache_lock:
            doc = self._cache_doc()
            probe_cache.invalidate(doc, name)
            probe_cache.save(doc)

    # ------------------------------------------------------------------
    # Custom path management
    # ------------------------------------------------------------------

    def set_custom_path(self, name: str, path: str) -> Dict[str, Any]:
        """Set a custom path for a tool and re-validate it."""
        self._custom_paths[name] = path
        # Clear cached instance so next get() re-instantiates
        self._tools.pop(name, None)
        # The override changes how the tool resolves, so any cached verdict
        # for it is about a different file now.
        self._invalidate_cached(name)
        # Re-instantiate and validate
        tool = self.get(name)
        return {
            "name": name,
            "path": getattr(tool, "tool_path", ""),
            "is_valid": bool(getattr(tool, "is_valid", False)),
            "version": getattr(tool, "version", "") if getattr(tool, "is_valid", False) else "",
        }

    def reset_custom_path(self, name: str) -> Dict[str, Any]:
        """Reset a tool to its default path."""
        self._custom_paths.pop(name, None)
        self._tools.pop(name, None)
        self._invalidate_cached(name)
        tool = self.get(name)
        return {
            "name": name,
            "path": getattr(tool, "tool_path", ""),
            "is_valid": bool(getattr(tool, "is_valid", False)),
            "version": getattr(tool, "version", "") if getattr(tool, "is_valid", False) else "",
        }

    def get_custom_paths(self) -> Dict[str, str]:
        """Return all custom path overrides."""
        return dict(self._custom_paths)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _canonical_tool_name(self, class_name: str) -> str:
        return class_name.lower()

    def _tools_base_dir(self) -> str:
        runtime_dir = get_runtime_dir()
        if runtime_dir and os.path.exists(runtime_dir):
            return runtime_dir
        raise RuntimeError(
            f"Environment variable 'BT_RUNTIME_DIR' is missing or invalid: "
            f"{runtime_dir}. Please configure the runtime path in "
            f"application settings."
        )

    def _default_tool_path(self, key: str) -> str:
        base = self._tools_base_dir()
        is_windows = platform.system() == "Windows"
        if key == "adb":
            return os.path.join(base, "adb", "adb.exe" if is_windows else "adb")
        if key == "aapt":
            return os.path.join(
                base, "aapt", "aapt2.exe" if is_windows else "aapt"
            )
        if key == "apktool":
            return os.path.join(base, "apktool", "apktool.jar")
        if key == "bundletool":
            return os.path.join(base, "bundletool", "bundletool.jar")
        if key == "zipalign":
            return os.path.join(
                base, "android", "zipalign.exe" if is_windows else "zipalign"
            )
        if key == "apksigner":
            return os.path.join(
                base, "android", "apksigner.jar" if is_windows else "apksigner"
            )
        if key == "jarsigner":
            return os.path.join(
                base,
                "jre", "bin",
                "jarsigner.exe" if is_windows else "jarsigner",
            )
        return ""


# ------------------------------------------------------------------
# Backward-compatible singleton wrapper
# ------------------------------------------------------------------

class ToolManager:
    """Backward-compatible singleton that delegates to ToolRegistry.

    Existing code using ``ToolManager.instance().get_tool('adb')``
    will continue to work unchanged.
    """

    _instance: Optional["ToolManager"] = None
    _lock = threading.Lock()

    def __new__(cls, search_system: bool = False):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, search_system: bool = False):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._registry = ToolRegistry(search_system=search_system)
        self._registry.discover()
        self.logger = Logger.get_logger("ToolManager")

    @classmethod
    def instance(cls, search_system: bool = False) -> "ToolManager":
        return cls(search_system=search_system)

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        try:
            return self._registry.get(tool_name)
        except ToolNotFoundError:
            return None

    def get_all_tools(self) -> Dict[str, BaseTool]:
        """Resolve every tool concurrently (see ``ToolRegistry.probe_all``)."""
        return {
            name: tool
            for name, tool in self._registry.probe_all().items()
            if tool is not None
        }

    def get_available_tools(self) -> Dict[str, BaseTool]:
        return self._registry.get_available_tools()

    def ensure_all_probed(self):
        """Warm every tool, reusing anything already resolved."""
        return self._registry.ensure_all_probed()

    @property
    def last_probe_ms(self) -> int:
        """Wall-clock duration of the last full probe (0 if none ran)."""
        return self._registry.last_probe_ms

    def refresh_tools(self):
        self._registry.refresh()

    def set_custom_path(self, name: str, path: str):
        return self._registry.set_custom_path(name, path)

    def reset_custom_path(self, name: str):
        return self._registry.reset_custom_path(name)

    def get_custom_paths(self):
        return self._registry.get_custom_paths()

    def _default_tool_path(self, key: str) -> str:
        return self._registry._default_tool_path(key)
