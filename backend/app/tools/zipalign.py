import os
import platform
from typing import List

from app.tools.base_tool import BinaryTool


class Zipalign(BinaryTool):
    """zipalign 封装"""

    def _validate_tool(self) -> bool:
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False
        # Use self.execute to handle tool path
        result = self.execute([]) # zipalign without args usually prints usage
        stdout = result.get("stdout", "") if isinstance(result, dict) else ""
        stderr = result.get("stderr", "") if isinstance(result, dict) else ""
        output = f"{stdout}\n{stderr}"
        return ("Zip alignment" in output) or ("zipalign" in output.lower())

    def _get_possible_tool_names(self) -> List[str]:
        if platform.system() == "Windows":
            return ["zipalign.exe"]
        return ["zipalign"]

    def _get_tool_version(self) -> str:
        # zipalign doesn't have a version flag usually, but let's try
        result = self.execute([])
        return "未知"
