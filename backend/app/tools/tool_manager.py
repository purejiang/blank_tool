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
from typing import Dict, Optional

from app.tools.base_tool import BaseTool
from app.utils.logger import Logger
from app.utils.env import get_runtime_dir
from app.common.exceptions import ToolNotFoundError


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
        self._discovered: Dict[str, type] = {}
        self._discover_lock = threading.Lock()
        self._initialized = False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, tool_package: str = 'app.tools'):
        """Auto-discover BaseTool subclasses in the given package.

        Scans all modules in *tool_package* for classes that inherit from
        BaseTool (excluding BaseTool itself, CommandTool, and classes
        defined in base_tool.py).
        """
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
        """Clear cached instances so the next get() re-instantiates."""
        self._tools.clear()

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

    def _default_tool_path(self, key: str) -> str:
        return self._registry._default_tool_path(key)
