import importlib.util
import os
import sys
import threading
import traceback
from typing import Dict, Any, List, Optional
from app.utils.logger import Logger
from app.utils.env import get_plugins_root
from app.plugins.context import PluginContext


class PluginManager:
    """Discovers and runs external ``.py`` plugins.

    Two scan roots, user overrides builtin on name collision:
      * builtin: ``backend/app/plugins/builtin/`` — ships with the app
        (read-only in a packaged install).
      * user:   ``<localdata>/plugins`` (``BT_PLUGINS_DIR``) — drop a
        ``.py`` here and it shows up after ``plugin.reload``.

    A plugin module must export ``run(context, **params)`` and may
    declare ``DESCRIPTION / VERSION / AUTHOR`` plus an optional
    ``PARAMS`` list for frontend form rendering.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        # builtin dir = builtin/ next to this file (NOT the framework dir
        # itself — manager.py/context.py were once scanned as "plugins").
        self.builtin_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "builtin"
        )
        self.plugins_dir = self.builtin_dir  # legacy alias, tests may read it
        self.user_dir = get_plugins_root()
        self.plugins: Dict[str, Any] = {}
        self.logger = Logger.get_logger("PluginManager")
        self._scan_lock = threading.RLock()
        self._ensure_dirs()
        self.load_plugins()
        self._initialized = True

    @classmethod
    def instance(cls) -> "PluginManager":
        return cls()

    @property
    def scan_dirs(self) -> List[str]:
        # user dir FIRST: same-name user plugin overrides the builtin one
        return [self.user_dir, self.builtin_dir]

    def _ensure_dirs(self):
        for d in (self.builtin_dir, self.user_dir):
            if not os.path.exists(d):
                try:
                    os.makedirs(d)
                    self.logger.info(f"创建插件目录: {d}")
                except Exception as e:
                    self.logger.error(f"无法创建插件目录 {d}: {e}")

    def load_plugins(self):
        """(Re)load all plugins from every scan root."""
        self.logger.info("开始加载插件...")
        loaded: Dict[str, Any] = {}
        with self._scan_lock:
            for scan_dir in self.scan_dirs:
                if not os.path.isdir(scan_dir):
                    self.logger.warning(f"插件目录不存在: {scan_dir}")
                    continue
                for filename in sorted(os.listdir(scan_dir)):
                    if not filename.endswith(".py") or filename.startswith("__"):
                        continue
                    plugin_name = filename[:-3]
                    # scan_dirs is [user, builtin] — the first (user) hit
                    # wins; never let the builtin copy overwrite it
                    if plugin_name in loaded:
                        continue
                    self.load_plugin(plugin_name, scan_dir=scan_dir, into=loaded)
            self.plugins = loaded
        self.logger.info(f"插件加载完成，共加载 {len(self.plugins)} 个插件")

    def load_plugin(
        self,
        plugin_name: str,
        scan_dir: Optional[str] = None,
        into: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """加载指定插件（默认从 scan_dirs 顺序查找）"""
        target = into if into is not None else self.plugins
        try:
            file_path = None
            dirs = [scan_dir] if scan_dir else self.scan_dirs
            for d in dirs:
                cand = os.path.join(d, f"{plugin_name}.py")
                if os.path.isfile(cand):
                    file_path = cand
                    break
            if not file_path:
                self.logger.error(f"插件文件不存在: {plugin_name}")
                return False

            # unique module key so a user plugin and a builtin with the
            # same name never collide in sys.modules
            mod_key = f"bt_plugin_{plugin_name}"
            spec = importlib.util.spec_from_file_location(mod_key, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_key] = module
                spec.loader.exec_module(module)

                # 验证插件是否有效（必须包含 run 函数）
                if not hasattr(module, "run"):
                    self.logger.warning(f"插件 {plugin_name} 无效: 缺少 run 函数")
                    return False

                target[plugin_name] = module
                self.logger.info(f"已加载插件: {plugin_name} ({file_path})")
                return True
            return False
        except Exception:
            # a broken plugin must never take down the backend
            self.logger.error(f"加载插件 {plugin_name} 失败: {traceback.format_exc()}")
            return False

    def get_plugin(self, plugin_name: str) -> Any:
        with self._scan_lock:
            return self.plugins.get(plugin_name)

    def get_all_plugins(self) -> List[Dict[str, Any]]:
        """获取所有插件信息"""
        with self._scan_lock:
            items = list(self.plugins.items())
        result = []
        for name, module in items:
            info = {
                "name": name,
                "description": getattr(module, "DESCRIPTION", "无描述"),
                "version": getattr(module, "VERSION", "0.0.1"),
                "author": getattr(module, "AUTHOR", "Unknown"),
            }
            params = getattr(module, "PARAMS", None)
            if isinstance(params, list):
                info["params"] = params
            result.append(info)
        return result

    def run_plugin(self, plugin_name: str, params: Dict[str, Any], stream_handler: Optional[Any] = None) -> Any:
        """运行插件"""
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            raise Exception(f"插件 {plugin_name} 未找到")

        context = PluginContext(plugin_name, stream_handler)
        try:
            context.log(f"开始运行插件: {plugin_name}")
            # 调用插件的 run 函数
            result = plugin.run(context, **params)
            context.log(f"插件运行结束")
            return result
        except Exception as e:
            error_msg = f"插件运行出错: {str(e)}"
            context.error(error_msg)
            self.logger.error(f"运行插件 {plugin_name} 失败: {traceback.format_exc()}")
            raise e
