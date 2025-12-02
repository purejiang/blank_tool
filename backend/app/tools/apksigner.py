import os
import platform
from typing import List

from app.tools.base_tool import CommandTool
from app.common.base_executor import CommandExecutionContext


class Apksigner(CommandTool):
    """apksigner 封装"""

    def validate_tool(self) -> bool:
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False
        java = self.get_java_path()
        command = [java, "-jar", self.tool_path, "--help"]
        result = super().execute(command)
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return "apksigner" in output.lower()

    def get_possible_tool_names(self) -> List[str]:
        if platform.system() == "Windows":
            return ["apksigner.jar", "apksigner.exe"]
        return ["apksigner"]

    def get_tool_version(self) -> str:
        """获取 apksigner 工具版本"""
        if not self.tool_path or not os.path.exists(self.tool_path):
            return ""
        java = self.get_java_path()
        command = [java, "-jar", self.tool_path, "version"]
        result = super().execute(command)
        stdout = result.get("stdout", "") if isinstance(result, dict) else ""
        stderr = result.get("stderr", "") if isinstance(result, dict) else ""
        output = f"{stdout}\n{stderr}"
        import re
        match = re.search(r"(\d[\d\.-]+)", output)
        if match:
            return match.group(1).strip()
        return output.strip()

    def get_name(self) -> str:
        return "apksigner"

