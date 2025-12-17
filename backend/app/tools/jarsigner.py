import os
import platform
from typing import List

from app.tools.base_tool import BinaryTool


class Jarsigner(BinaryTool):
    """jarsigner 封装"""

    def _validate_tool(self) -> bool:
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False
        result = self.execute(["-h"])
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return "jarsigner" in output.lower()

    def _get_possible_tool_names(self) -> List[str]:
        if platform.system() == "Windows":
            return ["jarsigner.exe", "jarsigner.bat"]
        return ["jarsigner"]

    def _get_tool_version(self) -> str:
        result = self.execute([])
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return "未知"
