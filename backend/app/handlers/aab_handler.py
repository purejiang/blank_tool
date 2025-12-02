import os
from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.utils.logger import Logger

logger = Logger.get_logger("AabHandler")
manager = ToolManager.instance()


def _success(payload):
    return {"type": "success", "payload": payload}


def _error(message):
    return {"type": "error", "payload": {"message": message}}


def aab_sign(params, stream_handler):
    aab_path = params.get("aab_path")
    keystore = params.get("keystore", {})
    if not aab_path or not os.path.exists(aab_path):
        return _error("AAB 路径不存在")
    if not keystore.get("path") or not keystore.get("alias"):
        return _error("缺少签名所需的 keystore 信息")

    try:
        jarsigner = manager.get_tool("jarsigner")
        if not jarsigner or not jarsigner.is_valid:
            return _error("未找到或无效的 jarsigner 工具")

        args = [
            "-keystore", keystore.get("path", ""),
            "-storepass", keystore.get("storepass", ""),
        ]
        if keystore.get("keypass"):
            args += ["-keypass", keystore.get("keypass", "")]
        args += [aab_path, keystore.get("alias", "")]

        context = CommandExecutionContext()
        result = jarsigner.execute([jarsigner.tool_path] + args, context)
        if result.get("returncode", 1) != 0:
            return _error(result.get("stderr", "签名失败"))
        return _success({"aab_path": aab_path})
    except Exception as e:
        logger.error(f"AAB 签名失败: {e}")
        return _error(str(e))


def convert_aab_to_apks(params, stream_handler):
    aab_path = params.get("aab_path")
    output_path = params.get("output_path") or (os.path.splitext(aab_path)[0] + ".apks")
    keystore = params.get("keystore", {})
    device_id = params.get("device_id")

    if not aab_path or not os.path.exists(aab_path):
        return _error("AAB 路径不存在")

    try:
        bundletool = manager.get_tool("bundletool")
        if not bundletool or not bundletool.is_valid:
            return _error("未找到或无效的 bundletool 工具")

        args = [
            "build-apks",
            "--bundle", aab_path,
            "--output", output_path,
        ]
        if device_id:
            args += ["--device-id", device_id]
        if keystore.get("path"):
            args += [
                "--ks", keystore.get("path", ""),
                "--ks-key-alias", keystore.get("alias", ""),
                "--ks-pass", f"pass:{keystore.get('storepass', '')}",
            ]
            if keystore.get("keypass"):
                args += ["--key-pass", f"pass:{keystore.get('keypass', '')}"]

        context = CommandExecutionContext()
        java = bundletool.get_java_path()
        if not java or not os.path.exists(java):
            return _error("未找到或无效的 Java 运行环境")
        result = bundletool.execute([java, "-jar", bundletool.tool_path] + args, context)
        if result.get("returncode", 1) != 0:
            return _error(result.get("stderr", "转换失败"))
        return _success({"apks_path": output_path})
    except Exception as e:
        logger.error(f"AAB 转换为 APKS 失败: {e}")
        return _error(str(e))


def install_aab(params, stream_handler):
    # 组合操作：先转换为 APKS，再安装到设备
    aab_path = params.get("aab_path")
    device_id = params.get("device_id")
    output_path = params.get("output_path")
    keystore = params.get("keystore", {})

    if not aab_path:
        return _error("缺少 aab_path")
    if not device_id:
        return _error("缺少 device_id")

    # 先转换
    convert_result = convert_aab_to_apks({
        "aab_path": aab_path,
        "output_path": output_path,
        "device_id": device_id,
        "keystore": keystore
    }, stream_handler)

    if convert_result.get("type") != "success":
        return convert_result

    apks_path = convert_result.get("payload", {}).get("apks_path")
    if not apks_path:
        return _error("转换后未得到 APKS 路径")

    # 再安装
    try:
        bundletool = manager.get_tool("bundletool")
        if not bundletool or not bundletool.is_valid:
            return _error("未找到或无效的 bundletool 工具")
        context = CommandExecutionContext()
        java = bundletool.get_java_path()
        if not java or not os.path.exists(java):
            return _error("未找到或无效的 Java 运行环境")
        result = bundletool.execute([java, "-jar", bundletool.tool_path, "install-apks", "--apks", apks_path, "--device-id", device_id], context)
        if result.get("returncode", 1) != 0:
            return _error(result.get("stderr", "安装失败"))
        return _success({"device_id": device_id, "apks_path": apks_path})
    except Exception as e:
        logger.error(f"安装 AAB 失败: {e}")
        return _error(str(e))


API_MAP = {
    "aab.sign": aab_sign,
    "device.convert_aab_to_apks": convert_aab_to_apks,
    "device.install_aab": install_aab,
}
