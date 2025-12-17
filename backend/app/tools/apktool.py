import os
import platform
from typing import List

from app.tools.base_tool import JavaTool


class ApkTool(JavaTool):
    """apktool 封装"""

    def _validate_tool(self) -> bool:
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False
        
        command = ["h"]
        result = self.execute(command)
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return "apktool" in output.lower()

    def _get_possible_tool_names(self) -> List[str]:
        if platform.system() == "Windows":
            return ["apktool.bat", "apktool.jar", "apktool.exe"]
        return ["apktool"]

    def _get_tool_version(self) -> str:
        command = ["-version"]
        result = self.execute(command)
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return output.strip()
