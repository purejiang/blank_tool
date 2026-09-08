from typing import Any, Dict, Optional, Callable
from app.tools.tool_manager import ToolManager
from app.utils.logger import Logger
import os

class PluginContext:
    """
    插件执行上下文
    提供给插件脚本使用的工具和环境信息
    """
    def __init__(self, plugin_name: str, stream_handler: Optional[Callable] = None):
        self.plugin_name = plugin_name
        self._stream_handler = stream_handler
        self._tool_manager = ToolManager.instance()
        self._logger = Logger.get_logger(f"Plugin.{plugin_name}")

    @property
    def logger(self):
        """获取日志记录器"""
        return self._logger

    def log(self, message: str):
        """记录日志并推送到前端"""
        self._logger.info(message)
        if self._stream_handler:
            self._stream_handler({
                "type": "log",
                "payload": f"[{self.plugin_name}] {message}"
            })

    def error(self, message: str):
        """记录错误并推送到前端"""
        self._logger.error(message)
        if self._stream_handler:
            self._stream_handler({
                "type": "error",
                "payload": f"[{self.plugin_name}] {message}"
            })

    def step_start(self, index: int, action: str):
        """Emit a per-step ``step_start`` event (index is 1-based).

        Lets the frontend render the row immediately (pending state) instead
        of only showing everything at ``complete`` time.
        """
        if self._stream_handler:
            self._stream_handler({
                "type": "step_start",
                "payload": {"index": index, "action": action},
            })

    def step(self, record: dict):
        """Emit a per-step ``step`` event with the finished step record.

        Payload shape matches the entry appended to ``result['steps']``:
        ``{index, action, ok, message, duration_ms[, screenshot]}``.
        """
        if self._stream_handler:
            self._stream_handler({
                "type": "step",
                "payload": record,
            })

    def complete(self, payload: dict):
        """Emit the terminal ``complete`` event so the frontend's
        ``waitForPhase('operation')`` latch resolves.

        Must be called exactly once at the end of a plugin run (success,
        abort, or cancel). After this, the streaming wrapper sends the
        final ``finished: True`` envelope.
        """
        self._logger.info(f"[{self.plugin_name}] complete: {payload}")
        if self._stream_handler:
            self._stream_handler({
                "type": "complete",
                "payload": payload,
            })

    def is_cancelled(self) -> bool:
        """Return True if the task was cancelled (stop_event set).

        The stop_event is attached to the stream callback by
        api_handler.stream_handler (``stream_callback.bt_stop_event``).
        Returns False when running outside a streaming context.
        """
        stop_event = getattr(self._stream_handler, "bt_stop_event", None)
        if stop_event is None:
            return False
        return bool(stop_event.is_set())

    def get_tool(self, tool_name: str) -> Any:
        """获取指定工具实例"""
        tool = self._tool_manager.get_tool(tool_name)
        if not tool or not getattr(tool, "is_valid", False):
            raise Exception(f"工具 {tool_name} 不可用")
        return tool

    @property
    def adb(self):
        """获取 ADB 工具"""
        return self.get_tool("adb")

    @property
    def apktool(self):
        """获取 Apktool 工具"""
        return self.get_tool("apktool")

    @property
    def aapt(self):
        """获取 AAPT 工具"""
        return self.get_tool("aapt")
        
    @property
    def apksigner(self):
        """获取 Apksigner 工具"""
        return self.get_tool("apksigner")

    @property
    def zipalign(self):
        """获取 Zipalign 工具"""
        return self.get_tool("zipalign")
