import os
import platform
from typing import List, Tuple

from app.tools.base_tool import BinaryTool


class Jarsigner(BinaryTool):
    """jarsigner 封装"""

    def _validate_tool(self) -> bool:
        """See ``probe`` — it is the single source of truth for this tool."""
        return self.probe()[0]

    def _get_possible_tool_names(self) -> List[str]:
        if platform.system() == "Windows":
            return ["jarsigner.exe", "jarsigner.bat"]
        return ["jarsigner"]

    def _get_tool_version(self) -> str:
        """See ``probe`` — it is the single source of truth for this tool."""
        return self.probe()[1]

    def probe(self) -> Tuple[bool, str]:
        """``jarsigner -h`` validates; the version half is always empty.

        The version only ever appeared inside the usage banner, which the old
        ``_get_tool_version`` discarded — so keeping the validation output
        costs one subprocess instead of two.
        """
        if not self.tool_path or not os.path.exists(self.tool_path):
            return False, ""
        result = self.execute(["-h"])
        output = result.get("stdout", "") if isinstance(result, dict) else ""
        return ("jarsigner" in output.lower()), ""
