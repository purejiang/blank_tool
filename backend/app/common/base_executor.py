#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础命令执行器
提供底层命令执行的抽象和实现
"""

import subprocess
import traceback
import shutil
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union
from app.utils.logger import Logger

class CommandExecutionContext:
    """命令执行上下文"""
    
    def __init__(self, 
                 cwd: str = None,
                 timeout: int = 120,
                 encoding: str = 'utf-8',
                 errors: str = 'ignore',
                 text: bool = True,
                 shell: bool = False,
                 capture_output: bool = True,
                 env: Dict[str, str] = None,
                 stream: bool = False,
                 log_output: bool = True):
        self.cwd = cwd
        self.timeout = timeout
        self.encoding = encoding
        self.errors = errors
        self.text = text
        self.shell = shell
        self.capture_output = capture_output
        self.env = env
        self.stream = stream
        self.log_output = log_output

class BaseCommandExecutor(ABC):
    """命令执行器抽象基类"""
    
    def __init__(self):
        self.name =  self.__class__.__name__
        self.logger = Logger.get_logger(self.name)
    
    @abstractmethod
    def execute(self, command: Union[str, List[str]], context: CommandExecutionContext = None) -> Dict[str, Any]:
        """执行命令"""
        pass
    
    @abstractmethod
    def validate_command(self, command: Union[str, List[str]]) -> bool:
        """验证命令是否有效"""
        pass
    
    def _log_info(self, message: str):
        """记录信息日志"""
        if self.logger:
            self.logger.info(message)
    
    def _log_warning(self, message: str):
        """记录警告日志"""
        if self.logger:
            self.logger.warning(message)
    
    def _log_error(self, message: str):
        """记录错误日志"""
        if self.logger:
            self.logger.error(message)
    
    def _log_debug(self, message: str):
        """记录调试日志"""
        if self.logger:
            self.logger.debug(message)


class CommandExecutor(BaseCommandExecutor):
    """命令行执行器"""
    
    def execute(self, command: Union[str, List[str]], 
                context: CommandExecutionContext) -> Union[Dict[str, Any], subprocess.Popen]:
        """执行系统命令"""

        if isinstance(command, str):
            cmd_str = command
            if context.shell is None:
                context.shell = True
        else:
            cmd_str = ' '.join(command)
            if context.shell is None:
                context.shell = False
        
        self._log_info(f"[COMMAND] 执行命令: {cmd_str}")
        self._log_debug(f"[CONTEXT] cwd={context.cwd} shell={context.shell} stream={context.stream}")

        if context.stream:
            return subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=context.text,
                encoding=context.encoding,
                errors=context.errors,
                cwd=context.cwd,
                shell=context.shell,
                env=context.env
            )
        
        try:
            result = subprocess.run(
                command,
                capture_output=context.capture_output,
                encoding=context.encoding,
                errors=context.errors,
                text=context.text,
                timeout=context.timeout,
                cwd=context.cwd,
                shell=context.shell,
                env=context.env
            )
            
            success = result.returncode == 0
            
            if not success:
                self._log_warning(f"[COMMAND] 返回码: {result.returncode}")
                if context.log_output:
                    if result.stdout:
                        self._log_warning(f"[STDOUT] {result.stdout.strip()}")
                    if result.stderr:
                        self._log_warning(f"[STDERR] {result.stderr.strip()}")
            else:
                self._log_debug(f"[COMMAND] 返回码: {result.returncode}")
                if context.log_output:
                    if result.stdout:
                        self._log_debug(f"[STDOUT] {result.stdout.strip()}")
                    if result.stderr:
                        self._log_debug(f"[STDERR] {result.stderr.strip()}")
                
            return {
                "success": success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": cmd_str
            }
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"命令执行超时 ({context.timeout}s): {cmd_str}"
            self._log_error(f"[COMMAND] {error_msg}")
            raise e
        except Exception as e:
            error_msg = f"命令执行异常: {cmd_str}, 错误: {str(e)}"
            tb = traceback.format_exc()
            self._log_error(f"[COMMAND] {error_msg}\n{tb}")
            raise e
    
    def validate_command(self, command: Union[str, List[str]]) -> bool:
        """验证系统命令是否有效"""
        if isinstance(command, str):
            cmd_name = command.split()[0] if command.strip() else ""
        else:
            cmd_name = command[0] if command else ""
        
        if not cmd_name:
            return False
            
        return shutil.which(cmd_name) is not None