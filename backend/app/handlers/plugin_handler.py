from app.plugins.manager import PluginManager
from app.utils.logger import Logger

logger = Logger.get_logger("PluginHandler")
manager = PluginManager.instance()

def list_plugins(params, stream_handler):
    """获取所有插件列表"""
    try:
        return manager.get_all_plugins()
    except Exception as e:
        logger.error(f"获取插件列表失败: {e}")
        raise e

def run_plugin(params, stream_handler):
    """运行指定插件"""
    plugin_name = params.get("name")
    plugin_params = params.get("params", {})
    
    if not plugin_name:
        raise Exception("未指定插件名称")
        
    try:
        return manager.run_plugin(plugin_name, plugin_params, stream_handler)
    except Exception as e:
        # 错误日志已经在 PluginManager 中记录
        raise e

def reload_plugins(params, stream_handler):
    """重新加载所有插件"""
    try:
        manager.load_plugins()
        return manager.get_all_plugins()
    except Exception as e:
        logger.error(f"重载插件失败: {e}")
        raise e

API_MAP = {
    "plugin.list": list_plugins,
    "plugin.run": run_plugin,
    "plugin.reload": reload_plugins
}
