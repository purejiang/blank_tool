import os
import platform
import re
from typing import List, Dict, Any, Union

from app.tools.base_tool import CommandTool
from app.common.base_executor import CommandExecutionContext

class BundleTool(CommandTool):
    """BundleTool工具类"""

    def validate_tool(self) -> bool:
        if not os.path.exists(self.tool_path):
            return False
        java = self.get_java_path()
        result = super().execute([java, "-jar", self.tool_path, "help"])
        output = result.get("stdout", "").lower() if isinstance(result, dict) else ""
        return "bundletool help" in output

    def get_possible_tool_names(self) -> List[str]:
        """获取可能的 bundletool 工具名称列表"""
        return ["bundletool.jar", "bundletool"]

    def get_tool_version(self) -> str:
        """获取 bundletool 工具版本"""
        java = self.get_java_path()
        result = super().execute([java, "-jar", self.tool_path, "version"])
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        match = re.search(r"(\d+\.\d+\.\d+)", output)
        if match:
            return match.group(1)
        return ""