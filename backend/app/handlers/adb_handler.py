import os
import traceback
import re
from app.tools.tool_manager import ToolManager
from app.common.base_executor import CommandExecutionContext
from app.utils.logger import Logger
from app.tools.adb import Adb
from app.utils.env import get_output_dir

logger = Logger.get_logger("AdbHandler")
manager = ToolManager.instance()

def adb_devices(params, stream_handler):
    try:
        adb_tool: Adb = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise Exception("未找到或无效的 adb 工具")

        return adb_tool.get_devices_detail()
    except Exception as e:
        logger.error(f"执行 adb devices 时出错: {e}")
        raise e

def adb_logcat(params, stream_handler):
    device_id = params.get("device_id")
    if not device_id:
        stream_handler({"type": "error", "payload": {"message": "请求中未包含 device_id"}})
        return

    try:
        adb_tool:Adb = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise Exception("未找到或无效的 adb 工具")

        adb_tool.start_logcat(stream_handler, device_id)

    except Exception as e:
        logger.error(f"启动 adb logcat 时出错: {traceback.format_exc()}")
        stream_handler({"type": "error", "payload": {"message": f"启动 adb logcat 失败: {traceback.format_exc()}"}})

def _stream_logcat_output(process, process_id, stream_handler):
    try:
        for line in iter(process.stdout.readline, b''):
            stream_handler({
                "type": "log",
                "payload": {"process_id": process_id, "line": line.decode('utf-8', errors='ignore').strip()}
            })
    except Exception as e:
        logger.error(f"读取 logcat 输出时出错 (Process ID: {process_id}): {e}")
    finally:
        process.stdout.close()
        return_code = process.wait()
        logger.info(f"Logcat 进程已终止 (Process ID: {process_id}, Return Code: {return_code})")
        stream_handler({"type": "process_finished", "payload": {"process_id": process_id, "return_code": return_code}})
        # 工具类会自动清理进程，这里不需要手动删除

def adb_stop_logcat(params, stream_handler):
    process_id = params.get("process_id")
    if not process_id:
        raise Exception("请求中未包含 process_id")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool:
            raise Exception("未找到 adb 工具")
        
        success = adb_tool.stop_process(process_id)
        if success:
            return {"message": f"已成功请求停止进程 {process_id}"}
        else:
            return {"type": "warning", "payload": {"message": f"未找到或无法停止进程 {process_id}"}}
    except Exception as e:
        logger.error(f"停止 logcat 进程时出错: {e}")
        raise e

def device_info(params, stream_handler):
    device_id = params.get("device_id")
    if not device_id:
        raise Exception("请求中未包含 device_id")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise Exception("未找到或无效的 adb 工具")

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

        ipr = adb_tool.execute(["-s", device_id, "shell", "ip", "-f", "inet", "addr", "show", "wlan0"], ctx)
        ip_text = ipr.get("stdout", "") or ""
        ip_addr = ""
        for line in ip_text.splitlines():
            t = line.strip()
            if t.startswith("inet "):
                parts = t.split()
                if len(parts) >= 2:
                    ip_addr = parts[1].split("/")[0]
                    break

        br = adb_tool.execute(["-s", device_id, "shell", "dumpsys", "battery"], ctx)
        battery_text = br.get("stdout", "") or ""
        battery_level = ""
        battery_status = ""
        status_map = {"1": "unknown", "2": "charging", "3": "discharging", "4": "not_charging", "5": "full"}
        for line in battery_text.splitlines():
            t = line.strip()
            if t.startswith("level:"):
                battery_level = t.split(":", 1)[1].strip()
            elif t.startswith("status:"):
                s = t.split(":", 1)[1].strip()
                battery_status = status_map.get(s, s)

        mr = adb_tool.execute(["-s", device_id, "shell", "cat", "/proc/meminfo"], ctx)
        mem_text = mr.get("stdout", "") or ""
        ram_total = ""
        for line in mem_text.splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2:
                    ram_total = parts[1] + (" " + parts[2] if len(parts) >= 3 else "")
                break

        dfr = adb_tool.execute(["-s", device_id, "shell", "df", "-h", "/data"], ctx)
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
            "buildNumber": gp("ro.build.version.incremental") or gp("ro.build.display.id"),
            "fingerprint": gp("ro.build.fingerprint"),
            "securityPatch": gp("ro.build.version.security_patch"),
            "hardware": gp("ro.hardware"),
            "architecture": gp("ro.product.cpu.abi"),
            "abiList": gp("ro.product.cpu.abilist"),
            "locale": gp("persist.sys.locale") or gp("ro.product.locale"),
            "screenSize": screen_size,
            "screenResolution": screen_size,
            "density": density,
            "ipAddress": ip_addr,
            "batteryLevel": battery_level,
            "batteryStatus": battery_status,
            "ramTotal": ram_total,
            "storageTotal": storage_total,
            "storageAvailable": storage_available,
            "totalStorage": storage_total,
            "availableStorage": storage_available,
            "systemActivationDate": gp("persist.vivo.initial_system_time_millis"),
            "pageSize": gp("ro.product.cpu.pagesize.max")
        }

        return info
    except Exception as e:
        logger.error(f"获取设备信息失败: {e}")
        raise e

def device_list_apps(params, stream_handler):
    device_id = params.get("device_id")
    app_type = (params.get("type") or params.get("app_type") or "all").strip().lower()
    if not device_id:
        raise Exception("缺少 device_id")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise Exception("未找到或无效的 adb 工具")

        pm_args = []
        if app_type == "system":
            pm_args = ["-s"]
        elif app_type in ("third_party", "thirdparty", "third-party", "user"):
            pm_args = ["-3"]

        ctx = CommandExecutionContext()
        r = adb_tool.execute(["-s", device_id, "shell", "pm", "list", "packages"] + pm_args, ctx)
        stdout = r.get("stdout", "") or ""
        if r.get("returncode", 0) != 0:
            raise Exception(r.get("stderr", "获取已安装应用失败"))

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
    except Exception as e:
        logger.error(f"列出设备应用失败: {e}")
        raise e

def device_shell(params, stream_handler):
    device_id = params.get("device_id")
    command = params.get("command")
    if not device_id or not command:
        raise Exception("缺少 device_id 或 command")
    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise Exception("未找到或无效的 adb 工具")
        ctx = CommandExecutionContext()
        r = adb_tool.execute(["-s", device_id, "shell", command], ctx)
        return {"output": r.get("stdout", ""), "returncode": r.get("returncode", 0)}
    except Exception as e:
        logger.error(f"执行 shell 命令失败: {e}")
        raise e

def device_reboot(params, stream_handler):
    device_id = params.get("device_id")
    mode = params.get("mode", "normal")
    if not device_id:
        raise Exception("缺少 device_id")
    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise Exception("未找到或无效的 adb 工具")
        args = ["-s", device_id, "reboot"]
        if mode and mode != "normal":
            args.append(mode)
        ctx = CommandExecutionContext()
        r = adb_tool.execute(args, ctx)
        success = r.get("returncode", 1) == 0
        if not success:
            raise Exception(r.get("stderr", "重启失败"))
        return {"device_id": device_id, "mode": mode}
    except Exception as e:
        logger.error(f"重启设备失败: {e}")
        raise e

def device_export_apk(params, stream_handler):
    device_id = params.get("device_id")
    package_name = params.get("package_name")
    
    if not device_id or not package_name:
        raise Exception("缺少 device_id 或 package_name")

    # Use unified output directory if not specified
    if not params.get("output_dir"):
         output_dir = os.path.join(get_output_dir(), "exported_apks", package_name)
         os.makedirs(output_dir, exist_ok=True)
    else:
         output_dir = params.get("output_dir")

    try:
        adb_tool = manager.get_tool("adb")
        if not adb_tool or not adb_tool.is_valid:
            raise Exception("未找到或无效的 adb 工具")

        # 1. 获取APK路径
        ctx = CommandExecutionContext()
        res = adb_tool.execute(["-s", device_id, "shell", "pm", "path", package_name], ctx)
        output = res.get("stdout", "")
        
        # Output format: package:/data/app/com.example.app/base.apk
        paths = []
        for line in output.splitlines():
            if line.startswith("package:"):
                paths.append(line[8:].strip())
        
        if not paths:
             raise Exception(f"未找到应用 {package_name} 的安装路径")

        # 2. 导出APK
        exported_files = []
        for remote_path in paths:
            filename = os.path.basename(remote_path)
            # 如果是 base.apk，重命名为 package_name.apk
            if filename == "base.apk":
                filename = f"{package_name}.apk"
            elif filename == "split_config.arm64_v8a.apk": # Example split apk
                 pass # keep original name or rename
            
            local_path = os.path.join(output_dir, filename)
            
            pull_res = adb_tool.execute(["-s", device_id, "pull", remote_path, local_path], ctx)
            if pull_res.get("returncode", 1) != 0:
                 logger.warning(f"导出文件 {remote_path} 失败: {pull_res.get('stderr')}")
                 continue
            
            exported_files.append(local_path)

        if not exported_files:
             raise Exception("导出 APK 失败")

        return {"success": True, "exported_files": exported_files, "output_dir": output_dir}

    except Exception as e:
        logger.error(f"导出 APK 失败: {e}")
        raise e

API_MAP = {
    "adb.devices": adb_devices,
    "adb.logcat": adb_logcat,
    "adb.stop_logcat": adb_stop_logcat,
    "device.info": device_info,
    "device.list_apps": device_list_apps,
    "device.get_device_info": device_info,
    "device.shell": device_shell,
    "device.reboot": device_reboot,
    "device.get_installed_packages": device_list_apps,
    "device.export_apk": device_export_apk
}
