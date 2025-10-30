#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提供统一的缓存接口和数据持久化（使用JSON文件存储）
"""

import json
import pickle
import threading
import time
from pathlib import Path
from typing import Any, Dict

from core.base_service import BaseService

class CacheService(BaseService):
    """缓存管理器"""
    
    def __init__(self, cache_dir: str = None, config: dict = None):
        super().__init__("CacheService")
        
        # 缓存目录 - 修改为项目最外层
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # 获取项目根目录（从python_scripts向上两级）
            project_root = Path(__file__).parent.parent.parent
            self.cache_dir = project_root / "cache"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self.memory_cache = {}
        self.cache_lock = threading.RLock()
        
        # JSON文件缓存
        self.json_cache_file = self.cache_dir / "cache.json"
        self._init_json_cache()
        
        # 缓存配置 - 从传入的配置或使用默认值
        cache_config = config.get('cache', {}) if config else {}
        self.max_memory_size = cache_config.get("max_memory_size", 100 * 1024 * 1024)  # 100MB
        self.default_ttl = cache_config.get("default_ttl", 3600)  # 1小时
        self.cleanup_interval = cache_config.get("cleanup_interval", 300)  # 5分钟
        
        # 启动清理任务
        self._start_cleanup_task()
        
        self.logger.info("缓存管理器初始化完成")
        
    def _init_json_cache(self):
        """初始化JSON缓存文件"""
        try:
            if not self.json_cache_file.exists():
                # 创建空的缓存文件
                self._save_json_cache({})
                self.logger.info(f"创建JSON缓存文件: {self.json_cache_file}")
            else:
                # 验证现有文件格式
                self._load_json_cache()
                self.logger.info(f"加载JSON缓存文件: {self.json_cache_file}")
        except Exception as e:
            self.logger.error(f"初始化JSON缓存失败: {e}")
            # 创建新的缓存文件
            self._save_json_cache({})
    
    def _load_json_cache(self) -> Dict[str, Any]:
        """加载JSON缓存数据"""
        try:
            with open(self.json_cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def _save_json_cache(self, data: Dict[str, Any]):
        """保存JSON缓存数据"""
        try:
            with open(self.json_cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"保存JSON缓存失败: {e}")
    
    def set(self, key: str, value: Any, ttl: int = None, storage: str = "memory") -> bool:
        """设置缓存值"""
        if ttl is None:
            ttl = self.default_ttl
            
        expires_at = time.time() + ttl
        
        try:
            if storage == "memory":
                return self._set_memory_cache(key, value, expires_at)
            elif storage == "disk":
                return self._set_disk_cache(key, value, expires_at)
            elif storage == "json":
                return self._set_json_cache(key, value, expires_at)
            else:
                self.logger.warning(f"未知的存储类型: {storage}")
                return False
        except Exception as e:
            self.logger.error(f"设置缓存失败 [{key}]: {e}")
            return False
    
    def get(self, key: str, default: Any = None, storage: str = "memory") -> Any:
        """获取缓存值"""
        try:
            if storage == "memory":
                return self._get_memory_cache(key, default)
            elif storage == "disk":
                return self._get_disk_cache(key, default)
            elif storage == "json":
                return self._get_json_cache(key, default)
            else:
                self.logger.warning(f"未知的存储类型: {storage}")
                return default
        except Exception as e:
            self.logger.error(f"获取缓存失败 [{key}]: {e}")
            return default
    
    def delete(self, key: str, storage: str = "memory") -> bool:
        """删除缓存值"""
        try:
            if storage == "memory":
                return self._delete_memory_cache(key)
            elif storage == "disk":
                return self._delete_disk_cache(key)
            elif storage == "json":
                return self._delete_json_cache(key)
            else:
                self.logger.warning(f"未知的存储类型: {storage}")
                return False
        except Exception as e:
            self.logger.error(f"删除缓存失败 [{key}]: {e}")
            return False
    
    def exists(self, key: str, storage: str = "memory") -> bool:
        """检查缓存是否存在"""
        try:
            if storage == "memory":
                return self._exists_memory_cache(key)
            elif storage == "disk":
                return self._exists_disk_cache(key)
            elif storage == "json":
                return self._exists_json_cache(key)
            else:
                self.logger.warning(f"未知的存储类型: {storage}")
                return False
        except Exception as e:
            self.logger.error(f"检查缓存存在性失败 [{key}]: {e}")
            return False
    
    # 内存缓存方法
    def _set_memory_cache(self, key: str, value: Any, expires_at: float) -> bool:
        """设置内存缓存"""
        with self.cache_lock:
            self.memory_cache[key] = {
                "value": value,
                "expires_at": expires_at,
                "created_at": time.time()
            }
        return True
    
    def _get_memory_cache(self, key: str, default: Any = None) -> Any:
        """获取内存缓存"""
        with self.cache_lock:
            if key not in self.memory_cache:
                return default
                
            cache_item = self.memory_cache[key]
            
            # 检查是否过期
            if time.time() > cache_item["expires_at"]:
                del self.memory_cache[key]
                return default
                
            return cache_item["value"]
    
    def _delete_memory_cache(self, key: str) -> bool:
        """删除内存缓存"""
        with self.cache_lock:
            if key in self.memory_cache:
                del self.memory_cache[key]
                return True
        return False
    
    def _exists_memory_cache(self, key: str) -> bool:
        """检查内存缓存是否存在"""
        with self.cache_lock:
            if key not in self.memory_cache:
                return False
                
            cache_item = self.memory_cache[key]
            
            # 检查是否过期
            if time.time() > cache_item["expires_at"]:
                del self.memory_cache[key]
                return False
                
            return True
    
    # 磁盘缓存方法
    def _set_disk_cache(self, key: str, value: Any, expires_at: float) -> bool:
        """设置磁盘缓存"""
        cache_file = self.cache_dir / f"{key}.cache"
        
        cache_data = {
            "value": value,
            "expires_at": expires_at,
            "created_at": time.time()
        }
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            return True
        except Exception as e:
            self.logger.error(f"保存磁盘缓存失败 [{key}]: {e}")
            return False
    
    def _get_disk_cache(self, key: str, default: Any = None) -> Any:
        """获取磁盘缓存"""
        cache_file = self.cache_dir / f"{key}.cache"
        
        if not cache_file.exists():
            return default
            
        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
                
            # 检查是否过期
            if time.time() > cache_data["expires_at"]:
                cache_file.unlink(missing_ok=True)
                return default
                
            return cache_data["value"]
            
        except Exception as e:
            self.logger.error(f"读取磁盘缓存失败 [{key}]: {e}")
            # 删除损坏的缓存文件
            cache_file.unlink(missing_ok=True)
            return default
    
    def _delete_disk_cache(self, key: str) -> bool:
        """删除磁盘缓存"""
        cache_file = self.cache_dir / f"{key}.cache"
        
        try:
            if cache_file.exists():
                cache_file.unlink()
                return True
        except Exception as e:
            self.logger.error(f"删除磁盘缓存失败 [{key}]: {e}")
            
        return False
    
    def _exists_disk_cache(self, key: str) -> bool:
        """检查磁盘缓存是否存在"""
        cache_file = self.cache_dir / f"{key}.cache"
        
        if not cache_file.exists():
            return False
            
        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
                
            # 检查是否过期
            if time.time() > cache_data["expires_at"]:
                cache_file.unlink(missing_ok=True)
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"检查磁盘缓存失败 [{key}]: {e}")
            # 删除损坏的缓存文件
            cache_file.unlink(missing_ok=True)
            return False
    
    # JSON缓存方法
    def _set_json_cache(self, key: str, value: Any, expires_at: float) -> bool:
        """设置JSON缓存"""
        try:
            cache_data = self._load_json_cache()
            
            cache_data[key] = {
                "value": value,
                "expires_at": expires_at,
                "created_at": time.time()
            }
            
            self._save_json_cache(cache_data)
            return True
        except Exception as e:
            self.logger.error(f"设置JSON缓存失败 [{key}]: {e}")
            return False
    
    def _get_json_cache(self, key: str, default: Any = None) -> Any:
        """获取JSON缓存"""
        try:
            cache_data = self._load_json_cache()
            
            if key not in cache_data:
                return default
                
            cache_item = cache_data[key]
            
            # 检查是否过期
            if time.time() > cache_item["expires_at"]:
                del cache_data[key]
                self._save_json_cache(cache_data)
                return default
                
            return cache_item["value"]
        except Exception as e:
            self.logger.error(f"获取JSON缓存失败 [{key}]: {e}")
            return default
    
    def _delete_json_cache(self, key: str) -> bool:
        """删除JSON缓存"""
        try:
            cache_data = self._load_json_cache()
            
            if key in cache_data:
                del cache_data[key]
                self._save_json_cache(cache_data)
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除JSON缓存失败 [{key}]: {e}")
            return False
    
    def _exists_json_cache(self, key: str) -> bool:
        """检查JSON缓存是否存在"""
        try:
            cache_data = self._load_json_cache()
            
            if key not in cache_data:
                return False
                
            cache_item = cache_data[key]
            
            # 检查是否过期
            if time.time() > cache_item["expires_at"]:
                del cache_data[key]
                self._save_json_cache(cache_data)
                return False
                
            return True
        except Exception as e:
            self.logger.error(f"检查JSON缓存失败 [{key}]: {e}")
            return False
    
    def cleanup_expired(self, storage: str = None) -> Dict[str, int]:
        """清理过期缓存"""
        cleaned = {"memory": 0, "disk": 0, "json": 0}
        current_time = time.time()
        
        try:
            # 清理内存缓存
            if storage is None or storage == "memory":
                with self.cache_lock:
                    expired_keys = []
                    for key, cache_item in self.memory_cache.items():
                        if current_time > cache_item["expires_at"]:
                            expired_keys.append(key)
                    
                    for key in expired_keys:
                        del self.memory_cache[key]
                        cleaned["memory"] += 1
            
            # 清理磁盘缓存
            if storage is None or storage == "disk":
                for cache_file in self.cache_dir.glob("*.cache"):
                    try:
                        with open(cache_file, 'rb') as f:
                            cache_data = pickle.load(f)
                            
                        if current_time > cache_data["expires_at"]:
                            cache_file.unlink()
                            cleaned["disk"] += 1
                            
                    except Exception as e:
                        self.logger.warning(f"清理磁盘缓存文件失败 [{cache_file}]: {e}")
                        # 删除损坏的缓存文件
                        cache_file.unlink(missing_ok=True)
                        cleaned["disk"] += 1
            
            # 清理JSON缓存
            if storage is None or storage == "json":
                cache_data = self._load_json_cache()
                expired_keys = []
                
                for key, cache_item in cache_data.items():
                    if current_time > cache_item["expires_at"]:
                        expired_keys.append(key)
                
                for key in expired_keys:
                    del cache_data[key]
                    cleaned["json"] += 1
                
                if expired_keys:
                    self._save_json_cache(cache_data)
            
            if sum(cleaned.values()) > 0:
                self.logger.info(f"清理过期缓存完成: {cleaned}")
                
        except Exception as e:
            self.logger.error(f"清理过期缓存失败: {e}")
            
        return cleaned
    
    def clear_all(self, storage: str = None) -> Dict[str, int]:
        """清空所有缓存"""
        cleared = {"memory": 0, "disk": 0, "json": 0}
        
        try:
            # 清空内存缓存
            if storage is None or storage == "memory":
                with self.cache_lock:
                    cleared["memory"] = len(self.memory_cache)
                    self.memory_cache.clear()
            
            # 清空磁盘缓存
            if storage is None or storage == "disk":
                for cache_file in self.cache_dir.glob("*.cache"):
                    try:
                        cache_file.unlink()
                        cleared["disk"] += 1
                    except Exception as e:
                        self.logger.warning(f"删除磁盘缓存文件失败 [{cache_file}]: {e}")
            
            # 清空JSON缓存
            if storage is None or storage == "json":
                cache_data = self._load_json_cache()
                cleared["json"] = len(cache_data)
                self._save_json_cache({})
            
            self.logger.info(f"清空缓存完成: {cleared}")
            
        except Exception as e:
            self.logger.error(f"清空缓存失败: {e}")
            
        return cleared
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            "memory": {"count": 0, "size": 0},
            "disk": {"count": 0, "size": 0},
            "json": {"count": 0, "size": 0}
        }
        
        try:
            # 内存缓存统计
            with self.cache_lock:
                stats["memory"]["count"] = len(self.memory_cache)
                # 估算内存使用量（简单估算）
                stats["memory"]["size"] = len(str(self.memory_cache).encode('utf-8'))
            
            # 磁盘缓存统计
            disk_files = list(self.cache_dir.glob("*.cache"))
            stats["disk"]["count"] = len(disk_files)
            stats["disk"]["size"] = sum(f.stat().st_size for f in disk_files if f.exists())
            
            # JSON缓存统计
            cache_data = self._load_json_cache()
            stats["json"]["count"] = len(cache_data)
            if self.json_cache_file.exists():
                stats["json"]["size"] = self.json_cache_file.stat().st_size
            
        except Exception as e:
            self.logger.error(f"获取缓存统计失败: {e}")
            
        return stats
    
    def get_info(self) -> Dict[str, Any]:
        """获取缓存管理器信息"""
        return {
            "cache_dir": str(self.cache_dir),
            "json_cache_file": str(self.json_cache_file),
            "max_memory_size": self.max_memory_size,
            "default_ttl": self.default_ttl,
            "cleanup_interval": self.cleanup_interval,
            "stats": self.get_stats()
        }
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态（实现BaseService抽象方法）"""
        return {
            "name": self.name,
            "status": "running",
            "cache_dir": str(self.cache_dir),
            "json_cache_file": str(self.json_cache_file),
            "max_memory_size": self.max_memory_size,
            "default_ttl": self.default_ttl,
            "cleanup_interval": self.cleanup_interval,
            "stats": self.get_stats()
        }
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(self.cleanup_interval)
                    self.cleanup_expired()
                except Exception as e:
                    self.logger.error(f"清理任务异常: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        self.logger.info("缓存清理任务已启动")
