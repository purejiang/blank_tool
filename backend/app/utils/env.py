import os
import sys
import platform
import shutil
import json
import subprocess
from typing import Dict, Optional, Set

# JAVA 环境变量
ENV_BT_JAVA_BIN = 'BT_JAVA_BIN'
# Python 环境变量
ENV_BT_PYTHON_BIN = 'BT_PYTHON_BIN'
# Node.js 环境变量
ENV_BT_NODE_BIN = 'BT_NODE_BIN'
# 日志级别环境变量
ENV_BT_LOG_LEVEL = 'BT_LOG_LEVEL'
# 是否自动搜索运行环境的变量
ENV_BT_SEARCH_SYSTEM_REQUIREMENTS = 'BT_SEARCH_SYSTEM_REQUIREMENTS'
# 运行时目录环境变量
ENV_BT_RUNTIME_DIR = 'BT_RUNTIME_DIR'
ENV_BT_SERVER_CONFIG = 'BT_SERVER_CONFIG'
# 应用版本环境变量
ENV_APP_VERSION = 'APP_VERSION'
# 项目名称环境变量
ENV_PROJECT_NAME = 'PROJECT_NAME'
# 输出目录环境变量
ENV_BT_OUTPUT_DIR = 'BT_OUTPUT_DIR'


# Backend root directory (absolute path)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

def resolve_path(path_str: str) -> str:
    """
    Resolve a path string to an absolute path.
    If the path is relative, it is resolved relative to the BACKEND_ROOTROOT.
    """
    if not path_str:
        return ""
    
    # If absolute, return as is
    if os.path.isabs(path_str):
        return path_str
        
    # Resolve relative to root
    resolved = os.path.normpath(os.path.join(ROOT, path_str))
    return resolved

def load_dotenv(path: str = None) -> Set[str]:
    """
    Simple .env file loader.
    """
    if path is None:
        # Default to .env in root
        path = os.path.join(ROOT, '.env')
    
    loaded_keys: Set[str] = set()
    if not os.path.exists(path):
        return loaded_keys

    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    if key and key not in os.environ:
                        os.environ[key] = value
                        loaded_keys.add(key)

    except Exception:
        pass
    return loaded_keys

def load_server_config(path: Optional[str] = None, override_keys: Optional[Set[str]] = None) -> Dict[str, str]:
    source_path = path or get_env(ENV_BT_SERVER_CONFIG, os.path.join(ROOT, 'server.config.json'))
    resolved_source = resolve_path(source_path)

    if not resolved_source or not os.path.exists(resolved_source):
        return {}

    try:
        with open(resolved_source, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    entries = raw.get('env') if isinstance(raw.get('env'), dict) else raw
    if not isinstance(entries, dict):
        return {}

    written: Dict[str, str] = {}
    override_keys = override_keys or set()
    for key, value in entries.items():
        if not isinstance(key, str):
            continue

        str_value = '' if value is None else str(value)
        if key in os.environ and key not in override_keys:
            continue

        os.environ[key] = str_value
        written[key] = str_value

    return written

def get_env(key: str, default=None):
    val = os.environ.get(key)
    return val if val not in (None, '') else default

def get_bool_env(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')

def get_output_dir() -> str:
    """
    Get the unified output directory.
    """
    output_dir = get_env(ENV_BT_OUTPUT_DIR, "./output")
    return resolve_path(output_dir)

def get_runtime_dir() -> str:
    """
    Get the runtime directory.
    """
    runtime_dir = get_env(ENV_BT_RUNTIME_DIR)
    if runtime_dir:
        return resolve_path(runtime_dir)
    
    # Fallback: Try to find 'runtime' in the project root or up one level
    # Development: backend/../runtime -> ROOT/runtime
    local_runtime = os.path.join(ROOT, 'runtime')
    if os.path.exists(local_runtime):
        return local_runtime
        
    # Production/Alternative: ROOT/../runtime
    up_runtime = os.path.abspath(os.path.join(ROOT, '..', 'runtime'))
    if os.path.exists(up_runtime):
        return up_runtime
        
    return ""

def get_cache_dir() -> str:
    """
    Return the resolved cache directory path.

    Uses the ``BT_CACHE_DIR`` environment variable, falling back to ``./cache``
    (resolved relative to the backend root). Creates the directory on disk if
    it does not exist.
    """
    cache_dir = get_env("BT_CACHE_DIR", "./cache")
    root = resolve_path(cache_dir)
    os.makedirs(root, exist_ok=True)
    return root


def get_tasks_root() -> str:
    """
    Return the root directory for all per-task working directories.

    This is placed *inside* the cache directory so that cache management
    (e.g. ``storage.clear``) can reach it.  Returns
    ``<cache_dir>/Tasks/`` and creates it on disk if missing.
    """
    tasks_root = os.path.join(get_cache_dir(), "Tasks")
    os.makedirs(tasks_root, exist_ok=True)
    return tasks_root


def get_task_dir(task_id: str) -> str:
    """
    Return the per-task working directory under the tasks root.

    Creates ``<tasks_root>/<task_id>/`` on disk (``exist_ok=True``) and
    returns the absolute path. Raises ``ValueError`` when *task_id* is empty
    or contains path traversal characters.
    """
    if not task_id:
        raise ValueError("task_id must be a non-empty string")

    task_id_str = str(task_id)

    # Reject "." as the exact id — resolves to current dir
    if task_id_str == ".":
        raise ValueError(f"task_id contains invalid characters: {task_id_str}")

    # Reject path separators and parent-dir traversal in any position
    invalid_chars = os.sep
    if os.sep == "\\":
        # On Windows, "/" is also a valid path separator
        invalid_chars += "/"
    if any(c in task_id_str for c in invalid_chars):
        raise ValueError(f"task_id contains invalid characters: {task_id_str}")

    # Reject ".." as a path component (handles "..", "a/..", etc.)
    if ".." in task_id_str:
        raise ValueError(f"task_id contains invalid characters: {task_id_str}")

    task_dir = os.path.join(get_tasks_root(), task_id_str)
    os.makedirs(task_dir, exist_ok=True)
    return task_dir

def get_task_subdir(task_id: str, name: str) -> str:
    """
    Return the absolute path to a named subdirectory of a task's working dir.

    *name* is typically ``"input"``, ``"output"`` or ``"logs"``.
    Creates the subdirectory on disk (``exist_ok=True``).
    """
    subdir = os.path.join(get_task_dir(task_id), name)
    os.makedirs(subdir, exist_ok=True)
    return subdir

def _is_executable_usable(path: str) -> bool:
    """Test whether an executable actually works by running it with -version."""
    if not path or not os.path.exists(path):
        return False
    try:
        result = subprocess.run(
            [path, "-version"],
            capture_output=True, text=True, timeout=10
        )
        # Some tools (like java) write version to stderr
        return result.returncode == 0
    except Exception:
        return False


def get_java_bin() -> str:
    # 1. First priority: Environment variable override
    override = os.environ.get(ENV_BT_JAVA_BIN)
    if override:
        resolved = resolve_path(override)
        if _is_executable_usable(resolved):
            return resolved

    # 2. Second priority: Bundled JRE in runtime dir (The User's Request)
    runtime_dir = get_runtime_dir()
    if runtime_dir:
        is_windows = platform.system() == 'Windows'
        java_exe = 'java.exe' if is_windows else 'java'
        
        # Possible locations for java executable in runtime
        candidates = [
            os.path.join(runtime_dir, 'jre', 'bin', java_exe),
            os.path.join(runtime_dir, 'java', 'bin', java_exe),
            os.path.join(runtime_dir, 'bin', java_exe),
            os.path.join(runtime_dir, java_exe)
        ]
        
        for candidate in candidates:
            if _is_executable_usable(candidate):
                return candidate

    # 3. Third priority: JAVA_HOME / JRE_HOME
    jh = os.environ.get('JAVA_HOME') or os.environ.get('JRE_HOME')
    if jh:
        candidate = os.path.join(jh, 'bin', 'java.exe' if platform.system() == 'Windows' else 'java')
        if _is_executable_usable(candidate):
            return candidate
        
    # 4. Last priority: System PATH
    which = shutil.which('java')
    if which and _is_executable_usable(which):
        return which
    return which or 'java'

def get_python_bin() -> str:
    override = os.environ.get(ENV_BT_PYTHON_BIN)
    if override:
        resolved = resolve_path(override)
        if os.path.exists(resolved):
            return resolved
            
    return sys.executable or 'python'

def get_node_bin() -> str:
    override = os.environ.get(ENV_BT_NODE_BIN)
    if override:
        resolved = resolve_path(override)
        if os.path.exists(resolved):
            return resolved
            
    which = shutil.which('node')
    return which or 'node'
