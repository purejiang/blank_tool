#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADB & device handlers.
"""

import os
import traceback
import re

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.exceptions import ToolNotFoundError, ToolException
from app.utils.logger import Logger
from app.tools.adb import Adb
from app.utils.env import get_output_dir
from app.common.decorators import streaming

logger = Logger.get_logger("AdbHandler")
manager = ToolManager.instance()


def adb_devices(params, stream_handler):
    try:
        adb_tool: Adb = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")
        return adb_tool.get_devices_detail()
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"Error executing adb devices: {e}")
        raise


@streaming
def adb_logcat(params, stream_handler):
    device_id = params.get("device_id")
    if not device_id:
        stream_handler({
            "type": "error",
            "payload": {"message": "Missing device_id"},
        })
        return

    try:
        adb_tool: Adb = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")
        adb_tool.start_logcat(stream_handler, device_id)
    except Exception as e:
        logger.error(f"Error starting adb logcat: {traceback.format_exc()}")
        stream_handler({
            "type": "error",
            "payload": {"message": f"Failed to start adb logcat: {e}"},
        })


def adb_stop_logcat(params, stream_handler):
    process_id = params.get("process_id")
    if not process_id:
        raise ToolException("Missing process_id")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool:
            raise ToolNotFoundError("adb")
        success = adb_tool.stop_process(process_id)
        if success:
            return {"message": f"Process {process_id} stop requested"}
        else:
            return {
                "type": "warning",
                "payload": {"message": f"Process {process_id} not found or could not be stopped"},
            }
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"Error stopping logcat: {e}")
        raise


def adb_export_logcat(params, stream_handler):
    device_id = params.get("device_id")
    file_path = params.get("file_path")

    if not device_id or not file_path:
        raise ToolException("Missing device_id or file_path")

    try:
        adb_tool: Adb = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")
        success = adb_tool.export_logcat(device_id, file_path)
        if success:
            return {"success": True, "file_path": file_path}
        else:
            raise ToolException("Export failed")
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"Export logcat failed: {e}")
        raise


def device_info(params, stream_handler):
    device_id = params.get("device_id")
    if not device_id:
        raise ToolException("Missing device_id")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")

        ctx = CommandExecutionContext()
        rp = adb_tool.execute(["-s", device_id, "shell", "getprop"], ctx)
        props_text = rp.get("stdout", "") or ""
        props = {}
        for line in props_text.splitlines():
            m = re.match(r"\[(.+?)\]: \[(.*)\]", line)
            if m:
                props[m.group(1)] = m.group(2)

        def gp(name):
            return props.get(name, "")

        rs = adb_tool.execute(["-s", device_id, "get-serialno"], ctx)
        serial = (rs.get("stdout", "") or "").strip()

        rst = adb_tool.execute(["-s", device_id, "get-state"], ctx)
        state = (rst.get("stdout", "") or "").strip()

        sz = adb_tool.execute(["-s", device_id, "shell", "wm", "size"], ctx)
        size_text = sz.get("stdout", "") or ""
        screen_size = ""
        for line in size_text.splitlines():
            if "Physical size:" in line:
                screen_size = line.split(":", 1)[1].strip()
                break

        dn = adb_tool.execute(["-s", device_id, "shell", "wm", "density"], ctx)
        density_text = dn.get("stdout", "") or ""
        density = ""
        for line in density_text.splitlines():
            if "Physical density:" in line:
                density = line.split(":", 1)[1].strip()
                break

        ipr = adb_tool.execute(
            ["-s", device_id, "shell", "ip", "-f", "inet", "addr", "show", "wlan0"],
            ctx,
        )
        ip_text = ipr.get("stdout", "") or ""
        ip_addr = ""
        for line in ip_text.splitlines():
            t = line.strip()
            if t.startswith("inet "):
                parts = t.split()
                if len(parts) >= 2:
                    ip_addr = parts[1].split("/")[0]
                    break

        br = adb_tool.execute(
            ["-s", device_id, "shell", "dumpsys", "battery"], ctx
        )
        battery_text = br.get("stdout", "") or ""
        battery_level = ""
        battery_status = ""
        status_map = {
            "1": "unknown", "2": "charging", "3": "discharging",
            "4": "not_charging", "5": "full",
        }
        for line in battery_text.splitlines():
            t = line.strip()
            if t.startswith("level:"):
                battery_level = t.split(":", 1)[1].strip()
            elif t.startswith("status:"):
                s = t.split(":", 1)[1].strip()
                battery_status = status_map.get(s, s)

        mr = adb_tool.execute(
            ["-s", device_id, "shell", "cat", "/proc/meminfo"], ctx
        )
        mem_text = mr.get("stdout", "") or ""
        ram_total = ""
        for line in mem_text.splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2:
                    ram_total = parts[1] + (
                        " " + parts[2] if len(parts) >= 3 else ""
                    )
                break

        dfr = adb_tool.execute(
            ["-s", device_id, "shell", "df", "-h", "/data"], ctx
        )
        df_text = dfr.get("stdout", "") or ""
        storage_total = ""
        storage_available = ""
        for line in df_text.splitlines():
            if "/data" in line and not line.lower().startswith("filesystem"):
                cols = [c for c in line.split() if c]
                if len(cols) >= 6:
                    storage_total = cols[1]
                    storage_available = cols[3]
                break

        info = {
            "deviceId": device_id,
            "state": state,
            "serial": serial,
            "model": gp("ro.product.model"),
            "brand": gp("ro.product.brand"),
            "manufacturer": gp("ro.product.manufacturer"),
            "device": gp("ro.product.device"),
            "product": gp("ro.product.name"),
            "androidVersion": gp("ro.build.version.release"),
            "apiLevel": gp("ro.build.version.sdk"),
            "buildId": gp("ro.build.id"),
            "buildNumber": gp("ro.build.version.incremental")
            or gp("ro.build.display.id"),
            "fingerprint": gp("ro.build.fingerprint"),
            "securityPatch": gp("ro.build.version.security_patch"),
            "hardware": gp("ro.hardware"),
            "architecture": gp("ro.product.cpu.abi"),
            "abiList": gp("ro.product.cpu.abilist"),
            "locale": gp("persist.sys.locale") or gp("ro.product.locale"),
            "screenResolution": screen_size,
            "density": density,
            "ipAddress": ip_addr,
            "batteryLevel": battery_level,
            "batteryStatus": battery_status,
            "ramTotal": ram_total,
            "totalStorage": storage_total,
            "availableStorage": storage_available,
            "systemActivationDate": gp(
                "persist.vivo.initial_system_time_millis"
            ),
            "pageSize": gp("ro.product.cpu.pagesize.max"),
        }

        return info
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"Failed to get device info: {e}")
        raise


def device_list_apps(params, stream_handler):
    device_id = params.get("device_id")
    app_type = (
        params.get("type") or params.get("app_type") or "all"
    ).strip().lower()
    if not device_id:
        raise ToolException("Missing device_id")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")

        pm_args = []
        if app_type == "system":
            pm_args = ["-s"]
        elif app_type in ("third_party", "thirdparty", "third-party", "user"):
            pm_args = ["-3"]

        ctx = CommandExecutionContext()
        r = adb_tool.execute(
            ["-s", device_id, "shell", "pm", "list", "packages"] + pm_args,
            ctx,
        )
        stdout = r.get("stdout", "") or ""
        if r.get("returncode", 0) != 0:
            raise ToolException(r.get("stderr", "Failed to list installed apps"))

        packages = []
        for line in stdout.splitlines():
            t = line.strip()
            if not t:
                continue
            if t.startswith("package:"):
                pkg = t.split("package:", 1)[1].strip()
                if pkg:
                    packages.append(pkg)

        return packages
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"Failed to list device apps: {e}")
        raise


def device_shell(params, stream_handler):
    device_id = params.get("device_id")
    command = params.get("command")
    if not device_id or not command:
        raise ToolException("Missing device_id or command")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")
        ctx = CommandExecutionContext()
        r = adb_tool.execute(["-s", device_id, "shell", command], ctx)
        return {
            "output": r.get("stdout", ""),
            "returncode": r.get("returncode", 0),
        }
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"Shell command failed: {e}")
        raise


def device_reboot(params, stream_handler):
    device_id = params.get("device_id")
    mode = params.get("mode", "normal")
    if not device_id:
        raise ToolException("Missing device_id")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")
        args = ["-s", device_id, "reboot"]
        if mode and mode != "normal":
            args.append(mode)
        ctx = CommandExecutionContext()
        r = adb_tool.execute(args, ctx)
        success = r.get("returncode", 1) == 0
        if not success:
            raise ToolException(r.get("stderr", "Reboot failed"))
        return {"device_id": device_id, "mode": mode}
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"Device reboot failed: {e}")
        raise


def device_export_apk(params, stream_handler):
    device_id = params.get("device_id")
    package_name = params.get("package_name")

    if not device_id or not package_name:
        raise ToolException("Missing device_id or package_name")

    if not params.get("output_dir"):
        output_dir = os.path.join(
            get_output_dir(), "exported_apks", package_name
        )
        os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = params.get("output_dir")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")

        ctx = CommandExecutionContext()
        res = adb_tool.execute(
            ["-s", device_id, "shell", "pm", "path", package_name], ctx
        )
        output = res.get("stdout", "")

        paths = []
        for line in output.splitlines():
            if line.startswith("package:"):
                paths.append(line[8:].strip())

        if not paths:
            raise ToolException(
                f"Install path not found for app {package_name}"
            )

        exported_files = []
        for remote_path in paths:
            filename = os.path.basename(remote_path)
            if filename == "base.apk":
                filename = f"{package_name}.apk"

            local_path = os.path.join(output_dir, filename)
            pull_res = adb_tool.execute(
                ["-s", device_id, "pull", remote_path, local_path], ctx
            )
            if pull_res.get("returncode", 1) != 0:
                logger.warning(
                    f"Export file {remote_path} failed: "
                    f"{pull_res.get('stderr')}"
                )
                continue
            exported_files.append(local_path)

        if not exported_files:
            raise ToolException("APK export failed")

        return {
            "success": True,
            "exported_files": exported_files,
            "output_dir": output_dir,
        }

    except ToolException:
        raise
    except Exception as e:
        logger.error(f"APK export failed: {e}")
        raise


def adb_connect(params, stream_handler):
    """Connect to a remote ADB device via TCP/IP."""
    address = params.get("address", "")
    if not address:
        raise ToolException("Missing address (e.g. 192.168.1.100:5555)")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")
        result = adb_tool.execute(
            ["connect", address],
            context=CommandExecutionContext(capture_output=True, log_output=False),
        )
        output = result.get("stdout", "") or result.get("stderr", "")
        success = "connected" in output.lower() or "already connected" in output.lower()
        return {"success": success, "output": output.strip(), "address": address}
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"adb connect failed: {e}")
        raise ToolException(f"Connect failed: {e}")


def adb_disconnect(params, stream_handler):
    """Disconnect from a remote ADB device or all devices."""
    address = params.get("address", "")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise ToolNotFoundError("adb")
        cmd = ["disconnect"]
        if address:
            cmd.append(address)
        result = adb_tool.execute(
            cmd,
            context=CommandExecutionContext(capture_output=True, log_output=False),
        )
        output = result.get("stdout", "") or result.get("stderr", "")
        return {"success": True, "output": output.strip(), "address": address or "all"}
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"adb disconnect failed: {e}")
        raise ToolException(f"Disconnect failed: {e}")


API_MAP = {
    "adb.devices": adb_devices,
    "adb.connect": adb_connect,
    "adb.disconnect": adb_disconnect,
    "adb.logcat": adb_logcat,
    "adb.stop_logcat": adb_stop_logcat,
    "adb.export_logcat": adb_export_logcat,
    "device.info": device_info,
    "device.list_apps": device_list_apps,
    "device.get_device_info": device_info,
    "device.shell": device_shell,
    "device.reboot": device_reboot,
    "device.get_installed_packages": device_list_apps,
    "device.export_apk": device_export_apk,
}
