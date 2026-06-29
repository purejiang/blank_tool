#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志管理器 - 支持按日期分割和大小限制
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from logging.handlers import BaseRotatingHandler

class DailyRotatingFileHandler(BaseRotatingHandler):
    """按日期和大小分割的日志处理器"""
    
    def __init__(self, log_dir: Path, max_bytes: int = 10 * 1024 * 1024, encoding: str = 'utf-8'):
        """
        初始化处理器
        
        Args:
            log_dir: 日志目录
            max_bytes: 单个文件最大字节数，默认3MB
            encoding: 文件编码
        """
        self.log_dir = Path(log_dir)
        self.max_bytes = max_bytes
        self.encoding = encoding
        
        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取当前日志文件路径
        self.current_log_file = self._get_current_log_file()
        
        # 调用父类初始化
        super().__init__(str(self.current_log_file), 'a', encoding=encoding)
        
    def _get_current_log_file(self) -> Path:
        """获取当前应该使用的日志文件路径"""
        today = datetime.now().strftime('%Y-%m-%d')
        base_file = self.log_dir / f"backend-{today}.log"
        
        # 如果基础文件不存在或大小未超限，直接使用
        if not base_file.exists() or base_file.stat().st_size < self.max_bytes:
            return base_file
        
        # 查找下一个可用的文件名
        counter = 2
        while True:
            numbered_file = self.log_dir / f"backend-{today}_{counter}.log"
            if not numbered_file.exists() or numbered_file.stat().st_size < self.max_bytes:
                return numbered_file
            counter += 1
    
    def shouldRollover(self, record):
        """判断是否需要切换文件"""
        # 检查日期是否变化
        today = datetime.now().strftime('%Y-%m-%d')
        # 从 backend-YYYY-MM-DD.log 提取日期
        stem = self.current_log_file.stem
        current_date = stem.replace('backend-', '').split('_')[0]
        
        if today != current_date:
            return True
        
        # 检查文件大小
        if self.stream:
            self.stream.seek(0, 2)  # 移动到文件末尾
            if self.stream.tell() >= self.max_bytes:
                return True
        
        return False
    
    def doRollover(self):
        """执行文件切换"""
        if self.stream:
            self.stream.close()
            self.stream = None
        
        # 获取新的日志文件路径
        self.current_log_file = self._get_current_log_file()
        self.baseFilename = str(self.current_log_file)
        
        # 重新打开文件流
        if not self.delay:
            self.stream = self._open()

class Logger:
    """统一日志管理器"""
    
    _loggers: Dict[str, logging.Logger] = {}
    _initialized = False
    _log_dir: Optional[Path] = None
    _file_handler: Optional[DailyRotatingFileHandler] = None
    
    @classmethod
    def initialize(cls, log_level: str = "INFO", log_dir: Optional[Path] = None, 
                   enable_console: bool = True, max_file_size: int = 3 * 1024 * 1024):
        """
        初始化日志系统
        
        Args:
            log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL, VERBOSE)
            log_dir: 日志目录
            enable_console: 是否启用控制台输出
            max_file_size: 单个日志文件最大大小（字节），默认3MB
        """
        if cls._initialized:
            return
            
        # 处理自定义日志级别
        level_upper = log_level.upper()
        # 使用标准日志级别
        actual_level = getattr(logging, level_upper, logging.INFO)
            
        # 设置根日志级别
        root_logger = logging.getLogger()
        root_logger.setLevel(actual_level)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器 - 输出到stderr避免干扰JSON输出
        if enable_console:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        # 文件处理器 - 使用新的目录结构
        try:
            if log_dir:
                cls._log_dir = Path(log_dir)
            else:
                backend_dir = Path(__file__).parent.parent  # 默认在父父目录
                cls._log_dir = backend_dir / "cache" / "logs"
            
            # 创建自定义的日志处理器
            cls._file_handler = DailyRotatingFileHandler(
                log_dir=cls._log_dir,
                max_bytes=max_file_size
            )
            cls._file_handler.setFormatter(formatter)
            root_logger.addHandler(cls._file_handler)
            
            # 输出日志文件信息
            if enable_console:
                current_log_file = cls._file_handler.current_log_file
                print(f"日志文件已创建: {current_log_file}", file=sys.stderr)
                print(f"日志目录: {cls._log_dir}", file=sys.stderr)
                
        except Exception as e:
            error_msg = f"警告: 无法创建日志文件处理器: {e}"
            print(error_msg, file=sys.stderr)
        
        cls._initialized = True
        
        # 清理超过3天的旧日志
        cls.cleanup_old_logs(days_to_keep=3)
        
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """获取指定名称的日志器"""
        if not cls._initialized:
            cls.initialize()
            
        if name not in cls._loggers:
            logger = logging.getLogger(name)
            cls._loggers[name] = logger
            
        return cls._loggers[name]
        
    @classmethod
    def set_level(cls, level: str):
        """设置全局日志级别"""
        log_level = getattr(logging, level.upper(), logging.INFO)
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # 同时设置所有处理器的级别
        for handler in root_logger.handlers:
            handler.setLevel(log_level)
        
        for logger in cls._loggers.values():
            logger.setLevel(log_level)
    
    @classmethod
    def get_current_log_file(cls) -> Optional[Path]:
        """获取当前正在使用的日志文件路径"""
        if cls._file_handler:
            return cls._file_handler.current_log_file
        return None
    
    @classmethod
    def get_log_directory(cls) -> Optional[Path]:
        """获取日志目录路径"""
        return cls._log_dir
    
    @classmethod
    def cleanup_old_logs(cls, days_to_keep: int = 3):
        """清理旧的日志文件（默认保留3天）"""
        if not cls._log_dir or not cls._log_dir.exists():
            return
        
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        try:
            for log_file in cls._log_dir.glob("backend-*.log"):
                # 从 backend-YYYY-MM-DD.log 提取日期
                stem = log_file.stem
                file_date_str = stem.replace('backend-', '').split('_')[0]
                try:
                    file_date = datetime.strptime(file_date_str, '%Y-%m-%d')
                    if file_date < cutoff_date:
                        log_file.unlink()
                        print(f"已删除旧日志文件: {log_file}", file=sys.stderr)
                except ValueError:
                    continue
        except Exception as e:
            print(f"清理日志文件时出错: {e}", file=sys.stderr)