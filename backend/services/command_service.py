#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的命令执行服务
提供所有命令行执行的抽象化接口
"""

import subprocess
import shutil
from typing import Dict, Any, List, Union, Optional, Callable
from abc import ABC, abstractmethod

from core.base_service import BaseService
from core.exceptions import ToolError

class CommandExecutor(ABC):
    """命令执行器抽象基类"""
    
    @abstractmethod
    def execute(self, command: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
        """执行命令"""
        pass
    
    @abstractmethod
    def validate_command(self, command: Union[str, List[str]]) -> bool:
        """验证命令是否有效"""
        pass

class SystemCommandExecutor(CommandExecutor):
    """系统命令执行器"""
    
    def __init__(self, logger=None):
        self.logger = logger
    
    def execute(self, command: Union[str, List[str]], 
                cwd: str = None, 
                timeout: int = 120,
                shell: bool = None,
                capture_output: bool = True,
                env: Dict[str, str] = None) -> Dict[str, Any]:
        """执行系统命令"""
        if isinstance(command, str):
            cmd_str = command
            if shell is None:
                shell = True
        else:
            cmd_str = ' '.join(command)
            if shell is None:
                shell = False
        
        if self.logger:
            self.logger.info(f"[SYSTEM] 执行命令: {cmd_str}")
        
        try:
            result = subprocess.run(
                command,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                cwd=cwd,
                shell=shell,
                env=env
            )
            
            success = result.returncode == 0
            
            if not success and self.logger:
                self.logger.warning(f"[SYSTEM] 命令执行失败: {cmd_str}, 返回码: {result.returncode}")
                if result.stderr:
                    self.logger.warning(f"[SYSTEM] 错误输出: {result.stderr.strip()}")
            elif success and self.logger:
                self.logger.info(f"[SYSTEM] 命令执行成功: {cmd_str}")
                
            return {
                "success": success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": cmd_str
            }
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"命令执行超时 ({timeout}s): {cmd_str}"
            if self.logger:
                self.logger.error(f"[SYSTEM] {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "stdout": "",
                "stderr": "Timeout",
                "returncode": -1,
                "command": cmd_str
            }
        except Exception as e:
            error_msg = f"命令执行异常: {cmd_str}, 错误: {str(e)}"
            if self.logger:
                self.logger.error(f"[SYSTEM] {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "command": cmd_str
            }
    
    def validate_command(self, command: Union[str, List[str]]) -> bool:
        """验证系统命令是否有效"""
        if isinstance(command, str):
            cmd_name = command.split()[0] if command.strip() else ""
        else:
            cmd_name = command[0] if command else ""
        
        if not cmd_name:
            return False
            
        return shutil.which(cmd_name) is not None

class ToolCommandExecutor(CommandExecutor):
    """工具命令执行器"""
    
    def __init__(self, tool_finder: Callable[[str, str], Optional[str]], logger=None):
        self.tool_finder = tool_finder
        self.logger = logger
        self.tools_cache = {}
    
    def execute(self, tool_name: str, args: List[str] = None,
                tool_category: str = None,
                cwd: str = None, 
                timeout: int = 120,
                config: dict = None) -> Dict[str, Any]:
        """执行工具命令"""
        try:
            command = self._get_tool_command(tool_name, tool_category)
            if not command:
                raise ToolError(f"工具不可用: {tool_name}", tool_name)
            
            args = args or []
            full_command = command + args
            
            if self.logger:
                self.logger.debug(f"[TOOL] 执行工具: {tool_name}，完整命令: {' '.join(full_command)}")
                self.logger.debug(f"[TOOL] 超时设置: {timeout}s")
            
            # 使用系统命令执行器执行
            system_executor = SystemCommandExecutor(self.logger)
            result = system_executor.execute(
                full_command, 
                cwd=cwd, 
                timeout=timeout, 
                shell=False
            )
            
            if not result["success"]:
                if self.logger:
                    self.logger.error(f"[TOOL] 工具执行失败: {tool_name}")
                raise ToolError(
                    f"工具执行失败: {result.get('error', result.get('stderr', '未知错误'))}",
                    tool_name,
                    result.get("returncode")
                )
            else:
                if self.logger:
                    self.logger.debug(f"[TOOL] 工具执行成功: {tool_name}")
            
            return result
            
        except ToolError:
            raise
        except Exception as e:
            if self.logger:
                self.logger.error(f"[TOOL] 工具执行异常: {tool_name}, 错误: {str(e)}")
            raise ToolError(f"工具执行异常: {str(e)}", tool_name)
    
    def validate_command(self, tool_name: str, tool_category: str = None) -> bool:
        """验证工具命令是否有效"""
        try:
            command = self._get_tool_command(tool_name, tool_category)
            return command is not None
        except Exception:
            return False
    
    def _get_tool_command(self, tool_name: str, tool_category: str = None) -> Optional[List[str]]:
        """获取工具执行命令"""
        cache_key = f"{tool_category}:{tool_name}" if tool_category else tool_name
        
        if cache_key in self.tools_cache:
            return self.tools_cache[cache_key]
        
        tool_path = self.tool_finder(tool_name, tool_category)
        if not tool_path:
            return None
            
        # 特殊处理Java工具
        if tool_name in ["apktool", "bundletool"] and tool_path.endswith(".jar"):
            # 对于bundletool，优先使用系统Java
            if tool_name == "bundletool":
                system_java = shutil.which("java")
                if system_java:
                    command = [system_java, "-Xmx2g", "-jar", tool_path]
                    self.tools_cache[cache_key] = command
                    return command
            
            # 使用内置JRE
            java_path = self.tool_finder("java", "jre")
            if java_path:
                command = [java_path, "-Xmx2g", "-jar", tool_path]
                self.tools_cache[cache_key] = command
                return command
            else:
                raise ToolError(f"运行 {tool_name} 需要Java环境", tool_name)
        
        command = [tool_path]
        self.tools_cache[cache_key] = command
        return command

class CommandService(BaseService):
    """统一的命令执行服务"""
    
    def __init__(self, tool_finder: Callable[[str, str], Optional[str]] = None):
        super().__init__("CommandService")
        
        # 初始化执行器
        self.system_executor = SystemCommandExecutor(self.logger)
        self.tool_executor = ToolCommandExecutor(tool_finder, self.logger) if tool_finder else None
        
        # 命令执行钩子
        self.pre_execute_hooks: List[Callable] = []
        self.post_execute_hooks: List[Callable] = []
    
    def add_pre_execute_hook(self, hook: Callable):
        """添加命令执行前钩子"""
        self.pre_execute_hooks.append(hook)
    
    def add_post_execute_hook(self, hook: Callable):
        """添加命令执行后钩子"""
        self.post_execute_hooks.append(hook)
    
    def execute_system_command(self, command: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
        """执行系统命令"""
        # 执行前钩子
        for hook in self.pre_execute_hooks:
            try:
                hook("system", command, kwargs)
            except Exception as e:
                self.logger.warning(f"执行前钩子失败: {e}")
        
        result = self.system_executor.execute(command, **kwargs)
        
        # 执行后钩子
        for hook in self.post_execute_hooks:
            try:
                hook("system", command, result)
            except Exception as e:
                self.logger.warning(f"执行后钩子失败: {e}")
        
        return result
    
    def execute_tool_command(self, tool_name: str, args: List[str] = None, **kwargs) -> Dict[str, Any]:
        """执行工具命令"""
        if not self.tool_executor:
            # 延迟初始化工具执行器
            _initialize_tool_executor()
            
        if not self.tool_executor:
            raise ToolError("工具执行器未初始化", tool_name)
        
        # 执行前钩子
        for hook in self.pre_execute_hooks:
            try:
                hook("tool", tool_name, {"args": args, **kwargs})
            except Exception as e:
                self.logger.warning(f"执行前钩子失败: {e}")
        
        result = self.tool_executor.execute(tool_name, args, **kwargs)
        
        # 执行后钩子
        for hook in self.post_execute_hooks:
            try:
                hook("tool", tool_name, result)
            except Exception as e:
                self.logger.warning(f"执行后钩子失败: {e}")
        
        return result
    
    def validate_system_command(self, command: Union[str, List[str]]) -> bool:
        """验证系统命令"""
        return self.system_executor.validate_command(command)
    
    def validate_tool_command(self, tool_name: str, tool_category: str = None) -> bool:
        """验证工具命令"""
        if not self.tool_executor:
            return False
        return self.tool_executor.validate_command(tool_name, tool_category)
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            "name": self.name,
            "system_executor_available": self.system_executor is not None,
            "tool_executor_available": self.tool_executor is not None,
            "pre_execute_hooks": len(self.pre_execute_hooks),
            "post_execute_hooks": len(self.post_execute_hooks)
        }

# 全局命令服务实例
_command_service = None

def get_command_service() -> CommandService:
    """获取全局命令服务实例"""
    global _command_service
    if _command_service is None:
        # 先创建不带工具执行器的命令服务，避免循环依赖
        _command_service = CommandService()
    return _command_service

def _initialize_tool_executor():
    """延迟初始化工具执行器，避免循环依赖"""
    global _command_service
    if _command_service and (_command_service.tool_executor is None):
        try:
            from .tool_service import get_tool_service
            tool_service = get_tool_service()
            _command_service.tool_executor = ToolCommandExecutor(tool_service.find_tool, _command_service.logger)
        except ImportError:
            pass

def execute_system_command(command: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
    """执行系统命令的便捷函数"""
    return get_command_service().execute_system_command(command, **kwargs)

def execute_tool_command(tool_name: str, args: List[str] = None, **kwargs) -> Dict[str, Any]:
    """执行工具命令的便捷函数"""
    return get_command_service().execute_tool_command(tool_name, args, **kwargs)