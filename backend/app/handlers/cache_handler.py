import os
import shutil
from app.utils.logger import Logger

logger = Logger.get_logger("CacheHandler")


def _success(payload):
    return {"type": "success", "payload": payload}


def _error(message):
    return {"type": "error", "payload": {"message": message}}


def _cache_root():
    here = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(here, "cache")


def cache_info(params, stream_handler):
    root = _cache_root()
    total_size = 0
    total_files = 0
    try:
        if os.path.exists(root):
            for dirpath, _, filenames in os.walk(root):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total_size += os.path.getsize(fp)
                        total_files += 1
                    except Exception:
                        pass
        return _success({"path": root, "size": total_size, "files": total_files})
    except Exception as e:
        logger.error(f"获取缓存信息失败: {e}")
        return _error(str(e))


def cache_clear(params, stream_handler):
    root = _cache_root()
    try:
        if os.path.exists(root):
            # 仅清理文件与空目录，不删除根目录
            for entry in os.listdir(root):
                p = os.path.join(root, entry)
                try:
                    if os.path.isfile(p) or os.path.islink(p):
                        os.remove(p)
                    elif os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                except Exception:
                    pass
        return _success({"path": root, "size": 0, "files": 0})
    except Exception as e:
        logger.error(f"清除缓存失败: {e}")
        return _error(str(e))


API_MAP = {
    "cache.get_info": cache_info,
    "cache.info": cache_info,
    "cache.clear": cache_clear,
}

