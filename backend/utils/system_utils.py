#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统操作工具函数
"""

import os
import platform
import socket
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import logging

# 可选依赖，如果不存在则使用基础功能
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

logger = logging.getLogger(__name__)

# 导入命令服务，用于统一命令执行
try:
    from services.command_service import get_command_service
    HAS_COMMAND_SERVICE = True
except ImportError:
    HAS_COMMAND_SERVICE = False

def get_system_info() -> Dict[str, Any]:
    """获取系统信息"""
    info = {
        'platform': platform.system(),
        'platform_version': platform.version(),
        'platform_release': platform.release(),
        'architecture': platform.machine(),
        'processor': platform.processor(),
        'python_version': platform.python_version(),
        'hostname': platform.node(),
    }
    
    if HAS_PSUTIL:
        try:
            info.update({
                'cpu_count': psutil.cpu_count(),
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_total': psutil.virtual_memory().total,
                'memory_available': psutil.virtual_memory().available,
                'memory_percent': psutil.virtual_memory().percent,
                'disk_usage': {
                    'total': psutil.disk_usage('/').total if platform.system() != 'Windows' else psutil.disk_usage('C:').total,
                    'used': psutil.disk_usage('/').used if platform.system() != 'Windows' else psutil.disk_usage('C:').used,
                    'free': psutil.disk_usage('/').free if platform.system() != 'Windows' else psutil.disk_usage('C:').free,
                }
            })
        except Exception as e:
            logger.warning(f"获取系统信息时出错: {e}")
    else:
        # 基础系统信息，不依赖psutil
        info.update({
            'cpu_count': os.cpu_count(),
            'memory_info': '需要安装psutil模块获取详细内存信息',
            'disk_info': '需要安装psutil模块获取详细磁盘信息'
        })
    
    return info

def check_process_running(process_name: str) -> List[Dict[str, Any]]:
    """检查进程是否运行"""
    processes = []
    
    if HAS_PSUTIL:
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if process_name.lower() in proc.info['name'].lower():
                        processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'cmdline': ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error(f"检查进程失败: {e}")
    else:
        # 使用系统命令作为备选方案
        try:
            if platform.system() == 'Windows':
                cmd = ['tasklist', '/FI', f'IMAGENAME eq {process_name}*']
            else:
                cmd = ['pgrep', '-f', process_name]
            
            # 优先使用命令服务
            if HAS_COMMAND_SERVICE:
                try:
                    command_service = get_command_service()
                    result = command_service.execute_system_command(cmd, timeout=10)
                    if result['success']:
                        if platform.system() == 'Windows':
                            if process_name.lower() in result['stdout'].lower():
                                processes.append({'name': process_name, 'status': 'running'})
                        else:
                            pids = result['stdout'].strip().split('\n')
                            for pid in pids:
                                if pid:
                                    processes.append({'pid': int(pid), 'name': process_name})
                    return processes
                except Exception as e:
                    logger.warning(f"使用命令服务检查进程失败，回退到直接执行: {e}")
            
            # 回退到直接执行
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if platform.system() == 'Windows':
                if result.returncode == 0 and process_name.lower() in result.stdout.lower():
                    processes.append({'name': process_name, 'status': 'running'})
            else:
                if result.returncode == 0:
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        if pid:
                            processes.append({'pid': int(pid), 'name': process_name})
        except Exception as e:
            logger.error(f"使用系统命令检查进程失败: {e}")
    
    return processes

def kill_process(pid: int, force: bool = False) -> Dict[str, Any]:
    """终止进程"""
    if HAS_PSUTIL:
        try:
            proc = psutil.Process(pid)
            if force:
                proc.kill()
            else:
                proc.terminate()
            return {'success': True, 'message': f'进程 {pid} 已终止'}
        except psutil.NoSuchProcess:
            return {'success': False, 'error': f'进程 {pid} 不存在'}
        except psutil.AccessDenied:
            return {'success': False, 'error': f'没有权限终止进程 {pid}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    else:
        # 使用系统命令作为备选方案
        try:
            if platform.system() == 'Windows':
                cmd = ['taskkill', '/F' if force else '/T', '/PID', str(pid)]
            else:
                cmd = ['kill', '-9' if force else '-15', str(pid)]
            
            # 优先使用命令服务
            if HAS_COMMAND_SERVICE:
                try:
                    command_service = get_command_service()
                    result = command_service.execute_system_command(cmd, timeout=10)
                    if result['success']:
                        return {'success': True, 'message': f'进程 {pid} 已终止'}
                    else:
                        return {'success': False, 'error': result.get('stderr', '终止进程失败')}
                except Exception as e:
                    logger.warning(f"使用命令服务终止进程失败，回退到直接执行: {e}")
            
            # 回退到直接执行
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return {'success': True, 'message': f'进程 {pid} 已终止'}
            else:
                return {'success': False, 'error': result.stderr or '终止进程失败'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

def get_available_port(start_port: int = 8000, end_port: int = 9000) -> Optional[int]:
    """获取可用端口"""
    for port in range(start_port, end_port + 1):
        if check_port_available(port):
            return port
    return None

def check_port_available(port: int, host: str = "localhost") -> bool:
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result != 0
    except Exception:
        return False

def run_command_safe(command: Union[str, List[str]], cwd: str = None, 
                    timeout: int = 30, capture_output: bool = True) -> Dict[str, Any]:
    """安全执行命令"""
    try:
        if isinstance(command, str):
            command = command.split()
        
        # 优先使用命令服务
        if HAS_COMMAND_SERVICE:
            try:
                command_service = get_command_service()
                return command_service.execute_system_command(
                    command=command,
                    cwd=cwd,
                    timeout=timeout,
                    capture_output=capture_output
                )
            except Exception as e:
                logger.warning(f"使用命令服务失败，回退到直接执行: {e}")
        
        # 详细的命令执行日志输出
        logger.info(f"[SYSTEM] 执行系统命令: {' '.join(command)}")
        logger.info(f"[SYSTEM] 超时设置: {timeout}s, 捕获输出: {capture_output}")
            
        result = subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            capture_output=capture_output,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            logger.info(f"[SYSTEM] 命令执行成功: {' '.join(command)}")
            if result.stdout and result.stdout.strip() and capture_output:
                logger.debug(f"[SYSTEM] 标准输出: {result.stdout.strip()}")
        else:
            logger.warning(f"[SYSTEM] 命令执行失败: {' '.join(command)}，返回码: {result.returncode}")
            if result.stderr and result.stderr.strip() and capture_output:
                logger.warning(f"[SYSTEM] 错误输出: {result.stderr.strip()}")
        
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout if capture_output else "",
            "stderr": result.stderr if capture_output else "",
            "command": " ".join(command)
        }
        
    except subprocess.TimeoutExpired:
        error_msg = f"命令执行超时 ({timeout}s): {' '.join(command)}"
        logger.error(f"[SYSTEM] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "timeout": True
        }
    except FileNotFoundError:
        error_msg = f"命令不存在: {command[0]}"
        logger.error(f"[SYSTEM] {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "command_not_found": True
        }
    except Exception as e:
        error_msg = f"命令执行失败: {str(e)}"
        logger.error(f"[SYSTEM] {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }

def get_environment_info() -> Dict[str, Any]:
    """获取环境信息"""
    try:
        env_info = {
            "path": os.environ.get("PATH", "").split(os.pathsep),
            "java_home": os.environ.get("JAVA_HOME"),
            "android_home": os.environ.get("ANDROID_HOME"),
            "android_sdk_root": os.environ.get("ANDROID_SDK_ROOT"),
            "user": os.environ.get("USER") or os.environ.get("USERNAME"),
            "home": os.environ.get("HOME") or os.environ.get("USERPROFILE"),
            "temp": os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
        }
        
        # 检查常用工具
        tools = ["java", "adb", "aapt", "apktool"]
        tool_status = {}
        
        for tool in tools:
            result = run_command_safe([tool, "--version"], timeout=5)
            tool_status[tool] = {
                "available": result["success"],
                "version": result.get("stdout", "").strip() if result["success"] else None
            }
            
        env_info["tools"] = tool_status
        
        return env_info
        
    except Exception as e:
        logger.error(f"获取环境信息失败: {e}")
        return {"error": str(e)}

def check_dependencies() -> Dict[str, Any]:
    """检查依赖项"""
    dependencies = {
        "python_modules": {},
        "system_tools": {},
        "java": {},
        "android_tools": {}
    }
    
    try:
        # 检查Python模块
        required_modules = ["psutil", "requests", "pathlib"]
        for module in required_modules:
            try:
                __import__(module)
                dependencies["python_modules"][module] = {"available": True}
            except ImportError:
                dependencies["python_modules"][module] = {"available": False}
        
        # 检查系统工具
        system_tools = ["java", "python", "git"]
        for tool in system_tools:
            result = run_command_safe([tool, "--version"], timeout=5)
            dependencies["system_tools"][tool] = {
                "available": result["success"],
                "version": result.get("stdout", "").strip() if result["success"] else None
            }
        
        # 检查Java环境
        java_home = os.environ.get("JAVA_HOME")
        dependencies["java"] = {
            "java_home": java_home,
            "java_home_exists": Path(java_home).exists() if java_home else False
        }
        
        # 检查Android工具
        android_tools = ["adb", "aapt", "apktool"]
        for tool in android_tools:
            result = run_command_safe([tool, "--version"], timeout=5)
            dependencies["android_tools"][tool] = {
                "available": result["success"],
                "version": result.get("stdout", "").strip() if result["success"] else None
            }
        
        return dependencies
        
    except Exception as e:
        logger.error(f"检查依赖项失败: {e}")
        return {"error": str(e)}


def get_build_info() -> Dict[str, Any]:
    """获取构建信息"""
    build_info = {}
    
    try:
        # Python版本信息
        build_info['python_version'] = platform.python_version()
        build_info['python_implementation'] = platform.python_implementation()
        build_info['python_compiler'] = platform.python_compiler()
        
        # 应用版本信息
        try:
            import json
            package_json_path = Path(__file__).parent.parent.parent / "package.json"
            if package_json_path.exists():
                with open(package_json_path, 'r', encoding='utf-8') as f:
                    package_data = json.load(f)
                    build_info['app_version'] = package_data.get('version', '1.0.0')
                    build_info['app_name'] = package_data.get('name', 'blank_tool')
                    build_info['app_description'] = package_data.get('description', '')
        except Exception as e:
            logger.warning(f"读取package.json失败: {e}")
            build_info['app_version'] = '1.0.0'
            build_info['app_name'] = 'blank_tool'
        
        # 工具版本信息
        tools_info = {}
        
        # Java版本
        try:
            java_result = run_command_safe(['java', '-version'], timeout=5)
            if java_result['success']:
                java_output = java_result.get('stderr', '') or java_result.get('stdout', '')
                if 'version' in java_output.lower():
                    # 提取Java版本号
                    import re
                    version_match = re.search(r'version "([^"]+)"', java_output)
                    if version_match:
                        tools_info['java_version'] = version_match.group(1)
                    else:
                        tools_info['java_version'] = java_output.split('\n')[0].strip()
                else:
                    tools_info['java_version'] = '未检测到'
            else:
                tools_info['java_version'] = '未安装'
        except Exception as e:
            tools_info['java_version'] = f'检测失败: {str(e)}'
        
        # ADB版本
        try:
            adb_result = run_command_safe(['adb', 'version'], timeout=5)
            if adb_result['success']:
                adb_output = adb_result.get('stdout', '')
                if 'Android Debug Bridge' in adb_output:
                    # 提取ADB版本号
                    import re
                    version_match = re.search(r'version (\S+)', adb_output)
                    if version_match:
                        tools_info['adb_version'] = version_match.group(1)
                    else:
                        tools_info['adb_version'] = adb_output.split('\n')[0].strip()
                else:
                    tools_info['adb_version'] = '未检测到'
            else:
                tools_info['adb_version'] = '未安装'
        except Exception as e:
            tools_info['adb_version'] = f'检测失败: {str(e)}'
        
        # AAPT版本
        try:
            aapt_result = run_command_safe(['aapt', 'version'], timeout=5)
            if aapt_result['success']:
                aapt_output = aapt_result.get('stdout', '') or aapt_result.get('stderr', '')
                if aapt_output:
                    tools_info['aapt_version'] = aapt_output.strip()
                else:
                    tools_info['aapt_version'] = '已安装'
            else:
                tools_info['aapt_version'] = '未安装'
        except Exception as e:
            tools_info['aapt_version'] = f'检测失败: {str(e)}'
        
        # APKTool版本
        try:
            apktool_result = run_command_safe(['java', '-jar', 'apktool.jar', '--version'], timeout=5)
            if apktool_result['success']:
                apktool_output = apktool_result.get('stdout', '')
                if apktool_output:
                    tools_info['apktool_version'] = apktool_output.strip()
                else:
                    tools_info['apktool_version'] = '已安装'
            else:
                tools_info['apktool_version'] = '未安装'
        except Exception as e:
            tools_info['apktool_version'] = f'检测失败: {str(e)}'
        
        build_info['tools'] = tools_info
        
        # 系统构建信息
        build_info['platform'] = platform.system()
        build_info['platform_version'] = platform.version()
        build_info['architecture'] = platform.machine()
        build_info['processor'] = platform.processor()
        
        return build_info
        
    except Exception as e:
        logger.error(f"获取构建信息失败: {e}")
        return {"error": str(e)}