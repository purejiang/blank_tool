
from app.utils.logger import Logger
from app.utils.env import ENV_APP_VERSION
from app.tools.tool_manager import ToolManager

logger = Logger.get_logger("AppHandler")
manager = ToolManager.instance()

def system_info(params, stream_handler):
    try:
        import platform
        info = {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
        }
        return _success({"system_info": info})
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        return _error(str(e))

def build_info(params, stream_handler):
    try:
        global manager
        names = ["adb", "aapt", "apktool"]
        versions = {}
        for name in names:
            tool = manager.get_tool(name)
            versions[f"{name}Version"] = getattr(tool, "version", "") if tool else ""
        payload = {"build_info": versions}
        # 尝试获取应用版本（开发环境）
        try:
            import json, os
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            pkg_path = os.path.join(root, "package.json")
            if os.path.exists(pkg_path):
                with open(pkg_path, "r", encoding="utf-8") as f:
                    pj = json.load(f)
                    v = pj.get("version")
                    if isinstance(v, str) and v:
                        payload["build_info"]["app_version"] = v
        except Exception:
            pass
        return _success(payload)
    except Exception as e:
        logger.error(f"获取构建信息失败: {e}")
        return _error(str(e))

def app_version(params, stream_handler):
    try:
        from app.utils.env import get_env
        version = get_env(ENV_APP_VERSION, "")
        return _success({"version": version})
    except Exception as e:
        logger.error(f"获取应用版本失败: {e}")
        return _error(str(e))
API_MAP = {
    "app.system": system_info,
    "app.build": build_info,
    "app.version": app_version
}