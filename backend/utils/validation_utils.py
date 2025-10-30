#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证工具函数
"""

import re
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Union
import logging

logger = logging.getLogger(__name__)

def validate_file_path(file_path: Union[str, Path], must_exist: bool = False, 
                      must_be_file: bool = False, must_be_dir: bool = False) -> Dict[str, Any]:
    """验证文件路径"""
    try:
        path = Path(file_path)
        
        result = {
            "valid": True,
            "path": str(path.absolute()),
            "exists": path.exists(),
            "is_file": path.is_file() if path.exists() else None,
            "is_directory": path.is_dir() if path.exists() else None
        }
        
        if must_exist and not path.exists():
            result["valid"] = False
            result["error"] = f"路径不存在: {path}"
            
        if must_be_file and path.exists() and not path.is_file():
            result["valid"] = False
            result["error"] = f"路径不是文件: {path}"
            
        if must_be_dir and path.exists() and not path.is_dir():
            result["valid"] = False
            result["error"] = f"路径不是目录: {path}"
            
        return result
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"路径验证失败: {str(e)}"
        }

def validate_device_id(device_id: str) -> Dict[str, Any]:
    """验证设备ID"""
    try:
        if not device_id or not isinstance(device_id, str):
            return {
                "valid": False,
                "error": "设备ID不能为空"
            }
            
        device_id = device_id.strip()
        
        # 设备ID格式检查（通常是字母数字组合）
        if not re.match(r'^[a-zA-Z0-9._-]+$', device_id):
            return {
                "valid": False,
                "error": "设备ID格式无效，只能包含字母、数字、点、下划线和连字符"
            }
            
        # 长度检查
        if len(device_id) < 3 or len(device_id) > 50:
            return {
                "valid": False,
                "error": "设备ID长度必须在3-50个字符之间"
            }
            
        return {
            "valid": True,
            "device_id": device_id
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"设备ID验证失败: {str(e)}"
        }

def validate_package_name(package_name: str) -> Dict[str, Any]:
    """验证Android包名"""
    try:
        if not package_name or not isinstance(package_name, str):
            return {
                "valid": False,
                "error": "包名不能为空"
            }
            
        package_name = package_name.strip()
        
        # Android包名格式检查
        pattern = r'^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$'
        if not re.match(pattern, package_name):
            return {
                "valid": False,
                "error": "包名格式无效，必须符合Android包名规范（如：com.example.app）"
            }
            
        # 长度检查
        if len(package_name) > 255:
            return {
                "valid": False,
                "error": "包名长度不能超过255个字符"
            }
            
        # 检查是否包含保留关键字
        parts = package_name.split('.')
        reserved_keywords = ['java', 'javax', 'android', 'com.android']
        
        for keyword in reserved_keywords:
            if package_name.startswith(keyword + '.'):
                return {
                    "valid": False,
                    "error": f"包名不能以保留关键字开头: {keyword}"
                }
                
        return {
            "valid": True,
            "package_name": package_name,
            "parts": parts
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"包名验证失败: {str(e)}"
        }

def validate_version_string(version: str) -> Dict[str, Any]:
    """验证版本字符串"""
    try:
        if not version or not isinstance(version, str):
            return {
                "valid": False,
                "error": "版本字符串不能为空"
            }
            
        version = version.strip()
        
        # 语义化版本格式检查 (major.minor.patch)
        semver_pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9\-\.]+))?(?:\+([a-zA-Z0-9\-\.]+))?$'
        semver_match = re.match(semver_pattern, version)
        
        if semver_match:
            major, minor, patch, prerelease, build = semver_match.groups()
            return {
                "valid": True,
                "version": version,
                "type": "semver",
                "major": int(major),
                "minor": int(minor),
                "patch": int(patch),
                "prerelease": prerelease,
                "build": build
            }
        
        # 简单版本格式检查 (数字和点)
        simple_pattern = r'^[\d\.]+$'
        if re.match(simple_pattern, version):
            parts = version.split('.')
            return {
                "valid": True,
                "version": version,
                "type": "simple",
                "parts": [int(p) for p in parts if p.isdigit()]
            }
        
        return {
            "valid": False,
            "error": "版本格式无效，支持语义化版本（如：1.0.0）或简单版本（如：1.0）"
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"版本验证失败: {str(e)}"
        }

def validate_url(url: str) -> Dict[str, Any]:
    """验证URL"""
    try:
        if not url or not isinstance(url, str):
            return {
                "valid": False,
                "error": "URL不能为空"
            }
            
        url = url.strip()
        
        # 解析URL
        parsed = urllib.parse.urlparse(url)
        
        if not parsed.scheme:
            return {
                "valid": False,
                "error": "URL缺少协议（如：http://或https://）"
            }
            
        if not parsed.netloc:
            return {
                "valid": False,
                "error": "URL缺少主机名"
            }
            
        # 检查协议
        if parsed.scheme not in ['http', 'https', 'ftp', 'ftps']:
            return {
                "valid": False,
                "error": f"不支持的协议: {parsed.scheme}"
            }
            
        return {
            "valid": True,
            "url": url,
            "scheme": parsed.scheme,
            "netloc": parsed.netloc,
            "path": parsed.path,
            "params": parsed.params,
            "query": parsed.query,
            "fragment": parsed.fragment
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"URL验证失败: {str(e)}"
        }

def validate_email(email: str) -> Dict[str, Any]:
    """验证邮箱地址"""
    try:
        if not email or not isinstance(email, str):
            return {
                "valid": False,
                "error": "邮箱地址不能为空"
            }
            
        email = email.strip().lower()
        
        # 邮箱格式检查
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return {
                "valid": False,
                "error": "邮箱地址格式无效"
            }
            
        # 分解邮箱地址
        local, domain = email.split('@')
        
        return {
            "valid": True,
            "email": email,
            "local": local,
            "domain": domain
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"邮箱验证失败: {str(e)}"
        }

def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """清理文件名，移除非法字符"""
    try:
        if not filename:
            return "unnamed"
            
        # 移除或替换非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        sanitized = re.sub(illegal_chars, replacement, filename)
        
        # 移除控制字符
        sanitized = re.sub(r'[\x00-\x1f\x7f]', '', sanitized)
        
        # 移除首尾空格和点
        sanitized = sanitized.strip(' .')
        
        # 检查保留名称（Windows）
        reserved_names = [
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        ]
        
        name_without_ext = sanitized.split('.')[0].upper()
        if name_without_ext in reserved_names:
            sanitized = f"{replacement}{sanitized}"
            
        # 确保文件名不为空
        if not sanitized:
            sanitized = "unnamed"
            
        # 限制长度
        if len(sanitized) > 255:
            name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
            max_name_len = 255 - len(ext) - 1 if ext else 255
            sanitized = name[:max_name_len] + ('.' + ext if ext else '')
            
        return sanitized
        
    except Exception as e:
        logger.error(f"文件名清理失败: {e}")
        return "unnamed"

def sanitize_input(input_str: str, max_length: int = 1000, 
                  allowed_chars: str = None) -> str:
    """清理用户输入"""
    try:
        if not input_str:
            return ""
            
        # 移除控制字符
        sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', input_str)
        
        # 如果指定了允许的字符集
        if allowed_chars:
            pattern = f'[^{re.escape(allowed_chars)}]'
            sanitized = re.sub(pattern, '', sanitized)
        
        # 限制长度
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
            
        return sanitized.strip()
        
    except Exception as e:
        logger.error(f"输入清理失败: {e}")
        return ""