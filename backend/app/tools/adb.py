import os
import platform
import re
from typing import List, Dict
from app.tools.base_tool import BinaryTool
from app.common.base_executor import CommandExecutionContext

class Adb(BinaryTool):
    """ADB工具类"""

    def _validate_tool(self) -> bool:
        """
        验证 adb 工具是否有效
        
        检查 adb 工具路径是否存在，并且通过执行 adb version 命令来验证工具是否有效。
        
        Returns:
            bool: 如果工具路径存在且 adb version 命令执行成功且输出包含 "Android Debug Bridge"，则返回 True，否则返回 False
        """
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False
        # 可以通过执行 adb version 命令来验证工具是否有效
        command = ["version"]
        result = self.execute(command)
        output = result.get("stdout", "")
        is_valid = "Android Debug Bridge" in output
        self._logger.info(f"adb is_valid: {is_valid}")
        return is_valid

    def _get_possible_tool_names(self) -> List[str]:
        """
        获取可能的 adb 工具名称列表
        
        根据操作系统返回可能的 adb 工具名称，Windows 下为 "adb.exe"，其他系统下为 "adb"。
        
        Returns:
            List[str]: 可能的 adb 工具名称列表，如 ["adb.exe"] 或 ["adb"]
        """
        if platform.system() == "Windows":
            return ["adb.exe"]
        else:
            return ["adb"]

    def _get_tool_version(self) -> str:
        """
        获取 adb 工具版本
        
        执行 adb version 命令，解析输出中的版本号。
        
        Returns:
            str: adb 工具版本号，如 "1.0.41"，如果无法获取则返回空字符串
        """
        command = ["version"]
        result = self.execute(command)
        output = result.get("stdout", "")
        match = re.search(r"version (\S+)", output)
        self._logger.info(f"adb version output: {output}")
        if match:
            return match.group(1)
        return ""
    
    def get_devices(self) -> List[str]:
        """
        获取连接的设备列表
        
        执行 adb devices 命令，解析输出中的设备ID列表。
        
        Returns:
            List[str]: 连接的设备ID列表，如 ["emulator-5554", "0123456789ABCDEF"]
        """
        command = ["devices"]
        result = self.execute(command)
        output = result.get("stdout", "")
        lines = output.strip().splitlines()
        devices = []
        for line in lines[1:]:  # 跳过第一行标题
            if line.strip():
                device_id = line.split("\t")[0]
                devices.append(device_id)
        self._logger.info(f"adb devices: {devices}")
        return devices

    def get_devices_detail(self) -> List[Dict[str, str]]:
        """
        获取连接的设备详细信息列表
        
        执行 adb devices -l 命令，解析输出中的设备详细信息。
        
        Returns:
            List[Dict[str, str]]: 连接的设备详细信息列表，每个元素为 {"id": str, "name": str, "status": str}
        """
        command = ["devices", "-l"]
        result = self.execute(command)
        output = result.get("stdout", "")
        lines = output.strip().splitlines()
        devices: List[Dict[str, str]] = []
        for line in lines[1:]:
            s = line.strip()
            if not s:
                continue
            cols = [c for c in s.split() if c]
            dev_id = cols[0]
            status = cols[1] if len(cols) > 1 else ""
            extras: Dict[str, str] = {}
            for tok in cols[2:]:
                if ":" in tok:
                    k, v = tok.split(":", 1)
                    extras[k] = v
            ctx = CommandExecutionContext()
            props = self.execute(["-s", dev_id, "shell", "getprop"], ctx)
            prop_text = props.get("stdout", "") or ""
            kv = {}
            for ln in prop_text.splitlines():
                m = re.match(r"\[(.+?)\]: \[(.*)\]", ln)
                if m:
                    kv[m.group(1)] = m.group(2)
            brand = kv.get("ro.product.brand", "")
            model = kv.get("ro.product.model", extras.get("model", ""))
            name = (brand + "-" + model).strip("-") if (brand or model) else (extras.get("device") or dev_id)
            devices.append({"id": dev_id, "name": name, "status": status})
        self._logger.info(f"adb devices detail: {devices}")
        return devices

    def start_logcat(self, stream_callback, device_id: str = None):
        command = []
        if device_id:
            command += ["-s", device_id]
        command += ["logcat", "-v", "threadtime"]
        context = CommandExecutionContext(stream=True)
        process = self.execute(command, context)
        process_id = f"{process.pid}"
        self._running_processes[process_id] = process
        try:
            stream_callback({"type": "started", "payload": {"process_id": process_id}})
            self._logger.info(f"adb logcat started: {process_id}")
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                stream_callback({"type": "log", "payload": {"process_id": process_id, "line": line.strip()}})
                self._logger.info(f"adb logcat log: {line.strip()}")
        except Exception:
            pass
        finally:
            try:
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()
            except Exception:
                pass
            rc = process.wait()
            self._logger.info(f"adb logcat finished: {process_id}, return code: {rc}")
            stream_callback({"type": "process_finished", "payload": {"process_id": process_id, "return_code": rc}})
    
    def stop_logcat(self, process_id: str):
        """
        停止 adb logcat 流输出
        
        调用 stop_process 方法停止指定进程ID的 logcat 流输出。
        
        Args:
            process_id (str): 要停止的 logcat 进程ID
        """
        super().stop_process(process_id)