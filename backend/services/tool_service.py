#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一管理Android开发工具的查找和调用
"""

import platform
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.base_service import BaseService
from core.exceptions import ToolError
from .command_service import get_command_service

class ToolService(BaseService):
    """统一的工具服务"""
    
    def __init__(self, config: dict = None):
        super().__init__("ToolService")
        self.tools_cache = {}
        self.project_root = self._find_project_root()
        self.config_tools = self._load_electron_config(config)
        
        # 优先查找tools
        if self.project_root:
            self.tools_dir = self.project_root / "tools"
        else:
            self.tools_dir = None
            
        self.logger.info(f"工具目录: {self.tools_dir}")
        
        # 使用统一的命令执行服务
        self.command_service = get_command_service()
        
    def _load_electron_config(self, config: dict = None) -> Dict[str, str]:
        """加载Electron应用的配置文件"""
        config_tools = {}
        
        # 如果传入了配置，直接使用
        if config and "tools" in config:
            tools_config = config["tools"]
            config_tools = {
                "adb": tools_config.get("adbPath", ""),
                "aapt": tools_config.get("aaptPath", ""),
                "apktool": tools_config.get("apktoolPath", ""),
                "bundletool": tools_config.get("bundletoolPath", ""),
                "java": tools_config.get("javaPath", "")
            }
            self.logger.debug("从传入配置加载工具路径")
            return config_tools
        
        if not self.project_root:
            return config_tools
            
        # 尝试加载配置文件（作为后备）
        config_paths = [
            self.project_root / "assets" / "default-config.json",
            self.project_root / "config" / "default-config.json",
            self.project_root / "default-config.json"
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                try:
                    import json
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    
                    tools_config = config_data.get("tools", {})
                    config_tools = {
                        "adb": tools_config.get("adbPath", ""),
                        "aapt": tools_config.get("aaptPath", ""),
                        "apktool": tools_config.get("apktoolPath", ""),
                        "bundletool": tools_config.get("bundletoolPath", ""),
                        "java": tools_config.get("javaPath", "")
                    }
                    
                    self.logger.debug(f"从配置文件加载工具路径: {config_path}")
                    break
                    
                except Exception as e:
                    self.logger.warning(f"加载配置文件失败 {config_path}: {e}")
                    
        return config_tools
        
    def _find_project_root(self) -> Optional[Path]:
        """查找项目根目录"""
        current_path = Path(__file__).parent.parent
        
        # 向上查找，直到找到包含tools目录或/tools目录的目录
        for _ in range(5):  # 最多向上查找5级
            if (current_path / "tools").exists():
                return current_path
            if (current_path / "package.json").exists():  # Electron项目标识
                return current_path
            parent = current_path.parent
            if parent == current_path:  # 到达根目录
                break
            current_path = parent
        
        return None
        
    def _get_executable_extension(self) -> str:
        """获取可执行文件扩展名"""
        return ".exe" if platform.system() == "Windows" else ""
        
    def _check_system_path(self, tool_name: str) -> Optional[str]:
        """检查系统PATH中是否存在工具"""
        try:
            result = self.command_service.execute_system_command(
                f"where {tool_name}" if platform.system() == "Windows" else f"which {tool_name}",
                timeout=5
            )
            if result["success"] and result["stdout"].strip():
                path = result["stdout"].strip().split('\n')[0]
                self.logger.debug(f"在系统PATH中找到 {tool_name}: {path}")
                return path
        except Exception as e:
            self.logger.debug(f"检查系统PATH失败: {e}")
        return None
        
    def find_tool(self, tool_name: str, tool_category: str = None) -> Optional[str]:
        """查找工具路径"""
        cache_key = f"{tool_category}:{tool_name}" if tool_category else tool_name
        
        if cache_key in self.tools_cache:
            cached_path = self.tools_cache[cache_key]
            if Path(cached_path).exists():
                return cached_path
            else:
                # 缓存的路径不存在，清除缓存
                del self.tools_cache[cache_key]
        
        # 首先检查配置文件中的工具路径
        config_path = self.config_tools.get(tool_name, "")
        if config_path and Path(config_path).exists():
            self.tools_cache[cache_key] = config_path
            self.logger.debug(f"从配置文件找到工具 {tool_name}: {config_path}")
            return config_path
        
        # 然后在项目工具目录中查找
        tool_path = self._search_tool(tool_name, tool_category)
        
        # 如果项目目录中没有找到，检查系统PATH
        if not tool_path:
            tool_path = self._check_system_path(tool_name)
        
        if tool_path:
            self.tools_cache[cache_key] = tool_path
            self.logger.debug(f"找到工具 {tool_name}: {tool_path}")
        else:
            self.logger.warning(f"未找到工具: {tool_name}")
            
        return tool_path
        
    def _search_tool(self, tool_name: str, tool_category: str = None) -> Optional[str]:
        """在工具目录中搜索工具"""
        if not self.tools_dir or not self.tools_dir.exists():
            return None
            
        exe_ext = self._get_executable_extension()
        possible_names = self._get_possible_tool_names(tool_name, exe_ext)
        
        search_dirs = []
        
        if tool_category:
            # 在指定类别目录中搜索
            category_dir = self.tools_dir / tool_category
            if category_dir.exists():
                search_dirs.append(category_dir)
        else:
            # 在所有子目录中搜索
            for item in self.tools_dir.iterdir():
                if item.is_dir():
                    search_dirs.append(item)
        
        # 搜索工具
        for search_dir in search_dirs:
            for name in possible_names:
                tool_path = search_dir / name
                if tool_path.exists() and tool_path.is_file():
                    return str(tool_path)
                    
                # 在bin子目录中搜索
                bin_path = search_dir / "bin" / name
                if bin_path.exists() and bin_path.is_file():
                    return str(bin_path)
            
            # 特殊处理：对于jar工具，查找带版本号的文件
            if tool_name in ["apktool", "bundletool"]:
                jar_pattern = f"{tool_name}_*.jar" if tool_name == "apktool" else f"{tool_name}-*.jar"
                try:
                    # 查找匹配模式的jar文件
                    jar_files = list(search_dir.glob(jar_pattern))
                    if jar_files:
                        # 返回最新版本的jar文件（按文件名排序）
                        latest_jar = sorted(jar_files, key=lambda x: x.name)[-1]
                        return str(latest_jar)
                except Exception as e:
                    self.logger.debug(f"搜索jar文件失败: {e}")
        
        return None
        
    def _get_possible_tool_names(self, tool_name: str, exe_ext: str) -> List[str]:
        """获取可能的工具名称列表"""
        names = [tool_name]
        
        # 添加扩展名版本
        if exe_ext and not tool_name.endswith(exe_ext):
            names.append(f"{tool_name}{exe_ext}")
        
        # 特殊工具名称映射
        special_mappings = {
            "adb": ["adb", f"adb{exe_ext}"],
            "aapt": ["aapt", f"aapt{exe_ext}", "aapt2", f"aapt2{exe_ext}"],
            "aapt2": ["aapt2", f"aapt2{exe_ext}"],
            "apktool": ["apktool", f"apktool{exe_ext}", "apktool.jar"],
            "bundletool": ["bundletool", f"bundletool{exe_ext}", "bundletool.jar"],
            "java": ["java", f"java{exe_ext}"],
            "javac": ["javac", f"javac{exe_ext}"]
        }
        
        if tool_name in special_mappings:
            names.extend(special_mappings[tool_name])
        
        # 去重并保持顺序
        return list(dict.fromkeys(names))
        
    def get_tool_command(self, tool_name: str, tool_category: str = None) -> Optional[List[str]]:
        """获取工具执行命令"""
        tool_path = self.find_tool(tool_name, tool_category)
        if not tool_path:
            return None
            
        # 特殊处理Java工具
        if tool_name in ["apktool", "bundletool"] and tool_path.endswith(".jar"):
            # 对于bundletool，优先使用系统Java，因为内置JRE可能缺少jar文件系统提供程序
            if tool_name == "bundletool":
                # 首先尝试系统Java
                system_java = shutil.which("java")
                if system_java:
                    heap_size = getattr(self, '_java_heap_size', "2g")
                    return [system_java, f"-Xmx{heap_size}", "-jar", tool_path]
            
            # 对于其他工具或系统Java不可用时，使用内置JRE
            java_path = self.find_tool("java", "jre")
            if java_path:
                # 使用默认的堆大小，或从参数中获取
                heap_size = getattr(self, '_java_heap_size', "2g")
                return [java_path, f"-Xmx{heap_size}", "-jar", tool_path]
            else:
                raise ToolError(f"运行 {tool_name} 需要Java环境", tool_name)
        
        return [tool_path]
        
    def run_tool_command(self, tool_name: str, args: List[str], 
                        tool_category: str = None, cwd: str = None, 
                        timeout: int = None, config: dict = None) -> Dict[str, Any]:
        """运行工具命令（使用统一的命令执行服务）"""
        try:
            # 使用传入的配置或默认超时时间
            if timeout is None:
                if config and 'tools' in config:
                    timeout = config['tools'].get(f"{tool_name}_timeout", 120)
                else:
                    timeout = 120
            
            return self.command_service.execute_tool_command(
                tool_name, 
                args, 
                tool_category=tool_category,
                cwd=cwd, 
                timeout=timeout, 
                config=config
            )
            
        except Exception as e:
            self.logger.error(f"[TOOL] 工具执行异常: {tool_name}, 错误: {str(e)}")
            raise ToolError(f"工具执行异常: {str(e)}", tool_name)
            
    def check_tool_availability(self, tool_name: str, tool_category: str = None) -> Dict[str, Any]:
        """检查工具可用性"""
        try:
            tool_path = self.find_tool(tool_name, tool_category)
            if not tool_path:
                return {
                    "available": False,
                    "error": f"未找到工具: {tool_name}",
                    "tool_name": tool_name
                }
            
            # 尝试运行工具获取版本信息
            version_args = {
                "adb": ["version"],
                "aapt": ["version"],
                "aapt2": ["version"],
                "apktool": ["--version"],
                "bundletool": ["version"],
                "java": ["-version"]
            }.get(tool_name, ["--version"])
            
            try:
                result = self.run_tool_command(tool_name, version_args, tool_category, timeout=10)
                version_info = result.get("stdout", "") + result.get("stderr", "")
                
                return {
                    "available": True,
                    "path": tool_path,
                    "version": version_info.strip(),
                    "tool_name": tool_name
                }
            except ToolError:
                # 即使版本检查失败，工具可能仍然可用
                return {
                    "available": True,
                    "path": tool_path,
                    "version": "未知版本",
                    "tool_name": tool_name,
                    "warning": "无法获取版本信息"
                }
                
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "tool_name": tool_name
            }
            
    def get_tools_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有工具状态"""
        tools = [
            ("adb", "adb"),
            ("aapt", "aapt"),
            ("aapt2", "aapt"),
            ("apktool", "apktool"),
            ("bundletool", "bundletool"),
            ("java", "jre")
        ]
        
        status = {}
        for tool_name, tool_category in tools:
            status[tool_name] = self.check_tool_availability(tool_name, tool_category)
            
        return status
        
    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        return {
            "name": self.name,
            "project_root": str(self.project_root) if self.project_root else None,
            "tools_dir": str(self.tools_dir) if self.tools_dir else None,
            "cached_tools": len(self.tools_cache),
            "tools_status": self.get_tools_status()
        }


# 全局工具服务实例
_tool_service = None

def get_tool_service() -> ToolService:
    """获取全局工具服务实例"""
    global _tool_service
    if _tool_service is None:
        _tool_service = ToolService()
    return _tool_service

def find_tool(tool_name: str, tool_category: str = None) -> Optional[str]:
    """便捷函数：查找工具"""
    return get_tool_service().find_tool(tool_name, tool_category)

def run_tool(tool_name: str, args: List[str], **kwargs) -> Dict[str, Any]:
    """便捷函数：运行工具"""
    return get_tool_service().run_tool_command(tool_name, args, **kwargs)