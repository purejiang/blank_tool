#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""white-label-packer — 白包打包插件（其他包 / 三星 / 谷歌 / 任意自定义渠道）。

输入：基础 APK（必填）+ 同版本 AAB（可选，谷歌优先直改）。
输出：每渠道签名 APK；谷歌渠道签名 AAB（直改源 AAB，失败回退重建）。

设计要点（与 docs/WHITE_LABEL_PACKER.md 对应）：

* 身份改名用 aapt2 ``--rename-manifest-package``（等价 AGP 的
  applicationIdSuffix）：清单 package 保持资源包名，类名/资源包名不动，
  资源 ID 用源 APK dump 出来的 ``--stable-ids`` 锁死。
* 图标不新增 drawable（否则要改 resources.pb），而是解析原图标资源文件，
  用 ``app.utils.png_image`` 把用户 PNG 缩放到每个 density 后覆盖同名文件；
  APK 重编和 AAB 直改共用同一份替换映射。
* AAB 直改：``bundletool dump manifest`` 只用来做一致性 guard；真正生成
  proto manifest 用 apktool 解码出的文本清单 + aapt2 ``--proto-format``
  （dump 出来的枚举属性是十六进制，aapt2 不认；APK 清单是可链接的）。
* AAB 重签：jarsigner（JAR v1），不是 apksigner；改完先删旧
  ``META-INF`` 签名再签。
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from app.common.exceptions import ToolException
from app.utils.env import get_output_dir, get_runtime_dir
from app.utils.png_image import (
    decode_png_rgba,
    image_dimensions,
    resize_png,
)

DESCRIPTION = (
    "从基础 APK（可选同版本 AAB）批量生成白包：其他包、三星、谷歌及任意自定义渠道。"
    "改包名、应用名、图标、签名、渠道标识、额外权限（如 BILLING）与 assets 文件；"
    "AAB 渠道优先直改源 AAB，失败自动回退重建。"
)
VERSION = "1.2.0"
AUTHOR = "blank_tool"

ANDROID_NS = "http://schemas.android.com/apk/res/android"
DIST_NS = "http://schemas.android.com/apk/distribution"
ANDROID = "{%s}" % ANDROID_NS

# 渠道预置（UI 也这么做兜底；改这里即可加内置渠道；用户还能在 UI 里
# 添加任意「其他包」，id 只用于产物文件名和报告，不参与业务逻辑）
CHANNEL_PRESETS = [
    {
        "id": "other",
        "label": "其他包",
        "format": "apk",
        "also_apk": True,
        "suffix": ".other",
        "notes": "通用白包渠道；默认 APK，也可选 AAB / 两者。",
    },
    {
        "id": "samsung",
        "label": "三星（Galaxy Store）",
        "format": "apk",
        "also_apk": True,
        "suffix": ".samsung",
        "notes": "常规 APK 上架；如涉及内购需按三星要求接 IAP。",
    },
    {
        "id": "google",
        "label": "谷歌（Google Play）",
        "format": "aab",
        "also_apk": True,
        "suffix": ".google",
        "notes": "Play 要求 AAB；有同版本 AAB 时直改，否则从 APK 重建。",
    },
]

# 签名条目（APK/AAB 通用）
_SIG_RE = re.compile(
    r"^META-INF/(MANIFEST\.MF|.*\.(SF|RSA|DSA|EC))$", re.IGNORECASE
)
_PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
_CHANNEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


class _Cancelled(Exception):
    """协作式取消：由 _check_cancel/命令 cancellation 抛出。"""


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return os.name == "nt"


def _exe(name: str) -> str:
    return name + ".exe" if _is_windows() else name


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _write_bytes(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tail(text: str, n: int = 40) -> str:
    lines = (text or "").splitlines()
    return "\n".join(lines[-n:])


def _fmt_size(n: Optional[int]) -> str:
    if not n:
        return "-"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _check_cancel(context) -> None:
    if context.is_cancelled():
        raise _Cancelled()


def _log_tail(context, title: str, text: str) -> None:
    tail = _tail(text)
    if tail:
        context.log(f"{title}: {tail}")


# ---------------------------------------------------------------------------
# 工具解析
# ---------------------------------------------------------------------------

_TOOL_NAMES = [
    ("apktool", "apktool"),
    ("aapt2", "aapt"),
    ("zipalign", "zipalign"),
    ("apksigner", "apksigner"),
    ("bundletool", "bundletool"),
    ("jarsigner", "jarsigner"),
]


def _tool_status(context) -> Dict[str, bool]:
    status: Dict[str, bool] = {}
    for key, name in _TOOL_NAMES:
        try:
            tool = context.get_tool(name)
            status[key] = bool(
                tool and getattr(tool, "is_valid", False)
                and getattr(tool, "tool_path", "")
            )
        except Exception:
            status[key] = False
    status["java"] = False
    status["keytool"] = False
    status["android_jar"] = False
    if status["apktool"]:
        try:
            java = context.get_tool("apktool").get_java_path()
            status["java"] = bool(java and os.path.isfile(java))
            if status["java"]:
                status["keytool"] = os.path.isfile(
                    os.path.join(os.path.dirname(java), _exe("keytool"))
                )
        except Exception:
            pass
    try:
        aapt2_path = ""
        try:
            aapt2_path = context.get_tool("aapt").tool_path
        except Exception:
            aapt2_path = ""
        jar = _android_jar(context, aapt2_path or None)
        status["android_jar"] = bool(jar and os.path.isfile(jar))
    except Exception:
        status["android_jar"] = False
    return status


def _android_jar(context, aapt2_path: Optional[str]) -> str:
    runtime = get_runtime_dir() or ""
    if runtime:
        cand = os.path.join(runtime, "android", "android.jar")
        if os.path.isfile(cand):
            return cand
    if aapt2_path:
        cand = os.path.join(
            os.path.dirname(os.path.dirname(aapt2_path)), "android", "android.jar"
        )
        if os.path.isfile(cand):
            return cand
    return ""


def _collect_tools(context, need_aab: bool = False) -> Dict[str, Any]:
    """解析插件需要的全部工具路径；缺失则抛 ToolException。"""
    tools: Dict[str, Any] = {}
    missing: List[str] = []
    for key, name in _TOOL_NAMES:
        try:
            tool = context.get_tool(name)
        except Exception:
            tool = None
        if not tool or not getattr(tool, "is_valid", False) or not getattr(
            tool, "tool_path", ""
        ):
            missing.append(name)
        tools[key] = tool

    if missing:
        raise ToolException("缺少运行工具: " + ", ".join(missing))

    java = ""
    try:
        java = tools["apktool"].get_java_path()
    except Exception:
        java = ""
    if not java or not os.path.isfile(java):
        raise ToolException("找不到 Java 运行时（runtime/jre/bin/java）")
    tools["java"] = java
    tools["keytool"] = os.path.join(os.path.dirname(java), _exe("keytool"))
    if not os.path.isfile(tools["keytool"]):
        tools["keytool"] = ""

    android_jar = _android_jar(context, tools["aapt2"].tool_path)
    if not android_jar:
        raise ToolException("找不到 runtime/android/android.jar（aapt2 link 需要）")
    tools["android_jar"] = android_jar
    tools["aapt2"] = tools["aapt2"].tool_path
    tools["apktool"] = tools["apktool"].tool_path
    tools["zipalign"] = tools["zipalign"].tool_path
    tools["apksigner"] = tools["apksigner"].tool_path
    tools["bundletool"] = tools["bundletool"].tool_path
    tools["jarsigner"] = tools["jarsigner"].tool_path
    return tools


# ---------------------------------------------------------------------------
# 命令执行
# ---------------------------------------------------------------------------

def _run(context, cmd: List[str], cwd: Optional[str] = None,
         timeout: Optional[float] = None) -> Tuple[int, str]:
    """长命令：走 context.run_command（逐行日志 + 取消），失败返回码+输出。"""
    _check_cancel(context)
    result = context.run_command(cmd, cwd=cwd, timeout=timeout)
    if result.get("cancelled"):
        raise _Cancelled()
    rc = result.get("returncode")
    if not isinstance(rc, int):
        rc = 1
    lines = result.get("output") or []
    return rc, "\n".join(str(x) for x in lines)


def _quiet_run(cmd: List[str], tmp_dir: str,
               timeout: float = 600.0) -> Tuple[int, str]:
    """短命令 / 大输出命令：stdout 重定向到文件，避免管道和日志刷屏。

    用文件而不是管道也让这个函数在受限环境（禁止匿名管道）下可跑。
    """
    os.makedirs(tmp_dir, exist_ok=True)
    path = os.path.join(tmp_dir, f"quiet-{uuid.uuid4().hex}.txt")
    try:
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            proc = subprocess.run(
                cmd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout
            )
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return int(proc.returncode), f.read()
    except subprocess.TimeoutExpired:
        return 1, "command timed out"
    except Exception as e:  # noqa: BLE001 — 调用方按失败处理
        return 1, str(e)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# 解析：badging / resources / apktool.yml
# ---------------------------------------------------------------------------

def _parse_badging(text: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "package": "",
        "label": "",
        "version_code": None,
        "version_name": "",
        "min_sdk": "",
        "target_sdk": "",
        "permissions": [],
        "abis": [],
        "split": "",
        "debuggable": False,
        "icon_files": [],
    }
    m = re.search(
        r"package: name='([^']*)'(?:[^\n]*?versionCode='([^']*)')?"
        r"(?:[^\n]*?versionName='([^']*)')?",
        text,
    )
    if m:
        info["package"] = m.group(1)
        info["version_code"] = _int_or_none(m.group(2))
        info["version_name"] = m.group(3) or ""
    m = re.search(r"split='([^']*)'", text)
    if m:
        info["split"] = m.group(1)
    m = re.search(r"application-label:'([^']*)'", text)
    if m:
        info["label"] = m.group(1)
    m = re.search(r"minSdkVersion:'([^']*)'", text)
    if m:
        info["min_sdk"] = m.group(1)
    m = re.search(r"targetSdkVersion:'([^']*)'", text)
    if m:
        info["target_sdk"] = m.group(1)
    info["permissions"] = re.findall(
        r"uses-permission(?:-sdk-23)?: name='([^']*)'", text
    )
    m = re.search(r"native-code:\s*(.+)", text)
    if m:
        info["abis"] = re.findall(r"'([^']+)'", m.group(1))
    info["debuggable"] = "application-debuggable" in text
    info["icon_files"] = re.findall(
        r"application-icon-\d+:\s*'([^']*)'", text
    )
    return info


def _int_or_none(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_resources(text: str) -> Dict[str, Any]:
    """解析 ``aapt2 dump resources``。

    Returns ``{package, id_to_name, name_to_id, id_to_files}``。
    """
    package = ""
    id_to_name: Dict[str, str] = {}
    name_to_id: Dict[str, str] = {}
    id_to_files: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        m = re.match(r"\s*Package name=(\S+)", line)
        if m:
            package = m.group(1)
            continue
        m = re.match(r"\s*resource (0x[0-9a-fA-F]+) (\S+)", line)
        if m:
            rid, name = m.group(1).lower(), m.group(2)
            current = rid
            id_to_name[rid] = name
            name_to_id[name] = rid
            id_to_files.setdefault(rid, [])
            continue
        if current:
            m = re.search(r"\(file\)\s+(\S+)", line)
            if m:
                id_to_files.setdefault(current, []).append(m.group(1))
    return {
        "package": package,
        "id_to_name": id_to_name,
        "name_to_id": name_to_id,
        "id_to_files": id_to_files,
    }


def _parse_apktool_yml(text: str) -> Dict[str, Any]:
    """apktool.yml 的最小行级解析（不引入 PyYAML）。"""
    out: Dict[str, Any] = {
        "version_code": None,
        "version_name": "",
        "min_sdk": "",
        "target_sdk": "",
        "max_sdk": "",
        "do_not_compress": [],
    }

    def _scalar(key: str, pattern: str) -> Optional[str]:
        m = re.search(pattern, text, re.M)
        return m.group(1).strip().strip("'\"") if m else None

    vc = _scalar("version_code", r"^\s*versionCode:\s*(.+)$")
    out["version_code"] = _int_or_none(vc)
    out["version_name"] = _scalar("version_name", r"^\s*versionName:\s*(.+)$") or ""
    out["min_sdk"] = _scalar("min_sdk", r"^\s*minSdkVersion:\s*(.+)$") or ""
    out["target_sdk"] = _scalar("target_sdk", r"^\s*targetSdkVersion:\s*(.+)$") or ""
    out["max_sdk"] = _scalar("max_sdk", r"^\s*maxSdkVersion:\s*(.+)$") or ""

    m = re.search(r"^doNotCompress:\s*\n((?:\s*-\s*.+\n?)*)", text, re.M)
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"\s*-\s*(\S+)", line)
            if mm:
                out["do_not_compress"].append(mm.group(1))
    return out


# ---------------------------------------------------------------------------
# 清单改写
# ---------------------------------------------------------------------------

_CLASS_ATTRS = {
    "application": ["name", "backupAgent", "manageSpaceActivity",
                    "appComponentFactory", "zygotePreloadName"],
    "activity": ["name", "parentActivityName"],
    "activity-alias": ["name", "targetActivity"],
    "service": ["name"],
    "receiver": ["name"],
    "provider": ["name"],
    "instrumentation": ["name"],
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _expand_class(value: str, old_pkg: str) -> str:
    if not value or value.startswith("@"):
        return value
    if value.startswith("."):
        return old_pkg + value
    if "." not in value:
        return old_pkg + "." + value
    return value


def _substitute(text: str, mapping: Dict[str, str]) -> str:
    def repl(m: "re.Match[str]") -> str:
        key = m.group(1)
        return mapping.get(key, m.group(0))

    return _PLACEHOLDER_RE.sub(repl, text or "")


def _patch_manifest(xml_text: str, spec: Dict[str, Any]) -> str:
    """把身份改动应用到文本 AndroidManifest.xml。"""
    for prefix, uri in re.findall(r'xmlns:([\w.-]+)="([^"]+)"', xml_text):
        if prefix == "xml":
            continue
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ToolException(f"AndroidManifest.xml 解析失败: {e}")

    old_pkg = (root.get("package") or "").strip()
    resource_pkg = spec.get("resource_pkg") or old_pkg
    new_pkg = spec["new_pkg"]
    app_name = spec.get("app_name") or ""

    # 1) 相对类名先按旧包名展开（aapt2 的 rename 本身也会按旧包名解析，
    #    这里加一道保险，并让后面把 package 改成资源包名不产生歧义）
    for elem in root.iter():
        attrs = _CLASS_ATTRS.get(_local(elem.tag))
        if not attrs:
            continue
        for attr in attrs:
            key = ANDROID + attr
            if key in elem.attrib:
                elem.set(key, _expand_class(elem.get(key, ""), old_pkg))

    # 2) 清单 package 用资源包名；applicationId 用 aapt2 的 rename 参数
    root.set("package", resource_pkg)
    root.attrib.pop("split", None)

    # 3) sharedUserId
    if spec.get("remove_shared_uid", True):
        root.attrib.pop(ANDROID + "sharedUserId", None)
        root.attrib.pop(ANDROID + "sharedUserLabel", None)

    # 4) 自定义权限 + 引用
    if spec.get("rename_permissions"):
        defined = set()
        for tag in ("permission", "permission-tree", "permission-group"):
            for elem in root.findall(tag):
                name = elem.get(ANDROID + "name", "")
                if name == old_pkg or name.startswith(old_pkg + "."):
                    defined.add(name)
        perm_map = {
            n: new_pkg + n[len(old_pkg):] if n != old_pkg else new_pkg
            for n in defined
        }
        for elem in root.iter():
            local = _local(elem.tag)
            if local in ("permission", "permission-tree", "permission-group",
                         "uses-permission", "uses-permission-sdk-23",
                         "uses-permission-sdk-m"):
                name = elem.get(ANDROID + "name", "")
                if name in perm_map:
                    elem.set(ANDROID + "name", perm_map[name])
            for attr in ("permission", "readPermission", "writePermission"):
                key = ANDROID + attr
                val = elem.get(key, "")
                if val == old_pkg or val.startswith(old_pkg + "."):
                    elem.set(key, new_pkg + val[len(old_pkg):])

    # 5) provider authorities
    if spec.get("rename_authorities"):
        for elem in root.iter():
            if _local(elem.tag) != "provider":
                continue
            raw = elem.get(ANDROID + "authorities")
            if not raw:
                continue
            parts = []
            for part in raw.split(";"):
                part = part.strip()
                if part == old_pkg:
                    parts.append(new_pkg)
                elif part.startswith(old_pkg + "."):
                    parts.append(new_pkg + part[len(old_pkg):])
                else:
                    parts.append(part)
            elem.set(ANDROID + "authorities", ";".join(parts))

    # 6) taskAffinity / process
    for elem in root.iter():
        for attr in ("taskAffinity",):
            key = ANDROID + attr
            val = elem.get(key, "")
            if val == old_pkg or val.startswith(old_pkg + "."):
                elem.set(key, new_pkg + val[len(old_pkg):])
        key = ANDROID + "process"
        val = elem.get(key, "")
        if val.startswith(old_pkg + ":"):
            elem.set(key, new_pkg + val[len(old_pkg):])

    # 7) 应用名 + launcher activity 的 label
    app = root.find("application")
    if app is None:
        raise ToolException("AndroidManifest.xml 缺少 <application>")
    if app_name:
        app.set(ANDROID + "label", app_name)
        for child in list(app):
            if _local(child.tag) not in ("activity", "activity-alias"):
                continue
            if not _is_launcher(child):
                continue
            if ANDROID + "label" in child.attrib:
                child.set(ANDROID + "label", app_name)

    # 8) 渠道 meta-data
    for item in spec.get("metadata") or []:
        name = _substitute(str(item.get("name") or ""), spec.get("mapping") or {})
        value = _substitute(str(item.get("value") or ""), spec.get("mapping") or {})
        if not name:
            continue
        found = None
        for child in list(app):
            if _local(child.tag) == "meta-data" and child.get(
                ANDROID + "name"
            ) == name:
                found = child
                break
        if found is None:
            found = ET.SubElement(app, "meta-data")
            found.set(ANDROID + "name", name)
        found.set(ANDROID + "value", value)
        found.attrib.pop(ANDROID + "resource", None)

    # 9) 额外 uses-permission（例如 com.android.vending.BILLING）
    existing_perms = {
        e.get(ANDROID + "name")
        for tag in ("uses-permission", "uses-permission-sdk-23")
        for e in root.findall(tag)
    }
    app_index = list(root).index(app)
    for perm in spec.get("permissions") or []:
        name = str(perm or "").strip()
        if not name or name in existing_perms:
            continue
        el = ET.Element("uses-permission")
        el.set(ANDROID + "name", name)
        root.insert(app_index, el)
        app_index += 1
        existing_perms.add(name)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _is_launcher(activity: ET.Element) -> bool:
    for intent in activity.findall("intent-filter"):
        actions = {a.get(ANDROID + "name") for a in intent.findall("action")}
        cats = {c.get(ANDROID + "name") for c in intent.findall("category")}
        if "android.intent.action.MAIN" in actions and \
                "android.intent.category.LAUNCHER" in cats:
            return True
    return False


# ---------------------------------------------------------------------------
# 图标：解析目标文件 / 替换
# ---------------------------------------------------------------------------

def _parse_manifest_icon_ids(xmltree_text: str) -> Dict[str, str]:
    ids: Dict[str, str] = {}
    for m in re.finditer(
        r"A: [^\n]*?:(icon|roundIcon)\(0x[0-9a-fA-F]+\)=@(0x[0-9a-fA-F]+)",
        xmltree_text,
    ):
        ids.setdefault(m.group(1), m.group(2).lower())
    return ids


def _parse_adaptive_refs(xmltree_text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    current = ""
    for line in xmltree_text.splitlines():
        m = re.match(r"\s*E: (\S+)", line)
        if m:
            current = m.group(1)
            continue
        m = re.search(r"drawable[^=]*=@(0x[0-9a-fA-F]+)", line)
        if m and current in ("foreground", "background"):
            out.setdefault(current, m.group(1).lower())
    return out


def _resolve_icon_targets(
    context, tools: Dict[str, Any], apk: str, tmp_dir: str
) -> Dict[str, Any]:
    """返回 ``{files:[res路径], skipped:[原因]}``（自适应图标取前景位图）。"""
    rc, tree = _quiet_run(
        [tools["aapt2"], "dump", "xmltree", "--file", "AndroidManifest.xml", apk],
        tmp_dir,
    )
    if rc != 0:
        return {"files": [], "skipped": ["无法读取清单图标属性"]}
    icon_ids = _parse_manifest_icon_ids(tree)
    if not icon_ids:
        return {"files": [], "skipped": ["清单未声明 icon/roundIcon"]}

    rc, res_text = _quiet_run([tools["aapt2"], "dump", "resources", apk], tmp_dir)
    resources = _parse_resources(res_text) if rc == 0 else {
        "id_to_files": {}, "id_to_name": {},
    }
    id_to_files = resources.get("id_to_files", {})
    id_to_name = resources.get("id_to_name", {})

    files: List[str] = []
    skipped: List[str] = []

    def _add_rasters(rid: str, why: str) -> bool:
        added = False
        for path in id_to_files.get(rid, []):
            low = path.lower()
            if low.endswith((".png", ".webp")):
                if path not in files:
                    files.append(path)
                added = True
            elif low.endswith(".xml"):
                rc2, x = _quiet_run(
                    [tools["aapt2"], "dump", "xmltree", "--file", path, apk],
                    tmp_dir,
                )
                refs = _parse_adaptive_refs(x) if rc2 == 0 else {}
                for key in ("foreground", "background"):
                    sub = refs.get(key)
                    if not sub:
                        continue
                    for p2 in id_to_files.get(sub, []):
                        low2 = p2.lower()
                        if low2.endswith((".png", ".webp")):
                            if p2 not in files:
                                files.append(p2)
                            added = True
                    if added:
                        break
                if not added:
                    skipped.append(f"{path}（自适应图标内层不是位图）")
            else:
                skipped.append(f"{path}（不是位图）")
        return added

    for attr, rid in icon_ids.items():
        if not _add_rasters(rid, attr):
            name = id_to_name.get(rid, rid)
            skipped.append(f"{attr} -> {name} 无法解析到位图资源")

    return {"files": files, "skipped": skipped}


def _apply_icons(
    project: str, apk: str, icon_path: str, targets: List[str]
) -> Tuple[Dict[str, bytes], Dict[str, bytes], List[str]]:
    """把用户 PNG 缩放到每个目标文件尺寸并覆盖项目 res。

    Returns ``(icons_map, restore_map, warnings)``。
    """
    warnings: List[str] = []
    if not icon_path:
        return {}, {}, warnings
    if not os.path.isfile(icon_path):
        raise ToolException(f"图标文件不存在: {icon_path}")
    with open(icon_path, "rb") as f:
        icon_bytes = f.read()
    if decode_png_rgba(icon_bytes) is None:
        raise ToolException("图标必须是受支持的 PNG（8-bit RGB/RGBA/调色板，非隔行）")

    icons_map: Dict[str, bytes] = {}
    restore: Dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(apk) as z:
            names = set(z.namelist())
            for res_path in targets:
                if res_path not in names:
                    warnings.append(f"{res_path} 不在源 APK 中，跳过")
                    continue
                src = z.read(res_path)
                dims = image_dimensions(src)
                if not dims:
                    warnings.append(f"{res_path} 尺寸无法识别，跳过")
                    continue
                data = resize_png(icon_bytes, dims[0], dims[1])
                if not data:
                    warnings.append(f"{res_path} 缩放失败，跳过")
                    continue
                proj_path = os.path.join(project, *res_path.split("/"))
                if not os.path.isfile(proj_path):
                    warnings.append(f"{res_path} 不在解码项目里，跳过")
                    continue
                if res_path not in restore:
                    with open(proj_path, "rb") as f:
                        restore[res_path] = f.read()
                _write_bytes(proj_path, data)
                icons_map[res_path] = data
                if res_path.lower().endswith(".webp"):
                    warnings.append(
                        f"{res_path} 原为 WebP，已写入 PNG 字节"
                        "（Android 按内容解码，需真机确认）"
                    )
    except Exception:
        # 中途失败时把已经改掉的文件恢复，避免污染下一个渠道
        _restore_icons(project, restore)
        raise
    return icons_map, restore, warnings


def _restore_icons(project: str, restore: Dict[str, bytes]) -> None:
    for res_path, data in restore.items():
        _write_bytes(os.path.join(project, *res_path.split("/")), data)


# ---------------------------------------------------------------------------
# zip 组装
# ---------------------------------------------------------------------------

def _is_link_owned(name: str) -> bool:
    return (
        name == "AndroidManifest.xml"
        or name == "resources.arsc"
        or name.startswith("res/")
    )


def _safe_asset_rel(path: str) -> str:
    raw = (path or "").replace("\\", "/").strip()
    if not raw:
        return ""
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ToolException(f"渠道文件路径不能是绝对路径: {path}")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ToolException(f"渠道文件路径不能包含 ..: {path}")
    if not parts:
        return ""
    if parts[0] != "assets":
        parts = ["assets"] + parts
    return "/".join(parts)


def _zip_copy_entry(
    zin: zipfile.ZipFile, info: zipfile.ZipInfo, zout: zipfile.ZipFile,
    data: Optional[bytes] = None,
) -> None:
    if info.is_dir():
        return
    zi = zipfile.ZipInfo(info.filename, info.date_time)
    zi.compress_type = info.compress_type
    zi.external_attr = info.external_attr
    zi.internal_attr = info.internal_attr
    zi.create_system = info.create_system
    if data is not None:
        zout.writestr(zi, data)
        return
    with zin.open(info) as src, zout.open(zi, "w") as dst:
        shutil.copyfileobj(src, dst)


def _rewrite_zip(
    src: str, dst: str, replace: Dict[str, bytes],
    extra: Dict[str, bytes], drop_sig: bool = True,
) -> None:
    written = set()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
        dst, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for info in zin.infolist():
            name = info.filename
            if drop_sig and _SIG_RE.match(name):
                continue
            data = replace.get(name)
            _zip_copy_entry(zin, info, zout, data)
            written.add(name)
        for name, data in extra.items():
            if name in written:
                continue
            zi = zipfile.ZipInfo(name, time.localtime()[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, data)


def _assemble_apk(
    link_apk: str, source_apk: str, out_apk: str,
    injected_assets: Dict[str, bytes],
) -> None:
    written = set()
    tmp = out_apk + ".tmp"
    with zipfile.ZipFile(link_apk) as zlink, \
            zipfile.ZipFile(source_apk) as zsrc, \
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zlink.infolist():
            if _SIG_RE.match(info.filename):
                continue
            _zip_copy_entry(zlink, info, zout)
            written.add(info.filename)
        for info in zsrc.infolist():
            name = info.filename
            if name in written or _is_link_owned(name) or _SIG_RE.match(name):
                continue
            data = injected_assets.get(name)
            _zip_copy_entry(zsrc, info, zout, data)
            written.add(name)
        for name, data in injected_assets.items():
            if name in written:
                continue
            zi = zipfile.ZipInfo(name)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, data)
    os.replace(tmp, out_apk)


def _build_module_zip(
    proto_apk: str, source_apk: str, out_zip: str,
    injected_assets: Dict[str, bytes],
) -> None:
    written = set()

    def put(zin: zipfile.ZipFile, info: zipfile.ZipInfo, name: str,
            data: Optional[bytes] = None) -> None:
        if name in written:
            return
        written.add(name)
        zi = zipfile.ZipInfo(name, info.date_time)
        zi.compress_type = info.compress_type
        if data is not None:
            zout.writestr(zi, data)
        else:
            with zin.open(info) as src, zout.open(zi, "w") as dst:
                shutil.copyfileobj(src, dst)

    with zipfile.ZipFile(proto_apk) as zproto, \
            zipfile.ZipFile(source_apk) as zsrc, \
            zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zproto.infolist():
            n = info.filename
            if _SIG_RE.match(n):
                continue
            if n == "AndroidManifest.xml":
                put(zproto, info, "manifest/AndroidManifest.xml")
            elif n == "resources.pb":
                put(zproto, info, "resources.pb")
            elif n.startswith("res/"):
                put(zproto, info, n)
        for info in zsrc.infolist():
            n = info.filename
            if n in written or _is_link_owned(n) or _SIG_RE.match(n):
                continue
            data = injected_assets.get(n)
            if n.startswith("classes") and n.endswith(".dex"):
                put(zsrc, info, "dex/" + n, data)
            elif n.startswith("lib/"):
                put(zsrc, info, n, data)
            elif n.startswith("assets/"):
                put(zsrc, info, n, data)
            else:
                put(zsrc, info, "root/" + n, data)
        for name, data in injected_assets.items():
            if name in written:
                continue
            written.add(name)
            zi = zipfile.ZipInfo(name)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, data)


def _entry_hashes(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name == "base/resources.pb" or name == "BundleConfig.pb" \
                    or name.startswith("base/dex/") or name.startswith("base/lib/"):
                out[name] = _sha256_bytes(z.read(name))
    return out


# ---------------------------------------------------------------------------
# 编译 / 链接 / 签名 / 校验
# ---------------------------------------------------------------------------

def _aapt2_compile(context, tools, project: str, out_zip: str) -> None:
    res_dir = os.path.join(project, "res")
    if not os.path.isdir(res_dir):
        raise ToolException("解码项目缺少 res/ 目录")
    rc, text = _run(
        context,
        [tools["aapt2"], "compile", "--dir", res_dir, "-o", out_zip,
         "--no-crunch"],
        timeout=1800,
    )
    if rc != 0:
        _log_tail(context, "aapt2 compile", text)
        raise ToolException(f"aapt2 compile 失败（exit={rc}）")


def _aapt2_link(
    context, tools, manifest: str, compiled: str, out_apk: str,
    new_pkg: str, meta: Dict[str, Any], stable_ids: str,
    proto: bool = False,
) -> None:
    args = [
        tools["aapt2"], "link", "-o", out_apk,
        "-I", tools["android_jar"],
        "--manifest", manifest,
        compiled,
        "--rename-manifest-package", new_pkg,
    ]
    if meta.get("min_sdk"):
        args += ["--min-sdk-version", str(meta["min_sdk"])]
    if meta.get("target_sdk"):
        args += ["--target-sdk-version", str(meta["target_sdk"])]
    if meta.get("max_sdk"):
        args += ["--max-sdk-version", str(meta["max_sdk"])]
    if meta.get("version_code") is not None:
        args += ["--version-code", str(meta["version_code"])]
    if meta.get("version_name"):
        args += ["--version-name", str(meta["version_name"])]
    args += [
        "--replace-version",
        "--no-auto-version", "--no-version-vectors",
        "--no-version-transitions", "--no-resource-deduping",
        "--no-compile-sdk-metadata", "--warn-manifest-validation",
    ]
    if stable_ids:
        args += ["--stable-ids", stable_ids]
    for ext in meta.get("do_not_compress") or []:
        e = str(ext)
        if e and e != "arsc":
            args += ["-0", e if e.startswith(".") else "." + e]
    if proto:
        args.append("--proto-format")
    rc, text = _run(context, args, timeout=1800)
    if rc != 0:
        _log_tail(context, "aapt2 link", text)
        raise ToolException(f"aapt2 link 失败（exit={rc}）")


def _zipalign(context, tools, src: str, dst: str) -> None:
    # -P 16：未压缩 .so 按 16KB 页对齐（Android 15+ 16KB page 设备要求；
    # 16KB 是 4KB 的整数倍，旧设备不受影响）。-p 与 -P 不能同时用。
    rc, text = _run(
        context, [tools["zipalign"], "-f", "-P", "16", "4", src, dst],
        timeout=600,
    )
    if rc != 0:
        _log_tail(context, "zipalign", text)
        raise ToolException(f"zipalign 失败（exit={rc}）")


def _zipalign_check(context, tools, apk: str) -> Tuple[bool, str]:
    rc, text = _run(
        context, [tools["zipalign"], "-c", "-P", "16", "4", apk], timeout=300
    )
    return rc == 0, text


def _apksigner_sign(context, tools, apk: str, keystore: Dict[str, str],
                    out_apk: str) -> None:
    args = [
        tools["java"], "-jar", tools["apksigner"], "sign",
        "--ks", keystore["path"],
        "--ks-key-alias", keystore["alias"],
        "--ks-pass", "pass:" + keystore.get("storepass", ""),
    ]
    if keystore.get("keypass"):
        args += ["--key-pass", "pass:" + keystore["keypass"]]
    args += ["--out", out_apk, apk]
    rc, text = _run(context, args, timeout=600)
    if rc != 0:
        _log_tail(context, "apksigner sign", text)
        raise ToolException(f"apksigner sign 失败（exit={rc}）")


def _apksigner_verify(context, tools, apk: str, tmp_dir: str) -> Tuple[int, str]:
    return _quiet_run(
        [tools["java"], "-jar", tools["apksigner"], "verify", "--verbose",
         "--print-certs", apk],
        tmp_dir,
        300,
    )


def _jarsigner_sign(context, tools, aab: str, keystore: Dict[str, str]) -> None:
    args = [
        tools["jarsigner"],
        "-keystore", keystore["path"],
        "-storepass", keystore.get("storepass", ""),
    ]
    if keystore.get("keypass"):
        args += ["-keypass", keystore["keypass"]]
    args += [
        # 不硬编码 -sigalg：JDK 会按 key 类型选 SHA256withRSA / SHA256withECDSA，
        # 显式锁定 digest 为 SHA-256。
        "-digestalg", "SHA-256",
        aab, keystore["alias"],
    ]
    rc, text = _run(context, args, timeout=900)
    if rc != 0:
        _log_tail(context, "jarsigner", text)
        raise ToolException(f"jarsigner 签名失败（exit={rc}）")


def _jarsigner_verify(context, tools, aab: str, tmp_dir: str) -> Tuple[int, str]:
    return _quiet_run([tools["jarsigner"], "-verify", aab], tmp_dir, 300)


def _keytool_printcert(tools, jar_path: str, tmp_dir: str) -> Tuple[int, str]:
    if not tools.get("keytool"):
        return 1, "keytool not found"
    return _quiet_run(
        [tools["keytool"], "-printcert", "-jarfile", jar_path], tmp_dir, 120
    )


def _bundletool_dump_manifest(context, tools, aab: str, tmp_dir: str) -> Tuple[int, str]:
    return _quiet_run(
        [tools["java"], "-jar", tools["bundletool"], "dump", "manifest",
         "--bundle=" + aab],
        tmp_dir,
        300,
    )


def _bundletool_validate(context, tools, aab: str, tmp_dir: str) -> Tuple[int, str]:
    return _quiet_run(
        [tools["java"], "-jar", tools["bundletool"], "validate",
         "--bundle=" + aab],
        tmp_dir,
        600,
    )


def _bundletool_build_apks(
    context, tools, aab: str, out_apks: str, tmp_dir: str,
    keystore: Dict[str, str],
) -> Tuple[int, str]:
    args = [
        tools["java"], "-jar", tools["bundletool"], "build-apks",
        "--bundle=" + aab,
        "--output=" + out_apks,
        "--ks=" + keystore["path"],
        "--ks-key-alias=" + keystore["alias"],
        "--ks-pass=pass:" + keystore.get("storepass", ""),
        # bundletool 在精简 JRE 下找不到 jar:// provider，显式给 aapt2
        "--aapt2=" + tools["aapt2"],
        "--overwrite",
    ]
    if keystore.get("keypass"):
        args.append("--key-pass=pass:" + keystore["keypass"])
    return _quiet_run(args, tmp_dir, 1800)


def _signer_sha256_from_apksigner(text: str) -> str:
    m = re.search(r"Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F:]+)", text)
    if not m:
        return ""
    return m.group(1).lower().replace(":", "")


def _signer_sha256_from_keytool(text: str) -> str:
    m = re.search(r"SHA256:\s*([0-9A-Fa-f:]+)", text)
    if not m:
        return ""
    return m.group(1).lower().replace(":", "")


# ---------------------------------------------------------------------------
# AAB：一致性 guard / 直改 / 重建
# ---------------------------------------------------------------------------

def _aab_guard(context, tools, aab: str, source: Dict[str, Any],
               tmp_dir: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": aab,
        "package": "",
        "version_code": None,
        "version_name": "",
        "modules": [],
        "same_build": False,
        "splice_available": False,
        "reason": "",
    }
    if not aab or not os.path.isfile(aab):
        info["reason"] = "未提供 AAB"
        return info
    try:
        with zipfile.ZipFile(aab) as z:
            names = z.namelist()
    except Exception as e:
        info["reason"] = f"AAB 不是可读 zip: {e}"
        return info
    tops = set()
    for n in names:
        top = n.split("/", 1)[0]
        if top:
            tops.add(top)
    modules = sorted(
        t for t in tops
        if t not in ("META-INF", "BUNDLE-METADATA", "BundleConfig.pb",
                     "SdkModulesConfig.pb")
    )
    info["modules"] = modules
    rc, text = _bundletool_dump_manifest(context, tools, aab, tmp_dir)
    if rc != 0:
        info["reason"] = "bundletool dump manifest 失败: " + _tail(text, 6)
        return info
    try:
        root = ET.fromstring(text)
        info["package"] = root.get("package", "")
        info["version_code"] = _int_or_none(root.get(ANDROID + "versionCode"))
        info["version_name"] = root.get(ANDROID + "versionName", "")
    except Exception:
        m = re.search(r'package="([^"]+)"', text)
        info["package"] = m.group(1) if m else ""
        m = re.search(r'versionCode="([^"]+)"', text)
        info["version_code"] = _int_or_none(m.group(1) if m else None)
        m = re.search(r'versionName="([^"]*)"', text)
        info["version_name"] = m.group(1) if m else ""

    reasons = []
    if modules != ["base"]:
        reasons.append("只支持单 base 模块")
    if info["package"] != source.get("package"):
        reasons.append("AAB 包名与 APK 不一致")
    if info["version_code"] != source.get("version_code"):
        reasons.append("AAB versionCode 与 APK 不一致")
    if info["version_name"] != source.get("version_name"):
        reasons.append("AAB versionName 与 APK 不一致")
    info["same_build"] = not reasons
    info["splice_available"] = not reasons
    if reasons:
        info["reason"] = "；".join(reasons)
    if "dist:" in text:
        info["reason"] = (info["reason"] + "；" if info["reason"] else "") + \
            "AAB 清单含 dist:*（直改会用 APK 清单，可能丢失 bundle 专属元素）"
    return info


def _splice_aab(
    context, tools, aab: str, new_manifest: bytes,
    icons_map: Dict[str, bytes], assets: Dict[str, bytes],
    out_aab: str, tmp_dir: str,
) -> None:
    with zipfile.ZipFile(aab) as z:
        existing = set(z.namelist())
    replace: Dict[str, bytes] = {
        "base/manifest/AndroidManifest.xml": new_manifest,
    }
    for res_path, data in icons_map.items():
        entry = "base/" + res_path
        if entry in existing:
            replace[entry] = data
    for rel, data in assets.items():
        replace["base/" + rel] = data
    _rewrite_zip(aab, out_aab + ".tmp", replace,
                 {k: v for k, v in replace.items() if k not in existing})
    os.replace(out_aab + ".tmp", out_aab)


def _rebuild_aab(
    context, tools, proto_apk: str, source_apk: str,
    assets: Dict[str, bytes], out_aab: str, tmp_dir: str,
) -> None:
    module = os.path.join(tmp_dir, "module.zip")
    _build_module_zip(proto_apk, source_apk, module, assets)
    rc, text = _run(
        context,
        [tools["java"], "-jar", tools["bundletool"], "build-bundle",
         "--modules=" + module, "--output=" + out_aab, "--overwrite"],
        timeout=1800,
    )
    if rc != 0:
        _log_tail(context, "bundletool build-bundle", text)
        raise ToolException(f"bundletool build-bundle 失败（exit={rc}）")


def _verify_aab(
    context, tools, aab: str, keystore: Dict[str, str],
    tmp_dir: str, strict: bool,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "jarsigner": None, "keytool": None,
        "bundletool_validate": None, "bundletool_build_apks": None,
        "signer_sha256": "",
    }
    rc, text = _jarsigner_verify(context, tools, aab, tmp_dir)
    out["jarsigner"] = "ok" if rc == 0 else (_tail(text, 6) or "verify failed")
    rc, text = _keytool_printcert(tools, aab, tmp_dir)
    out["keytool"] = "ok" if rc == 0 else (_tail(text, 6) or "printcert failed")
    out["signer_sha256"] = _signer_sha256_from_keytool(text) if rc == 0 else ""
    rc, text = _bundletool_validate(context, tools, aab, tmp_dir)
    out["bundletool_validate"] = "ok" if rc == 0 else (_tail(text, 8) or "validate failed")
    if strict:
        apks = os.path.join(tmp_dir, "verify.apks")
        rc, text = _bundletool_build_apks(context, tools, aab, apks, tmp_dir, keystore)
        out["bundletool_build_apks"] = (
            "ok" if rc == 0 else (_tail(text, 8) or "build-apks failed")
        )
    return out


# ---------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------

def _profiles_path() -> str:
    return os.path.join(get_output_dir(), "white-label", "profiles.json")


def _load_profiles() -> Dict[str, Any]:
    path = _profiles_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_profiles(payload: Dict[str, Any]) -> None:
    path = _profiles_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _profile_from_channel(ch: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "label": ch.get("label") or "",
        "enabled": bool(ch.get("enabled")),
        "package_name": ch.get("package_name") or "",
        "app_name": ch.get("app_name") or "",
        "version_code": ch.get("version_code"),
        "version_name": ch.get("version_name") or "",
        "icon_path": ch.get("icon_path") or "",
        "format": ch.get("format") or "",
        "keystore": {
            "path": (ch.get("keystore") or {}).get("path") or "",
            "alias": (ch.get("keystore") or {}).get("alias") or "",
        },
        "metadata": ch.get("metadata") or [],
        "permissions": ch.get("permissions") or [],
        "asset": ch.get("asset") or {"path": "", "content": ""},
        "rename_authorities": bool(ch.get("rename_authorities")),
        "rename_permissions": bool(ch.get("rename_permissions")),
        "remove_shared_uid": bool(ch.get("remove_shared_uid", True)),
    }


# ---------------------------------------------------------------------------
# 输入校验 / 身份
# ---------------------------------------------------------------------------

def _validate_apk(path: str) -> None:
    if not path or not os.path.isfile(path):
        raise ToolException(f"APK 不存在: {path}")
    if not zipfile.is_zipfile(path):
        raise ToolException(f"不是有效 APK（zip）: {path}")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "AndroidManifest.xml" not in names:
            raise ToolException("APK 缺少 AndroidManifest.xml")
        if not any(n.startswith("classes") and n.endswith(".dex") for n in names):
            # 没有 dex 也能打，但提示一下
            pass


def _read_source(context, tools, apk: str, tmp_dir: str) -> Dict[str, Any]:
    rc, badging = _quiet_run([tools["aapt2"], "dump", "badging", apk], tmp_dir)
    if rc != 0:
        raise ToolException("aapt2 dump badging 失败: " + _tail(badging, 8))
    info = _parse_badging(badging)
    if not info["package"]:
        raise ToolException("无法从 badging 解析包名")
    if info["split"]:
        raise ToolException(
            f"输入是 split APK（split={info['split']}），请用 base/universal APK"
        )
    rc, res_text = _quiet_run([tools["aapt2"], "dump", "resources", apk], tmp_dir)
    resources = _parse_resources(res_text) if rc == 0 else {
        "package": info["package"], "id_to_name": {}, "name_to_id": {},
        "id_to_files": {},
    }
    info["resource_package"] = resources.get("package") or info["package"]
    info["resource_dump"] = resources
    rc, text = _apksigner_verify(context, tools, apk, tmp_dir)
    info["signer_sha256"] = (
        _signer_sha256_from_apksigner(text) if rc == 0 else ""
    )
    info["signed"] = rc == 0
    icon = _resolve_icon_targets(context, tools, apk, tmp_dir)
    info["icon"] = icon
    return info


def _source_meta(tools, project: str, source: Dict[str, Any]) -> Dict[str, Any]:
    yml = os.path.join(project, "apktool.yml")
    meta = _parse_apktool_yml(_read_text(yml)) if os.path.isfile(yml) else {}
    return {
        "version_code": meta.get("version_code") or source.get("version_code"),
        "version_name": meta.get("version_name") or source.get("version_name") or "",
        "min_sdk": meta.get("min_sdk") or source.get("min_sdk") or "",
        "target_sdk": meta.get("target_sdk") or source.get("target_sdk") or "",
        "max_sdk": meta.get("max_sdk") or "",
        "do_not_compress": meta.get("do_not_compress") or [],
    }


def _validate_package(pkg: str, source_pkg: str) -> None:
    if not _PKG_RE.match(pkg or ""):
        raise ToolException(f"包名不合法: {pkg}")
    if pkg == source_pkg:
        raise ToolException("新包名不能与源包名相同")


# ---------------------------------------------------------------------------
# 渠道构建
# ---------------------------------------------------------------------------

def _channel_config(ch: Dict[str, Any]) -> Dict[str, Any]:
    cid = str(ch.get("id") or "").strip().lower()
    if not _CHANNEL_ID_RE.match(cid):
        raise ToolException(
            f"渠道标识不合法（a-z 开头，只含 a-z0-9_-，1~32 字符）: {cid or '(空)'}"
        )
    preset = next((c for c in CHANNEL_PRESETS if c["id"] == cid), {})
    fmt = str(
        ch.get("format") or preset.get("format")
        or ("aab" if cid == "google" else "apk")
    ).strip().lower()
    if fmt not in ("apk", "aab", "both"):
        raise ToolException(f"渠道 {cid} 格式非法: {fmt}（只能是 apk / aab / both）")
    label = str(ch.get("label") or preset.get("label") or cid).strip() or cid
    ks = ch.get("keystore") or {}
    vc = ch.get("version_code")
    if isinstance(vc, float) and vc.is_integer():
        vc = int(vc)
    elif isinstance(vc, str) and vc.strip().isdigit():
        vc = int(vc.strip())
    metadata = []
    for item in ch.get("metadata") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            metadata.append({"name": name, "value": str(item.get("value") or "")})
    raw_perms = ch.get("permissions") or []
    if isinstance(raw_perms, str):
        raw_perms = re.split(r"[\s,]+", raw_perms)
    permissions = []
    for item in raw_perms:
        if not isinstance(item, str):
            continue
        perm = item.strip()
        if not perm or perm in permissions:
            continue
        if not _PKG_RE.match(perm):
            raise ToolException(f"权限名不合法: {perm}")
        permissions.append(perm)
    asset = ch.get("asset") if isinstance(ch.get("asset"), dict) else {}
    return {
        "id": cid,
        "label": label[:64],
        "enabled": bool(ch.get("enabled", True)),
        "package_name": str(ch.get("package_name") or "").strip(),
        "app_name": str(ch.get("app_name") or "").strip(),
        "version_code": vc,
        "version_name": (str(ch.get("version_name")).strip()
                         if ch.get("version_name") is not None else ""),
        "icon_path": str(ch.get("icon_path") or "").strip(),
        "format": fmt,
        "keystore": {
            "path": str(ks.get("path") or "").strip(),
            "alias": str(ks.get("alias") or "").strip(),
            "storepass": str(ks.get("storepass") or ""),
            "keypass": str(ks.get("keypass") or ""),
        },
        "metadata": metadata,
        "permissions": permissions,
        "asset": {"path": str(asset.get("path") or ""),
                  "content": str(asset.get("content") or "")},
        "rename_authorities": bool(ch.get("rename_authorities")),
        "rename_permissions": bool(ch.get("rename_permissions")),
        "remove_shared_uid": bool(ch.get("remove_shared_uid", True)),
    }


def _validate_channel(ch: Dict[str, Any], source: Dict[str, Any]) -> None:
    _validate_package(ch["package_name"], source["package"])
    if not ch["app_name"]:
        raise ToolException("应用名不能为空")
    vc = ch["version_code"]
    if vc is not None and (not isinstance(vc, int) or vc <= 0):
        raise ToolException("versionCode 必须是正整数")
    if ch["icon_path"] and not os.path.isfile(ch["icon_path"]):
        raise ToolException(f"图标不存在: {ch['icon_path']}")
    ks = ch["keystore"]
    if not ks["path"] or not os.path.isfile(ks["path"]):
        raise ToolException(f"keystore 不存在: {ks['path']}")
    if not ks["alias"]:
        raise ToolException("keystore alias 不能为空")
    if not ks["storepass"]:
        raise ToolException("keystore storepass 不能为空")


def _preflight_keystore(context, tools, ch: Dict[str, Any], tmp_dir: str) -> None:
    if not tools.get("keytool"):
        return
    ks = ch["keystore"]
    rc, text = _quiet_run(
        [tools["keytool"], "-list", "-keystore", ks["path"],
         "-storepass", ks["storepass"], "-alias", ks["alias"]],
        tmp_dir, 60,
    )
    if rc != 0:
        raise ToolException(
            f"keystore 预检失败（{ch['id']}）：密码/别名不对或文件不可读"
        )


def _assets_for(ch: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, bytes]:
    asset = ch.get("asset") or {}
    rel = _safe_asset_rel(asset.get("path") or "")
    content = asset.get("content") or ""
    if not rel or not content:
        return {}
    return {rel: _substitute(str(content), mapping).encode("utf-8")}


# ---------------------------------------------------------------------------
# 单渠道构建
# ---------------------------------------------------------------------------

def _build_channel(
    context, tools, source: Dict[str, Any], project: str,
    source_meta: Dict[str, Any], stable_ids: str,
    ch: Dict[str, Any], output_dir: str, work: str,
    google_mode: str, aab_guard: Optional[Dict[str, Any]],
    strict_aab: bool,
) -> Dict[str, Any]:
    t0 = time.time()
    cid = ch["id"]
    context.log(f"[{cid}] 开始处理：{ch['package_name']} / {ch['app_name']}")
    old_pkg = source["package"]
    resource_pkg = source["resource_package"]
    new_pkg = ch["package_name"]
    version_code = ch["version_code"]
    if version_code is None:
        version_code = source_meta.get("version_code")
    version_name = ch["version_name"]
    if not version_name:
        version_name = source_meta.get("version_name") or ""
    if version_code is None:
        raise ToolException("无法确定 versionCode（源 APK 与渠道都为空）")

    mapping = {
        "channel": cid,
        "package": new_pkg,
        "app_name": ch["app_name"],
        "version_name": str(version_name),
        "version_code": str(version_code),
    }
    assets = _assets_for(ch, mapping)
    icon_map: Dict[str, bytes] = {}
    restore: Dict[str, bytes] = {}
    warnings: List[str] = []
    if ch["icon_path"]:
        if not source["icon"]["files"]:
            warnings.append("源 APK 未声明 launcher icon/roundIcon，无法替换图标")
        icon_map, restore, icon_warn = _apply_icons(
            project, source["path"], ch["icon_path"], source["icon"]["files"]
        )
        warnings.extend(icon_warn)

    try:
        spec = {
            "resource_pkg": resource_pkg,
            "new_pkg": new_pkg,
            "app_name": ch["app_name"],
            "metadata": ch["metadata"],
            "permissions": ch["permissions"],
            "mapping": mapping,
            "rename_authorities": ch["rename_authorities"],
            "rename_permissions": ch["rename_permissions"],
            "remove_shared_uid": ch["remove_shared_uid"],
        }
        manifest_text = _patch_manifest(source["manifest_text"], spec)
        manifest_path = os.path.join(work, f"manifest_{cid}.xml")
        _write_text(manifest_path, manifest_text)

        compiled = os.path.join(work, f"compiled_{cid}.zip")
        _aapt2_compile(context, tools, project, compiled)

        link_meta = {
            "version_code": version_code,
            "version_name": version_name,
            "min_sdk": source_meta.get("min_sdk"),
            "target_sdk": source_meta.get("target_sdk"),
            "max_sdk": source_meta.get("max_sdk"),
            "do_not_compress": source_meta.get("do_not_compress"),
        }

        item: Dict[str, Any] = {
            "channel": cid,
            "label": ch["label"],
            "format": ch["format"],
            "package_name": new_pkg,
            "app_name": ch["app_name"],
            "version_code": version_code,
            "version_name": version_name,
            "apk_path": None,
            "aab_path": None,
            "aab_mode": None,
            "size_apk": None,
            "size_aab": None,
            "sha256_apk": None,
            "sha256_aab": None,
            "signer_sha256": "",
            "verify": {
                "badging": None, "apksigner": None, "zipalign": None,
                "resource_ids": None, "jarsigner": None, "keytool": None,
                "bundletool_validate": None, "bundletool_build_apks": None,
            },
            "icon": {
                "replaced": sorted(icon_map.keys()),
                "skipped": source["icon"]["skipped"] if ch["icon_path"] else [],
            },
            "warnings": warnings,
            "error": None,
            "duration_ms": 0,
            # 仅内部使用，返回前删除
            "_keystore": ch["keystore"],
        }

        fmt = ch["format"]
        if fmt in ("apk", "both"):
            _build_apk_output(
                context, tools, source, manifest_path, compiled, link_meta,
                stable_ids, new_pkg, ch["app_name"], version_code,
                version_name, assets, output_dir, work, cid, item,
            )
        if fmt in ("aab", "both"):
            _build_aab_output(
                context, tools, source, manifest_path, compiled, link_meta,
                stable_ids, ch, assets, icon_map, output_dir, work,
                google_mode, aab_guard, strict_aab, item, new_pkg,
                version_code, version_name,
            )
        if fmt in ("aab", "both") and not item["aab_path"]:
            raise ToolException("谷歌渠道未产出 AAB")
        if fmt in ("apk", "both") and not item["apk_path"]:
            raise ToolException("渠道未产出 APK")

        item["duration_ms"] = int((time.time() - t0) * 1000)
        item.pop("_keystore", None)
        context.log(f"[{cid}] 完成，用时 {item['duration_ms']} ms")
        return item
    finally:
        if restore:
            _restore_icons(project, restore)


def _build_apk_output(
    context, tools, source, manifest_path, compiled, link_meta,
    stable_ids, new_pkg, app_name, version_code, version_name,
    assets, output_dir, work, cid, item,
) -> None:
    link_apk = os.path.join(work, f"link_{cid}.apk")
    _aapt2_link(
        context, tools, manifest_path, compiled, link_apk,
        new_pkg, link_meta, stable_ids, proto=False,
    )
    injected = dict(assets)
    unsigned = os.path.join(work, f"unsigned_{cid}.apk")
    _assemble_apk(link_apk, source["path"], unsigned, injected)

    aligned = os.path.join(work, f"aligned_{cid}.apk")
    _zipalign(context, tools, unsigned, aligned)

    out_apk = os.path.join(output_dir, f"{new_pkg}-{cid}.apk")
    if os.path.exists(out_apk):
        os.remove(out_apk)
    _apksigner_sign(context, tools, aligned, item["_keystore"], out_apk)

    item["apk_path"] = out_apk
    item["size_apk"] = os.path.getsize(out_apk)
    item["sha256_apk"] = _sha256_file(out_apk)

    rc, vtext = _apksigner_verify(context, tools, out_apk, work)
    item["verify"]["apksigner"] = "ok" if rc == 0 else (_tail(vtext, 6) or "verify failed")
    if rc == 0:
        item["signer_sha256"] = _signer_sha256_from_apksigner(vtext)
    ok_align, atext = _zipalign_check(context, tools, out_apk)
    item["verify"]["zipalign"] = "ok" if ok_align else (_tail(atext, 6) or "not aligned")

    rc, bad = _quiet_run([tools["aapt2"], "dump", "badging", out_apk], work)
    if rc == 0:
        info = _parse_badging(bad)
        if info["package"] != new_pkg:
            item["verify"]["badging"] = f"包名不符: {info['package']}"
        elif info["label"] != app_name:
            item["warnings"].append(
                f"产物应用名解析为 {info['label']!r}（期望 {app_name!r}）"
            )
            item["verify"]["badging"] = "ok"
        else:
            item["verify"]["badging"] = "ok"
    else:
        item["verify"]["badging"] = _tail(bad, 6) or "dump badging failed"

    rc, res_text = _quiet_run([tools["aapt2"], "dump", "resources", out_apk], work)
    if rc == 0:
        new_res = _parse_resources(res_text)
        drift = _resource_drift(
            source["resource_dump"].get("id_to_name", {}), new_res
        )
        if drift:
            item["verify"]["resource_ids"] = drift
        else:
            item["verify"]["resource_ids"] = "ok"


def _resource_drift(
    old_ids: Dict[str, str], new_res: Dict[str, Any]
) -> str:
    new_name_to_id = new_res.get("name_to_id", {})
    changed = []
    missing = []
    for rid, name in old_ids.items():
        new_id = new_name_to_id.get(name)
        if not new_id:
            missing.append(name)
        elif new_id.lower() != rid.lower():
            changed.append(f"{name}: {rid}->{new_id}")
    if changed or missing:
        parts = []
        if changed:
            parts.append("ID 漂移 " + ", ".join(changed[:5]))
        if missing:
            parts.append("资源缺失 " + ", ".join(missing[:5]))
        return "；".join(parts)
    return ""


def _build_aab_output(
    context, tools, source, manifest_path, compiled, link_meta,
    stable_ids, ch, assets, icon_map, output_dir, work,
    google_mode, aab_guard, strict_aab, item, new_pkg,
    version_code, version_name,
) -> None:
    cid = ch["id"]
    proto_apk = os.path.join(work, f"proto_{cid}.apk")
    _aapt2_link(
        context, tools, manifest_path, compiled, proto_apk,
        new_pkg, link_meta, stable_ids, proto=True,
    )
    out_aab = os.path.join(output_dir, f"{new_pkg}-{cid}.aab")
    if os.path.exists(out_aab):
        os.remove(out_aab)

    use_splice = bool(
        aab_guard and aab_guard.get("splice_available")
        and google_mode in ("auto", "splice")
    )
    if google_mode == "reconstruct":
        use_splice = False
    if google_mode == "splice" and not (aab_guard and aab_guard.get("splice_available")):
        raise ToolException(
            "AAB 直改不可用：" + (aab_guard or {}).get("reason", "未提供 AAB")
        )

    if use_splice:
        with zipfile.ZipFile(proto_apk) as z:
            new_manifest = z.read("AndroidManifest.xml")
        if icon_map:
            with zipfile.ZipFile(aab_guard["path"]) as z:
                aab_names = set(z.namelist())
            for res_path in icon_map:
                if "base/" + res_path not in aab_names:
                    item["warnings"].append(
                        f"源 AAB 不含 base/{res_path}，该图标文件未替换"
                    )
        _splice_aab(
            context, tools, aab_guard["path"], new_manifest, icon_map,
            assets, out_aab, work,
        )
        item["aab_mode"] = "splice"
        before = _entry_hashes(aab_guard["path"])
        after = _entry_hashes(out_aab)
        if before != after:
            changed = [k for k in before if before.get(k) != after.get(k)]
            raise ToolException("AAB 直改破坏了未改动条目: " + ", ".join(changed[:5]))
    else:
        if aab_guard and aab_guard.get("path") and google_mode != "reconstruct":
            item["warnings"].append(
                "AAB 直改不可用，已从 APK 重建："
                + (aab_guard.get("reason") or "未知原因")
            )
        _rebuild_aab(
            context, tools, proto_apk, source["path"],
            assets, out_aab, work,
        )
        item["aab_mode"] = "reconstruct"

    _jarsigner_sign(context, tools, out_aab, item["_keystore"])
    item["aab_path"] = out_aab
    item["size_aab"] = os.path.getsize(out_aab)
    item["sha256_aab"] = _sha256_file(out_aab)

    verify = _verify_aab(
        context, tools, out_aab, item["_keystore"], work, strict_aab
    )
    # 直改后结构校验失败：auto 模式回退重建，避免交付一个 validate 不过的 AAB
    if (item["aab_mode"] == "splice" and google_mode == "auto"
            and verify.get("bundletool_validate") != "ok"):
        item["warnings"].append(
            "AAB 直改校验失败，已自动回退重建："
            + str(verify.get("bundletool_validate") or "validate failed")
        )
        try:
            os.remove(out_aab)
        except OSError:
            pass
        _rebuild_aab(
            context, tools, proto_apk, source["path"], assets, out_aab, work,
        )
        _jarsigner_sign(context, tools, out_aab, item["_keystore"])
        item["aab_mode"] = "reconstruct"
        verify = _verify_aab(
            context, tools, out_aab, item["_keystore"], work, strict_aab
        )
    for k, v in verify.items():
        if k == "signer_sha256":
            if v and not item["signer_sha256"]:
                item["signer_sha256"] = v
        else:
            item["verify"][k] = v
    item["size_aab"] = os.path.getsize(out_aab)
    item["sha256_aab"] = _sha256_file(out_aab)
    rc, dumped = _bundletool_dump_manifest(context, tools, out_aab, work)
    if rc == 0:
        got_pkg = ""
        m = re.search(r'package="([^"]+)"', dumped)
        if m:
            got_pkg = m.group(1)
        if got_pkg and got_pkg != new_pkg:
            item["warnings"].append(f"AAB 清单包名解析为 {got_pkg}（期望 {new_pkg}）")


# ---------------------------------------------------------------------------
# 动作：presets / inspect / pack
# ---------------------------------------------------------------------------

def _presets(context) -> Dict[str, Any]:
    saved = _load_profiles()
    # 旧版内置预置 tencent 已改成通用 other；把旧配置平滑迁移过来
    chans = saved.get("channels") if isinstance(saved, dict) else None
    if isinstance(chans, dict) and "tencent" in chans:
        if "other" not in chans:
            chans["other"] = chans.pop("tencent")
        else:
            chans.pop("tencent")
    status = _tool_status(context)
    return {
        "success": True,
        "action": "presets",
        "channels": CHANNEL_PRESETS,
        "defaults": {
            "output_dir": os.path.join(get_output_dir(), "white-label"),
            "google_mode": "auto",
            "strict_aab_check": True,
            "save_profiles": True,
        },
        "saved_profiles": saved,
        "tools": status,
        "notes": [
            "「其他包」是通用渠道；可继续添加任意多个自定义渠道，标识用于产物文件名。",
            "AAB 直改需要同一次构建的 APK + AAB；不一致时自动回退重建。",
            "包名不能与源包名相同；每个渠道可使用独立 keystore。",
            "图标替换复用原图标资源文件，矢量图标会跳过并告警。",
        ],
    }


def _inspect(context, params: Dict[str, Any]) -> Dict[str, Any]:
    apk = str(params.get("apk_path") or "").strip()
    aab = str(params.get("aab_path") or "").strip()
    task_id = str(params.get("task_id") or "")
    if not apk:
        return {"success": False, "action": "inspect", "error": "缺少 apk_path"}
    try:
        _validate_apk(apk)
        tools = _collect_tools(context)
        tmp = context.work_dir(task_id, "inspect") if task_id else \
            os.path.join(get_output_dir(), "white-label", ".inspect")
        os.makedirs(tmp, exist_ok=True)
        source = _read_source(context, tools, apk, tmp)
        aab_info = _aab_guard(context, tools, aab, source, tmp) if aab else None
        return {
            "success": True,
            "action": "inspect",
            "source": {
                "path": apk,
                "package": source["package"],
                "label": source.get("label") or "",
                "version_code": source.get("version_code"),
                "version_name": source.get("version_name") or "",
                "min_sdk": source.get("min_sdk") or "",
                "target_sdk": source.get("target_sdk") or "",
                "signer_sha256": source.get("signer_sha256") or "",
                "abis": source.get("abis") or [],
                "split": bool(source.get("split")),
                "resource_package": source.get("resource_package") or "",
                "debuggable": bool(source.get("debuggable")),
                "icon": source.get("icon") or {"files": [], "skipped": []},
            },
            "aab": aab_info,
            "warnings": [],
        }
    except _Cancelled:
        raise
    except Exception as e:  # noqa: BLE001 — 解析失败以结果返回给 UI
        return {"success": False, "action": "inspect", "error": str(e)}


def _pack(context, params: Dict[str, Any]) -> Any:
    task_id = str(params.get("task_id") or "")
    apk = str(params.get("apk_path") or "").strip()
    aab_raw = params.get("aab_path")
    aab = str(aab_raw).strip() if aab_raw else ""
    output_dir = str(params.get("output_dir") or "").strip() or \
        os.path.join(get_output_dir(), "white-label")
    google_mode = str(params.get("google_mode") or "auto").strip().lower()
    if google_mode == "rebuild":
        google_mode = "reconstruct"
    if google_mode not in ("auto", "splice", "reconstruct"):
        google_mode = "auto"
    strict_aab = bool(params.get("strict_aab_check", True))
    save_profiles = bool(params.get("save_profiles", True))
    keep_workdir = bool(params.get("keep_workdir", False))
    raw_channels = params.get("channels") or []
    if not isinstance(raw_channels, list):
        raise ToolException("channels 必须是数组")
    raw_channels = [c for c in raw_channels if isinstance(c, dict)]

    _validate_apk(apk)
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    work = context.work_dir(task_id, "work") if task_id else \
        os.path.join(output_dir, ".work")
    os.makedirs(work, exist_ok=True)

    tools = _collect_tools(context, need_aab=bool(aab))
    source = _read_source(context, tools, apk, work)

    channels = [_channel_config(c) for c in raw_channels]
    channels = [c for c in channels if c["enabled"]]
    if not channels:
        raise ToolException("没有启用的渠道")

    seen_pkgs: Dict[str, str] = {}
    seen_ids: Dict[str, bool] = {}
    for ch in channels:
        if ch["id"] in seen_ids:
            raise ToolException(f"渠道标识重复: {ch['id']}")
        seen_ids[ch["id"]] = True
        pkg = ch["package_name"]
        if pkg in seen_pkgs:
            raise ToolException(
                f"渠道包名重复: {pkg}（{seen_pkgs[pkg]} 与 {ch['id']}）"
            )
        seen_pkgs[pkg] = ch["id"]

    # 预检：包名/keystore 先过，避免解码后才发现
    pre_errors: List[Dict[str, Any]] = []
    valid_channels = []
    for ch in channels:
        try:
            _validate_channel(ch, source)
            _preflight_keystore(context, tools, ch, work)
            valid_channels.append(ch)
        except _Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            pre_errors.append({"channel": ch["id"], "error": str(e)})
    if not valid_channels:
        raise ToolException(
            "所有渠道配置都无效: " + "；".join(
                f"{e['channel']}: {e['error']}" for e in pre_errors
            )
        )

    # 解码一次
    project = os.path.join(work, "project")
    if os.path.isdir(project):
        shutil.rmtree(project, ignore_errors=True)
    _check_cancel(context)
    context.log("解码 APK（apktool d -s）…")
    rc, text = _run(
        context,
        [tools["java"], "-jar", tools["apktool"], "d", "-f", "-s",
         "-o", project, apk],
        timeout=1800,
    )
    if rc != 0:
        _log_tail(context, "apktool", text)
        raise ToolException(f"apktool 解码失败（exit={rc}）")
    source["path"] = apk
    source["manifest_text"] = _read_text(
        os.path.join(project, "AndroidManifest.xml")
    )
    source_meta = _source_meta(tools, project, source)

    # stable-ids（一次）
    stable_ids = os.path.join(work, "stable-ids.txt")
    lines = []
    for rid, name in source["resource_dump"].get("id_to_name", {}).items():
        lines.append(f"{source['resource_package']}:{name}={rid}")
    if lines:
        _write_text(stable_ids, "\n".join(lines) + "\n")
    else:
        stable_ids = ""

    # AAB guard（一次）
    aab_guard = _aab_guard(context, tools, aab, source, work) if aab else None
    if aab_guard and aab_guard.get("reason"):
        context.log("[aab] " + aab_guard["reason"])

    items: List[Dict[str, Any]] = list(pre_errors)
    for ch in valid_channels:
        _check_cancel(context)
        try:
            item = _build_channel(
                context, tools, source, project, source_meta, stable_ids,
                ch, output_dir, work, google_mode, aab_guard, strict_aab,
            )
        except _Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 — 单渠道失败不拖垮其他渠道
            context.log(f"[{ch['id']}] 失败: {e}")
            item = {
                "channel": ch["id"],
                "label": ch["label"],
                "format": ch["format"],
                "package_name": ch["package_name"],
                "app_name": ch["app_name"],
                "version_code": ch["version_code"],
                "version_name": ch["version_name"],
                "apk_path": None, "aab_path": None, "aab_mode": None,
                "size_apk": None, "size_aab": None,
                "sha256_apk": None, "sha256_aab": None,
                "signer_sha256": "", "verify": {}, "icon": {},
                "warnings": [], "error": str(e), "duration_ms": 0,
            }
        items.append(item)

    # profiles
    if save_profiles:
        try:
            profiles = {
                "schema": 1,
                "output_dir": output_dir,
                "google_mode": google_mode,
                "channels": {},
            }
            for raw in raw_channels:
                cid = str(raw.get("id") or "")
                if cid:
                    profiles["channels"][cid] = _profile_from_channel(raw)
            _save_profiles(profiles)
        except Exception as e:  # noqa: BLE001 — 配置保存失败不影响产物
            context.log(f"保存 profiles 失败: {e}")

    ts = time.strftime("%Y%m%d-%H%M%S")
    report_path = os.path.join(output_dir, f"white-label-report-{ts}.json")
    report = {
        "schema": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": {k: v for k, v in source.items()
                   if k not in ("resource_dump", "manifest_text", "icon")},
        "source_icon": source.get("icon"),
        "aab": aab_guard,
        "google_mode": google_mode,
        "output_dir": output_dir,
        "items": items,
        "errors": pre_errors,
        "warnings": [],
    }
    try:
        _write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as e:  # noqa: BLE001
        context.log(f"写报告失败: {e}")
        report_path = ""

    succeeded = [i for i in items if i.get("apk_path") or i.get("aab_path")]
    all_ok = all(not i.get("error") for i in items)
    if not keep_workdir and all_ok:
        shutil.rmtree(work, ignore_errors=True)
    return context.finish({
        "success": bool(succeeded),
        "action": "pack",
        "report_path": report_path,
        "items": items,
        "errors": pre_errors,
        "warnings": [],
    })


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def run(context, action: str = "pack", **params):
    action = (action or "pack").strip().lower()
    try:
        if action == "presets":
            return context.finish(_presets(context))
        if action == "inspect":
            return context.finish(_inspect(context, params))
        if action == "pack":
            return _pack(context, params)
        raise ToolException(f"未知 action: {action}")
    except _Cancelled:
        context.cancelled({"action": action, "cancelled": True})
        return {"cancelled": True, "action": action}
