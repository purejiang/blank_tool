import importlib.util
import json
import os
import shutil
import sys
import threading
import traceback
from typing import Dict, Any, List, Optional
from app.utils.logger import Logger
from app.utils.env import get_plugins_root
from app.plugins.context import PluginContext


class PluginManager:
    """Discovers and runs external plugins.

    Two scan roots, user overrides builtin on name collision:
      * builtin: ``backend/app/plugins/builtin/`` — ships with the app
        (read-only in a packaged install).
      * user:   ``<localdata>/plugins`` (``BT_PLUGINS_DIR``) — drop a
        ``.py`` here and it shows up after ``plugin.reload``.

    Two plugin layouts per scan root:
      * flat file: ``<name>.py`` — plugin name = file stem (legacy).
      * package dir: ``<dir>/manifest.json`` + entry (default
        ``main.py``) — plugin name = manifest ``id`` (fallback: dir
        name). Metadata (DESCRIPTION/VERSION/AUTHOR/PARAMS) comes from
        the manifest, module attributes win if both exist.

    ``manifest.name`` is display-only: it surfaces as ``display_name``
    in ``get_all_plugins()``, while the id remains the identity every
    API (run / export / delete) keys on.

    A plugin module must export ``run(context, **params)`` and may
    declare ``DESCRIPTION / VERSION / AUTHOR`` plus an optional
    ``PARAMS`` list for frontend form rendering.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        # builtin dir = builtin/ next to this file (NOT the framework dir
        # itself — manager.py/context.py were once scanned as "plugins").
        self.builtin_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "builtin"
        )
        self.user_dir = get_plugins_root()
        self.plugins: Dict[str, Any] = {}
        # plugin name -> base dir (scan dir for flat plugins, package dir
        # for manifest plugins); used by plugin.export to zip a package
        self.plugin_paths: Dict[str, str] = {}
        # plugin name -> parsed manifest.json (package plugins only)
        self.manifests: Dict[str, Dict[str, Any]] = {}
        self.logger = Logger.get_logger("PluginManager")
        self._scan_lock = threading.RLock()
        self._ensure_dirs()
        self.load_plugins()
        self._initialized = True

    @classmethod
    def instance(cls) -> "PluginManager":
        return cls()

    @property
    def scan_dirs(self) -> List[str]:
        # user dir FIRST: same-name user plugin overrides the builtin one
        return [self.user_dir, self.builtin_dir]

    def _ensure_dirs(self):
        for d in (self.builtin_dir, self.user_dir):
            if not os.path.exists(d):
                try:
                    os.makedirs(d)
                    self.logger.info(f"创建插件目录: {d}")
                except Exception as e:
                    self.logger.error(f"无法创建插件目录 {d}: {e}")

    def load_plugins(self):
        """(Re)load all plugins from every scan root (flat .py + package dirs)."""
        self.logger.info("开始加载插件...")
        loaded: Dict[str, Any] = {}
        paths: Dict[str, str] = {}
        mans: Dict[str, Dict[str, Any]] = {}
        with self._scan_lock:
            for scan_dir in self.scan_dirs:
                if not os.path.isdir(scan_dir):
                    self.logger.warning(f"插件目录不存在: {scan_dir}")
                    continue
                for filename in sorted(os.listdir(scan_dir)):
                    path = os.path.join(scan_dir, filename)
                    if os.path.isfile(path) and filename.endswith(".py") and not filename.startswith("__"):
                        # legacy flat plugin: name = file stem, no manifest
                        plugin_name = filename[:-3]
                        manifest: Optional[Dict[str, Any]] = None
                    elif os.path.isdir(path) and not filename.startswith("__"):
                        manifest = self._read_manifest(path)
                        if manifest is None:
                            continue  # plain dir without manifest.json — not a plugin
                        plugin_name = str(manifest.get("id") or filename).strip() or filename
                    else:
                        continue
                    # scan_dirs is [user, builtin] — the first (user) hit
                    # wins; never let the builtin copy overwrite it
                    if plugin_name in loaded:
                        continue
                    if self._load_from_path(plugin_name, path, manifest, into=loaded):
                        paths[plugin_name] = path
                        if manifest is not None:
                            mans[plugin_name] = manifest
            self.plugins = loaded
            self.plugin_paths = paths
            self.manifests = mans
        self.logger.info(f"插件加载完成，共加载 {len(self.plugins)} 个插件")

    @staticmethod
    def _read_manifest(pkg_dir: str) -> Optional[Dict[str, Any]]:
        """Read ``<pkg_dir>/manifest.json``; None if missing/invalid."""
        mpath = os.path.join(pkg_dir, "manifest.json")
        if not os.path.isfile(mpath):
            return None
        try:
            with open(mpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except Exception:
            Logger.get_logger("PluginManager").error(
                f"manifest.json 解析失败: {mpath}\n{traceback.format_exc()}"
            )
            return None

    def _load_from_path(
        self,
        plugin_name: str,
        base_path: str,
        manifest: Optional[Dict[str, Any]],
        into: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Load one plugin from ``base_path`` (flat .py file or package dir)."""
        target = into if into is not None else self.plugins
        try:
            if manifest is None:
                file_path = base_path
            else:
                # entry must resolve INSIDE the package dir (zip-slip guard
                # also applies to on-disk manifests)
                entry = str(manifest.get("entry") or "main.py")
                file_path = os.path.normpath(os.path.join(base_path, entry))
                if not file_path.startswith(os.path.normpath(base_path) + os.sep):
                    self.logger.error(f"插件 {plugin_name} 无效: entry 越界 ({entry})")
                    return False
            if not os.path.isfile(file_path):
                self.logger.error(f"插件文件不存在: {file_path}")
                return False

            # unique module key so a user plugin and a builtin with the
            # same name never collide in sys.modules
            mod_key = f"bt_plugin_{plugin_name}"
            spec = importlib.util.spec_from_file_location(mod_key, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_key] = module
                spec.loader.exec_module(module)

                # 验证插件是否有效（必须包含 run 函数）
                if not hasattr(module, "run"):
                    self.logger.warning(f"插件 {plugin_name} 无效: 缺少 run 函数")
                    return False

                # manifest metadata fills gaps; module attributes win
                if manifest:
                    if not hasattr(module, "DESCRIPTION") and manifest.get("description"):
                        module.DESCRIPTION = manifest["description"]
                    if not hasattr(module, "VERSION") and manifest.get("version"):
                        module.VERSION = manifest["version"]
                    if not hasattr(module, "AUTHOR") and manifest.get("author"):
                        module.AUTHOR = manifest["author"]
                    if not hasattr(module, "PARAMS") and isinstance(manifest.get("params"), list):
                        module.PARAMS = manifest["params"]

                target[plugin_name] = module
                self.logger.info(f"已加载插件: {plugin_name} ({file_path})")
                return True
            return False
        except Exception:
            # a broken plugin must never take down the backend
            self.logger.error(f"加载插件 {plugin_name} 失败: {traceback.format_exc()}")
            return False

    def load_plugin(
        self,
        plugin_name: str,
        scan_dir: Optional[str] = None,
        into: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """加载指定插件（默认从 scan_dirs 顺序查找，仅平铺 .py）"""
        try:
            file_path = None
            dirs = [scan_dir] if scan_dir else self.scan_dirs
            for d in dirs:
                cand = os.path.join(d, f"{plugin_name}.py")
                if os.path.isfile(cand):
                    file_path = cand
                    break
            if not file_path:
                self.logger.error(f"插件文件不存在: {plugin_name}")
                return False
            return self._load_from_path(plugin_name, file_path, None, into=into)
        except Exception:
            self.logger.error(f"加载插件 {plugin_name} 失败: {traceback.format_exc()}")
            return False

    def get_plugin(self, plugin_name: str) -> Any:
        with self._scan_lock:
            return self.plugins.get(plugin_name)

    def _is_builtin(self, name: str) -> bool:
        """True when the plugin came from the app's builtin dir."""
        base = self.plugin_paths.get(name)
        if not base:
            return False
        b = os.path.normpath(base)
        root = os.path.normpath(self.builtin_dir)
        return b == root or b.startswith(root + os.sep)

    @staticmethod
    def _display_name(name: str, manifest: Optional[Dict[str, Any]]) -> str:
        """Human-readable label for ``name``.

        Package plugins may declare ``manifest.name`` as a display-only
        label — the id stays the identity used by run/export/delete, so a
        pretty name never changes what the frontend has to send back.
        Flat ``.py`` plugins have no manifest → label == id.
        """
        if isinstance(manifest, dict):
            label = str(manifest.get("name") or "").strip()
            if label:
                return label
        return name

    def get_all_plugins(self) -> List[Dict[str, Any]]:
        """获取所有插件信息"""
        with self._scan_lock:
            items = list(self.plugins.items())
            # snapshot alongside the modules so a concurrent reload can't
            # pull the manifest/path dicts out from under this loop
            manifests = dict(self.manifests)
            paths = dict(self.plugin_paths)
        result = []
        for name, module in items:
            manifest = manifests.get(name)
            info = {
                "name": name,
                # display-only; `name` (id) is what the frontend sends back
                "display_name": self._display_name(name, manifest),
                "description": getattr(module, "DESCRIPTION", "无描述"),
                "version": getattr(module, "VERSION", "0.0.1"),
                "author": getattr(module, "AUTHOR", "Unknown"),
                "builtin": self._is_builtin(name),
            }
            params = getattr(module, "PARAMS", None)
            if isinstance(params, list):
                info["params"] = params
            # package plugin with a custom UI: expose the absolute ui html
            # path so the frontend can render it in a sandboxed iframe
            if manifest and manifest.get("ui"):
                base = paths.get(name)
                if base:
                    info["ui_path"] = os.path.normpath(
                        os.path.join(base, str(manifest["ui"]))
                    )
            result.append(info)
        return result

    def delete_plugin(self, name: str) -> List[Dict[str, Any]]:
        """Delete a plugin's file/dir from its scan root, then rescan.

        Only paths inside a scan root are removable. Builtin plugins qualify
        too — deleting one edits the app install (read-only in a packaged
        build, which surfaces as a clear error instead of a silent no-op).
        Returns the refreshed plugin list.
        """
        with self._scan_lock:
            base = self.plugin_paths.get(name)
            if not base:
                raise Exception(f"插件 {name} 未找到")
            target = os.path.normpath(base)
            roots = [os.path.normpath(self.user_dir),
                     os.path.normpath(self.builtin_dir)]
            if not any(target == r or target.startswith(r + os.sep) for r in roots):
                raise Exception(f"拒绝删除扫描目录之外的路径: {base}")
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target)
                elif os.path.isfile(target):
                    os.remove(target)
                else:
                    raise Exception(f"路径不存在: {target}")
            except Exception as e:
                raise Exception(f"删除插件 {name} 失败: {e}")
        self.logger.info(f"已删除插件: {name} ({target})")
        # drop the loaded module so a same-name plugin reloaded later never
        # reuses this one's already-imported code
        sys.modules.pop(f"bt_plugin_{name}", None)
        self.load_plugins()
        return self.get_all_plugins()

    def run_plugin(self, plugin_name: str, params: Dict[str, Any], stream_handler: Optional[Any] = None) -> Any:
        """运行插件"""
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            raise Exception(f"插件 {plugin_name} 未找到")

        context = PluginContext(plugin_name, stream_handler)
        try:
            context.log(f"开始运行插件: {plugin_name}")
            # 调用插件的 run 函数
            result = plugin.run(context, **params)
            context.log(f"插件运行结束")
            return result
        except Exception as e:
            context.error(f"插件运行出错: {e}")
            self.logger.error(f"运行插件 {plugin_name} 失败: {traceback.format_exc()}")
            raise
