import os
import platform
import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from app.common.base_executor import CommandExecutor, CommandExecutionContext
from app.utils.logger import Logger
from app.utils.env import get_java_bin


class BaseTool(ABC):
    """工具抽象基类"""

    def __init__(self, name: str = None, path: str = None, search_system: bool = True):
        self.name = name or self.__class__.__name__
        self.logger = Logger.get_logger(self.__class__.__name__)
        self.tool_path = path or (self.find_tool_path_in_system() if search_system else "")
        self.is_valid = self.validate_tool()
        self.version = "" if not self.tool_path or not self.is_valid else self.get_tool_version()

    def find_tool_path_in_system(self) -> str:
        """
        在系统的PATH环境变量中查找工具
        
        根据工具的可能名称列表，遍历PATH环境变量中的每个目录，查找是否存在该工具。
        如果找到，记录工具的完整路径并返回；如果未找到，记录警告日志并返回空字符串。
        
        Returns:
            str: 工具的完整路径，如果未找到则返回空字符串
        """
        possible_names = self.get_possible_tool_names()
        for name in possible_names:
            path = shutil.which(name)
            if path:
                self.logger.info(f"在 {path} 找到工具: {self.name}")
                return path
        self.logger.warning(f"在系统中未找到工具: {self.name}")
        return ""

    @abstractmethod
    def validate_tool(self) -> bool:
        """验证工具是否有效"""
        pass

    @abstractmethod
    def get_possible_tool_names(self) -> List[str]:
        """获取可能的工具名称列表"""
        pass

    @abstractmethod
    def get_tool_version(self) -> str:
        """获取工具版本"""
        pass
    
    def get_java_path(self) -> str:
        return get_java_bin()



class CommandTool(BaseTool):
    """命令行工具基类"""

    def __init__(self, name: str = None, path: str = None, search_system: bool = True):
        self.command_executor = CommandExecutor()
        self.running_processes = {}
        super().__init__(name, path, search_system=search_system)

    def is_process_running(self, process_id: str) -> bool:
        """
        检查指定ID的进程是否仍在运行
        
        根据进程ID从运行中的进程字典中获取进程对象，检查进程是否存在且未结束。
        
        Args:
            process_id (str): 要检查的进程ID
            
        Returns:
            bool: 如果进程存在且未结束，则返回 True，否则返回 False
        """
        process = self.running_processes.get(process_id)
        return process is not None and process.poll() is None
    
    def execute_stream(self, command: List[str], context: CommandExecutionContext = None, callback=None):
        """
        执行流式命令
        
        根据提供的命令列表和执行上下文，执行一个流式命令。
        命令的执行结果会通过回调函数进行实时处理。
        
        Args:
            command (List[str]): 要执行的命令列表，第一个元素为工具的完整路径
            context (CommandExecutionContext): 命令执行上下文，包含环境变量、工作目录等
            callback (function): 处理命令输出的回调函数，参数为 {"type": "output", "payload": line.strip()}
        """
        # 将工具的完整路径添加到命令的最前面
        context = context or CommandExecutionContext()
        if not self.command_executor:
            self.logger.error("CommandExecutor 未初始化")
            return
        process = self.command_executor.execute(command, context)
        process_id = f"{process.pid}"
        self.running_processes[process_id] = process
        if callback:
            callback({"type": "started", "payload": {"process_id": process_id}})
        while self.is_process_running(process_id):
            # 读取进程的输出
            line = process.stdout.readline()
            if line and callback:
                callback({"type": "output", "payload": line.strip()})
    
    def execute(self, command: List[str], context: CommandExecutionContext = None)->Dict[str, Any]:
        """
        执行命令，并根据上下文管理流式进程
        
        根据提供的命令列表和执行上下文，执行一个命令。
        如果上下文指定了流式输出，会通过回调函数进行实时处理；否则，直接返回命令执行结果。
        
        Args:
            command (List[str]): 要执行的命令列表，第一个元素为工具的完整路径
            context (CommandExecutionContext): 命令执行上下文，包含环境变量、工作目录等
            
        Returns:
            Dict[str, Any]: 命令执行结果，包含进程ID、返回码、标准输出等
        """
        # 将工具的完整路径添加到命令的最前面
        context = context or CommandExecutionContext()

        if not self.command_executor:
            self.logger.error("CommandExecutor 未初始化")
            return
        # 对于非流式命令，直接返回结果
        return self.command_executor.execute(command, context)

    def stop_process(self, process_id: str) -> bool:
        """
        通过ID停止一个由该工具启动的进程
        
        根据进程ID从运行中的进程字典中获取进程对象，检查进程是否存在。
        如果进程存在且未结束，尝试优雅地终止进程；如果超时，强制终止。
        最后，关闭进程的标准输出和错误流，并从运行中的进程字典中移除。
        
        Args:
            process_id (str): 要停止的进程ID
            
        Returns:
            bool: 如果进程成功停止或不存在，则返回 True；否则返回 False
        """
        process = self.running_processes.get(process_id)
        if not process:
            self.logger.warning(f"尝试停止一个不存在的进程: {process_id}")
            return False

        if process.poll() is not None:
            self.logger.info(f"进程 {process_id} 已经停止。")
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
            del self.running_processes[process_id]
            return True

        try:
            self.logger.info(f"正在终止进程: {process_id} (PID: {process.pid})")
            process.terminate() # 尝试优雅地终止
            process.wait(timeout=5) # 等待5秒
            self.logger.info(f"进程 {process_id} 已成功终止。")
        except subprocess.TimeoutExpired:
            self.logger.warning(f"优雅终止超时，强制杀死进程: {process_id}")
            process.kill() # 如果失败，则强制杀死
            process.wait()
        except Exception as e:
            self.logger.error(f"停止进程 {process_id} 时发生错误: {e}")
            return False
        finally:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
            if process_id in self.running_processes:
                del self.running_processes[process_id]
        
        return True

    def stop_all_processes(self):
        """
        停止所有由该工具实例启动的正在运行的进程
        
        遍历运行中的进程字典，对每个进程调用 stop_process 方法进行停止。
        最后，清空运行中的进程字典。
        """
        self.logger.info(f"正在停止所有由 {self.name} 启动的进程...")
        for process_id in list(self.running_processes.keys()):
            self.stop_process(process_id)
