import os
import platform
from typing import List

from app.tools.base_tool import CommandTool
from app.common.base_executor import CommandExecutionContext


class Jarsigner(CommandTool):
    """jarsigner 封装"""

    def validate_tool(self) -> bool:
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False
        result = super().execute([self.tool_path, "-h"])
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return "jarsigner" in output.lower()

    def get_possible_tool_names(self) -> List[str]:
        if platform.system() == "Windows":
            return ["jarsigner.exe", "jarsigner.bat"]
        return ["jarsigner"]

    def get_tool_version(self) -> str:
        result = super().execute([self.tool_path])
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return "未知"
