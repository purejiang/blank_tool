#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plugin package import/export (zip bundles with manifest.json).

Package layout (zip root, or one top-level folder inside the zip):
    manifest.json   — {"id", "name"?, "version"?, "author"?,
                       "description"?, "entry"?: "main.py", "params"?: [...]}
    main.py         — entry module, must export run(context, **params)
    ui/index.html   — optional custom frontend UI (sandboxed iframe)
    assets/...      — optional resources

Import extracts into ``<BT_PLUGINS_DIR>/<id>/`` and reloads; export zips
an installed plugin (package dir as-is; legacy flat .py gets a generated
manifest).
"""

import json
import os
import re
import shutil
import traceback
import zipfile

from app.plugins.manager import PluginManager
from app.utils.logger import Logger
from app.utils.env import get_plugins_root
from app.common.exceptions import ToolException

logger = Logger.get_logger("PluginPackageHandler")

MANIFEST_NAME = "manifest.json"
DEFAULT_ENTRY = "main.py"
# plugin id = install dir name; keep it filesystem-safe
_ID_RE = re.compile(r"^[\w][\w.-]*$")


def _safe_join(base: str, rel: str) -> str:
    """Join and guarantee the result stays inside ``base`` (zip-slip guard)."""
    dest = os.path.normpath(os.path.join(base, rel))
    if not (dest == os.path.normpath(base) or dest.startswith(os.path.normpath(base) + os.sep)):
        raise ToolException(f"非法压缩包路径: {rel}")
    return dest


def _read_manifest_from_zip(zf: zipfile.ZipFile) -> tuple:
    """Locate manifest.json at zip root or under a single top-level folder.

    Returns (manifest_dict, prefix) where prefix is the folder wrapper
    ("" or "folder/") that all entries share.
    """
    names = [n.replace("\\", "/") for n in zf.namelist()]
    candidates = [n for n in names if n == MANIFEST_NAME or n.endswith("/" + MANIFEST_NAME)]
    if len(candidates) != 1:
        raise ToolException("压缩包中未找到唯一的 manifest.json")
    prefix = candidates[0][: -len(MANIFEST_NAME)]  # "" or "folder/"
    try:
        manifest = json.loads(zf.read(candidates[0]).decode("utf-8"))
    except Exception as e:
        raise ToolException(f"manifest.json 解析失败: {e}")
    if not isinstance(manifest, dict):
        raise ToolException("manifest.json 内容必须是 JSON 对象")
    # every entry must live under the same prefix
    for n in names:
        if n.endswith("/") or not n:
            continue
        if not n.startswith(prefix):
            raise ToolException("压缩包布局不一致：存在 manifest.json 同级的多余文件")
    return manifest, prefix


def _validate_manifest(manifest: dict, zf: zipfile.ZipFile, prefix: str) -> str:
    pid = str(manifest.get("id") or "").strip()
    if not pid or not _ID_RE.match(pid):
        raise ToolException(
            "manifest.json 缺少合法的 id（字母/数字/下划线/点/横线开头）"
        )
    if pid.startswith("__"):
        raise ToolException(f"非法插件 id: {pid}")
    entry = str(manifest.get("entry") or DEFAULT_ENTRY)
    entry_norm = entry.replace("\\", "/").lstrip("/")
    if entry_norm.startswith("../") or "/../" in entry_norm or ".." in entry_norm.split("/"):
        raise ToolException(f"非法 entry 路径: {entry}")
    names = {n.replace("\\", "/") for n in zf.namelist()}
    if prefix + entry_norm not in names:
        raise ToolException(f"入口文件不存在: {entry}")
    return pid


def import_plugin(params, stream_handler):
    """plugin.import — install a zip plugin package into the user dir.

    params: {zip_path, overwrite?: bool}
    Returns the refreshed plugin list, or {needs_overwrite: true, id}
    when the target exists and ``overwrite`` was not set.
    """
    zip_path = str(params.get("zip_path") or "")
    overwrite = bool(params.get("overwrite"))
    if not zip_path or not os.path.isfile(zip_path):
        raise ToolException(f"压缩包不存在: {zip_path}")

    user_dir = get_plugins_root()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            manifest, prefix = _read_manifest_from_zip(zf)
            pid = _validate_manifest(manifest, zf, prefix)
            dest = _safe_join(user_dir, pid)
            if os.path.exists(dest):
                if not overwrite:
                    return {"needs_overwrite": True, "id": pid}
                shutil.rmtree(dest)
            os.makedirs(dest, exist_ok=True)
            base = os.path.normpath(dest)
            for info in zf.infolist():
                rel = info.filename.replace("\\", "/")
                if rel.endswith("/"):
                    continue  # dir entries — created implicitly
                if prefix and rel.startswith(prefix):
                    rel = rel[len(prefix):]
                elif prefix:
                    raise ToolException("压缩包布局不一致：存在 manifest.json 同级的多余文件")
                target = _safe_join(base, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    except ToolException:
        raise
    except Exception as e:
        logger.error(f"导入插件失败: {traceback.format_exc()}")
        raise ToolException(f"导入插件失败: {e}")

    # strip the dir name so the manifest id decides (defensive; ids match
    # by construction, but a hand-edited zip could disagree)
    manager = PluginManager.instance()
    manager.load_plugins()
    names = [p["name"] for p in manager.get_all_plugins()]
    if pid not in names:
        raise ToolException(f"插件已解压但未被识别（id={pid}），请检查 entry 是否含 run 函数")
    logger.info(f"插件导入成功: {pid} -> {dest}")
    return manager.get_all_plugins()


def _generate_manifest(module, pid: str) -> dict:
    """Manifest for a legacy flat .py export."""
    return {
        "id": pid,
        "name": pid,
        "version": str(getattr(module, "VERSION", "0.0.1")),
        "author": str(getattr(module, "AUTHOR", "Unknown")),
        "description": str(getattr(module, "DESCRIPTION", "无描述")),
        "entry": DEFAULT_ENTRY,
        **({"params": module.PARAMS} if isinstance(getattr(module, "PARAMS", None), list) else {}),
    }


def export_plugin(params, stream_handler):
    """plugin.export — zip an installed plugin to ``target_path``.

    params: {name, target_path}
    Package plugins zip their dir as-is; legacy flat .py plugins are
    wrapped with a generated manifest.json.
    """
    name = str(params.get("name") or "")
    target_path = str(params.get("target_path") or "")
    if not name:
        raise ToolException("插件名未指定")
    if not target_path:
        raise ToolException("导出路径未指定")
    if not target_path.lower().endswith(".zip"):
        target_path += ".zip"

    manager = PluginManager.instance()
    plugin = manager.get_plugin(name)
    if plugin is None:
        raise ToolException(f"插件 {name} 未找到")
    base = manager.plugin_paths.get(name)
    if not base:
        raise ToolException(f"插件 {name} 缺少来源路径，请重新加载")

    try:
        with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.isfile(base) and base.endswith(".py"):
                # legacy flat plugin -> minimal package
                zf.write(base, DEFAULT_ENTRY)
                zf.writestr(MANIFEST_NAME, json.dumps(
                    _generate_manifest(plugin, name), ensure_ascii=False, indent=2
                ))
            else:
                for root, _dirs, files in os.walk(base):
                    for fn in sorted(files):
                        full = os.path.join(root, fn)
                        rel = os.path.relpath(full, base).replace(os.sep, "/")
                        zf.write(full, rel)
    except Exception as e:
        logger.error(f"导出插件失败: {traceback.format_exc()}")
        raise ToolException(f"导出插件失败: {e}")

    logger.info(f"插件导出成功: {name} -> {target_path}")
    return {"path": target_path}


API_MAP = {
    "plugin.import": import_plugin,
    "plugin.export": export_plugin,
}
