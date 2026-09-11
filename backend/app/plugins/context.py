#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PluginContext — what a plugin is allowed to touch.

Extends the generic :class:`~app.common.stream_context.StreamContext`
(log / step / complete / cancel streaming) with plugin-only capabilities:

* ``get_tool`` / named tool properties — the built-in runtime tools
  (adb / apktool / aapt / apksigner / zipalign) via ToolRegistry.
* ``which`` — locate an external executable (env override → ``runtime/``
  → PATH) for tools that ship OUTSIDE the bundled runtime (jadx, ...).
* ``run_command`` — run an external CLI with line-streamed output,
  timeout and cooperative cancellation.
* ``work_dir`` — a per-run directory for artifacts.
* ``finish`` — emit ``complete`` once and return the result; the
  standard way for a plugin to end.
"""

import os
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

from app.common.stream_context import StreamContext
from app.tools.tool_manager import ToolManager
from app.utils.env import get_runtime_dir, get_task_dir


class PluginContext(StreamContext):
    """
    插件执行上下文
    提供给插件脚本使用的工具和环境信息
    """

    def __init__(self, plugin_name: str, stream_handler: Optional[Callable] = None):
        super().__init__(plugin_name, stream_handler)
        self._tool_manager = ToolManager.instance()

    # ------------------------------------------------------------ tools --

    def get_tool(self, tool_name: str) -> Any:
        """获取指定工具实例"""
        tool = self._tool_manager.get_tool(tool_name)
        if not tool or not getattr(tool, "is_valid", False):
            raise Exception(f"工具 {tool_name} 不可用")
        return tool

    # named sugar — ``context.adb`` is just ``context.get_tool("adb")``
    def _tool_prop(name):
        return property(lambda self: self.get_tool(name))

    adb = _tool_prop("adb")
    apktool = _tool_prop("apktool")
    aapt = _tool_prop("aapt")
    apksigner = _tool_prop("apksigner")
    zipalign = _tool_prop("zipalign")

    # ------------------------------------------------- external executables --

    def which(self, name: str) -> Optional[str]:
        """Locate an external executable by name.

        Resolution order:
          1. ``BT_TOOL_<NAME>`` env var (uppercase, non-alnum → ``_``) —
             explicit user override pointing straight at the binary.
          2. ``<runtime_dir>/<name>/`` — drop the binary (or e.g.
             ``bin/<name>.bat``) there and it is picked up.
          3. ``shutil.which`` — the system PATH.

        Returns the resolved absolute path, or None when not found.
        """
        env_key = "BT_TOOL_" + "".join(
            c if c.isalnum() else "_" for c in name.upper()
        )
        override = os.environ.get(env_key)
        if override and os.path.isfile(override):
            return override

        runtime_root = get_runtime_dir()
        for base in (os.path.join(runtime_root, name),
                     os.path.join(runtime_root, name, "bin")):
            if not os.path.isdir(base):
                continue
            for ext in (".exe", ".bat", ".cmd", ""):
                cand = os.path.join(base, name + ext)
                if os.path.isfile(cand):
                    return cand

        return shutil.which(name)

    def finish(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Standard plugin exit: emit ``complete`` once and return the
        result — ``return context.finish({...})`` keeps the
        "complete exactly once" contract unbreakable by duplication."""
        self.complete(result)
        return result

    def run_command(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        on_line: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Run an external command with line-streamed output and cancellation.

        stdout and stderr are merged (``stderr=STDOUT``); each line is
        forwarded to ``on_line`` (when given) AND emitted as a ``log``
        event. Cancellation is cooperative: the read loop polls
        :meth:`is_cancelled` between lines, then terminate() → kill().

        Returns ``{"returncode": int|None, "cancelled": bool,
        "duration_ms": int, "output": [str]}``. ``returncode`` is None
        when the process had to be killed. A non-zero return code is NOT
        an exception — the plugin decides how to react.
        """
        started = time.time()
        output: List[str] = []
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        cancelled = False
        try:
            for line in proc.stdout:
                line = line.rstrip("\r\n")
                output.append(line)
                if on_line:
                    try:
                        on_line(line)
                    except Exception:
                        self._logger.exception("on_line callback failed")
                self.log(line)
                if self.is_cancelled():
                    cancelled = True
                    proc.terminate()
                    break
            if not cancelled:
                # stdin drained — wait for exit, still honoring cancel/timeout
                while True:
                    try:
                        proc.wait(timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        if self.is_cancelled():
                            cancelled = True
                            proc.terminate()
                            try:
                                proc.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            break
                        if timeout and time.time() - started > timeout:
                            proc.terminate()
                            try:
                                proc.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            break
        finally:
            if proc.poll() is None:
                proc.kill()
        return {
            "returncode": proc.returncode,
            "cancelled": cancelled,
            "duration_ms": int((time.time() - started) * 1000),
            "output": output,
        }

    # ------------------------------------------------------------ work dir --

    def work_dir(self, task_id: str = "", sub: str = "") -> str:
        """Return (and create) a directory for this run's artifacts.

        With a ``task_id`` (the streaming wrapper injects one) it is the
        per-task dir under ``<tasks_root>/<task_id>/``; without one it
        falls back to ``<output_dir>/plugins/``. ``sub`` optionally
        appends a named subdirectory.
        """
        if task_id:
            base = get_task_dir(task_id)
        else:
            from app.utils.env import get_output_dir
            base = os.path.join(get_output_dir(), "plugins")
            os.makedirs(base, exist_ok=True)
        path = os.path.join(base, sub) if sub else base
        os.makedirs(path, exist_ok=True)
        return path
