import os
import platform
from typing import List, Tuple

from app.tools.base_tool import BinaryTool


class Zipalign(BinaryTool):
    """zipalign 封装"""

    def _validate_tool(self) -> bool:
        """See ``probe`` — it is the single source of truth for this tool."""
        return self.probe()[0]

    def _get_possible_tool_names(self) -> List[str]:
        if platform.system() == "Windows":
            return ["zipalign.exe"]
        return ["zipalign"]

    def _get_tool_version(self) -> str:
        """See ``probe`` — it is the single source of truth for this tool."""
        return self.probe()[1]

    def probe(self) -> Tuple[bool, str]:
        """One no-arg run is all this tool can tell us.

        ``zipalign`` has no version flag, so the version half is always empty —
        the second subprocess the historical two-step probe launched was pure
        waste.
        """
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False, ""
        result = self.execute([])
        stdout = result.get("stdout", "") if isinstance(result, dict) else ""
        stderr = result.get("stderr", "") if isinstance(result, dict) else ""
        output = f"{stdout}\n{stderr}"
        is_valid = ("Zip alignment" in output) or ("zipalign" in output.lower())
        return is_valid, ""
