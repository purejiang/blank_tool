#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToolRegistry — lazy-loading tool registry with auto-discovery and dependency injection.
"""

import json
import os
import platform
import pkgutil
import importlib
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional, Any

from app.tools.base_tool import BaseTool
from app.tools.descriptor_tool import DescriptorTool, load_descriptor
from app.env.registry import get_env_registry
from app.env.overrides_store import OverridesStore
from app.utils.logger import Logger
from app.utils.env import get_output_dir, get_runtime_dir
from app.common.exceptions import ToolNotFoundError


class ToolRegistry:
    """Lazy-loading tool registry with dependency injection.

    Discovers BaseTool subclasses at import time but only instantiates
    them on first access via get().
    """

    def __init__(
        self,
        search_system: bool = False,
        registry_overlay_dir: Optional[str] = None,
    ):
        env_flag = os.environ.get("BT_SEARCH_SYSTEM_TOOLS") == "1"
        self.search_system = search_system or env_flag
        self.logger = Logger.get_logger("ToolRegistry")
        self._tools: Dict[str, BaseTool] = {}
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
        """Auto-discover code-based and descriptor-based tools.

        Scans all modules in *tool_package* for classes that inherit from
        BaseTool (excluding BaseTool itself, CommandTool, and classes
        defined in base_tool.py), then registers descriptor-declared tools
        from ``registry/tools/*.json`` (descriptors win over code classes).
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
        """Load custom-path and env overrides from ``<overlay>/overrides.json``.

        Missing file or malformed JSON is tolerated (no-op); the registry
        stays usable with empty overrides.
        """
        data = OverridesStore(self._registry_overlay_dir).load()
        paths = data.get("custom_paths")
        if isinstance(paths, dict):
            self._custom_paths = {str(k): str(v) for k, v in paths.items()}
        env_overrides = data.get("env_overrides")
        if isinstance(env_overrides, dict):
            self._env_overrides = {str(k): dict(v) for k, v in env_overrides.items() if isinstance(v, dict)}
        else:
            self._env_overrides = {}

    def _save_overrides(self) -> None:
        """Persist custom-path and env overrides to ``<overlay>/overrides.json``.

        The overlay root is created lazily (exist_ok=True) so absent-output-dir
        does not prevent discovery; only the first write materializes the dir.
        """
        data = {
            "custom_paths": dict(self._custom_paths),
            "env_overrides": dict(getattr(self, "_env_overrides", {})),
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
                self.logger.info(f"Discovered tool (descriptor): {descriptor.name}")

        _scan_descriptor_dir(bundled_dir)
        if overlay_dir is not None:
            _scan_descriptor_dir(overlay_dir)

    # ------------------------------------------------------------------
    # Lazy access
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseTool:
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

    def add_descriptor_file(self, descriptor_json: dict) -> DescriptorTool:
        """Validate *descriptor_json*, write it to the overlay tools/ dir,
        and re-discover so the new tool is immediately visible.

        For script-type tools (python_script / node_script / shell_script),
        when the ``path`` field references an existing local file, the file is
        copied into ``<overlay>/scripts/<tool_name>/<filename>`` and the
        descriptor's ``path`` is rewritten to the copied location so the tool
        stays usable even when the original source file is moved or deleted.

        Args:
            descriptor_json: a dict conforming to :class:`ToolDescriptor`.

        Returns:
            The constructed :class:`DescriptorTool`.

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

        # Re-discover so the new tool is immediately visible
        self._rediscover_descriptors()

        tool = self._descriptor_tools.get(descriptor.name)
        if tool is None:
            raise ToolNotFoundError(descriptor.name)
        return tool

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
        self._discover_descriptors()

    # ------------------------------------------------------------------
    # Environment overrides (T15)
    # ------------------------------------------------------------------

    def get_env_overrides(self) -> Dict[str, dict]:
        """Return all environment overrides."""
        return dict(getattr(self, "_env_overrides", {}))

    def set_env_override(self, name: str, overrides: dict) -> None:
        """Set or replace override dict for environment *name* and persist."""
        if not hasattr(self, "_env_overrides"):
            self._env_overrides: Dict[str, dict] = {}
        self._env_overrides[name] = dict(overrides)
        self._save_overrides()

    def reset_env_override(self, name: str) -> None:
        """Remove override dict for environment *name* and persist."""
        if hasattr(self, "_env_overrides") and name in self._env_overrides:
            del self._env_overrides[name]
            self._save_overrides()

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
        # bootstrap).  Runs once (guarded by _initialized).
        self._load_shipped_plugins()

    def _load_shipped_plugins(self) -> None:
        """Register the shipped-native builtin plugins into the shared registry.

        Deferred import avoids a top-level circular import (plugin context /
        loader import ToolManager).  A loader bug must NOT prevent ToolManager
        from constructing, so failures are logged, not raised.
        """
        try:
            from app.plugins.context import PluginContext
            from app.plugins.loader import SHIPPED_MANIFEST, load_plugins

            load_plugins(PluginContext(), manifest=SHIPPED_MANIFEST)
        except Exception:
            self.logger.warning(
                "failed to load shipped-native builtin plugins", exc_info=True
            )

    @classmethod
    def instance(cls, search_system: bool = False) -> "ToolManager":
        return cls(search_system=search_system)

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        try:
            return self._registry.get(tool_name)
        except ToolNotFoundError:
            return None

    def get_all_tools(self) -> Dict[str, BaseTool]:
        result: Dict[str, BaseTool] = {}
        for name in self._registry.list_all():
            try:
                result[name] = self._registry.get(name)
            except ToolNotFoundError:
                pass
        return result

    def get_available_tools(self) -> Dict[str, BaseTool]:
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

    # T15: env override delegates
    def get_env_overrides(self):
        return self._registry.get_env_overrides()

    def set_env_override(self, name: str, overrides: dict):
        return self._registry.set_env_override(name, overrides)

    def reset_env_override(self, name: str):
        return self._registry.reset_env_override(name)

    def _default_tool_path(self, key: str) -> str:
        return self._registry._default_tool_path(key)
