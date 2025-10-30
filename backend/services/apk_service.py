#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用于解析和分析Android APK文件
"""
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any

from core.base_service import BaseService
from core.exceptions import AnalysisError
from utils import file_utils
from .tool_service import get_tool_service

class ApkService(BaseService):
    """APK管理器"""
    
    def __init__(self):
        super().__init__("ApkService")
        self.tool_service = get_tool_service()
        
        # 缓存工具状态，避免重复检查
        self._tools_status = self.tool_service.get_tools_status()
        
        # 检查工具可用性
        self.apktool_available = self._check_apktool_availability()
        self.aapt_available = self._check_aapt_availability()
        
    def _get_tool_status(self, tool_name: str) -> Dict[str, Any]:
        """获取工具状态，使用缓存避免重复调用"""
        return self._tools_status.get(tool_name, {"available": False})
        
    def _check_apktool_availability(self) -> bool:
        """检查apktool是否可用"""
        return self._get_tool_status("apktool")["available"]
        
    def _check_aapt_availability(self) -> bool:
        """检查aapt是否可用"""
        # 优先使用aapt2
        if self._get_tool_status("aapt2")["available"]:
            return True
        # 回退到aapt
        return self._get_tool_status("aapt")["available"]
        
    def analyze_apk(self, apk_path: str, config: dict = None) -> Dict[str, Any]:
        """分析APK文件"""
        try:
            apk_file = self.validate_file_path(apk_path, must_exist=True, must_be_file=True)
            
            # 检查文件大小
            analysis_config = config.get('analysis', {}) if config else {}
            max_size = analysis_config.get("maxFileSize", "500MB")
            max_bytes = file_utils.parse_size(max_size)
            if apk_file.stat().st_size > max_bytes:
                raise AnalysisError(f"APK文件过大，超过限制 {max_size}", str(apk_file))
            
            self.logger.info(f"开始分析APK: {apk_file}")
            
            # 基础信息提取
            basic_info = self._extract_basic_info(apk_file)
            
            # 使用aapt获取详细信息
            aapt_info = self._extract_aapt_info(apk_file)
            
            # 合并信息
            result = {
                "success": True,
                "file_path": str(apk_file),
                "file_size": apk_file.stat().st_size,
                "basic_info": basic_info,
                **aapt_info
            }
            
            # 如果启用深度分析
            if analysis_config.get("deep_analysis", False):
                try:
                    deep_info = self._deep_analysis(apk_file)
                    result["deep_analysis"] = deep_info
                except Exception as e:
                    self.logger.warning(f"深度分析失败: {e}")
                    result["deep_analysis_error"] = str(e)
            
            self.logger.info(f"APK分析完成: {apk_file}")
            return result
            
        except AnalysisError:
            raise
        except Exception as e:
            error_msg = f"APK分析失败: {str(e)}"
            self.logger.error(error_msg)
            raise AnalysisError(error_msg, apk_path)
            
    def _extract_basic_info(self, apk_path: Path) -> Dict[str, Any]:
        """提取基础信息（通过ZIP读取）"""
        try:
            with zipfile.ZipFile(apk_path, 'r') as apk_zip:
                file_list = apk_zip.namelist()
                
                # 统计文件类型
                file_types = {}
                for file_name in file_list:
                    ext = Path(file_name).suffix.lower()
                    file_types[ext] = file_types.get(ext, 0) + 1
                
                # 查找关键文件
                has_manifest = 'AndroidManifest.xml' in file_list
                has_classes_dex = any(f.startswith('classes') and f.endswith('.dex') for f in file_list)
                has_resources = 'resources.arsc' in file_list
                
                # 计算压缩前大小
                uncompressed_size = sum(apk_zip.getinfo(f).file_size for f in file_list)
                
                return {
                    "file_count": len(file_list),
                    "file_types": file_types,
                    "uncompressed_size": uncompressed_size,
                    "compression_ratio": round((1 - apk_path.stat().st_size / uncompressed_size) * 100, 2),
                    "has_manifest": has_manifest,
                    "has_classes_dex": has_classes_dex,
                    "has_resources": has_resources
                }
                
        except Exception as e:
            self.logger.warning(f"提取基础信息失败: {e}")
            return {"error": str(e)}
            
    def _extract_aapt_info(self, apk_path: Path) -> Dict[str, Any]:
        """使用aapt提取APK信息"""
        if not self.aapt_available:
            return {"aapt_error": "aapt工具不可用"}
            
        try:
            # 尝试使用aapt2
            aapt_tool = "aapt2"
            if not self._get_tool_status("aapt2")["available"]:
                aapt_tool = "aapt"
            
            # 获取基本信息
            result = self.tool_service.run_tool_command(
                aapt_tool, ["dump", "badging", str(apk_path)], "aapt"
            )
            
            if not result["success"]:
                return {"aapt_error": result.get("stderr", "aapt执行失败")}
            
            return self._parse_aapt_output(result["stdout"])
            
        except Exception as e:
            self.logger.warning(f"aapt信息提取失败: {e}")
            return {"aapt_error": str(e)}
            
    def _parse_aapt_output(self, output: str) -> Dict[str, Any]:
        """解析aapt输出"""
        info = {
            "permissions": [],
            "activities": [],
            "services": [],
            "receivers": [],
            "providers": []
        }
        
        for line in output.split('\n'):
            line = line.strip()
            
            if line.startswith('package:'):
                # 解析包信息
                parts = line.split()
                for part in parts:
                    if part.startswith('name='):
                        info['package_name'] = part.split('=', 1)[1].strip("'\"")
                    elif part.startswith('versionCode='):
                        info['version_code'] = part.split('=', 1)[1].strip("'\"")
                    elif part.startswith('versionName='):
                        info['version_name'] = part.split('=', 1)[1].strip("'\"")
                        
            elif line.startswith('application-label:'):
                info['app_name'] = line.split(':', 1)[1].strip().strip("'\"")
                
            elif line.startswith('sdkVersion:'):
                info['min_sdk'] = line.split(':', 1)[1].strip().strip("'\"")
                
            elif line.startswith('targetSdkVersion:'):
                info['target_sdk'] = line.split(':', 1)[1].strip().strip("'\"")
                
            elif line.startswith('uses-permission:'):
                perm = line.split(':', 1)[1].strip().strip("'\"")
                if perm not in info['permissions']:
                    info['permissions'].append(perm)
                    
            elif line.startswith('launchable-activity:'):
                activity = line.split(':', 1)[1].strip().strip("'\"")
                info['main_activity'] = activity
                if activity not in info['activities']:
                    info['activities'].append(activity)
                    
        return info
        
    def _deep_analysis(self, apk_path: Path) -> Dict[str, Any]:
        """深度分析（使用apktool反编译）"""
        if not self.apktool_available:
            return {"error": "apktool不可用"}
            
        try:
            # 创建临时目录
            temp_dir = self.create_temp_dir("apk_analysis_")
            output_dir = temp_dir / "decompiled"
            
            # 使用apktool反编译
            result = self.tool_service.run_tool_command(
                "apktool", ["d", str(apk_path), "-o", str(output_dir), "-f"], "apktool"
            )
            
            if not result["success"]:
                return {"error": f"反编译失败: {result.get('stderr', '未知错误')}"}
            
            # 分析反编译结果
            analysis = {}
            
            # 分析AndroidManifest.xml
            manifest_path = output_dir / "AndroidManifest.xml"
            if manifest_path.exists():
                analysis["manifest"] = self._analyze_manifest(manifest_path)
            
            # 分析资源文件
            res_dir = output_dir / "res"
            if res_dir.exists():
                analysis["resources"] = self._analyze_resources(res_dir)
            
            # 分析smali代码
            smali_dir = output_dir / "smali"
            if smali_dir.exists():
                analysis["code"] = self._analyze_smali(smali_dir)
            
            return analysis
            
        except Exception as e:
            return {"error": str(e)}
            
    def _analyze_manifest(self, manifest_path: Path) -> Dict[str, Any]:
        """分析AndroidManifest.xml"""
        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            
            analysis = {
                "package": root.get("package"),
                "activities": [],
                "services": [],
                "receivers": [],
                "providers": [],
                "permissions": [],
                "features": []
            }
            
            # 分析组件
            for activity in root.findall(".//activity"):
                name = activity.get("{http://schemas.android.com/apk/res/android}name")
                if name:
                    analysis["activities"].append(name)
            
            for service in root.findall(".//service"):
                name = service.get("{http://schemas.android.com/apk/res/android}name")
                if name:
                    analysis["services"].append(name)
            
            for receiver in root.findall(".//receiver"):
                name = receiver.get("{http://schemas.android.com/apk/res/android}name")
                if name:
                    analysis["receivers"].append(name)
            
            for provider in root.findall(".//provider"):
                name = provider.get("{http://schemas.android.com/apk/res/android}name")
                if name:
                    analysis["providers"].append(name)
            
            # 分析权限
            for permission in root.findall(".//uses-permission"):
                name = permission.get("{http://schemas.android.com/apk/res/android}name")
                if name:
                    analysis["permissions"].append(name)
            
            # 分析特性
            for feature in root.findall(".//uses-feature"):
                name = feature.get("{http://schemas.android.com/apk/res/android}name")
                if name:
                    analysis["features"].append(name)
            
            return analysis
            
        except Exception as e:
            return {"error": str(e)}
            
    def _analyze_resources(self, res_dir: Path) -> Dict[str, Any]:
        """分析资源文件"""
        try:
            analysis = {
                "layouts": 0,
                "drawables": 0,
                "values": 0,
                "raw": 0,
                "assets": 0
            }
            
            for item in res_dir.rglob("*"):
                if item.is_file():
                    parent_name = item.parent.name
                    if parent_name.startswith("layout"):
                        analysis["layouts"] += 1
                    elif parent_name.startswith("drawable"):
                        analysis["drawables"] += 1
                    elif parent_name.startswith("values"):
                        analysis["values"] += 1
                    elif parent_name.startswith("raw"):
                        analysis["raw"] += 1
            
            return analysis
            
        except Exception as e:
            return {"error": str(e)}
            
    def _analyze_smali(self, smali_dir: Path) -> Dict[str, Any]:
        """分析smali代码"""
        try:
            analysis = {
                "classes": 0,
                "methods": 0,
                "fields": 0
            }
            
            for smali_file in smali_dir.rglob("*.smali"):
                try:
                    with open(smali_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    if content.startswith(".class"):
                        analysis["classes"] += 1
                        
                    analysis["methods"] += content.count(".method")
                    analysis["fields"] += content.count(".field")
                    
                except Exception:
                    continue
            
            return analysis
            
        except Exception as e:
            return {"error": str(e)}
            
    def extract_resources(self, apk_path: str, output_dir: str) -> Dict[str, Any]:
        """提取APK资源"""
        try:
            apk_file = self.validate_file_path(apk_path, must_exist=True, must_be_file=True)
            output_path = self.validate_dir_path(output_dir, must_exist=False, create_if_missing=True)
            
            if not self.apktool_available:
                return {
                    "success": False,
                    "error": "apktool不可用，无法提取资源"
                }
            
            # 使用apktool提取资源
            result = self.tool_service.run_tool_command(
                "apktool", ["d", str(apk_file), "-o", str(output_path), "-f"], "apktool"
            )
            
            if not result["success"]:
                return {
                    "success": False,
                    "error": f"资源提取失败: {result.get('stderr', '未知错误')}"
                }
            
            # 统计提取的文件
            file_count = sum(1 for _ in output_path.rglob("*") if _.is_file())
            
            return {
                "success": True,
                "output_dir": str(output_path),
                "file_count": file_count,
                "message": f"成功提取 {file_count} 个文件到 {output_path}"
            }
            
        except Exception as e:
            error_msg = f"提取资源失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
            
    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        # 直接从tool_manager获取所有工具状态，避免重复调用
        all_tools_status = self.tool_service.get_tools_status()
        
        return {
            "name": self.name,
            "apktool_available": self.apktool_available,
            "aapt_available": self.aapt_available,
            "tools_status": {
                "apktool": all_tools_status.get("apktool", {"available": False}),
                "aapt2": all_tools_status.get("aapt2", {"available": False}),
                "aapt": all_tools_status.get("aapt", {"available": False})
            }
        }
