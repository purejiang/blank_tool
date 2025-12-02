import os
import re
from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.utils.logger import Logger

logger = Logger.get_logger("ApkHandler")
manager = ToolManager.instance()


def _success(payload):
    return {"type": "success", "payload": payload}


def _error(message):
    return {"type": "error", "payload": {"message": message}}


def apk_analyze(params, stream_handler):
    apk_path = params.get("apk_path")
    if not apk_path or not os.path.exists(apk_path):
        return _error("APK路径不存在")

    try:
        aapt = manager.get_tool("aapt")
        if not aapt or not aapt.is_valid:
            return _error("未找到或无效的 aapt 工具")

        context = CommandExecutionContext()
        result = aapt.execute(["dump", "badging", apk_path], context)
        output = result.get("stdout", "")

        info = {}
        pkg_match = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", output)
        if pkg_match:
            info["package_name"] = pkg_match.group(1)
            info["version_code"] = pkg_match.group(2)
            info["version_name"] = pkg_match.group(3)

        app_label = re.search(r"application-label:'([^']+)'", output)
        if app_label:
            info["application_label"] = app_label.group(1)

        sdk_match = re.search(r"sdkVersion:'([^']+)'", output)
        if sdk_match:
            info["min_sdk_version"] = sdk_match.group(1)
        target_sdk = re.search(r"targetSdkVersion:'([^']+)'", output)
        if target_sdk:
            info["target_sdk_version"] = target_sdk.group(1)

        permissions = re.findall(r"uses-permission(?:-sdk-23)?: name='([^']+)'", output)
        info["permissions"] = permissions

        return _success(info)
    except Exception as e:
        logger.error(f"分析APK失败: {e}")
        return _error(str(e))


def apk_decompile(params, stream_handler):
    file_path = params.get("file_path")
    options = params.get("options", {})
    if not file_path or not os.path.exists(file_path):
        return _error("APK文件不存在")

    output_dir = options.get("output_dir") or os.path.splitext(file_path)[0] + "_decompiled"
    try:
        apktool = manager.get_tool("apktool")
        if not apktool or not apktool.is_valid:
            return _error("未找到或无效的 apktool 工具")

        context = CommandExecutionContext(cwd=options.get("cwd"))
        result = apktool.execute(["d", file_path, "-f", "-o", output_dir], context)
        if result.get("returncode", 1) != 0:
            return _error(result.get("stderr", "反编译失败"))
        return _success({"output_dir": output_dir})
    except Exception as e:
        logger.error(f"反编译失败: {e}")
        return _error(str(e))


def apk_recompile(params, stream_handler):
    project_path = params.get("project_path")
    options = params.get("options", {})
    if not project_path or not os.path.exists(project_path):
        return _error("项目路径不存在")

    output_apk = options.get("output_apk") or os.path.join(project_path, "dist", "recompiled.apk")
    try:
        apktool = manager.get_tool("apktool")
        if not apktool or not apktool.is_valid:
            return _error("未找到或无效的 apktool 工具")

        context = CommandExecutionContext(cwd=options.get("cwd"))
        result = apktool.execute(["b", project_path, "-o", output_apk], context)
        if result.get("returncode", 1) != 0:
            return _error(result.get("stderr", "回编译失败"))

        # 可选 zipalign 与签名
        if options.get("zipalign"):
            zipalign = manager.get_tool("zipalign")
            if zipalign and zipalign.is_valid:
                aligned_apk = output_apk.replace(".apk", "-aligned.apk")
                zr = zipalign.execute(["-f", "4", output_apk, aligned_apk], CommandExecutionContext())
                if zr.get("returncode", 1) == 0:
                    output_apk = aligned_apk

        if options.get("sign") and options.get("keystore"):
            keystore = options.get("keystore", {})
            apksigner = manager.get_tool("apksigner")
            if apksigner and apksigner.is_valid:
                args = [
                    "sign",
                    "--ks", keystore.get("path", ""),
                    "--ks-key-alias", keystore.get("alias", ""),
                    "--ks-pass", f"pass:{keystore.get('storepass', '')}",
                ]
                if keystore.get("keypass"):
                    args += ["--key-pass", f"pass:{keystore.get('keypass', '')}"]
                args += [output_apk]
                sr = apksigner.execute(args, CommandExecutionContext())
                if sr.get("returncode", 1) != 0:
                    return _error(sr.get("stderr", "签名失败"))

        return _success({"output_apk": output_apk})
    except Exception as e:
        logger.error(f"回编译失败: {e}")
        return _error(str(e))


def apk_sign(params, stream_handler):
    apk_path = params.get("apk_path")
    keystore = params.get("keystore", {})
    options = params.get("options", {})
    if not apk_path or not os.path.exists(apk_path):
        return _error("APK路径不存在")
    if not keystore.get("path") or not keystore.get("alias"):
        return _error("缺少签名所需的 keystore 信息")

    try:
        apksigner = manager.get_tool("apksigner")
        if not apksigner or not apksigner.is_valid:
            return _error("未找到或无效的 apksigner 工具")

        args = [
            "sign",
            "--ks", keystore.get("path", ""),
            "--ks-key-alias", keystore.get("alias", ""),
            "--ks-pass", f"pass:{keystore.get('storepass', '')}",
        ]
        if keystore.get("keypass"):
            args += ["--key-pass", f"pass:{keystore.get('keypass', '')}"]
        if options.get("v2") is False:
            args += ["--v2-signing-enabled", "false"]
        if options.get("v3") is False:
            args += ["--v3-signing-enabled", "false"]
        args += [apk_path]

        context = CommandExecutionContext()
        result = apksigner.execute(args, context)
        if result.get("returncode", 1) != 0:
            return _error(result.get("stderr", "签名失败"))
        return _success({"apk_path": apk_path})
    except Exception as e:
        logger.error(f"签名失败: {e}")
        return _error(str(e))


def apk_getinfo(params, stream_handler):
    # 与 analyze 类似，保留别名以兼容不同调用名
    return apk_analyze(params, stream_handler)


def apk_extract_resources(params, stream_handler):
    apk_path = params.get("apk_path")
    output_dir = params.get("output_dir")
    if not apk_path or not os.path.exists(apk_path):
        return _error("APK路径不存在")
    out_dir = output_dir or os.path.splitext(apk_path)[0] + "_resources"
    try:
        apktool = manager.get_tool("apktool")
        if not apktool or not apktool.is_valid:
            return _error("未找到或无效的 apktool 工具")
        # -r 仅资源，不反编译 smali
        context = CommandExecutionContext()
        result = apktool.execute(["d", "-r", apk_path, "-f", "-o", out_dir], context)
        if result.get("returncode", 1) != 0:
            return _error(result.get("stderr", "资源提取失败"))
        return _success({"output_dir": out_dir})
    except Exception as e:
        logger.error(f"资源提取失败: {e}")
        return _error(str(e))


def apk_get_progress(params, stream_handler):
    # 最小可用：若指定输出存在，则认为完成
    task_id = params.get("task_id")
    output_dir = params.get("output_dir")
    output_apk = params.get("output_apk")
    progress = 0
    try:
        if output_dir and os.path.exists(output_dir):
            progress = 100
        if output_apk and os.path.exists(output_apk):
            progress = 100
        return _success({"task_id": task_id, "progress": progress})
    except Exception as e:
        return _error(str(e))


def apk_cancel_task(params, stream_handler):
    # 当前任务为同步执行，不支持取消，返回 warning
    task_id = params.get("task_id")
    return {"type": "warning", "payload": {"task_id": task_id, "message": "当前任务不可取消"}}


API_MAP = {
    "apk.analyze": apk_analyze,
    "apk.analyze_apk": apk_analyze,
    "apk.getInfo": apk_getinfo,
    "apk.extract_resources": apk_extract_resources,
    "apk.extractResources": apk_extract_resources,
    "apk.decompile": apk_decompile,
    "apk.recompile": apk_recompile,
    "apk.sign": apk_sign,
    "apk.get_progress": apk_get_progress,
    "apk.getProgress": apk_get_progress,
    "apk.cancel_task": apk_cancel_task,
    "apk.cancelTask": apk_cancel_task,
}
