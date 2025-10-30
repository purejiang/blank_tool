#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理Android设备连接和应用安装
"""

import threading
import time
from typing import Dict, Any, List, Callable

from core.base_service import BaseService
from .tool_service import get_tool_service

class DeviceService(BaseService):
    """设备管理器"""
    
    def __init__(self):
        super().__init__("DeviceService")
        self.tool_service = get_tool_service()
        self.monitor_thread = None
        self.monitor_running = False
        self.device_change_callback = None
        self.last_devices = []
        
        # 缓存工具状态，避免重复检查
        self._tools_status = None
        
        # 检查ADB可用性
        if not self._get_tool_status("adb")["available"]:
            self.logger.warning("ADB不可用，设备管理功能将受限")
    
    def _get_tool_status(self, tool_name: str) -> Dict[str, Any]:
        """获取工具状态，使用缓存避免重复调用"""
        if self._tools_status is None:
            self._tools_status = self.tool_service.get_tools_status()
        return self._tools_status.get(tool_name, {"available": False})
    
    def _refresh_tools_status(self):
        """刷新工具状态缓存"""
        self._tools_status = None
            
    def get_devices(self) -> Dict[str, Any]:
        """获取设备列表"""
        try:
            result = self.tool_service.run_tool_command("adb", ["devices", "-l"], "adb")
            
            devices = []
            lines = result["stdout"].strip().split('\n')[1:]  # 跳过第一行标题
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('*'):
                    continue
                    
                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]
                    
                    # 解析设备属性
                    properties = {}
                    for part in parts[2:]:
                        if ':' in part:
                            key, value = part.split(':', 1)
                            properties[key] = value
                    
                    device_info = {
                        "id": device_id,
                        "status": status,
                        "model": properties.get("model", "未知"),
                        "device": properties.get("device", "未知"),
                        "transport_id": properties.get("transport_id"),
                        "product": properties.get("product", "未知")
                    }
                    
                    # 如果设备在线，获取更多信息
                    if status == "device":
                        try:
                            device_info.update(self._get_device_details(device_id))
                        except Exception as e:
                            self.logger.warning(f"获取设备详细信息失败 {device_id}: {e}")
                    
                    devices.append(device_info)
            
            return {
                "success": True,
                "devices": devices,
                "count": len(devices)
            }
            
        except Exception as e:
            error_msg = f"获取设备列表失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "devices": [],
                "count": 0
            }
            
    def _get_device_details(self, device_id: str) -> Dict[str, Any]:
        """获取设备详细信息"""
        details = {}
        
        # 获取设备属性
        properties_to_get = [
            ("ro.build.version.release", "android_version"),
            ("ro.build.version.sdk", "api_level"),
            ("ro.product.manufacturer", "manufacturer"),
            ("ro.product.brand", "brand"),
            ("ro.product.model", "model_name"),
            ("ro.product.device", "device_name"),
            ("ro.build.display.id", "build_id"),
            ("ro.build.version.incremental", "build_number"),
            ("ro.build.id", "build_version"),
            ("ro.build.fingerprint", "build_fingerprint"),
            ("ro.serialno", "serial_number"),
            ("ro.product.cpu.abi", "cpu_abi"),
            ("ro.sf.lcd_density", "density"),
            ("ro.build.date", "build_date"),
            ("ro.build.user", "build_user"),
            ("ro.build.host", "build_host"),
            ("ro.bootloader", "bootloader_version"),
            ("ro.baseband", "baseband_version"),
            ("ro.build.type", "build_type"),
            ("ro.build.tags", "build_tags")
        ]
        
        for prop, key in properties_to_get:
            try:
                result = self.tool_service.run_tool_command(
                    "adb", ["-s", device_id, "shell", "getprop", prop], "adb", timeout=5
                )
                if result["success"]:
                    value = result["stdout"].strip()
                    if value:
                        details[key] = value
            except Exception:
                pass
        
        # 获取网络信息
        try:
            # 获取IP地址
            result = self.tool_service.run_tool_command(
                "adb", ["-s", device_id, "shell", "ip", "route", "get", "1"], "adb", timeout=5
            )
            if result["success"]:
                output = result["stdout"].strip()
                # 解析IP地址
                for line in output.split('\n'):
                    if 'src' in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == 'src' and i + 1 < len(parts):
                                details["ip_address"] = parts[i + 1]
                                break
        except Exception:
            pass
        
        # 获取WiFi状态
        try:
            result = self.tool_service.run_tool_command(
                "adb", ["-s", device_id, "shell", "dumpsys", "wifi", "|", "grep", "mWifiEnabled"], "adb", timeout=5
            )
            if result["success"]:
                output = result["stdout"].strip()
                if "true" in output.lower():
                    details["wifi_status"] = "已启用"
                else:
                    details["wifi_status"] = "已禁用"
        except Exception:
            details["wifi_status"] = "未知"
        
        # 获取存储信息
        try:
            result = self.tool_service.run_tool_command(
                "adb", ["-s", device_id, "shell", "df", "/data"], "adb", timeout=5
            )
            if result["success"]:
                lines = result["stdout"].strip().split('\n')
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 4:
                        total_kb = int(parts[1])
                        used_kb = int(parts[2])
                        
                        # 转换为GB
                        total_gb = round(total_kb / (1024 * 1024), 2)
                        used_gb = round(used_kb / (1024 * 1024), 2)
                        usage_percent = round((used_kb / total_kb) * 100, 1)
                        
                        details["storage_total"] = f"{total_gb}GB"
                        details["storage_used"] = f"{used_gb}GB"
                        details["storage_usage"] = usage_percent
        except Exception:
            pass
                
        return details
        
    def get_device_info(self, device_id: str) -> Dict[str, Any]:
        """获取指定设备信息"""
        try:
            devices_result = self.get_devices()
            if not devices_result["success"]:
                return devices_result
                
            for device in devices_result["devices"]:
                if device["id"] == device_id:
                    return {
                        "success": True,
                        "device": device
                    }
                    
            return {
                "success": False,
                "error": f"设备不存在: {device_id}"
            }
            
        except Exception as e:
            error_msg = f"获取设备信息失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    def convert_aab_to_apks(self, aab_path: str) -> Dict[str, Any]:
        """将AAB转换为APKS文件"""
        try:
            self.validate_file_path(aab_path, must_exist=True, must_be_file=True)
            
            # 检查bundletool可用性
            bundletool_status = self._get_tool_status("bundletool")
            if not bundletool_status["available"]:
                return {
                    "success": False,
                    "error": "bundletool不可用，无法转换AAB文件"
                }
            
            # 创建临时目录
            temp_dir = self.create_temp_dir("aab_convert_")
            apks_path = temp_dir / "app.apks"
            
            # 生成APKS文件（不指定设备，生成通用版本）
            build_cmd = [
                "build-apks",
                f"--bundle={aab_path}",
                f"--output={apks_path}",
                "--mode=universal"  # 生成通用APK
            ]
                
            result = self.tool_service.run_tool_command("bundletool", build_cmd, "bundletool")
            
            if not result["success"]:
                return {
                    "success": False,
                    "error": f"AAB转换为APKS失败: {result.get('stderr', '未知错误')}"
                }
            
            return {
                "success": True,
                "message": "AAB转换为APKS成功",
                "apksPath": str(apks_path),
                "output": result["stdout"]
            }
            
        except Exception as e:
            error_msg = f"AAB转换为APKS失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    def install_apks(self, apks_path: str) -> Dict[str, Any]:
        """安装APKS文件"""
        try:
            self.validate_file_path(apks_path, must_exist=True, must_be_file=True)
            
            # 检查bundletool可用性
            bundletool_status = self._get_tool_status("bundletool")
            if not bundletool_status["available"]:
                return {
                    "success": False,
                    "error": "bundletool不可用，无法安装APKS文件"
                }
            
            # 安装APKS到默认设备
            install_cmd = [
                "install-apks",
                f"--apks={apks_path}"
            ]
                
            result = self.tool_service.run_tool_command("bundletool", install_cmd, "bundletool")
            
            success = result["success"]
            
            return {
                "success": success,
                "message": "APKS安装成功" if success else "APKS安装失败",
                "output": result["stdout"],
                "error": result.get("stderr") if not success else None
            }
            
        except Exception as e:
            error_msg = f"安装APKS失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
            
    def start_device_monitoring(self, callback: Callable = None):
        """开始设备监控"""
        if self.monitor_running:
            return {
                "success": True,
                "message": "设备监控已在运行中"
            }
            
        self.device_change_callback = callback
        self.monitor_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("设备监控已启动")
        
        return {
            "success": True,
            "message": "设备监控已启动"
        }
        
    def stop_device_monitoring(self):
        """停止设备监控"""
        if not self.monitor_running:
            return {
                "success": True,
                "message": "设备监控未在运行"
            }
            
        self.monitor_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.logger.info("设备监控已停止")
        
        return {
            "success": True,
            "message": "设备监控已停止"
        }
        
    def _monitor_loop(self):
        """设备监控循环"""
        # 使用默认监控间隔或从实例属性获取
        interval = getattr(self, '_monitor_interval', 2)
        
        while self.monitor_running:
            try:
                current_devices = self.get_devices()
                if current_devices["success"]:
                    if self._devices_changed(current_devices["devices"]):
                        self.last_devices = current_devices["devices"]
                        if self.device_change_callback:
                            try:
                                self.device_change_callback(current_devices["devices"])
                            except Exception as e:
                                self.logger.error(f"设备变化回调执行失败: {e}")
                                
                time.sleep(interval)
            except Exception as e:
                self.logger.error(f"设备监控异常: {e}")
                time.sleep(interval)
                
    def _devices_changed(self, current_devices: List[Dict]) -> bool:
        """检查设备列表是否发生变化"""
        if len(current_devices) != len(self.last_devices):
            return True
            
        current_ids = {d["id"]: d["status"] for d in current_devices}
        last_ids = {d["id"]: d["status"] for d in self.last_devices}
        
        return current_ids != last_ids
        
    def install_apk(self, apk_path: str, device_id: str = None) -> Dict[str, Any]:
        """安装APK"""
        try:
            self.validate_file_path(apk_path, must_exist=True, must_be_file=True)
            
            cmd = ["install", "-r", apk_path]  # -r 表示替换安装
            
            # 如果指定了设备ID，添加设备参数
            if device_id:
                cmd = ["-s", device_id] + cmd
                
            result = self.tool_service.run_tool_command("adb", cmd, "adb", timeout=120)
            
            success = "Success" in result["stdout"]
            
            return {
                "success": success,
                "message": "APK安装成功" if success else "APK安装失败",
                "output": result["stdout"],
                "error": result.get("stderr") if not success else None
            }
            
        except Exception as e:
            error_msg = f"安装APK失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
            
    def install_aab(self, aab_path: str, device_id: str = None) -> Dict[str, Any]:
        """安装AAB（使用bundletool）"""
        try:
            self.validate_file_path(aab_path, must_exist=True, must_be_file=True)
            
            # 检查bundletool可用性
            bundletool_status = self._get_tool_status("bundletool")
            if not bundletool_status["available"]:
                return {
                    "success": False,
                    "error": "bundletool不可用，无法安装AAB文件"
                }
            
            # 创建临时目录
            temp_dir = self.create_temp_dir("aab_install_")
            apks_path = temp_dir / "app.apks"
            
            # 生成APKS文件
            build_cmd = [
                "build-apks",
                f"--bundle={aab_path}",
                f"--output={apks_path}"
            ]
            
            if device_id:
                build_cmd.extend(["--connected-device", "--device-id", device_id])
            else:
                build_cmd.append("--connected-device")
                
            result = self.tool_service.run_tool_command("bundletool", build_cmd, "bundletool")
            
            if not result["success"]:
                return {
                    "success": False,
                    "error": f"生成APKS失败: {result.get('stderr', '未知错误')}"
                }
            
            # 安装APKS
            install_cmd = [
                "install-apks",
                f"--apks={apks_path}"
            ]
            
            if device_id:
                install_cmd.extend(["--device-id", device_id])
                
            result = self.tool_service.run_tool_command("bundletool", install_cmd, "bundletool")
            
            success = result["success"]
            
            return {
                "success": success,
                "message": "AAB安装成功" if success else "AAB安装失败",
                "output": result["stdout"],
                "error": result.get("stderr") if not success else None
            }
            
        except Exception as e:
            error_msg = f"安装AAB失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
            
    def uninstall_app(self, package_name: str) -> Dict[str, Any]:
        """卸载应用"""
        try:
            cmd = ["uninstall", package_name]
                
            result = self.tool_service.run_tool_command("adb", cmd, "adb")
            
            success = "Success" in result["stdout"]
            
            return {
                "success": success,
                "message": f"应用 {package_name} 卸载成功" if success else f"应用 {package_name} 卸载失败",
                "output": result["stdout"],
                "error": result.get("stderr") if not success else None
            }
            
        except Exception as e:
            error_msg = f"卸载应用失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
            
    def export_apk(self, package_name: str, device_id: str = None, output_dir: str = None) -> Dict[str, Any]:
        """从设备导出APK文件"""
        try:
            if not device_id:
                devices = self.get_devices()
                if not devices["success"] or not devices["devices"]:
                    return {"success": False, "error": "没有可用设备"}
                device_id = devices["devices"][0]["id"]
            
            # 获取APK路径
            result = self.tool_service.run_tool_command(
                "adb", ["-s", device_id, "shell", "pm", "path", package_name], "adb"
            )
            
            if not result["success"] or not result["stdout"].strip():
                return {
                    "success": False,
                    "error": f"无法找到包 {package_name} 的APK路径"
                }
            
            # 解析APK路径
            apk_path = result["stdout"].strip()
            if apk_path.startswith("package:"):
                apk_path = apk_path[8:]  # 移除 "package:" 前缀
            
            # 设置输出目录
            if not output_dir:
                from pathlib import Path
                
                # 使用默认导出路径
                output_dir = Path.home() / "Downloads" / "exported_apks"
                
                output_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成输出文件名
            output_file = Path(output_dir) / f"{package_name}.apk"
            
            # 使用adb pull导出APK
            pull_result = self.tool_service.run_tool_command(
                "adb", ["-s", device_id, "pull", apk_path, str(output_file)], "adb"
            )
            
            if not pull_result["success"]:
                return {
                    "success": False,
                    "error": f"导出APK失败: {pull_result.get('stderr', '未知错误')}"
                }
            
            # 检查文件是否成功导出
            if not output_file.exists():
                return {
                    "success": False,
                    "error": "APK文件导出失败，文件不存在"
                }
            
            file_size = output_file.stat().st_size
            
            return {
                "success": True,
                "path": str(output_file),
                "size": file_size,
                "message": f"APK已导出到: {output_file}"
            }
            
        except Exception as e:
            error_msg = f"导出APK失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    def get_installed_packages(self, device_id: str = None) -> Dict[str, Any]:
        """获取已安装应用列表"""
        try:
            cmd = ["shell", "pm", "list", "packages", "-3"]  # -3 只显示第三方应用
            if device_id:
                cmd = ["-s", device_id] + cmd
                
            result = self.tool_service.run_tool_command("adb", cmd, "adb")
            
            if not result["success"]:
                error_msg = f"获取应用列表失败: {result.get('stderr', '未知错误')}"
                self.logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "packages": [],
                    "count": 0
                }
            
            packages = []
            stdout = result.get("stdout", "")
            
            # 检查输出是否为空
            if not stdout or not stdout.strip():
                self.logger.warning("ADB命令返回空输出")
                return {
                    "success": True,
                    "packages": [],
                    "count": 0
                }
            
            # 解析包列表
            for line in stdout.strip().split('\n'):
                if line.startswith('package:'):
                    package_name = line.replace('package:', '').strip()
                    if package_name:
                        packages.append(package_name)
            
            self.logger.info(f"成功获取到 {len(packages)} 个应用包")
            return {
                "success": True,
                "packages": packages,
                "count": len(packages)
            }
            
        except Exception as e:
            error_msg = f"获取应用列表失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "packages": [],
                "count": 0
            }
            
    def reboot_device(self, device_id: str = None) -> Dict[str, Any]:
        """重启设备"""
        try:
            cmd = ["reboot"]
            if device_id:
                cmd = ["-s", device_id] + cmd
                
            result = self.tool_service.run_tool_command("adb", cmd, "adb", timeout=10)
            
            return {
                "success": result["success"],
                "message": "设备重启命令已发送" if result["success"] else "设备重启失败",
                "error": result.get("stderr") if not result["success"] else None
            }
            
        except Exception as e:
            error_msg = f"重启设备失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
            
    def execute_shell_command(self, command: str, device_id: str = None) -> Dict[str, Any]:
        """执行shell命令"""
        try:
            cmd = ["shell", command]
            if device_id:
                cmd = ["-s", device_id] + cmd
                
            result = self.tool_service.run_tool_command("adb", cmd, "adb")
            
            return {
                "success": result["success"],
                "output": result["stdout"],
                "error": result.get("stderr") if not result["success"] else None
            }
            
        except Exception as e:
            error_msg = f"执行shell命令失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
            
    def start_realtime_device_monitoring(self) -> Dict[str, Any]:
        """启动实时设备监控（用于Electron主进程调用）"""
        try:
            import json
            import time
            
            # 持续监控设备变化并输出JSON格式
            last_devices = []
            
            while True:
                current_devices_result = self.get_devices()
                if current_devices_result["success"]:
                    current_devices = current_devices_result["devices"]
                    
                    # 检查设备是否有变化
                    if self._devices_changed_simple(current_devices, last_devices):
                        # 输出设备变化事件
                        event = {
                            "type": "device_change",
                            "timestamp": time.time(),
                            "devices": current_devices
                        }
                        print(json.dumps(event), flush=True)
                        last_devices = current_devices.copy()
                
                time.sleep(2)  # 每2秒检查一次
                
        except KeyboardInterrupt:
            return {"success": True, "message": "监控已停止"}
        except Exception as e:
            self.logger.error(f"实时设备监控失败: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _devices_changed_simple(self, current: List[Dict], last: List[Dict]) -> bool:
        """简单的设备变化检测"""
        if len(current) != len(last):
            return True
        
        current_ids = {device.get("id") for device in current}
        last_ids = {device.get("id") for device in last}
        
        return current_ids != last_ids

    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        # 直接从tool_manager获取所有工具状态，避免重复调用
        all_tools_status = self.tool_service.get_tools_status()
        adb_status = all_tools_status.get("adb", {"available": False})
        
        devices_result = self.get_devices()
        
        return {
            "name": self.name,
            "adb_available": adb_status["available"],
            "adb_path": adb_status.get("path"),
            "monitoring": self.monitor_running,
            "connected_devices": devices_result.get("count", 0),
            "devices": devices_result.get("devices", [])
        }
