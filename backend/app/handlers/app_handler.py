
from app.utils.logger import Logger
from app.utils.env import ENV_APP_VERSION
from app.tools.tool_manager import ToolManager

logger = Logger.get_logger("AppHandler")
manager = ToolManager.instance()

def system_info(params, stream_handler):
    try:
        import platform
        import socket
        
        # 尝试导入 psutil
        try:
            import psutil
            has_psutil = True
        except ImportError:
            has_psutil = False
            logger.warning("psutil module not found, system info will be incomplete")
        
        # CPU信息
        cpu_info = {}
        if has_psutil:
            try:
                cpu_info = {
                    "count_logical": psutil.cpu_count(logical=True),
                    "count_physical": psutil.cpu_count(logical=False),
                    "percent": psutil.cpu_percent(interval=None),
                    "freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {}
                }
            except Exception as e:
                logger.warning(f"Failed to get CPU info: {e}")
        
        # 内存信息
        memory_info = {}
        if has_psutil:
            try:
                mem = psutil.virtual_memory()
                memory_info = {
                    "total": mem.total,
                    "available": mem.available,
                    "used": mem.used,
                    "percent": mem.percent
                }
            except Exception as e:
                logger.warning(f"Failed to get memory info: {e}")

        # 网络信息
        hostname = socket.gethostname()
        try:
            ip_address = socket.gethostbyname(hostname)
        except Exception:
            ip_address = "127.0.0.1"

        info = {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "hostname": hostname,
            "ip_address": ip_address,
            "cpu": cpu_info,
            "memory": memory_info
        }
        return {"system_info": info}
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        raise e

def build_info(params, stream_handler):
    try:
        import sys
        import subprocess
        from app.utils.env import get_python_bin, get_java_bin

        # Python 版本
        python_bin = get_python_bin()
        python_version = "Unknown"
        try:
            # 优先使用配置的 Python 解释器获取版本
            result = subprocess.run([python_bin, "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                # 输出示例: Python 3.11.4
                output = result.stdout.strip() or result.stderr.strip()
                python_version = output.split()[-1] if "Python" in output else output
            else:
                # 回退到当前环境
                python_version = sys.version.split()[0]
        except Exception:
            python_version = sys.version.split()[0]

        # Java 版本
        java_bin = get_java_bin()
        java_version = "Unknown"
        try:
            # 使用配置的 Java 路径
            result = subprocess.run([java_bin, "-version"], capture_output=True, text=True)
            if result.returncode == 0:
                # 输出示例: openjdk version "11.0.11" 2021-04-20
                output = result.stderr
                for line in output.splitlines():
                    if "version" in line:
                        java_version = line.split('"')[1]
                        break
        except Exception:
            pass

        return {
            "python_version": python_version,
            "java_version": java_version,
            "python_path": python_bin,
            "java_path": java_bin
        }
    except Exception as e:
        logger.error(f"获取构建信息失败: {e}")
        raise e
def app_info(params, stream_handler):
    try:
        from app.utils.env import get_env
        version = get_env(ENV_APP_VERSION, "")
        return {"version": version}
    except Exception as e:
        logger.error(f"获取应用信息失败: {e}")
        raise e
API_MAP = {
    "system.info": system_info,
    "build.info": build_info,
    "app.info": app_info
}
