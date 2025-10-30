#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后端API接口 v1.0
提供统一的API接口供Electron主进程调用

Usage:
    main.py --action=<action> [--params=<params>] [--log-level=<level>]
    main.py (-h | --help)
    main.py --version

Actions:
    system.info          获取系统信息
    system.dependencies  检查依赖工具
    system.status        获取系统状态
    
    tool.check           检查工具可用性
    tool.run             执行工具命令
    
    device.list          获取设备列表
    device.info          获取设备信息
    device.install.apk   安装APK到设备
    device.install.aab   安装AAB到设备
    device.install.apks  安装APKS到设备
    device.uninstall     卸载应用
    device.packages      获取已安装应用
    device.export        导出APK
    device.reboot        重启设备
    device.shell         执行shell命令
    device.monitor.start 开始设备监控
    device.monitor.stop  停止设备监控
    device.monitor.realtime 实时设备监控
    
    apk.analyze          分析APK文件
    apk.info             获取APK信息
    apk.extract          提取APK资源
    
    aab.convert          转换AAB文件
    
    log.start            开始日志监控
    log.stop             停止日志监控
    log.export           导出设备日志
    log.preview          获取日志预览
    
    cache.set            设置缓存
    cache.get            获取缓存
    cache.delete         删除缓存
    cache.clear          清空缓存
    cache.stats          缓存统计
    cache.info           缓存信息

Options:
    --action=<action>       要执行的操作
    --params=<params>       JSON格式的参数
    -h --help               显示帮助信息
    --version               显示版本信息

Examples:
    main.py --action=apk.parse --params='{"file":"app.apk"}'
    main.py --action=adb.device.list
    main.py --action=apk.decompile --params='{"file":"app.apk","output":"./output"}'
"""

import sys
import json
from pathlib import Path

# 添加当前目录到Python路径，确保可以导入模块
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 导入docopt
sys.path.insert(0, str(current_dir.parent / "tools" / "python_runtime"))
from docopt import docopt

import utils
from utils.logger import Logger
from services import ToolService, DeviceService, ApkService, LogCatService, CacheService


class BackendAPI:
    """后端API管理器"""
    
    def __init__(self, config: dict = None):
        # 初始化日志
        self.logger = Logger.get_logger("BackendAPI")
        self.logger.debug("开始初始化BackendAPI")
        
        # 保存配置，按需初始化服务
        self.config = config or {}
        self._tool_service = None
        self._device_service = None
        self._apk_service = None
        self._log_service = None
        self._cache_service = None
        
        self.logger.info("后端API初始化完成")
    
    @property
    def tool_service(self):
        """按需初始化工具服务"""
        if self._tool_service is None:
            self._tool_service = ToolService(self.config)
        return self._tool_service
    
    @property
    def device_service(self):
        """按需初始化设备服务"""
        if self._device_service is None:
            self._device_service = DeviceService()
        return self._device_service
    
    @property
    def apk_service(self):
        """按需初始化APK服务"""
        if self._apk_service is None:
            self._apk_service = ApkService()
        return self._apk_service
    
    @property
    def log_service(self):
        """按需初始化日志服务"""
        if self._log_service is None:
            self._log_service = LogCatService()
        return self._log_service
    
    @property
    def cache_service(self):
        """按需初始化缓存服务"""
        if self._cache_service is None:
            cache_config = self.config.get('cache', {})
            self._cache_service = CacheService(cache_config)
        return self._cache_service
        
    def handle_request(self, action: str, params: dict = None, config: dict = None) -> dict:
        """处理API请求"""
        if params is None:
            params = {}
        if config is None:
            config = {}
            
        try:
            self.logger.debug(f"处理请求: {action}, 参数: {params}, 配置: {config}")
            
            # 系统信息相关
            if action == "system.info":
                return self._get_system_info()
            elif action == "system.build":
                return self._get_build_info()
            elif action == "system.dependencies":
                return self._check_dependencies()
            elif action == "system.status":
                return self._get_status()
                
            # 工具管理相关
            elif action == "/api/tools/status" or action == "tool.status":
                return {
                    "success": True,
                    "tools": self.tool_service.get_tools_status()
                }
            elif action == "tool.check":
                return self.tool_service.check_tool_availability(
                    params.get("tool_name"), params.get("tool_type")
                )
            elif action == "tool.run":
                return self.tool_service.run_tool_command(
                    params.get("tool_name"), params.get("args", []), 
                    params.get("tool_type"), config
                )
                
            # 设备管理相关
            elif action == "device.list":
                return self.device_service.get_devices()
            elif action == "device.info":
                return self.device_service.get_device_info(params.get("device_id"))
            elif action == "device.install.apk":
                return self.device_service.install_apk(
                    params.get("apk_path")
                )
            elif action == "device.install.aab":
                return self.device_service.install_aab(
                    params.get("aab_path")
                )
            elif action == "device.install.apks":
                return self.device_service.install_apks(
                    params.get("apks_path")
                )
            elif action == "device.uninstall":
                return self.device_service.uninstall_app(
                    params.get("package_name")
                )
            elif action == "device.packages":
                return self.device_service.get_installed_packages(params.get("device_id"))
            elif action == "device.export":
                return self.device_service.export_apk(
                    params.get("package_name"), params.get("device_id"), params.get("output_dir")
                )
            elif action == "device.reboot":
                return self.device_service.reboot_device(params.get("device_id"))
            elif action == "device.shell":
                return self.device_service.execute_shell_command(
                    params.get("command"), params.get("device_id")
                )
            elif action == "device.monitor.start":
                return self.device_service.start_device_monitoring()
            elif action == "device.monitor.stop":
                return self.device_service.stop_device_monitoring()
            elif action == "device.monitor.realtime":
                return self.device_service.start_realtime_device_monitoring()
                
            # APK分析相关
            elif action == "apk.analyze":
                return self.apk_service.analyze_apk(params.get("apk_path"), config)
            elif action == "apk.info":
                return self.apk_service.get_apk_info(params.get("apk_path"))
            elif action == "apk.extract":
                return self.apk_service.extract_resources(
                    params.get("apk_path"), params.get("output_dir")
                )
                
            # AAB转换相关
            elif action == "aab.convert":
                return self.device_service.convert_aab_to_apks(
                    params.get("aab_path")
                )
                
            # 日志管理相关
            elif action == "log.start":
                return self.log_service.start_logcat(
                    params.get("device_id"), params.get("logLevel"), 
                    params.get("callback"), params.get("tagFilter")
                )
            elif action == "log.stop":
                return self.log_service.stop_logcat()
            elif action == "log.export":
                # 新增：导出设备日志到文件
                from datetime import datetime
                from pathlib import Path
                
                device_id = params.get("device_id")
                content = params.get("content", "")
                timestamp = params.get("timestamp", datetime.now().isoformat())
                
                # 生成文件名
                safe_device_id = device_id.replace(":", "_").replace("-", "_") if device_id else "unknown"
                filename = f"device_log_{safe_device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                
                # 使用默认导出路径
                output_dir = Path.home() / "Downloads" / "device_logs"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / filename
                
                try:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(f"# 设备日志导出\n")
                        f.write(f"# 设备ID: {device_id}\n")
                        f.write(f"# 导出时间: {timestamp}\n")
                        f.write(f"# ==========================================\n\n")
                        f.write(content)
                    
                    return {
                        "success": True,
                        "filePath": str(output_file),
                        "message": f"日志已导出到: {output_file}"
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"导出日志失败: {str(e)}"
                    }
            elif action == "log.preview":
                return self.log_service.get_log_preview(
                    params.get("device_id"), params.get("lines", 100)
                )
                
            # 缓存管理相关
            elif action == "cache.set":
                return {
                    "success": self.cache_service.set(
                        params.get("key"), params.get("value"),
                        params.get("ttl"), params.get("storage", "memory")
                    )
                }
            elif action == "cache.get":
                return {
                    "success": True,
                    "value": self.cache_service.get(
                        params.get("key"), params.get("default"),
                        params.get("storage", "memory")
                    )
                }
            elif action == "cache.delete":
                return {
                    "success": self.cache_service.delete(
                        params.get("key"), params.get("storage", "memory")
                    )
                }
            elif action == "cache.clear":
                return self.cache_service.clear_all(params.get("storage"))
            elif action == "cache.stats":
                return {
                    "success": True,
                    "statistics": self.cache_service.get_stats()
                }
            elif action == "cache.info":
                return {
                    "success": True,
                    "cache_info": self.cache_service.get_info()
                }

            else:
                self.logger.warning(f"未知的操作: {action}")
                return {
                    "success": False,
                    "error": f"未知的操作: {action}"
                }
                
        except Exception as e:
            self.logger.error(f"处理请求时发生错误: {action}, 错误: {str(e)}")
            error_msg = f"处理请求失败 [{action}]: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
            
    def _get_system_info(self) -> dict:
        """获取系统信息"""
        try:
            system_info = utils.get_system_info()
            return {
                "success": True,
                "system_info": system_info
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取系统信息失败: {str(e)}"
            }
    
    def _get_build_info(self) -> dict:
        """获取构建信息"""
        try:
            build_info = utils.get_build_info()
            return {
                "success": True,
                "build_info": build_info
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取构建信息失败: {str(e)}"
            }
            
    def _check_dependencies(self) -> dict:
        """检查依赖项"""
        try:
            dependencies = utils.check_dependencies()
            return {
                "success": True,
                "dependencies": dependencies
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"检查依赖项失败: {str(e)}"
            }
            
    def _get_status(self) -> dict:
        """获取所有管理器状态"""
        try:
            status = {
                "tool_manager": self.tool_service.get_status(),
                "device_manager": self.device_service.get_status(),
                "apk_manager": self.apk_service.get_status(),
                "log_manager": self.log_service.get_status(),
                "cache_manager": self.cache_service.get_status()
            }
            
            return {
                "success": True,
                "status": status
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取状态失败: {str(e)}"
            }

def main():
    """主函数"""
    # 使用docopt解析命令行参数，捕获SystemExit异常
    try:
        args = docopt(__doc__, version='Android工具后端API v1.0')
    except SystemExit as e:
        # docopt在帮助或版本信息时会调用sys.exit()
        # 如果是正常的帮助或版本请求（code为None），直接退出
        if e.code is None:
            sys.exit(0)
        # 如果是参数错误（code为空字符串或其他错误码），输出错误信息并退出
        else:
            error_result = {
                "success": False,
                "error": "命令行参数错误，请使用 --help 查看帮助信息"
            }
            print(json.dumps(error_result, ensure_ascii=False))
            sys.exit(1)
    
    try:
        # 创建日志文件路径
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "backend.log"
        
        # 初始化日志系统，支持文件输出
        log_level = args['--log-level'] or 'INFO'  # 设置默认值
        Logger.initialize(log_level, str(log_file))
        logger = Logger.get_logger("main")
        logger.info(f"程序启动，执行操作: {args['--action']}")
        logger.info(f"日志文件: {log_file}")
        
        # 解析参数
        params = {}
        if args['--params']:
            logger.debug(f"解析参数: {args['--params']}")
            params = json.loads(args['--params'])
        else:
            logger.debug("无参数传入")
        logger.debug(f"参数: {params}")
            
        # 创建API实例并处理请求
        logger.debug("创建BackendAPI实例")
        config = {}  # 移除全局config变量依赖
        api = BackendAPI(config)
        
        logger.debug(f"开始处理请求: {args['--action']}")
        result = api.handle_request(args['--action'], params, config)
        logger.debug(f"请求处理完成，结果: {result.get('success', False)}")
        
        # 输出结果 - 只输出纯JSON，不带缩进
        print(json.dumps(result, ensure_ascii=False))
        
        # 设置退出码
        exit_code = 0 if result.get("success", False) else 1
        logger.debug(f"程序退出，退出码: {exit_code}")
        sys.exit(exit_code)
        
    except json.JSONDecodeError as e:
        error_result = {
            "success": False,
            "error": f"参数JSON格式错误: {str(e)}"
        }
        # 输出详细错误信息到stderr用于调试
        import traceback
        print(f"=== JSON解析错误 ===", file=sys.stderr)
        print(f"错误信息: {str(e)}", file=sys.stderr)
        print(f"输入参数: {args['--params']}", file=sys.stderr)
        print(f"堆栈跟踪: {traceback.format_exc()}", file=sys.stderr)
        print("==================", file=sys.stderr)
        
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)
        
    except Exception as e:
        error_result = {
            "success": False,
            "error": f"程序执行失败: {str(e)}"
        }
        # 输出详细错误信息到stderr用于调试
        import traceback
        print(f"=== 程序执行错误 ===", file=sys.stderr)
        print(f"错误信息: {str(e)}", file=sys.stderr)
        print(f"执行动作: {args['--action']}", file=sys.stderr)
        print(f"输入参数: {args['--params']}", file=sys.stderr)
        print(f"堆栈跟踪: {traceback.format_exc()}", file=sys.stderr)
        print("==================", file=sys.stderr)
        
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
