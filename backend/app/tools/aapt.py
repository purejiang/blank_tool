import os
import platform
import re
from typing import List, Dict, Any, Union

from app.tools.base_tool import CommandTool
from app.common.base_executor import CommandExecutionContext

class Aapt(CommandTool):
    """AAPT工具类"""

    def validate_tool(self) -> bool:
        tool_path = self.tool_path
        if not os.path.exists(tool_path):
            return False

        result = super().execute([self.tool_path, "--help"])
        stdout = result.get("stdout", "") if isinstance(result, dict) else ""
        stderr = result.get("stderr", "") if isinstance(result, dict) else ""
        output = f"{stdout}\n{stderr}"
        return ("aapt2" in output.lower()) or ("aapt" in output.lower())

    def get_possible_tool_names(self) -> List[str]:
        """获取可能的 aapt 工具名称列表"""
        if platform.system() == "Windows":
            return ["aapt.exe", "aapt2.exe"]
        else:
            return ["aapt", "aapt2"]

    def get_tool_version(self) -> str:
        tool_path = self.tool_path
        if not tool_path or not os.path.exists(tool_path):
            return ""
        result = super().execute([self.tool_path, "version"])
        stdout = result.get("stdout", "") if isinstance(result, dict) else ""
        stderr = result.get("stderr", "") if isinstance(result, dict) else ""
        output = f"{stdout}\n{stderr}"
        match = re.search(r"(\d[\d\.-]+)", output)
        if match:
            return match.group(1).strip()
        return ""

    def execute(self, command: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
        if isinstance(command, list):
            return super().execute(command, **kwargs)
        else:
            return super().execute(command, **kwargs)
