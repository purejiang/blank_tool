#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义异常类
"""

class ToolError(Exception):
    """工具相关错误"""
    def __init__(self, message: str, tool_name: str = None, error_code: int = None):
        super().__init__(message)
        self.tool_name = tool_name
        self.error_code = error_code
        self.message = message

    def to_dict(self):
        return {
            'error': self.message,
            'tool_name': self.tool_name,
            'error_code': self.error_code,
            'type': 'ToolError'
        }

class DeviceError(Exception):
    """设备相关错误"""
    def __init__(self, message: str, device_id: str = None, error_code: int = None):
        super().__init__(message)
        self.device_id = device_id
        self.error_code = error_code
        self.message = message

    def to_dict(self):
        return {
            'error': self.message,
            'device_id': self.device_id,
            'error_code': self.error_code,
            'type': 'DeviceError'
        }

class AnalysisError(Exception):
    """分析相关错误"""
    def __init__(self, message: str, file_path: str = None, error_code: int = None):
        super().__init__(message)
        self.file_path = file_path
        self.error_code = error_code
        self.message = message

    def to_dict(self):
        return {
            'error': self.message,
            'file_path': self.file_path,
            'error_code': self.error_code,
            'type': 'AnalysisError'
        }

class ConfigError(Exception):
    """配置相关错误"""
    def __init__(self, message: str, config_key: str = None):
        super().__init__(message)
        self.config_key = config_key
        self.message = message

    def to_dict(self):
        return {
            'error': self.message,
            'config_key': self.config_key,
            'type': 'ConfigError'
        }