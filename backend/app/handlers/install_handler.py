#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK / APKS installation handlers.
"""

import os

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.exceptions import ToolNotFoundError, ToolException
from app.utils.logger import Logger

logger = Logger.get_logger("InstallHandler")
manager = ToolManager.instance()


def device_install_apk(params, stream_handler):
    apk_path = params.get("apk_path")
    device_id = params.get("device_id")
    if not apk_path:
        raise ToolException("Missing apk_path")
    if not device_id:
        raise ToolException("Missing device_id")
    if not os.path.exists(apk_path):
        raise ToolException(f"APK file does not exist: {apk_path}")

    try:
        adb = manager.get_tool("adb")
        if not adb or not adb.is_valid or not os.path.exists(adb.tool_path):
            raise ToolNotFoundError("adb")
        context = CommandExecutionContext()
        result = adb.execute(
            [adb.tool_path, "-s", device_id, "install", "-r", apk_path],
            context,
        )
        success = result.get("returncode", 1) == 0
        if not success:
            raise ToolException(result.get("stderr", "Installation failed"))
        return {"device_id": device_id, "apk_path": apk_path}
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"APK installation failed: {e}")
        raise


def device_install_apks(params, stream_handler):
    apks_path = params.get("apks_path")
    device_id = params.get("device_id")
    if not apks_path:
        raise ToolException("Missing apks_path")
    if not device_id:
        raise ToolException("Missing device_id")
    if not os.path.exists(apks_path):
        raise ToolException(f"APKS file does not exist: {apks_path}")

    try:
        bundletool = manager.get_tool("bundletool")
        if (
            not bundletool
            or not bundletool.is_valid
            or not os.path.exists(bundletool.tool_path)
        ):
            raise ToolNotFoundError("bundletool")

        adb = manager.get_tool("adb")
        if not adb or not adb.is_valid or not os.path.exists(adb.tool_path):
            raise ToolNotFoundError("adb")

        context = CommandExecutionContext()
        java = bundletool.get_java_path()
        if not java or not os.path.exists(java):
            raise ToolException("Java runtime not found or invalid")

        args = [
            java, "-jar", bundletool.tool_path,
            "install-apks", "--apks", apks_path,
            "--adb", adb.tool_path, "--device-id", device_id,
        ]

        result = bundletool.execute(args, context)
        success = result.get("returncode", 1) == 0
        if not success:
            raise ToolException(
                result.get("stderr", "APKS installation failed")
            )
        return {"device_id": device_id, "apks_path": apks_path}
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"APKS installation failed: {e}")
        raise


API_MAP = {
    "device.install_apk": device_install_apk,
    "device.install_apks": device_install_apks,
}
