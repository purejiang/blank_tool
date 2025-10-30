#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志管理器
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Optional

class Logger:
    """统一日志管理器"""
    
    _loggers: Dict[str, logging.Logger] = {}
    _initialized = False
    
    @classmethod
    def initialize(cls, log_level: str = "INFO", log_file: Optional[str] = None, enable_console: bool = True):
        """初始化日志系统"""
        if cls._initialized:
            return
            
        # 设置根日志级别
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        
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
        
        # 文件处理器（如果指定了日志文件）
        if log_file:
            try:
                log_path = Path(log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                
                file_handler = logging.FileHandler(log_path, encoding='utf-8')
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                
                # 如果启用了控制台输出，也在stderr中输出日志文件路径
                if enable_console:
                    print(f"日志文件已创建: {log_path}", file=sys.stderr)
            except Exception as e:
                error_msg = f"警告: 无法创建日志文件 {log_file}: {e}"
                print(error_msg, file=sys.stderr)
        
        cls._initialized = True
        
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