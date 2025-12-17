import os
import platform
import shutil

ENV_BT_JAVA_BIN = 'BT_JAVA_BIN'
ENV_BT_PYTHON_BIN = 'BT_PYTHON_BIN'
ENV_BT_NODE_BIN = 'BT_NODE_BIN'
ENV_BT_LOG_LEVEL = 'BT_LOG_LEVEL'
ENV_BT_SEARCH_SYSTEM_TOOLS = 'BT_SEARCH_SYSTEM_TOOLS'

ENV_APP_VERSION = 'APP_VERSION'
ENV_PROJECT_NAME = 'PROJECT_NAME'


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

def load_dotenv(path: str = None):
    """
    Simple .env file loader.
    """
    if path is None:
        # Default to .env in root
        path = os.path.join(ROOT, '.env')
    
    if not os.path.exists(path):
        return

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

    except Exception:
        pass

def get_env(key: str, default=None):
    val = os.environ.get(key)
    return val if val not in (None, '') else default

def get_bool_env(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')

def get_java_bin() -> str:
    override = os.environ.get(ENV_BT_JAVA_BIN)
    if override:
        resolved = resolve_path(override)
        if os.path.exists(resolved):
            return resolved

    jh = os.environ.get('JAVA_HOME') or os.environ.get('JRE_HOME')
    if jh:
        candidate = os.path.join(jh, 'bin', 'java.exe' if platform.system() == 'Windows' else 'java')
        if os.path.exists(candidate):
            return candidate
        
    which = shutil.which('java')
    return which or 'java'

def get_python_bin() -> str:
    override = os.environ.get(ENV_BT_PYTHON_BIN)
    if override:
        resolved = resolve_path(override)
        if os.path.exists(resolved):
            return resolved
            
    import sys
    return sys.executable or 'python'

def get_node_bin() -> str:
    override = os.environ.get(ENV_BT_NODE_BIN)
    if override:
        resolved = resolve_path(override)
        if os.path.exists(resolved):
            return resolved
            
    which = shutil.which('node')
    return which or 'node'
