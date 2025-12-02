import os
from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.utils.logger import Logger

logger = Logger.get_logger("InstallHandler")
manager = ToolManager.instance()


def _success(payload):
    return {"type": "success", "payload": payload}


def _error(message):
    return {"type": "error", "payload": {"message": message}}


def device_install_apk(params, stream_handler):
    apk_path = params.get("apk_path")
    device_id = params.get("device_id")
    if not apk_path:
        return _error("缺少 apk_path")
    if not device_id:
        return _error("缺少 device_id")
    if not os.path.exists(apk_path):
        return _error(f"APK 文件不存在: {apk_path}")

    try:
        adb = manager.get_tool("adb")
        if not adb or not adb.is_valid or not os.path.exists(adb.tool_path):
            return _error("未找到或无效的 adb 工具")
        context = CommandExecutionContext()
        result = adb.execute([adb.tool_path, "-s", device_id, "install", "-r", apk_path], context)
        success = result.get("returncode", 1) == 0
        if not success:
            return _error(result.get("stderr", "安装失败"))
        return _success({"device_id": device_id, "apk_path": apk_path})
    except Exception as e:
        logger.error(f"安装APK失败: {e}")
        return _error(str(e))


def device_install_apks(params, stream_handler):
    apks_path = params.get("apks_path")
    device_id = params.get("device_id")
    if not apks_path:
        return _error("缺少 apks_path")
    if not device_id:
        return _error("缺少 device_id")
    if not os.path.exists(apks_path):
        return _error(f"APKS 文件不存在: {apks_path}")

    try:
        bundletool = manager.get_tool("bundletool")
        if not bundletool or not bundletool.is_valid or not os.path.exists(bundletool.tool_path):
            return _error("未找到或无效的 bundletool 工具")
        context = CommandExecutionContext()
        java = bundletool.get_java_path()
        if not java or not os.path.exists(java):
            return _error("未找到或无效的 Java 运行环境")
        result = bundletool.execute([java, "-jar", bundletool.tool_path, "install-apks", "--apks", apks_path, "--device-id", device_id], context)
        success = result.get("returncode", 1) == 0
        if not success:
            return _error(result.get("stderr", "安装APKS失败"))
        return _success({"device_id": device_id, "apks_path": apks_path})
    except Exception as e:
        logger.error(f"安装APKS失败: {e}")
        return _error(str(e))


API_MAP = {
    "device.install_apk": device_install_apk,
    "device.install_apks": device_install_apks,
}
