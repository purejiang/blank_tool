#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToolRegistry — lazy-loading tool registry with auto-discovery and dependency injection.
"""

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional, Any

from app.tools.descriptor_tool import DescriptorTool, load_descriptor
from app.env.registry import get_env_registry
from app.env.overrides_store import OverridesStore
from app.utils.logger import Logger
from app.utils.env import get_output_dir
from app.common.exceptions import ToolNotFoundError
from app.tools.bootstrap.plugins import bootstrap_shipped_plugins


class ToolRegistry:
    """Lazy-loading tool registry with dependency injection.

    Discovers descriptor-declared tools and instantiates them lazily on
    first access via get().  Plugin tools (shipped-native / native) are
    registered explicitly via :meth:`register_plugin_tool`.
    """

    def __init__(
        self,
        search_system: bool = False,
        registry_overlay_dir: Optional[str] = None,
    ):
        env_flag = os.environ.get("BT_SEARCH_SYSTEM_TOOLS") == "1"
        self.search_system = search_system or env_flag
        self.logger = Logger.get_logger("ToolRegistry")
        self._tools: Dict[str, Any] = {}
        self._custom_paths: Dict[str, str] = {}
        self._discovered: Dict[str, type] = {}
        self._descriptor_tools: Dict[str, DescriptorTool] = {}
        # Plugin tools (BuiltinTool/native plugin instances, NOT BaseTool) and
        # their kind metadata.  These are resident (registered explicitly, not
        # discovered) and survive refresh().
        self._plugin_tools: Dict[str, Any] = {}
        self._kinds: Dict[str, str] = {}
        self._discover_lock = threading.Lock()
        self._initialized = False
        # Writable registry overlay directory (user-imported descriptors + overrides)
        self._registry_overlay_dir: str = self._resolve_registry_overlay_dir(
            registry_overlay_dir
        )
        # Load persisted custom-path overrides (survive restarts)
        self._load_overrides()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, tool_package: str = 'app.tools'):
        """Auto-discover descriptor-declared tools.

        Scans bundled and overlay descriptor directories
        (``registry/tools/*.json``).  Code-class (``BaseTool`` subclass)
        discovery was removed — descriptors are the only discoverable code
        surface; plugin tools are registered explicitly via
        :meth:`register_plugin_tool`.
        """
        with self._discover_lock:
            if self._initialized:
                return
            self._initialized = True
            self._discover_descriptors()

    def _resolve_registry_overlay_dir(self, explicit: Optional[str]) -> str:
        """Return the writable registry overlay root directory.

        When *explicit* is given it is used as-is (test injection).
        Otherwise resolves ``<output_dir>/registry`` via :func:`get_output_dir`.
        """
        if explicit:
            return explicit
        return os.path.join(get_output_dir(), "registry")

    def _load_overrides(self) -> None:
        """Load custom-path overrides from ``<overlay>/overrides.json``.

        Missing file or malformed JSON is tolerated (no-op); the registry
        stays usable with empty overrides.
        """
        data = OverridesStore(self._registry_overlay_dir).load()
        paths = data.get("custom_paths")
        if isinstance(paths, dict):
            self._custom_paths = {str(k): str(v) for k, v in paths.items()}

    def _save_overrides(self) -> None:
        """Persist custom-path overrides to ``<overlay>/overrides.json``.

        The overlay root is created lazily (exist_ok=True) so absent-output-dir
        does not prevent discovery; only the first write materializes the dir.
        """
        data = {
            "custom_paths": dict(self._custom_paths),
        }
        OverridesStore(self._registry_overlay_dir).save(data)

    def _discover_descriptors(self) -> None:
        """Register tool descriptors from bundled and overlay directories.

        Scans the bundled ``cli/registry/tools/`` first, then the
        per-user overlay ``<output>/registry/tools/``.  Overlay
        descriptors win over same-named bundled ones (processed second).
        Descriptors also win over code-based classes.
        """
        bundled_dir = (
            Path(__file__).resolve().parent.parent.parent / "registry" / "tools"
        )
        overlay_dir = (
            Path(self._registry_overlay_dir) / "tools"
            if self._registry_overlay_dir
            else None
        )

        def _scan_descriptor_dir(
            dir_path: Path,
        ) -> None:
            """Load every ``*.json`` descriptor from *dir_path* into the registry."""
            if not dir_path.is_dir():
                return
            for file_path in sorted(dir_path.glob("*.json")):
                try:
                    descriptor = load_descriptor(str(file_path))
                except ValueError as exc:
                    self.logger.warning(
                        f"skipping malformed tool descriptor {file_path.name}: {exc}"
                    )
                    continue
                try:
                    tool = DescriptorTool(
                        descriptor, get_env_registry(), source_dir=str(dir_path)
                    )
                except Exception as exc:  # construction must not block discovery
                    self.logger.warning(
                        f"failed to construct descriptor tool {descriptor.name!r}: {exc}"
                    )
                    continue
                self._descriptor_tools[descriptor.name] = tool
                self._kinds[descriptor.name] = "descriptor"
                self.logger.info(f"Discovered tool (descriptor): {descriptor.name}")

        _scan_descriptor_dir(bundled_dir)
        if overlay_dir is not None:
            _scan_descriptor_dir(overlay_dir)

    # ------------------------------------------------------------------
    # Lazy access
    # ------------------------------------------------------------------

    def get(self, name: str) -> Any:
        """Lazy-instantiate and return a tool by name.

        Resolution priority (first match wins):
        1. instance cache ``self._tools``;
        2. plugin tools ``self._plugin_tools`` (resident BuiltinTool/native
           instances — a ``shipped-native`` builtin wins over a same-name
           descriptor/code tool);
        3. descriptor tools ``self._descriptor_tools`` (instantiated at
           discovery time);
        4. code classes ``self._discovered`` (lazy instantiation).
        Raises ToolNotFoundError if the tool was not found in any source.
        """
        if name in self._tools:
            return self._tools[name]

        plugin_tool = self._plugin_tools.get(name)
        if plugin_tool is not None:
            self._tools[name] = plugin_tool
            return plugin_tool

        descriptor_tool = self._descriptor_tools.get(name)
        if descriptor_tool is not None:
            self._tools[name] = descriptor_tool
            return descriptor_tool

        tool_cls = self._discovered.get(name)
        if not tool_cls:
            raise ToolNotFoundError(name)

        # Check for custom path override first
        custom_path = self._custom_paths.get(name)
        if custom_path:
            instance = tool_cls(name=name, path=custom_path, search_system=False)
            self._tools[name] = instance
            return instance

        default_path = self._default_tool_path(name)

        # Same construction logic as the original ToolManager for backward
        # compatibility with BaseTool subclasses.
        if self.search_system:
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

        self._tools[name] = instance
        return instance

    def list_all(self) -> list[str]:
        """Return names of all known tools (descriptors + plugin tools + code classes)."""
        return list(
            dict.fromkeys(
                list(self._descriptor_tools.keys())
                + list(self._plugin_tools.keys())
                + list(self._discovered.keys())
            )
        )

    def get_available_tools(self) -> Dict[str, Any]:
        """Return all tools that are currently valid/available."""
        result: Dict[str, Any] = {}
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

        Only ``self._tools`` (the instance cache) is cleared.  Plugin tools
        in ``self._plugin_tools`` are resident (registered explicitly by
        plugins) and MUST survive refresh so they are not lost on a tool
        re-scan.
        """
        self._tools.clear()

    # ------------------------------------------------------------------
    # Plugin tool registration (Wave 2)
    # ------------------------------------------------------------------

    _PLUGIN_TOOL_KINDS = frozenset({"shipped-native", "native"})

    def register_plugin_tool(self, name: str, tool: Any, kind: str) -> Any:
        """Register a plugin-provided tool instance under *name* with *kind*.

        Plugin tools are resident instances (``BuiltinTool`` or other native
        plugin objects — NOT ``BaseTool`` subclasses) registered explicitly
        by plugins, distinct from discovered code classes and descriptors.

        Args:
            name: unique tool identifier.
            tool: the tool instance to register.
            kind: one of ``"shipped-native"`` (bundled builtin, exempt from
                descriptor/code name-conflicts; ``get()`` priority makes it
                win) or ``"native"`` (plugin native tool, must not override
                a descriptor/code tool).

        Returns:
            The registered *tool* instance.

        Raises:
            ValueError: on an unknown *kind*, a duplicate plugin-tool name,
                or (for ``"native"``) a name conflict with a descriptor or
                discovered code tool.
        """
        if kind not in self._PLUGIN_TOOL_KINDS:
            raise ValueError(
                f"invalid plugin tool kind {kind!r}; must be one of "
                f"{sorted(self._PLUGIN_TOOL_KINDS)}"
            )

        if name in self._plugin_tools:
            raise ValueError(f"plugin tool {name!r} is already registered")

        if kind == "native" and (
            name in self._descriptor_tools or name in self._discovered
        ):
            raise ValueError(
                f"native plugin tool {name!r} conflicts with an existing "
                f"descriptor/code tool"
            )

        self._plugin_tools[name] = tool
        self._kinds[name] = kind
        return tool

    def unregister_plugin_tool(self, name: str) -> None:
        """Remove a plugin tool by *name*, re-resolving it on next get()."""
        self._plugin_tools.pop(name, None)
        self._kinds.pop(name, None)
        self._tools.pop(name, None)

    def get_kind(self, name: str) -> Optional[str]:
        """Return the kind of a registered plugin tool, or None if unknown."""
        return self._kinds.get(name)

    # ------------------------------------------------------------------
    # Custom path management
    # ------------------------------------------------------------------

    def set_custom_path(self, name: str, path: str) -> Dict[str, Any]:
        """Set a custom path for a tool, re-validate, and persist."""
        self._custom_paths[name] = path
        self._save_overrides()
        # Clear cached instance so next get() re-instantiates
        self._tools.pop(name, None)
        # Re-instantiate and validate
        tool = self.get(name)
        return {
            "name": name,
            "path": getattr(tool, "tool_path", ""),
            "is_valid": bool(getattr(tool, "is_valid", False)),
            "version": getattr(tool, "version", "") if getattr(tool, "is_valid", False) else "",
        }

    def reset_custom_path(self, name: str) -> Dict[str, Any]:
        """Reset a tool to its default path and persist."""
        self._custom_paths.pop(name, None)
        self._save_overrides()
        self._tools.pop(name, None)
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
    # Descriptor CRUD (T15)
    # ------------------------------------------------------------------

    def _overlay_tools_dir(self) -> Optional[Path]:
        """Return ``<overlay>/tools/``, or None when unresolvable."""
        if self._registry_overlay_dir:
            return Path(self._registry_overlay_dir) / "tools"
        return None

    # Script-type descriptor types that carry a script file alongside the JSON.
    _SCRIPT_TOOL_TYPES = frozenset({"python_script", "node_script", "shell_script"})

    def _overlay_scripts_dir(self) -> Optional[Path]:
        """Return ``<overlay>/scripts/``, or None when unresolvable."""
        if self._registry_overlay_dir:
            return Path(self._registry_overlay_dir) / "scripts"
        return None

    def _write_descriptor_file(self, descriptor_json: dict) -> str:
        """Validate *descriptor_json* and write it to the overlay tools/ dir.

        Does NOT re-discover — the caller decides when to rebuild the
        descriptor cache (single adds re-discover immediately; batch imports
        re-discover once at the end).

        For script-type tools (python_script / node_script / shell_script),
        when the ``path`` field references an existing local file, the file is
        copied into ``<overlay>/scripts/<tool_name>/<filename>`` and the
        descriptor's ``path`` is rewritten to the copied location so the tool
        stays usable even when the original source file is moved or deleted.

        Returns the validated descriptor's name.

        Raises:
            ValueError: if the dict fails ``load_descriptor`` validation.
            OSError: if the overlay file cannot be written.
        """
        overlay_tools = self._overlay_tools_dir()
        if overlay_tools is None:
            raise OSError("Cannot resolve overlay tools directory")
        overlay_tools.mkdir(parents=True, exist_ok=True)

        # ── Script type: copy the script file into the overlay ─────────
        tool_type = descriptor_json.get("type", "")
        if isinstance(tool_type, str) and tool_type in self._SCRIPT_TOOL_TYPES:
            script_path = descriptor_json.get("path", "")
            if isinstance(script_path, str) and os.path.isfile(script_path):
                tool_name = descriptor_json.get("name", "unknown")
                if not isinstance(tool_name, str) or not tool_name:
                    tool_name = "unknown"
                scripts_dir = self._overlay_scripts_dir()
                if scripts_dir is not None:
                    dest_dir = scripts_dir / tool_name
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_file = dest_dir / os.path.basename(script_path)
                    shutil.copy2(script_path, str(dest_file))
                    # Rewrite the path in the descriptor dict to the copied location
                    # so the descriptor JSON is self-contained.
                    descriptor_json = dict(descriptor_json)
                    descriptor_json["path"] = str(dest_file)

        # Validate via load_descriptor BEFORE writing (no partial files)
        import tempfile as _tempfile
        with _tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        ) as tmp:
            json.dump(descriptor_json, tmp)
            tmp_path = tmp.name
        try:
            descriptor = load_descriptor(tmp_path)
        finally:
            os.unlink(tmp_path)

        out_path = overlay_tools / f"{descriptor.name}.json"
        out_path.write_text(
            json.dumps(descriptor_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return descriptor.name

    def add_descriptor_file(self, descriptor_json: dict) -> DescriptorTool:
        """Validate *descriptor_json*, write it to the overlay tools/ dir,
        and re-discover so the new tool is immediately visible.

        Args:
            descriptor_json: a dict conforming to :class:`ToolDescriptor`.

        Returns:
            The constructed :class:`DescriptorTool`.

        Raises:
            ValueError: if the dict fails ``load_descriptor`` validation.
            OSError: if the overlay file cannot be written.
        """
        name = self._write_descriptor_file(descriptor_json)

        # Re-discover so the new tool is immediately visible
        self._rediscover_descriptors()

        tool = self._descriptor_tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool

    def import_descriptor_dir(self, dir_path: str) -> Dict[str, Any]:
        """Import every ``*.json`` descriptor in *dir_path* (two-phase).

        Phase 1 pre-validates every file with :func:`load_descriptor`; ANY
        failure aborts the whole import with zero writes (the failing entries
        carry ``status: "failed"`` + ``reason``, the valid ones are reported
        as ``status: "skipped"``).  Phase 2 writes each descriptor via
        :meth:`_write_descriptor_file` (script self-containment included) and
        re-discovers ONCE at the end.

        A tool that already had an overlay descriptor is reported as
        ``"updated"``, otherwise ``"added"``.  Post-import, a tool that is
        not ``is_valid`` gets non-blocking ``warnings`` (unresolved env
        deps, missing binary/script).

        Returns:
            ``{"ok": bool, "imported": int, "updated": int, "failed": int,
            "results": [{name, status, reason?, warnings?}, ...]}``; when
            *dir_path* is unusable a top-level ``"error"`` key is set.
        """
        empty = {"ok": False, "imported": 0, "updated": 0, "failed": 0,
                 "results": []}
        if not isinstance(dir_path, str) or not os.path.isdir(dir_path):
            return {**empty, "error": f"not a directory: {dir_path!r}"}

        files = sorted(
            f for f in os.listdir(dir_path)
            if f.endswith(".json")
            and os.path.isfile(os.path.join(dir_path, f))
        )
        if not files:
            return {**empty,
                    "error": f"no *.json descriptors found in {dir_path!r}"}

        # ── Phase 1: pre-validate everything, write nothing ────────────
        payloads = []  # (filename, raw_dict, descriptor_name)
        results = []
        precheck_failed = False
        for fname in files:
            fpath = os.path.join(dir_path, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if not isinstance(raw, dict):
                    raise ValueError("descriptor root must be an object")
                descriptor = load_descriptor(fpath)
                payloads.append((fname, raw, descriptor.name))
            except Exception as exc:
                results.append({
                    "name": fname[: -len(".json")],
                    "status": "failed",
                    "reason": f"{fname}: {exc}",
                })
                precheck_failed = True

        if precheck_failed:
            for _fname, _raw, name in payloads:
                results.append({
                    "name": name,
                    "status": "skipped",
                    "reason": "aborted: another descriptor failed validation",
                })
            results.sort(key=lambda r: r["name"])
            return {**empty, "failed": sum(
                1 for r in results if r["status"] == "failed"
            ), "results": results}

        # ── Phase 2: write all, re-discover once ───────────────────────
        written = []  # (name, had_overlay_before)
        for _fname, raw, name in payloads:
            had_overlay = self.is_overlay_descriptor(name)
            try:
                self._write_descriptor_file(raw)
                written.append((name, had_overlay))
            except Exception as exc:
                results.append({
                    "name": name, "status": "failed", "reason": str(exc),
                })

        self._rediscover_descriptors()

        for name, had_overlay in written:
            entry: Dict[str, Any] = {
                "name": name,
                "status": "updated" if had_overlay else "added",
            }
            tool = self._descriptor_tools.get(name)
            if tool is not None and not getattr(tool, "is_valid", False):
                warnings = []
                unresolved = [
                    dep for dep, binary
                    in getattr(tool, "_env_resolutions", {}).items()
                    if not binary
                ]
                if unresolved:
                    warnings.append(
                        f"env deps unresolved: {', '.join(unresolved)}"
                    )
                tool_path = getattr(tool, "tool_path", "")
                if not tool_path or not os.path.exists(tool_path):
                    warnings.append(
                        f"binary/script not found: {tool_path or '(unresolved)'}"
                    )
                if warnings:
                    entry["warnings"] = warnings
            results.append(entry)

        results.sort(key=lambda r: r["name"])
        failed = sum(1 for r in results if r["status"] == "failed")
        return {
            "ok": failed == 0,
            "imported": sum(1 for r in results if r["status"] == "added"),
            "updated": sum(1 for r in results if r["status"] == "updated"),
            "failed": failed,
            "results": results,
        }

    def delete_descriptor(self, name: str) -> None:
        """Remove the overlay descriptor file for *name* and re-discover.

        Raises:
            ValueError: if *name* has no overlay descriptor (bundled/code-only
                or unknown).
        """
        overlay_tools = self._overlay_tools_dir()
        if overlay_tools is None:
            raise ValueError(
                f"Cannot resolve overlay directory to delete {name!r}"
            )

        file_path = overlay_tools / f"{name}.json"
        if not file_path.exists():
            raise ValueError(
                f"Tool {name!r} is not an overlay descriptor "
                f"(bundled or code-based tools cannot be deleted)"
            )

        file_path.unlink()
        self._rediscover_descriptors()

    def is_overlay_descriptor(self, name: str) -> bool:
        """Return True when *name* has an overlay descriptor file on disk."""
        overlay_tools = self._overlay_tools_dir()
        if overlay_tools is None:
            return False
        return (overlay_tools / f"{name}.json").exists()

    def _rediscover_descriptors(self) -> None:
        """Clear descriptor tools and re-scan bundled + overlay dirs."""
        self._descriptor_tools.clear()
        # Drop stale descriptor kinds before re-scanning; native /
        # shipped-native plugin kinds are untouched.
        self._kinds = {
            name: kind
            for name, kind in self._kinds.items()
            if kind != "descriptor"
        }
        self._discover_descriptors()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _default_tool_path(self, key: str) -> str:
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
        # The engine now resolves tools exclusively via get_tool(), so the
        # shipped-native builtins must live in the shared registry — load them
        # here (headless CLI + tests construct ToolManager without cli/main.py's
        # bootstrap).  Runs once (guarded by _initialized).  The loading logic
        # lives in app.tools.bootstrap.plugins so plugin bootstrap is a single
        # extension point (and the import cycle with plugin context stays
        # deferred).
        bootstrap_shipped_plugins()

    @classmethod
    def instance(cls, search_system: bool = False) -> "ToolManager":
        return cls(search_system=search_system)

    def get_registry(self):
        """Return the shared :class:`ToolRegistry` backing this manager.

        Replaces the previously-private ``_registry`` attribute so callers no
        longer reach into ToolManager internals.
        """
        return self._registry

    def get_kind(self, name: str):
        """Return the kind of a registered tool, or None if unknown."""
        return self._registry.get_kind(name)

    def get_tool(self, tool_name: str) -> Optional[Any]:
        try:
            return self._registry.get(tool_name)
        except ToolNotFoundError:
            return None

    def get_all_tools(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for name in self._registry.list_all():
            try:
                result[name] = self._registry.get(name)
            except ToolNotFoundError:
                pass
        return result

    def get_available_tools(self) -> Dict[str, Any]:
        return self._registry.get_available_tools()

    def refresh_tools(self):
        self._registry.refresh()

    def set_custom_path(self, name: str, path: str):
        return self._registry.set_custom_path(name, path)

    def reset_custom_path(self, name: str):
        return self._registry.reset_custom_path(name)

    def get_custom_paths(self):
        return self._registry.get_custom_paths()

    # T15: descriptor CRUD delegates
    def add_tool_descriptor(self, descriptor_json: dict):
        return self._registry.add_descriptor_file(descriptor_json)

    def delete_tool_descriptor(self, name: str):
        return self._registry.delete_descriptor(name)

    def is_overlay_descriptor(self, name: str) -> bool:
        return self._registry.is_overlay_descriptor(name)

    def _default_tool_path(self, key: str) -> str:
        return self._registry._default_tool_path(key)
