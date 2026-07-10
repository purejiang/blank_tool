#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK / APKS installation handlers.
"""

import os

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.task_manager import TaskManager
from app.common.decorators import streaming
from app.common.exceptions import ToolNotFoundError, ToolException
from app.utils.logger import Logger
from app.utils.task_log_writer import append_task_log

logger = Logger.get_logger("InstallHandler")
manager = ToolManager.instance()


def _get_install_task_id(params: dict) -> str:
    """Extract task_id from install handler params."""
    return str(params.get("task_id") or "")


@streaming
def device_install_apk(params, stream_handler):
    apk_path = params.get("apk_path")
    device_id = params.get("device_id")
    task_id = _get_install_task_id(params)
    task_manager = TaskManager()
    process_holder: dict = {}
    if task_id:
        task_manager.register(task_id, process_holder)
        logger.info(f"Install task {task_id}: registered, holder_id={id(process_holder)}")

    try:
        if not apk_path:
            raise ToolException("Missing apk_path")
        if not device_id:
            raise ToolException("Missing device_id")
        if not os.path.exists(apk_path):
            raise ToolException(f"APK file does not exist: {apk_path}")

        adb = manager.get_tool("adb")
        if not adb or not adb.is_valid or not os.path.exists(adb.tool_path):
            raise ToolNotFoundError("adb")
        context = CommandExecutionContext(
            task_id=task_id,
            process_holder=process_holder,
            stream=True,
        )
        logger.info(f"Install task {task_id}: about to execute, ctx.holder_is_None={context.process_holder is None}")
        proc = adb.execute(
            [adb.tool_path, "-s", device_id, "install", "-r", apk_path],
            context,
        )
        if task_manager.is_cancelled(task_id):
            proc.kill()
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return

        for line in iter(proc.stdout.readline, ''):
            if task_id and task_manager.is_cancelled(task_id):
                proc.kill()
                stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                return
            line = line.rstrip('\n')
            if line:
                append_task_log(task_id, line)
                stream_handler({"type": "log", "line": line})

        proc.wait()

        if task_id and task_manager.is_cancelled(task_id):
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return

        if proc.returncode != 0:
            stream_handler({"type": "error", "payload": {"message": "Installation failed"}})
            return

        stream_handler({"type": "complete", "payload": {"device_id": device_id, "success": True}})
    except Exception as e:
        if task_id and task_manager.is_cancelled(task_id):
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return
        logger.error(f"APK installation failed: {e}")
        stream_handler({"type": "error", "payload": {"message": str(e)}})
    finally:
        if task_id:
            task_manager.unregister(task_id)


@streaming
def device_install_apks(params, stream_handler):
    apks_path = params.get("apks_path")
    device_id = params.get("device_id")
    task_id = _get_install_task_id(params)
    task_manager = TaskManager()
    process_holder: dict = {}
    if task_id:
        task_manager.register(task_id, process_holder)
        logger.info(f"Install task {task_id}: registered, holder_id={id(process_holder)}")

    try:
        if not apks_path:
            raise ToolException("Missing apks_path")
        if not device_id:
            raise ToolException("Missing device_id")
        if not os.path.exists(apks_path):
            raise ToolException(f"APKS file does not exist: {apks_path}")

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

        context = CommandExecutionContext(
            task_id=task_id,
            process_holder=process_holder,
            stream=True,
        )
        java = bundletool.get_java_path()
        if not java or not os.path.exists(java):
            raise ToolException("Java runtime not found or invalid")

        args = [
            java, "-jar", bundletool.tool_path,
            "install-apks", "--apks", apks_path,
            "--adb", adb.tool_path, "--device-id", device_id,
        ]

        proc = bundletool.execute(args, context)
        if task_manager.is_cancelled(task_id):
            proc.kill()
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return

        for line in iter(proc.stdout.readline, ''):
            if task_id and task_manager.is_cancelled(task_id):
                proc.kill()
                stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
                return
            line = line.rstrip('\n')
            if line:
                append_task_log(task_id, line)
                stream_handler({"type": "log", "line": line})

        proc.wait()

        if task_id and task_manager.is_cancelled(task_id):
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return

        if proc.returncode != 0:
            stream_handler({"type": "error", "payload": {"message": "APKS installation failed"}})
            return

        stream_handler({"type": "complete", "payload": {"device_id": device_id, "success": True}})
    except Exception as e:
        if task_id and task_manager.is_cancelled(task_id):
            stream_handler({"type": "cancelled", "payload": {"task_id": task_id}})
            return
        logger.error(f"APKS installation failed: {e}")
        stream_handler({"type": "error", "payload": {"message": str(e)}})
    finally:
        if task_id:
            task_manager.unregister(task_id)


API_MAP = {
    "device.install_apk": device_install_apk,
    "device.install_apks": device_install_apks,
}
