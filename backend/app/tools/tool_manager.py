import os
import platform
import pkgutil
import importlib
import threading
from typing import Dict, Optional
from app.tools.base_tool import BaseTool
from app.utils.logger import Logger
from app.utils.env import get_runtime_dir

class ToolManager:
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
        env_flag = os.environ.get("BT_SEARCH_SYSTEM_TOOLS") == "1"
        self.search_system = search_system or env_flag
        self.logger = Logger.get_logger("ToolManager")
        self.tools: Optional[Dict[str, BaseTool]] = None
        self._discover_lock = threading.Lock()
        self._initialized = True

    @classmethod
    def instance(cls, search_system: bool = False) -> "ToolManager":
        return cls(search_system=search_system)

    def _discover_tools(self) -> Dict[str, BaseTool]:
        tools: Dict[str, BaseTool] = {}
        package = importlib.import_module('app.tools')
        for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
            module = importlib.import_module(name)
            for attribute_name in dir(module):
                attribute = getattr(module, attribute_name)
                if (
                    isinstance(attribute, type)
                    and issubclass(attribute, BaseTool)
                    and attribute is not BaseTool
                    and attribute.__name__ != "CommandTool"
                    and attribute.__module__ != "app.tools.base_tool"
                ):
                    key = self._canonical_tool_name(attribute.__name__)
                    default_path = self._default_tool_path(key)
                    self.logger.info(f"发现工具: {attribute.__name__}: {default_path}")

                    # 当 search_system 为 True 时，优先从系统查找
                    if self.search_system:
                        instance = attribute(search_system=True)
                        if not getattr(instance, "is_valid", False):
                            if default_path and os.path.exists(default_path):
                                instance = attribute(path=default_path, search_system=True)
                            else:
                                instance = attribute(search_system=True)
                    else:
                        # 默认优先使用内置路径
                        if default_path and os.path.exists(default_path):
                            instance = attribute(path=default_path, search_system=False)
                        else:
                            instance = attribute(search_system=False)
                        # 内置不可用时，回退到系统查找
                        if not getattr(instance, "is_valid", False):
                            instance = attribute(search_system=True)

                    tools[key] = instance
        return tools

    def get_tool(self, tool_name: str):
        self._ensure_discovered()
        return self.tools.get(tool_name) if self.tools else None

    def get_all_tools(self):
        self._ensure_discovered()
        return self.tools or {}

    def get_available_tools(self) -> Dict[str, BaseTool]:
        self._ensure_discovered()
        return {k: v for k, v in (self.tools or {}).items() if getattr(v, "is_valid", False)}

    def refresh_tools(self):
        self.tools = None
        self._ensure_discovered()

    def _canonical_tool_name(self, class_name: str) -> str:
        base = class_name.lower()
        return base

    def _tools_base_dir(self) -> str:
        # 优先使用环境变量中传入的 BT_RUNTIME_DIR
        runtime_dir = get_runtime_dir()
        if runtime_dir and os.path.exists(runtime_dir):
            return runtime_dir
            
        # 如果没有配置环境变量，或者路径不存在，直接抛出异常
        raise RuntimeError(
            f"Environment variable 'BT_RUNTIME_DIR' is missing or invalid: {runtime_dir}. "
            "Please configure the runtime path in application settings."
        )

    def _default_tool_path(self, key: str) -> str:
        base = self._tools_base_dir()
        is_windows = platform.system() == "Windows"
        if key == "adb":
            return os.path.join(base, "adb", "adb.exe" if is_windows else "adb")
        if key == "aapt":
            return os.path.join(base, "aapt", "aapt2.exe" if is_windows else "aapt")
        if key == "apktool":
            return os.path.join(base, "apktool", "apktool.jar")
        if key == "bundletool":
            return os.path.join(base, "bundletool", "bundletool.jar")
        if key == "zipalign":
            return os.path.join(base, "android", "zipalign.exe" if is_windows else "zipalign")
        if key == "apksigner":
            return os.path.join(base, "android", "apksigner.jar" if is_windows else "apksigner")
        if key == "jarsigner":
            return os.path.join(base, "jre", "bin", "jarsigner.exe" if is_windows else "jarsigner")
        return ""

    def _ensure_discovered(self):
        if self.tools is not None:
            return
        with self._discover_lock:
            if self.tools is None:
                self.tools = self._discover_tools()
