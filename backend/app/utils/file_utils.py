#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件操作工具函数
"""

import hashlib
import shutil
import zipfile
import tarfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import logging

logger = logging.getLogger(__name__)

def parse_size(size_str: str) -> int:
    """解析大小字符串为字节数"""
    size_str = size_str.upper()
    if size_str.endswith('KB'):
        return int(size_str[:-2]) * 1024
    elif size_str.endswith('MB'):
        return int(size_str[:-2]) * 1024 * 1024
    elif size_str.endswith('GB'):
        return int(size_str[:-2]) * 1024 * 1024 * 1024
    else:
        return int(size_str)

def ensure_directory(path: Union[str, Path]) -> Path:
    """确保目录存在"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path

def safe_file_operation(operation: str, source: Union[str, Path], 
                       destination: Union[str, Path] = None) -> Dict[str, Any]:
    """安全的文件操作"""
    try:
        source = Path(source)
        
        if operation == "copy" and destination:
            destination = Path(destination)
            ensure_directory(destination.parent)
            shutil.copy2(source, destination)
            return {"success": True, "message": f"文件已复制: {source} -> {destination}"}
            
        elif operation == "move" and destination:
            destination = Path(destination)
            ensure_directory(destination.parent)
            shutil.move(str(source), str(destination))
            return {"success": True, "message": f"文件已移动: {source} -> {destination}"}
            
        elif operation == "delete":
            if source.is_file():
                source.unlink()
                return {"success": True, "message": f"文件已删除: {source}"}
            elif source.is_dir():
                shutil.rmtree(source)
                return {"success": True, "message": f"目录已删除: {source}"}
            else:
                return {"success": False, "error": f"文件不存在: {source}"}
                
        else:
            return {"success": False, "error": f"不支持的操作: {operation}"}
            
    except Exception as e:
        error_msg = f"文件操作失败 [{operation}]: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

def get_file_hash(file_path: Union[str, Path], algorithm: str = "md5") -> Optional[str]:
    """计算文件哈希值"""
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            return None
            
        hash_obj = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
                
        return hash_obj.hexdigest()
        
    except Exception as e:
        logger.error(f"计算文件哈希失败 [{file_path}]: {e}")
        return None

def copy_file_safe(source: Union[str, Path], destination: Union[str, Path]) -> Dict[str, Any]:
    """安全复制文件"""
    return safe_file_operation("copy", source, destination)

def move_file_safe(source: Union[str, Path], destination: Union[str, Path]) -> Dict[str, Any]:
    """安全移动文件"""
    return safe_file_operation("move", source, destination)

def delete_file_safe(path: Union[str, Path]) -> Dict[str, Any]:
    """安全删除文件或目录"""
    return safe_file_operation("delete", path)

def get_file_info(file_path: Union[str, Path]) -> Dict[str, Any]:
    """获取文件信息"""
    try:
        file_path = Path(file_path)
        
        if not file_path.exists():
            return {"exists": False}
            
        stat = file_path.stat()
        
        info = {
            "exists": True,
            "path": str(file_path.absolute()),
            "name": file_path.name,
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "accessed": stat.st_atime,
            "is_file": file_path.is_file(),
            "is_directory": file_path.is_dir(),
            "is_symlink": file_path.is_symlink()
        }
        
        if file_path.is_file():
            info["extension"] = file_path.suffix
            info["stem"] = file_path.stem
            info["md5"] = get_file_hash(file_path, "md5")
            info["sha256"] = get_file_hash(file_path, "sha256")
            
        return info
        
    except Exception as e:
        logger.error(f"获取文件信息失败 [{file_path}]: {e}")
        return {"exists": False, "error": str(e)}

def find_files(directory: Union[str, Path], pattern: str = "*", 
               recursive: bool = True, include_dirs: bool = False) -> List[Path]:
    """查找文件"""
    try:
        directory = Path(directory)
        
        if not directory.exists() or not directory.is_dir():
            return []
            
        if recursive:
            files = directory.rglob(pattern)
        else:
            files = directory.glob(pattern)
            
        result = []
        for file_path in files:
            if include_dirs or file_path.is_file():
                result.append(file_path)
                
        return sorted(result)
        
    except Exception as e:
        logger.error(f"查找文件失败 [{directory}]: {e}")
        return []

def compress_directory(source_dir: Union[str, Path], output_file: Union[str, Path], 
                      format: str = "zip") -> Dict[str, Any]:
    """压缩目录"""
    try:
        source_dir = Path(source_dir)
        output_file = Path(output_file)
        
        if not source_dir.exists() or not source_dir.is_dir():
            return {"success": False, "error": f"源目录不存在: {source_dir}"}
            
        ensure_directory(output_file.parent)
        
        if format.lower() == "zip":
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in source_dir.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(source_dir)
                        zipf.write(file_path, arcname)
                        
        elif format.lower() in ["tar", "tar.gz", "tgz"]:
            mode = "w:gz" if format.lower() in ["tar.gz", "tgz"] else "w"
            with tarfile.open(output_file, mode) as tarf:
                tarf.add(source_dir, arcname=source_dir.name)
                
        else:
            return {"success": False, "error": f"不支持的压缩格式: {format}"}
            
        file_size = output_file.stat().st_size
        
        return {
            "success": True,
            "output_file": str(output_file),
            "size": file_size,
            "message": f"目录已压缩: {source_dir} -> {output_file} ({file_size} 字节)"
        }
        
    except Exception as e:
        error_msg = f"压缩目录失败: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

def extract_archive(archive_file: Union[str, Path], extract_dir: Union[str, Path]) -> Dict[str, Any]:
    """解压缩文件"""
    try:
        archive_file = Path(archive_file)
        extract_dir = Path(extract_dir)
        
        if not archive_file.exists():
            return {"success": False, "error": f"压缩文件不存在: {archive_file}"}
            
        ensure_directory(extract_dir)
        
        if archive_file.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive_file, 'r') as zipf:
                zipf.extractall(extract_dir)
                extracted_files = zipf.namelist()
                
        elif archive_file.suffix.lower() in [".tar", ".gz", ".tgz"]:
            with tarfile.open(archive_file, 'r:*') as tarf:
                tarf.extractall(extract_dir)
                extracted_files = tarf.getnames()
                
        else:
            return {"success": False, "error": f"不支持的压缩格式: {archive_file.suffix}"}
            
        return {
            "success": True,
            "extract_dir": str(extract_dir),
            "extracted_files": len(extracted_files),
            "message": f"文件已解压: {archive_file} -> {extract_dir} ({len(extracted_files)} 个文件)"
        }
        
    except Exception as e:
        error_msg = f"解压缩失败: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}