#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AAB signing, conversion, and installation handlers.
"""

import os
from typing import Any, Callable, Dict

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.task_manager import TaskManager
from app.common.exceptions import ToolNotFoundError, ToolException
from app.utils.logger import Logger

logger = Logger.get_logger("AabHandler")
manager = ToolManager.instance()


def _get_aab_task_id(params: dict) -> str:
    """Extract task_id from AAB handler params."""
    return str(
        params.get("task_id") or
        params.get("options", {}).get("task_id") or ""
    )


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
        )
        result = jarsigner.execute(
            [jarsigner.tool_path] + args, context
        )
        if task_manager.is_cancelled(task_id):
            return {"cancelled": True, "task_id": task_id}
        if result.get("returncode", 1) != 0:
            raise ToolException(result.get("stderr", "Signing failed"))
        return {"aab_path": aab_path}
    except ToolException:
        raise
    except Exception as e:
        if task_manager.is_cancelled(task_id):
            return {"cancelled": True, "task_id": task_id}
        logger.error(f"AAB signing failed: {e}")
        raise
    finally:
        if task_id:
            task_manager.unregister(task_id)


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
    if task_id:
        task_manager.register(task_id, process_holder, cleanup_paths=[output_path])

    try:
        bundletool = manager.get_tool("bundletool")
        if not bundletool or not bundletool.is_valid:
            raise ToolNotFoundError("bundletool")

        args = [
            "build-apks",
            "--bundle", aab_path,
            "--output", output_path,
        ]
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
        return {"apks_path": output_path}
    except ToolException:
        raise
    except Exception as e:
        if task_manager.is_cancelled(task_id):
            return {"cancelled": True, "task_id": task_id}
        logger.error(f"AAB to APKS conversion failed: {e}")
        raise
    finally:
        if task_id:
            task_manager.unregister(task_id)


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

        bundletool = manager.get_tool("bundletool")
        if not bundletool or not bundletool.is_valid:
            raise ToolNotFoundError("bundletool")

        adb = manager.get_tool("adb")
        if not adb or not adb.is_valid or not os.path.exists(adb.tool_path):
            raise ToolNotFoundError("adb")

        context = CommandExecutionContext(
            process_holder=process_holder,
        )
        java = bundletool.get_java_path()
        if not java or not os.path.exists(java):
            raise ToolException("Java runtime not found or invalid")

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
        return {"device_id": device_id, "apks_path": apks_path}
    except ToolException:
        raise
    except Exception as e:
        if task_manager.is_cancelled(task_id):
            return {"cancelled": True, "task_id": task_id}
        logger.error(f"AAB installation failed: {e}")
        raise
    finally:
        if task_id:
            task_manager.unregister(task_id)


API_MAP = {
    "aab.sign": aab_sign,
    "device.convert_aab_to_apks": convert_aab_to_apks,
    "device.install_aab": install_aab,
}
