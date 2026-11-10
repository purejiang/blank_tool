#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AAB analysis, signing, conversion, and installation handlers.
"""

import os
import re
import zipfile
from typing import Any, Callable, Dict

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.task_manager import TaskManager
from app.common.decorators import streaming, logs_errors
from app.common.exceptions import ToolNotFoundError, ToolException, error_payload
from app.utils.logger import Logger
from app.utils.task_log_writer import append_task_log
from app.utils.file_utils import get_file_hash
from app.utils.apk_inspector import (
    check_16kb_page_support,
    compare_so_across_arches,
    parse_bundle_config,
)

logger = Logger.get_logger("AabHandler")
manager = ToolManager.instance()


def _parse_bundle_manifest(xml_text: str) -> Dict:
    """
    从 ``bundletool dump manifest`` 输出的 XML 文本中提取基本信息。

    bundletool 会把 AAB 内 protobuf 形式的 AndroidManifest.xml 打印成普通 XML：
    ``<manifest xmlns:android="..." android:versionCode="42" package="com.x">``
    ``  <uses-sdk android:minSdkVersion="24" .../>``
    ``  <uses-permission android:name="android.permission.INTERNET"/>``
    ``  <application android:label="App"/>``

    Returns:
        可并入分析 payload 的字段（package_name / version_code / version_name /
        min_sdk_version / target_sdk_version / permissions / application_label）。
    """
    info: Dict[str, Any] = {}
    if not xml_text:
        return info

    def _manifest_attr(name: str) -> str:
        m = re.search(
            r'<manifest\b[^>]*?\b(?:android:)?' + re.escape(name) + r'="([^"]*)"',
            xml_text,
        )
        return m.group(1) if m else ""

    package = _manifest_attr('package')
    if package:
        info["package_name"] = package
    version_code = _manifest_attr('versionCode')
    if version_code:
        info["version_code"] = version_code
    version_name = _manifest_attr('versionName')
    if version_name:
        info["version_name"] = version_name

    m = re.search(r'\bminSdkVersion="([^"]+)"', xml_text)
    if m:
        info["min_sdk_version"] = m.group(1)
    m = re.search(r'\btargetSdkVersion="([^"]+)"', xml_text)
    if m:
        info["target_sdk_version"] = m.group(1)

    info["permissions"] = re.findall(
        r'<uses-permission\b[^>]*?\b(?:android:)?name="([^"]+)"', xml_text
    )

    m = re.search(
        r'<application\b[^>]*?\b(?:android:)?label="([^"]*)"', xml_text
    )
    if m and m.group(1) and not m.group(1).startswith('@'):
        info["application_label"] = m.group(1)
    return info


def _scan_aab_native_libs(aab_path: str) -> Dict:
    """按 ABI 分组枚举 AAB 中的 ``<module>/lib/<abi>/*.so``（跨模块合并）。"""
    so_map: Dict[str, list] = {}
    try:
        with zipfile.ZipFile(aab_path, 'r') as zf:
            for name in zf.namelist():
                if not name.endswith('.so'):
                    continue
                parts = name.split('/')
                if len(parts) < 4 or parts[1] != 'lib':
                    continue
                abi, so_file = parts[2], parts[-1]
                so_map.setdefault(abi, []).append(so_file)
    except Exception:
        logger.warning("Failed to enumerate AAB native libs: %s", aab_path, exc_info=True)
    for abi in so_map:
        so_map[abi] = sorted(set(so_map[abi]))
    return so_map


@streaming
@logs_errors("AabHandler")
def aab_analyze(params, stream_handler):
    """
    分析 AAB 基础信息 + 16KB 兼容性。

    与 APK 分析不同，AAB 的 manifest 是 protobuf 格式，且本身不做 zipalign，
    因此这里通过 bundletool 读取：
    - ``bundletool dump manifest`` → 包名/版本/SDK/权限等基本信息；
    - ``bundletool dump config`` → BundleConfig 中未压缩原生库开关与对齐
      （PAGE_ALIGNMENT_16K / 4K / 64K）；
    原生库 ELF 段仍由纯 Python 解析（``<module>/lib/<abi>/*.so``）。
    """
    aab_path = params.get("aab_path") or params.get("file_path")
    if not aab_path or not os.path.exists(aab_path):
        raise ToolException(f"AAB path does not exist: {aab_path}")

    task_id = _get_aab_task_id(params) or str(params.get("task_id", ""))
    task_manager = TaskManager()
    process_holder: dict = {}
    if task_id:
        task_manager.register(task_id, process_holder)

    try:
        bundletool = manager.get_tool("bundletool")
        if not bundletool or not bundletool.is_valid:
            raise ToolNotFoundError("bundletool")
        java = bundletool.get_java_path()
        if not java or not os.path.exists(java):
            raise ToolException("Java runtime not found or invalid")

        context = CommandExecutionContext(
            task_id=task_id, process_holder=process_holder, log_output=False
        )
        info: Dict[str, Any] = {
            "is_bundle": True,
            "warnings": [],
            "app_icon": "-",
            "permissions": [],
        }

        def _log(line: str) -> None:
            if task_id:
                append_task_log(task_id, line)
            if stream_handler:
                stream_handler({"type": "log", "task_id": task_id, "line": line})

        def _cancelled() -> bool:
            return bool(task_id and task_manager.is_cancelled(task_id))

        _log("[AAB Analysis] Reading bundle config...")
        result = bundletool.execute(
            [java, "-jar", bundletool.tool_path, "dump", "config", "--bundle", aab_path],
            context,
        )
        if _cancelled():
            if stream_handler:
                stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return
        bundle_config = parse_bundle_config((result or {}).get("stdout", ""))
        if (result or {}).get("returncode", 1) != 0:
            info["warnings"].append("bundletool dump config failed")

        _log("[AAB Analysis] Reading manifest...")
        result = bundletool.execute(
            [java, "-jar", bundletool.tool_path, "dump", "manifest", "--bundle", aab_path],
            context,
        )
        if _cancelled():
            if stream_handler:
                stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return
        if (result or {}).get("returncode", 1) == 0:
            info.update(_parse_bundle_manifest((result or {}).get("stdout", "")))
        else:
            info["warnings"].append("bundletool dump manifest failed")

        _log("[16KB Page Check] Starting...")
        info["page_size_16kb"] = check_16kb_page_support(
            aab_path, container='aab', bundle_config=bundle_config
        )

        so_map = _scan_aab_native_libs(aab_path)
        info["native_so_detail"] = so_map
        if so_map:
            info["so_comparison"] = compare_so_across_arches(so_map)
            info["native_libs"] = sorted(so_map.keys())
        else:
            info["native_libs"] = []

        info["file_size"] = os.path.getsize(aab_path)
        try:
            info["file_md5"] = get_file_hash(aab_path, "md5") or "-"
        except Exception:
            info["file_md5"] = "-"
            info["warnings"].append("File MD5 failed")

        p16 = info["page_size_16kb"]
        if task_id:
            append_task_log(
                task_id,
                f"[AAB_ANALYZE] package={info.get('package_name', '-')} "
                f"version={info.get('version_name', '-')} "
                f"abis={info.get('native_libs', [])}",
            )
            append_task_log(
                task_id,
                f"[AAB_16KB] supported={p16.get('supported')} "
                f"gate_ok={p16.get('gate_ok')} "
                f"relro_risk={len(p16.get('relro_risk') or [])} "
                f"relro_unknown={len(p16.get('relro_unknown') or [])} "
                f"no_64bit_native={p16.get('no_64bit_native')} "
                f"alignment={(p16.get('bundle') or {}).get('alignment')} "
                f"source={(p16.get('bundle') or {}).get('alignment_source')} "
                f"uncompress={(p16.get('bundle') or {}).get('uncompress_enabled')} "
                f"bundle_ok={(p16.get('bundle') or {}).get('ok')} "
                f"applied={(p16.get('bundle') or {}).get('applied')}",
            )

        if stream_handler:
            stream_handler({"type": "complete", "payload": info})
        return info
    except ToolException as exc:
        logger.error("AAB analysis tool error: %s", exc)
        if stream_handler:
            stream_handler(error_payload(exc))
    except Exception as exc:
        if task_id and task_manager.is_cancelled(task_id):
            if stream_handler:
                stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
        else:
            logger.error("AAB analysis failed: %s", exc, exc_info=True)
            if stream_handler:
                stream_handler(error_payload(exc))
    finally:
        if task_id:
            task_manager.unregister(task_id)


def _get_aab_task_id(params: dict) -> str:
    """Extract task_id from AAB handler params."""
    return str(
        params.get("task_id") or
        params.get("options", {}).get("task_id") or ""
    )


@logs_errors("AabHandler")
def aab_sign(
    params: Dict[str, Any], stream_handler: Callable[[str], None] = None
) -> Dict[str, Any]:
    """Sign an AAB file using jarsigner."""
    aab_path = params.get("aab_path")
    keystore = params.get("keystore", {})
    task_id = _get_aab_task_id(params)
    if not aab_path or not os.path.exists(aab_path):
        raise ToolException("AAB path does not exist")
    if not keystore.get("path") or not keystore.get("alias"):
        raise ToolException("Missing keystore info for signing")

    task_manager = TaskManager()
    process_holder: dict = {}
    if task_id:
        task_manager.register(task_id, process_holder)

    try:
        jarsigner = manager.get_tool("jarsigner")
        if not jarsigner or not jarsigner.is_valid:
            raise ToolNotFoundError("jarsigner")

        args = [
            "-keystore", keystore.get("path", ""),
            "-storepass", keystore.get("storepass", ""),
        ]
        if keystore.get("keypass"):
            args += ["-keypass", keystore.get("keypass", "")]
        args += [aab_path, keystore.get("alias", "")]

        context = CommandExecutionContext(
            process_holder=process_holder,
            task_id=task_id,
        )
        result = jarsigner.execute(
            [jarsigner.tool_path] + args, context
        )
        if task_manager.is_cancelled(task_id):
            return {"cancelled": True, "task_id": task_id}
        if result.get("returncode", 1) != 0:
            raise ToolException(result.get("stderr", "Signing failed"))
        if task_id:
            append_task_log(task_id, f"[AAB_SIGN] signed: {aab_path}")
        return {"aab_path": aab_path}
    finally:
        if task_id:
            task_manager.unregister(task_id)


@logs_errors("AabHandler")
def convert_aab_to_apks(params, stream_handler):
    """Convert AAB to APKS using bundletool."""
    aab_path = params.get("aab_path")
    output_path = params.get("output_path") or (
        os.path.splitext(aab_path)[0] + ".apks"
    )
    keystore = params.get("keystore", {})
    device_id = params.get("device_id")
    task_id = _get_aab_task_id(params)

    if not aab_path or not os.path.exists(aab_path):
        raise ToolException("AAB path does not exist")

    task_manager = TaskManager()
    process_holder: dict = {}
    own_registration = False
    if task_id:
        if task_manager.is_registered(task_id):
            # Nested call (install_aab passes its task_id down): the caller
            # already registered this id. Re-registering would overwrite the
            # caller's process_holder, and our finally-unregister would tear
            # down the caller's registration while its install step is still
            # running — leaving the task uncancellable ("task not found") and
            # the UI stuck at "running" forever. Reuse the caller's holder so
            # cancel can kill the build-apks java process.
            process_holder = task_manager.get_process_holder(task_id) or process_holder
        else:
            task_manager.register(task_id, process_holder, cleanup_paths=[output_path])
            own_registration = True

    try:
        bundletool = manager.get_tool("bundletool")
        if not bundletool or not bundletool.is_valid:
            raise ToolNotFoundError("bundletool")

        args = [
            "build-apks",
            "--bundle", aab_path,
            "--output", output_path,
        ]
        # Bundletool internally extracts aapt2 from its own jar via
        # jdk.zipfs (jar:// FileSystem provider), which is missing from
        # our stripped runtime JRE. Point it at the bundled aapt2 binary
        # to avoid ProviderNotFoundException: Provider "jar" not found.
        aapt = manager.get_tool("aapt")
        if aapt and aapt.is_valid and aapt.tool_path:
            args += ["--aapt2", aapt.tool_path]
        if keystore.get("path"):
            args += [
                "--ks", keystore.get("path", ""),
                "--ks-key-alias", keystore.get("alias", ""),
                "--ks-pass", f"pass:{keystore.get('storepass', '')}",
            ]
            if keystore.get("keypass"):
                args += [
                    "--key-pass",
                    f"pass:{keystore.get('keypass', '')}",
                ]

        context = CommandExecutionContext(
            process_holder=process_holder,
            task_id=task_id,
        )
        java = bundletool.get_java_path()
        if not java or not os.path.exists(java):
            raise ToolException("Java runtime not found or invalid")
        result = bundletool.execute(
            [java, "-jar", bundletool.tool_path] + args, context
        )
        if task_manager.is_cancelled(task_id):
            return {"cancelled": True, "task_id": task_id}
        if result.get("returncode", 1) != 0:
            raise ToolException(result.get("stderr", "Conversion failed"))
        if task_id:
            append_task_log(task_id, f"[AAB_CONVERT] apks_path: {output_path}")
        return {"apks_path": output_path}
    finally:
        # Only tear down a registration this call created — a nested call
        # (task_id already registered by install_aab) must leave the
        # caller's entry intact so cancel keeps working for the install.
        if task_id and own_registration:
            task_manager.unregister(task_id)


@streaming
@logs_errors("AabHandler")
def install_aab(params, stream_handler):
    """Convert AAB to APKS then install on a device."""
    aab_path = params.get("aab_path")
    device_id = params.get("device_id")
    output_path = params.get("output_path")
    keystore = params.get("keystore", {})
    task_id = _get_aab_task_id(params)

    if not aab_path:
        raise ToolException("Missing aab_path")
    if not device_id:
        raise ToolException("Missing device_id")

    if not output_path:
        output_path = os.path.splitext(aab_path)[0] + ".apks"

    if os.path.exists(output_path):
        try:
            os.remove(output_path)
            logger.info(f"Removed old APKS file: {output_path}")
        except Exception as e:
            logger.warning(f"Failed to remove old APKS file: {e}")

    task_manager = TaskManager()
    process_holder: dict = {}
    if task_id:
        task_manager.register(task_id, process_holder, cleanup_paths=[output_path])

    try:
        if stream_handler:
            stream_handler({"type": "log", "task_id": task_id, "line": "[AAB] Converting to APKS..."})
        convert_result = convert_aab_to_apks(
            {
                "aab_path": aab_path,
                "output_path": output_path,
                "device_id": device_id,
                "keystore": keystore,
                "task_id": task_id,
            },
            stream_handler,
        )
        if task_manager.is_cancelled(task_id):
            return {"cancelled": True, "task_id": task_id}

        apks_path = convert_result.get("apks_path")
        if not apks_path:
            raise ToolException("No APKS path after conversion")

        if stream_handler:
            stream_handler({"type": "log", "task_id": task_id, "line": f"[AAB] APKS generated: {apks_path}"})

        bundletool = manager.get_tool("bundletool")
        if not bundletool or not bundletool.is_valid:
            raise ToolNotFoundError("bundletool")

        adb = manager.get_tool("adb")
        if not adb or not adb.is_valid or not os.path.exists(adb.tool_path):
            raise ToolNotFoundError("adb")

        context = CommandExecutionContext(
            process_holder=process_holder,
            task_id=task_id,
        )
        java = bundletool.get_java_path()
        if not java or not os.path.exists(java):
            raise ToolException("Java runtime not found or invalid")

        if stream_handler:
            stream_handler({"type": "log", "task_id": task_id, "line": f"[AAB] Installing to device {device_id}..."})

        args = [
            java, "-jar", bundletool.tool_path,
            "install-apks", "--apks", apks_path,
            "--adb", adb.tool_path, "--device-id", device_id,
        ]

        result = bundletool.execute(args, context)
        if task_manager.is_cancelled(task_id):
            return {"cancelled": True, "task_id": task_id}
        if result.get("returncode", 1) != 0:
            raise ToolException(result.get("stderr", "Installation failed"))
        if task_id:
            append_task_log(task_id, f"[AAB_INSTALL] device={device_id} apks={apks_path}")
        if stream_handler:
            stream_handler({"type": "complete", "payload": {"device_id": device_id, "apks_path": apks_path, "success": True}})
        return {"device_id": device_id, "apks_path": apks_path}
    finally:
        if task_id:
            task_manager.unregister(task_id)


API_MAP = {
    "aab.analyze": aab_analyze,
    "aab.sign": aab_sign,
    "device.convert_aab_to_apks": convert_aab_to_apks,
    "device.install_aab": install_aab,
}
