import os
import re
from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.utils.logger import Logger
from app.utils.env import get_output_dir

logger = Logger.get_logger("ApkHandler")
manager = ToolManager.instance()

def apk_analyze(params, stream_handler):
    # 支持 apk_path 或 file_path
    apk_path = params.get("apk_path")
    if not apk_path or not os.path.exists(apk_path):
        raise Exception(f"APK路径不存在: {apk_path}")

    try:
        aapt = manager.get_tool("aapt")
        if not aapt or not aapt.is_valid:
            raise Exception("未找到或无效的 aapt 工具")

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

        sdk_match = re.search(r"minSdkVersion:'([^']+)'", output)
        if sdk_match:
            info["min_sdk_version"] = sdk_match.group(1)

        target_sdk = re.search(r"targetSdkVersion:'([^']+)'", output)
        if target_sdk:
            info["target_sdk_version"] = target_sdk.group(1)

        permissions = re.findall(r"uses-permission(?:-sdk-23)?: name='([^']+)'", output)
        info["permissions"] = permissions

        return info
    except Exception as e:
        logger.error(f"分析APK失败: {e}")
        raise e


def apk_decompile(params, stream_handler):
    file_path = params.get("file_path")
    options = params.get("options", {})
    if not file_path or not os.path.exists(file_path):
        raise Exception("APK文件不存在")

    # Use unified output directory if not specified
    if not options.get("output_dir"):
         base_name = os.path.splitext(os.path.basename(file_path))[0]
         output_dir = os.path.join(get_output_dir(), "decompiled", base_name)
    else:
         output_dir = options.get("output_dir")

    try:
        apktool = manager.get_tool("apktool")
        if not apktool or not apktool.is_valid:
            raise Exception("未找到或无效的 apktool 工具")

        context = CommandExecutionContext(cwd=options.get("cwd"), timeout=600)
        result = apktool.execute(["d", file_path, "-f", "-o", output_dir], context)
        if result.get("returncode", 1) != 0:
            raise Exception(result.get("stderr", "反编译失败"))
        return {"output_dir": output_dir}
    except Exception as e:
        logger.error(f"反编译失败: {e}")
        raise e


def apk_recompile(params, stream_handler):
    project_path = params.get("project_path")
    options = params.get("options", {})
    if not project_path or not os.path.exists(project_path):
        raise Exception("项目路径不存在")

    # Use unified output directory if not specified
    if not options.get("output_apk"):
        base_name = os.path.basename(project_path)
        output_apk = os.path.join(get_output_dir(), "recompiled", f"{base_name}.apk")
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_apk), exist_ok=True)
    else:
        output_apk = options.get("output_apk")

    try:
        apktool = manager.get_tool("apktool")
        if not apktool or not apktool.is_valid:
            raise Exception("未找到或无效的 apktool 工具")

        context = CommandExecutionContext(cwd=options.get("cwd"))
        result = apktool.execute(["b", project_path, "-o", output_apk], context)
        if result.get("returncode", 1) != 0:
            raise Exception(result.get("stderr", "回编译失败"))

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
                
                if options.get("v2") is False:
                    args += ["--v2-signing-enabled", "false"]

                args += [output_apk]
                sr = apksigner.execute(args, CommandExecutionContext())
                if sr.get("returncode", 1) != 0:
                    raise Exception(sr.get("stderr", "签名失败"))

        return {"output_apk": output_apk}
    except Exception as e:
        logger.error(f"回编译失败: {e}")
        raise e


def apk_sign(params, stream_handler):
    apk_path = params.get("apk_path")
    keystore = params.get("keystore", {})
    options = params.get("options", {})
    if not apk_path or not os.path.exists(apk_path):
        raise Exception("APK路径不存在")
    if not keystore.get("path") or not keystore.get("alias"):
        raise Exception("缺少签名所需的 keystore 信息")

    try:
        apksigner = manager.get_tool("apksigner")
        if not apksigner or not apksigner.is_valid:
            raise Exception("未找到或无效的 apksigner 工具")

        # 生成输出路径，避免原地修改导致的文件占用问题
        dir_name = os.path.dirname(apk_path)
        base_name = os.path.basename(apk_path)
        name_without_ext = os.path.splitext(base_name)[0]
        # 使用 -signed 后缀，如果文件名已有 -signed 则不再重复添加（简单处理）
        if name_without_ext.endswith("-signed"):
             output_apk = os.path.join(dir_name, f"{name_without_ext}_new.apk")
        else:
             output_apk = os.path.join(dir_name, f"{name_without_ext}-signed.apk")

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
        
        # 指定输出文件
        args += ["--out", output_apk]
        args += [apk_path]

        context = CommandExecutionContext()
        result = apksigner.execute(args, context)
        if result.get("returncode", 1) != 0:
            raise Exception(result.get("stderr", "签名失败"))
        return {"apk_path": output_apk}
    except Exception as e:
        logger.error(f"签名失败: {e}")
        raise e

def apk_getinfo(params, stream_handler):
    # 与 analyze 类似，保留别名以兼容不同调用名
    return apk_analyze(params, stream_handler)


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
        return {"task_id": task_id, "progress": progress}
    except Exception as e:
        raise e


def apk_cancel_task(params, stream_handler):
    # 当前任务为同步执行，不支持取消，返回 warning
    task_id = params.get("task_id")
    return {"type": "warning", "payload": {"task_id": task_id, "message": "当前任务不可取消"}}


API_MAP = {
    "apk.analyze": apk_analyze,
    "apk.analyze_apk": apk_analyze,
    "apk.getInfo": apk_getinfo,
    "apk.decompile": apk_decompile,
    "apk.recompile": apk_recompile,
    "apk.sign": apk_sign,
    "apk.get_progress": apk_get_progress,
    "apk.getProgress": apk_get_progress,
    "apk.cancel_task": apk_cancel_task,
    "apk.cancelTask": apk_cancel_task,
}
