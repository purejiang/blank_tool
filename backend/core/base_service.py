#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础服务类
提供所有服务的通用功能
"""

import json
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Union
from abc import ABC, abstractmethod

from utils.logger import Logger

class BaseService(ABC):
    """基础服务抽象类"""
    
    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__
        self.logger = Logger.get_logger(self.name)
        self._temp_dirs = []
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        
    def cleanup(self):
        """清理临时资源"""
        for temp_dir in self._temp_dirs:
            try:
                if temp_dir.exists():
                    import shutil
                    shutil.rmtree(temp_dir)
                    self.logger.debug(f"已清理临时目录: {temp_dir}")
            except Exception as e:
                self.logger.warning(f"清理临时目录失败: {temp_dir}, 错误: {e}")
        self._temp_dirs.clear()
        
    def create_temp_dir(self, prefix: str = None) -> Path:
        """创建临时目录"""
        prefix = prefix or f"{self.name}_"
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self._temp_dirs.append(temp_dir)
        self.logger.debug(f"创建临时目录: {temp_dir}")
        return temp_dir
        
    def run_command(self, cmd: Union[str, List[str]], 
                   cwd: str = None, 
                   timeout: int = 120,
                   shell: bool = None,
                   capture_output: bool = True,
                   env: Dict[str, str] = None) -> Dict[str, Any]:
        """执行系统命令（使用统一的命令执行服务）"""
        # 延迟导入避免循环依赖
        from services.command_service import get_command_service
        
        command_service = get_command_service()
        return command_service.execute_system_command(
            cmd, 
            cwd=cwd, 
            timeout=timeout, 
            shell=shell, 
            capture_output=capture_output,
            env=env
        )
            
    def validate_file_path(self, file_path: Union[str, Path], 
                          must_exist: bool = True,
                          must_be_file: bool = True) -> Path:
        """验证文件路径"""
        path = Path(file_path)
        
        if must_exist and not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
            
        if must_be_file and path.exists() and not path.is_file():
            raise ValueError(f"路径不是文件: {path}")
            
        return path
        
    def validate_dir_path(self, dir_path: Union[str, Path], 
                         must_exist: bool = True,
                         create_if_missing: bool = False) -> Path:
        """验证目录路径"""
        path = Path(dir_path)
        
        if not path.exists():
            if create_if_missing:
                path.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"创建目录: {path}")
            elif must_exist:
                raise FileNotFoundError(f"目录不存在: {path}")
                
        if path.exists() and not path.is_dir():
            raise ValueError(f"路径不是目录: {path}")
            
        return path
        
    def safe_json_loads(self, json_str: str, default: Any = None) -> Any:
        """安全的JSON解析"""
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"JSON解析失败: {e}")
            return default
            
    def safe_json_dumps(self, obj: Any, indent: int = 2) -> str:
        """安全的JSON序列化"""
        try:
            return json.dumps(obj, indent=indent, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            self.logger.warning(f"JSON序列化失败: {e}")
            return "{}"
            
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        pass