import os
import re
from typing import List

from app.tools.base_tool import JavaTool

class BundleTool(JavaTool):
    """BundleTool工具类"""

    def _validate_tool(self) -> bool:
        if not os.path.exists(self.tool_path):
            return False
        result = self.execute(["help"])
        output = result.get("stdout", "").lower() if isinstance(result, dict) else ""
        return "bundletool help" in output

    def _get_possible_tool_names(self) -> List[str]:
        """获取可能的 bundletool 工具名称列表"""
        return ["bundletool.jar", "bundletool"]

    def _get_tool_version(self) -> str:
        """获取 bundletool 工具版本"""
        result = self.execute(["version"])
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        match = re.search(r"(\d+\.\d+\.\d+)", output)
        if match:
            return match.group(1)
        return ""
