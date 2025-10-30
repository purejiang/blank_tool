#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理Android设备日志（logcat）
"""

import subprocess
import threading
import json

from typing import Dict, Any, Callable

from core.base_service import BaseService
from .tool_service import get_tool_service

class LogCatService(BaseService):
    """日志管理器"""
    
    def __init__(self):
        super().__init__("LogCatService")
        self.tool_service = get_tool_service()
        self.log_process = None
        self.log_thread = None
        self.log_callback = None
        self.log_running = False
        self.current_device = None
        self.current_level = None

    def start_logcat(self, device_id: str = None, log_level: str = None, 
                    callback: Callable = None, tag_filter: str = None) -> Dict[str, Any]:
        """启动logcat监控"""
        try:
            # 如果已经在运行，先停止
            if self.log_running:
                self.stop_logcat()
            
            # 构建logcat命令
            cmd = ["logcat", "-v", "time"]
            
            # 添加设备参数
            if device_id:
                cmd = ["-s", device_id] + cmd
            
            # 添加日志级别过滤
            if log_level:
                level_map = {
                    "verbose": "V",
                    "debug": "D", 
                    "info": "I",
                    "warn": "W",
                    "error": "E",
                    "fatal": "F"
                }
                level_char = level_map.get(log_level.lower(), "V")
                if tag_filter:
                    cmd.append(f"{tag_filter}:{level_char}")
                else:
                    cmd.append(f"*:{level_char}")
            elif tag_filter:
                cmd.append(f"{tag_filter}:V")
            
            # 启动logcat进程 - 使用异步方式
            # 获取 adb 工具路径
            adb_command = self.tool_service.get_tool_command("adb", "adb")
            if not adb_command:
                return {
                    "success": False,
                    "error": "ADB工具不可用"
                }
            
            # 构建完整的adb命令 - adb_command已经是列表
            full_cmd = adb_command + cmd
            
            self.logger.info(f"启动logcat命令: {' '.join(full_cmd)}")
            
            # 启动进程
            self.log_process = subprocess.Popen(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # 设置运行状态
            self.log_running = True
            self.current_device = device_id
            self.current_level = log_level
            
            # 设置回调函数 - 使用stdout输出而非回调参数
            self.log_callback = self._output_log_to_stdout
            
            # 启动读取线程
            self.log_thread = threading.Thread(target=self._read_log_output, daemon=True)
            self.log_thread.start()
            
            # 生成进程ID用于跟踪
            import uuid
            process_id = str(uuid.uuid4())
            
            self.logger.info(f"logcat已启动 - 设备: {device_id or '默认'}, 级别: {log_level or '全部'}, 标签: {tag_filter or '全部'}")
            
            return {
                "success": True,
                "message": "logcat监控已启动",
                "device_id": device_id,
                "log_level": log_level,
                "tag_filter": tag_filter,
                "processId": process_id
            }
            
        except Exception as e:
            error_msg = f"启动logcat失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    def stop_logcat(self) -> Dict[str, Any]:
        """停止logcat监控"""
        try:
            self.log_running = False
            
            if self.log_process:
                try:
                    self.log_process.terminate()
                    # 等待进程结束，最多等待3秒
                    try:
                        self.log_process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.log_process.kill()
                        self.log_process.wait()
                except Exception as e:
                    self.logger.warning(f"终止logcat进程时出错: {e}")
                finally:
                    self.log_process = None
            
            if self.log_thread and self.log_thread.is_alive():
                try:
                    self.log_thread.join(timeout=2)
                except Exception as e:
                    self.logger.warning(f"等待日志线程结束时出错: {e}")
                finally:
                    self.log_thread = None
            
            self.log_callback = None
            self.current_device = None
            self.current_level = None
            
            self.logger.info("logcat监控已停止")
            
            return {
                "success": True,
                "message": "logcat监控已停止"
            }
            
        except Exception as e:
            error_msg = f"停止logcat失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    def _read_log_output(self):
        """读取日志输出"""
        try:
            while self.log_running and self.log_process:
                try:
                    line = self.log_process.stdout.readline()
                    if not line:
                        break
                        
                    line = line.strip()
                    if line and self.log_callback:
                        try:
                            # 解析日志行
                            log_entry = self._parse_log_line(line)
                            self.log_callback(log_entry)
                        except Exception as e:
                            self.logger.warning(f"日志回调执行失败: {e}")
                            
                except Exception as e:
                    if self.log_running:
                        self.logger.error(f"读取日志输出时出错: {e}")
                    break
                    
        except Exception as e:
            self.logger.error(f"日志读取线程异常: {e}")
        finally:
            self.log_running = False

    def _parse_log_line(self, line: str) -> Dict[str, Any]:
        """解析日志行"""
        try:
            # logcat时间格式: MM-DD HH:MM:SS.mmm PID TID LEVEL TAG: MESSAGE
            parts = line.split(None, 5)
            if len(parts) >= 6:
                return {
                    "timestamp": f"{parts[0]} {parts[1]}",
                    "pid": parts[2],
                    "tid": parts[3], 
                    "level": parts[4],
                    "tag": parts[5].split(':', 1)[0] if ':' in parts[5] else "",
                    "message": parts[5].split(':', 1)[1].strip() if ':' in parts[5] else parts[5],
                    "raw": line
                }
            else:
                return {
                    "raw": line,
                    "message": line
                }
        except Exception:
            return {
                "raw": line,
                "message": line
            }

    def _output_log_to_stdout(self, log_entry):
        """将日志输出到stdout，供主进程捕获"""
        try:
            # 构造日志输出格式，供主进程解析
            output_data = {
                "type": "logcat_output",
                "data": log_entry
            }
            # 输出到stdout，主进程会捕获这个输出
            print(f"LOGCAT_OUTPUT:{json.dumps(output_data)}", flush=True)
        except Exception as e:
            self.logger.warning(f"输出日志到stdout失败: {e}")

    def is_running(self) -> bool:
        """检查logcat是否正在运行"""
        return self.log_running and self.log_process is not None

    def get_status(self) -> Dict[str, Any]:
        """获取logcat状态"""
        return {
            "running": self.is_running(),
            "device": self.current_device,
            "level": self.current_level,
            "process_id": id(self.log_process) if self.log_process else None
        }

    def cleanup(self):
        """清理资源"""
        if self.log_running:
            self.stop_logcat()
        super().cleanup()
