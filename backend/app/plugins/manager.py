import importlib.util
import os
import sys
import threading
import traceback
from typing import Dict, Any, List, Optional
from app.utils.logger import Logger
from app.plugins.context import PluginContext

class PluginManager:
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
        
        # 插件目录位于 backend/plugins
        self.plugins_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "plugins"))
        self.plugins: Dict[str, Any] = {}
        self.logger = Logger.get_logger("PluginManager")
        self._ensure_plugins_dir()
        self.load_plugins()
        self._initialized = True

    @classmethod
    def instance(cls) -> "PluginManager":
        return cls()

    def _ensure_plugins_dir(self):
        if not os.path.exists(self.plugins_dir):
            try:
                os.makedirs(self.plugins_dir)
                self.logger.info(f"创建插件目录: {self.plugins_dir}")
            except Exception as e:
                self.logger.error(f"无法创建插件目录: {e}")

    def load_plugins(self):
        """加载所有插件"""
        self.logger.info("开始加载插件...")
        self.plugins = {}
        
        if not os.path.exists(self.plugins_dir):
            self.logger.warning("插件目录不存在")
            return

        for filename in os.listdir(self.plugins_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                plugin_name = filename[:-3]
                self.load_plugin(plugin_name)
        
        self.logger.info(f"插件加载完成，共加载 {len(self.plugins)} 个插件")

    def load_plugin(self, plugin_name: str) -> bool:
        """加载指定插件"""
        try:
            file_path = os.path.join(self.plugins_dir, f"{plugin_name}.py")
            if not os.path.exists(file_path):
                self.logger.error(f"插件文件不存在: {file_path}")
                return False

            spec = importlib.util.spec_from_file_location(plugin_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[plugin_name] = module
                spec.loader.exec_module(module)
                
                # 验证插件是否有效（必须包含 run 函数）
                if not hasattr(module, "run"):
                    self.logger.warning(f"插件 {plugin_name} 无效: 缺少 run 函数")
                    return False
                
                self.plugins[plugin_name] = module
                self.logger.info(f"已加载插件: {plugin_name}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"加载插件 {plugin_name} 失败: {traceback.format_exc()}")
            return False

    def get_plugin(self, plugin_name: str) -> Any:
        return self.plugins.get(plugin_name)

    def get_all_plugins(self) -> List[Dict[str, Any]]:
        """获取所有插件信息"""
        result = []
        for name, module in self.plugins.items():
            info = {
                "name": name,
                "description": getattr(module, "DESCRIPTION", "无描述"),
                "version": getattr(module, "VERSION", "0.0.1"),
                "author": getattr(module, "AUTHOR", "Unknown")
            }
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
