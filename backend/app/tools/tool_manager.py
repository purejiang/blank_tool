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
from pathlib import Path
from typing import Dict, Optional, Any

from app.tools.base_tool import BaseTool
from app.tools.descriptor_tool import DescriptorTool, load_descriptor
from app.env.registry import EnvironmentRegistry
from app.utils.logger import Logger
from app.utils.env import get_runtime_dir
from app.common.exceptions import ToolNotFoundError


# ------------------------------------------------------------------
# Environment registry singleton (module-level lazy, like app.utils.env)
# ------------------------------------------------------------------

_env_registry: Optional[EnvironmentRegistry] = None
_env_registry_lock = threading.Lock()


def _get_env_registry() -> EnvironmentRegistry:
    """Return the process-wide EnvironmentRegistry, discovering on first use."""
    global _env_registry
    if _env_registry is None:
        with _env_registry_lock:
            if _env_registry is None:
                registry = EnvironmentRegistry()
                registry.discover()
                _env_registry = registry
    return _env_registry


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
        self._descriptor_tools: Dict[str, DescriptorTool] = {}
        self._discover_lock = threading.Lock()
        self._initialized = False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, tool_package: str = 'app.tools'):
        """Auto-discover code-based and descriptor-based tools.

        Scans all modules in *tool_package* for classes that inherit from
        BaseTool (excluding BaseTool itself, CommandTool, and classes
        defined in base_tool.py), then registers descriptor-declared tools
        from ``registry/tools/*.json`` (descriptors win over code classes,
        except for names in ``_CODE_PRIORITY_NAMES``).
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

    # Tool names whose code-based class wins over the descriptor.
    _CODE_PRIORITY_NAMES = frozenset(set())

    def _discover_descriptors(self) -> None:
        """Register pre-installed tools declared by registry/tools/*.json.

        Descriptors win over code-based classes (registered after the
        pkgutil scan, they shadow same-named entries), except for names in
        ``_CODE_PRIORITY_NAMES`` where the code class stays primary.
        """
        descriptor_dir = (
            Path(__file__).resolve().parent.parent.parent / "registry" / "tools"
        )
        if not descriptor_dir.is_dir():
            return
        for file_path in sorted(descriptor_dir.glob("*.json")):
            try:
                descriptor = load_descriptor(str(file_path))
            except ValueError as exc:
                self.logger.warning(
                    f"skipping malformed tool descriptor {file_path.name}: {exc}"
                )
                continue
            if descriptor.name in self._CODE_PRIORITY_NAMES:
                self.logger.info(
                    f"Descriptor {descriptor.name!r} shadowed by code class"
                )
                continue
            try:
                tool = DescriptorTool(descriptor, _get_env_registry())
            except Exception as exc:  # construction must not block discovery
                self.logger.warning(
                    f"failed to construct descriptor tool {descriptor.name!r}: {exc}"
                )
                continue
            self._descriptor_tools[descriptor.name] = tool
            self.logger.info(f"Discovered tool (descriptor): {descriptor.name}")

    # ------------------------------------------------------------------
    # Lazy access
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseTool:
        """Lazy-instantiate and return a tool by name.

        Descriptor-declared tools win over code-based classes (they are
        instantiated at discovery time and returned directly); anything else
        falls through to the lazy code-class path. Raises
        ToolNotFoundError if the tool class was not discovered.
        """
        if name in self._tools:
            return self._tools[name]

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
        """Return names of all discovered tools (code classes + descriptors)."""
        return list(
            dict.fromkeys(
                list(self._discovered.keys()) + list(self._descriptor_tools.keys())
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
        """Clear cached instances so the next get() re-instantiates."""
        self._tools.clear()

    # ------------------------------------------------------------------
    # Custom path management
    # ------------------------------------------------------------------

    def set_custom_path(self, name: str, path: str) -> Dict[str, Any]:
        """Set a custom path for a tool and re-validate it."""
        self._custom_paths[name] = path
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
        """Reset a tool to its default path."""
        self._custom_paths.pop(name, None)
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

    def _default_tool_path(self, key: str) -> str:
        return self._registry._default_tool_path(key)
