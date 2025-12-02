import os
import platform
import shutil
from pathlib import Path

ENV_BT_JAVA_BIN = 'BT_JAVA_BIN'
ENV_BT_LOG_LEVEL = 'BT_LOG_LEVEL'
ENV_BT_SEARCH_SYSTEM_TOOLS = 'BT_SEARCH_SYSTEM_TOOLS'

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
    if override and os.path.exists(override):
        return override
    jh = os.environ.get('JAVA_HOME') or os.environ.get('JRE_HOME')
    if jh:
        candidate = os.path.join(jh, 'bin', 'java.exe' if platform.system() == 'Windows' else 'java')
        if os.path.exists(candidate):
            return candidate
    packaged = Path(__file__).resolve().parent.parent.parent / 'runtime' / 'jre' / 'bin' / ('java.exe' if platform.system() == 'Windows' else 'java')
    if packaged.exists():
        return str(packaged)
    which = shutil.which('java')
    return which or 'java'