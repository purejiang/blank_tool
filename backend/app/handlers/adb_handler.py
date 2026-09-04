#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADB & device handlers.
"""

import os
import re
import time

from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.common.exceptions import ToolNotFoundError, ToolException
from app.utils.logger import Logger
from app.tools.adb import Adb
from app.utils.env import get_output_dir
from app.utils.adb_auto_core import (
    tap,
    swipe,
    input_text,
    keyevent,
    ui_dump,
    find_element,
    tap_element,
    current_activity,
)
from app.common.decorators import streaming, logs_errors

logger = Logger.get_logger("AdbHandler")
manager = ToolManager.instance()


@logs_errors("AdbHandler")
def adb_devices(params, stream_handler):
    adb_tool: Adb = manager.get_tool("adb")
    if not adb_tool or not adb_tool.is_valid:
        raise ToolNotFoundError("adb")
    return adb_tool.get_devices_detail()


@streaming
@logs_errors("AdbHandler")
def adb_logcat(params, stream_handler):
    device_id = params.get("device_id")
    if not device_id:
        stream_handler({
            "type": "error",
            "payload": {"message": "Missing device_id"},
        })
        return

    adb_tool: Adb = manager.get_tool("adb")
    if not adb_tool or not adb_tool.is_valid:
        raise ToolNotFoundError("adb")
    adb_tool.start_logcat(stream_handler, device_id)


@logs_errors("AdbHandler")
def adb_stop_logcat(params, stream_handler):
    process_id = params.get("process_id")
    if not process_id:
        raise ToolException("Missing process_id")

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


@logs_errors("AdbHandler")
def adb_export_logcat(params, stream_handler):
    device_id = params.get("device_id")
    file_path = params.get("file_path")

    if not device_id or not file_path:
        raise ToolException("Missing device_id or file_path")

    adb_tool: Adb = manager.get_tool("adb")
    if not adb_tool or not adb_tool.is_valid:
        raise ToolNotFoundError("adb")
    success = adb_tool.export_logcat(device_id, file_path)
    if success:
        return {"success": True, "file_path": file_path}
    else:
        raise ToolException("Export failed")


@logs_errors("AdbHandler")
def device_info(params, stream_handler):
    device_id = params.get("device_id")
    if not device_id:
        raise ToolException("Missing device_id")

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


@logs_errors("AdbHandler")
def device_list_apps(params, stream_handler):
    device_id = params.get("device_id")
    app_type = (
        params.get("type") or params.get("app_type") or "all"
    ).strip().lower()
    if not device_id:
        raise ToolException("Missing device_id")

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


@logs_errors("AdbHandler")
def device_shell(params, stream_handler):
    device_id = params.get("device_id")
    command = params.get("command")
    if not device_id or not command:
        raise ToolException("Missing device_id or command")

    adb_tool = manager.get_tool("adb")
    if not adb_tool or not adb_tool.is_valid:
        raise ToolNotFoundError("adb")
    ctx = CommandExecutionContext()
    r = adb_tool.execute(["-s", device_id, "shell", command], ctx)
    return {
        "output": r.get("stdout", ""),
        "returncode": r.get("returncode", 0),
    }


@logs_errors("AdbHandler")
def device_reboot(params, stream_handler):
    device_id = params.get("device_id")
    mode = params.get("mode", "normal")
    if not device_id:
        raise ToolException("Missing device_id")

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


@logs_errors("AdbHandler")
def device_uninstall_app(params, stream_handler):
    device_id = params.get("device_id")
    package_name = params.get("package_name")
    if not device_id or not package_name:
        raise ToolException("Missing device_id or package_name")

    adb_tool = manager.get_tool("adb")
    if not adb_tool or not adb_tool.is_valid:
        raise ToolNotFoundError("adb")

    ctx = CommandExecutionContext()
    r = adb_tool.execute(["-s", device_id, "uninstall", package_name], ctx)
    success = r.get("returncode", 1) == 0
    if not success:
        raise ToolException(r.get("stderr", "Uninstall failed"))
    return {"device_id": device_id, "package_name": package_name, "success": True}


@logs_errors("AdbHandler")
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


@logs_errors("AdbHandler")
def device_launch_app(params, stream_handler):
    """Launch an installed app via monkey (no activity name required)."""
    device_id = params.get("device_id")
    package_name = params.get("package_name")
    if not device_id or not package_name:
        raise ToolException("Missing device_id or package_name")

    adb_tool = manager.get_tool("adb")
    if not adb_tool or not adb_tool.is_valid:
        raise ToolNotFoundError("adb")

    ctx = CommandExecutionContext()
    r = adb_tool.execute(
        [
            "-s", device_id, "shell", "monkey", "-p", package_name,
            "-c", "android.intent.category.LAUNCHER", "1",
        ],
        ctx,
    )
    success = r.get("returncode", 1) == 0
    if not success:
        raise ToolException(r.get("stderr", "Launch failed"))
    return {"device_id": device_id, "package_name": package_name, "success": True}


@logs_errors("AdbHandler")
def device_clear_app_data(params, stream_handler):
    """Clear all app data via ``pm clear`` (destructive, frontend confirms first)."""
    device_id = params.get("device_id")
    package_name = params.get("package_name")
    if not device_id or not package_name:
        raise ToolException("Missing device_id or package_name")

    adb_tool = manager.get_tool("adb")
    if not adb_tool or not adb_tool.is_valid:
        raise ToolNotFoundError("adb")

    ctx = CommandExecutionContext()
    r = adb_tool.execute(
        ["-s", device_id, "shell", "pm", "clear", package_name], ctx
    )
    stdout = (r.get("stdout", "") or "").strip()
    success = r.get("returncode", 1) == 0 and "Success" in stdout
    if not success:
        raise ToolException(stdout or r.get("stderr", "Clear data failed"))
    return {"device_id": device_id, "package_name": package_name, "success": True}


@logs_errors("AdbHandler")
def device_screenshot(params, stream_handler):
    """Capture device screen to a local PNG.

    Screencap writes to a device-side temp file first (avoids the stdout
    ``\\r\\n`` corruption of ``screencap -p`` on old devices), then pulls to
    the user-chosen path (or the default screenshots output dir).
    """
    device_id = params.get("device_id")
    if not device_id:
        raise ToolException("Missing device_id")

    file_path = params.get("file_path")
    if not file_path:
        ts = time.strftime("%Y%m%d-%H%M%S")
        screenshots_dir = os.path.join(get_output_dir(), "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        file_path = os.path.join(screenshots_dir, f"screenshot-{ts}.png")

    adb_tool = manager.get_tool("adb")
    if not adb_tool or not adb_tool.is_valid:
        raise ToolNotFoundError("adb")

    ctx = CommandExecutionContext()
    remote = "/sdcard/blank_tool_screenshot.png"

    cap = adb_tool.execute(["-s", device_id, "shell", "screencap", "-p", remote], ctx)
    if cap.get("returncode", 1) != 0:
        raise ToolException(cap.get("stderr", "Screencap failed"))

    pull = adb_tool.execute(["-s", device_id, "pull", remote, file_path], ctx)
    # Best-effort cleanup of the device-side temp file regardless of pull result.
    adb_tool.execute(
        ["-s", device_id, "shell", "rm", "-f", remote],
        CommandExecutionContext(capture_output=True, log_output=False),
    )
    if pull.get("returncode", 1) != 0:
        raise ToolException(pull.get("stderr", "Pull screenshot failed"))

    return {"success": True, "file_path": file_path}


# ----------------------------------------------------------------------
# ADB UI automation atomic handlers (batch 1)
# Thin wrappers over app.utils.adb_auto_core, exposed as backend APIs so the
# frontend "pick element from current screen" can call them directly, and the
# adb_auto plugin orchestrates them.
# ----------------------------------------------------------------------

@logs_errors("AdbHandler")
def device_tap(params, stream_handler):
    device_id = params.get("device_id")
    x = params.get("x")
    y = params.get("y")
    if not device_id or x is None or y is None:
        raise ToolException("Missing device_id or x/y")
    return tap(device_id, int(x), int(y))


@logs_errors("AdbHandler")
def device_swipe(params, stream_handler):
    device_id = params.get("device_id")
    x1 = params.get("x1")
    y1 = params.get("y1")
    x2 = params.get("x2")
    y2 = params.get("y2")
    if not device_id or None in (x1, y1, x2, y2):
        raise ToolException("Missing device_id or swipe coords")
    duration = params.get("duration_ms", 300)
    return swipe(device_id, int(x1), int(y1), int(x2), int(y2), int(duration))


@logs_errors("AdbHandler")
def device_input_text(params, stream_handler):
    device_id = params.get("device_id")
    text = params.get("text")
    if not device_id or text is None:
        raise ToolException("Missing device_id or text")
    return input_text(device_id, str(text))


@logs_errors("AdbHandler")
def device_keyevent(params, stream_handler):
    device_id = params.get("device_id")
    key = params.get("key")
    if not device_id or not key:
        raise ToolException("Missing device_id or key")
    return keyevent(device_id, str(key))


@logs_errors("AdbHandler")
def device_ui_dump(params, stream_handler):
    device_id = params.get("device_id")
    if not device_id:
        raise ToolException("Missing device_id")
    ok, xml = ui_dump(device_id, timeout_ms=int(params.get("timeout_ms", 8000)))
    if not ok:
        return {"success": False, "xml": "", "error": xml}
    return {"success": True, "xml": xml, "error": ""}


@logs_errors("AdbHandler")
def device_find_element(params, stream_handler):
    device_id = params.get("device_id")
    by = params.get("by")
    value = params.get("value")
    if not device_id or not by or value is None:
        raise ToolException("Missing device_id/by/value")
    return find_element(
        device_id, by, value, timeout_ms=int(params.get("timeout_ms", 10000))
    )


@logs_errors("AdbHandler")
def device_tap_element(params, stream_handler):
    device_id = params.get("device_id")
    by = params.get("by")
    value = params.get("value")
    if not device_id or not by or value is None:
        raise ToolException("Missing device_id/by/value")
    return tap_element(
        device_id, by, value, timeout_ms=int(params.get("timeout_ms", 10000))
    )


@logs_errors("AdbHandler")
def device_current_activity(params, stream_handler):
    device_id = params.get("device_id")
    if not device_id:
        raise ToolException("Missing device_id")
    return current_activity(
        device_id, timeout_ms=int(params.get("timeout_ms", 3000))
    )


@logs_errors("AdbHandler")
def adb_connect(params, stream_handler):
    """Connect to a remote ADB device via TCP/IP."""
    address = params.get("address", "")
    if not address:
        raise ToolException("Missing address (e.g. 192.168.1.100:5555)")

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


@logs_errors("AdbHandler")
def adb_disconnect(params, stream_handler):
    """Disconnect from a remote ADB device or all devices."""
    address = params.get("address", "")

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
    "device.uninstall_app": device_uninstall_app,
    "device.uninstall": device_uninstall_app,
    "device.launch_app": device_launch_app,
    "device.clear_app_data": device_clear_app_data,
    "device.screenshot": device_screenshot,
    "device.export_apk": device_export_apk,
    "device.tap": device_tap,
    "device.swipe": device_swipe,
    "device.input_text": device_input_text,
    "device.keyevent": device_keyevent,
    "device.ui_dump": device_ui_dump,
    "device.find_element": device_find_element,
    "device.tap_element": device_tap_element,
    "device.current_activity": device_current_activity,
}
