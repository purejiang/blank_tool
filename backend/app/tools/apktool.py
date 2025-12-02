import os
import platform
from typing import List

from app.tools.base_tool import CommandTool
from app.common.base_executor import CommandExecutionContext


class ApkTool(CommandTool):
    """apktool 封装"""

    def validate_tool(self) -> bool:
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False
        java = self.get_java_path()
        result = super().execute([java, "-jar", self.tool_path, "h"])
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return "apktool" in output.lower()

    def get_possible_tool_names(self) -> List[str]:
        if platform.system() == "Windows":
            return ["apktool.bat", "apktool.jar", "apktool.exe"]
        return ["apktool"]

    def get_tool_version(self) -> str:
        java = self.get_java_path()
        result = super().execute([java, "-jar", self.tool_path, "-version"])
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return output.strip()
