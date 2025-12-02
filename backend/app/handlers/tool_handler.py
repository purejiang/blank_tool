from app.tools.tool_manager import ToolManager
import os
import os.path
from app.utils.logger import Logger

logger = Logger.get_logger("ToolHandler")
manager = ToolManager.instance()


def _success(payload):
    return {"type": "success", "payload": payload}


def _error(message):
    return {"type": "error", "payload": {"message": message}}


def _source_for(manager: ToolManager, name: str, path: str):
    try:
        default_path = manager._default_tool_path(name)
        if path and default_path and os.path.abspath(path) == os.path.abspath(default_path):
            return "builtin"
        if path:
            return "system"
        return "none"
    except Exception:
        return "unknown"


def get_tools(params, stream_handler):
    tool_name = params.get("tool_name")
    refresh = bool(params.get("refresh", False))

    try:
        if refresh:
            manager.refresh_tools()
        if tool_name:
            tool = manager.get_tool(tool_name)
            if not tool:
                return _error("未找到该工具")
            info = {
                "name": tool_name,
                "is_valid": bool(getattr(tool, "is_valid", False)),
                "version": getattr(tool, "version", ""),
                "path": getattr(tool, "tool_path", "")
            }
            info["source"] = _source_for(manager, tool_name, info["path"]) 
            info["status"] = "available" if info["is_valid"] else "unavailable"
            return _success(info)
        names = ["adb", "apktool", "apksigner", "zipalign", "aapt", "bundletool", "jarsigner"]
        report = {}
        for name in names:
            tool = manager.get_tool(name)
            item = {
                "is_valid": bool(getattr(tool, "is_valid", False)) if tool else False,
                "version": getattr(tool, "version", "") if tool else "",
                "path": getattr(tool, "tool_path", "") if tool else ""
            }
            item["source"] = _source_for(manager, name, item["path"]) if tool else "none"
            item["status"] = "available" if item["is_valid"] else "unavailable"
            report[name] = item
        return _success(report)
    except Exception as e:
        logger.error(f"工具检查失败: {e}")
        return _error(str(e))


check_tool_availability = get_tools

def tool_version(params, stream_handler):
    try:
        global manager
        aapt = manager.get_tool("aapt")
        if not aapt or not aapt.is_valid:
            return _error("未找到或无效的 aapt 工具")
        return _success({"version": getattr(aapt, "version", "")})
    except Exception as e:
        logger.error(f"获取 aapt 版本失败: {e}")
        return _error(str(e))


def set_search_mode(params, stream_handler):
    try:
        enabled = bool(params.get("system_search", False))
        if enabled:
            os.environ["BT_SEARCH_SYSTEM_TOOLS"] = "1"
        else:
            if "BT_SEARCH_SYSTEM_TOOLS" in os.environ:
                del os.environ["BT_SEARCH_SYSTEM_TOOLS"]
        global manager
        manager.refresh_tools()
        return _success({"system_search": enabled})
    except Exception as e:
        logger.error(f"设置系统工具查找开关失败: {e}")
        return _error(str(e))


API_MAP = {
    "tool.check_tool_availability": get_tools,
    "tool.version": tool_version,
    "tool.get_tools": get_tools,
    "tool.set_search_mode": set_search_mode,
}

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
        import json, os
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        pkg_path = os.path.join(root, "package.json")
        version = ""
        if os.path.exists(pkg_path):
            with open(pkg_path, "r", encoding="utf-8") as f:
                pj = json.load(f)
                v = pj.get("version")
                if isinstance(v, str):
                    version = v
        return _success({"version": version})
    except Exception as e:
        logger.error(f"获取应用版本失败: {e}")
        return _error(str(e))

# 映射新增 API
API_MAP["system.info"] = system_info
API_MAP["build.info"] = build_info
API_MAP["app.version"] = app_version
