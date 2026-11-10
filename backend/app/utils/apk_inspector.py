#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK 分析工具 - 纯 Python 标准库实现，无外部依赖。
提供 SO 文件枚举、架构对比、压缩分析和 16KB 页面对齐检测。

16KB 页面检测覆盖 4 个位置（全部纯 Python 解析，不依赖 aapt/zipalign）：
- AndroidManifest.xml 中 ``<application android:extractNativeLibs>`` 原生库压缩开关
- .so 的 PT_LOAD 段 p_align >= 0x4000
- .so 的 PT_GNU_RELRO 结束地址（VirtAddr + MemSiz）按 0x4000 对齐，或其后
  没有可写数据（RELRO 占满其所在 LOAD 段），判定规则见
  https://developer.android.com/guide/practices/page-sizes#relro-flag
- APK 内 STORED 条目的数据偏移（zipalign：通用 4 字节 + .so 16KB）

AAB（``container='aab'``）本身不做 zipalign：未压缩原生库的 ZIP 对齐由
bundletool 生成 APK 时施加，取决于 ``BundleConfig`` 的
``optimizations.uncompressNativeLibraries``。该消息缺省时的默认值随 bundle
记录的 bundletool 版本变化（见 ``_bundletool_defaults``），因此不能简单按
4KB 处理。
"""

import json
import logging
import os
import re
import struct
import zipfile
from typing import Dict, List, Optional

_logger = logging.getLogger(__name__)

# 64-bit Android ABI names
_64BIT_ABIS = {"arm64-v8a", "x86_64"}

# Regex: classes.dex, classes2.dex, classes3.dex, ...
_DEX_NAME_RE = re.compile(r'^classes\d*\.dex$')

# ELF constants
ELF_MAGIC = b'\x7fELF'
ELFCLASS64 = 2
PT_LOAD = 1
PT_GNU_RELRO = 0x6474E552
PAGE_16KB = 16384  # 0x4000
ELF64_EHDR_SIZE = 64
ELF64_PHDR_SIZE = 56
ELF64_SHDR_SIZE = 64
PF_W = 0x2          # program header: 段可写
SHF_WRITE = 0x1     # section header: 段可写
SHF_ALLOC = 0x2     # section header: 占用运行时内存

# ZIP alignment constants (mirror `zipalign -P 16 4`)
ZIP_DEFAULT_ALIGN = 4
ZIP_MISALIGNED_SAMPLE = 32  # 只保留前 N 个未对齐条目，避免 payload 过大

# BundleConfig 缺省值随"生成 bundle 时使用的 bundletool 版本"变化，来源：
# bundletool ApkOptimizations.DEFAULT_OPTIMIZATIONS_BY_BUNDLETOOL_VERSION
# （https://github.com/google/bundletool/blob/master/src/main/java/com/android/tools/
#   build/bundletool/optimizations/ApkOptimizations.java）
# - 1.17.0 起默认页对齐为 16KB（release notes: "Default page size is now set to 16 KB"）；
# - 0.6.0 起默认启用未压缩原生库。
# 解析规则见 OptimizationsMerger.mergeWithDefaults：显式值优先，否则取上表默认值；
# bundle 未记录版本时 bundletool 用自身当前版本，这里按现代版本处理。
_BUNDLETOOL_VERSION_16K_DEFAULT = (1, 17, 0)
_BUNDLETOOL_VERSION_UNCOMPRESS_DEFAULT = (0, 6, 0)
_BUNDLETOOL_VERSION_RE = re.compile(r'\s*(\d+)\.(\d+)(?:\.(\d+))?')

# 防御性上限：正常 AndroidManifest.xml 只有几十 KB，避免恶意 APK 触发大内存分配
MAX_MANIFEST_BYTES = 4 * 1024 * 1024

# Android binary XML (AXML / ResXMLTree) constants
AXML_TYPE = 0x0003
AXML_STRING_POOL = 0x0001
AXML_RESOURCE_MAP = 0x0180
AXML_START_ELEMENT = 0x0102
AXML_NO_INDEX = 0xFFFFFFFF
AXML_UTF8_FLAG = 0x100
AXML_TYPE_STRING = 0x03
AXML_TYPE_INT_BOOLEAN = 0x12
# android.R.attr.extractNativeLibs（framework 属性的资源 ID）
AXML_ATTR_EXTRACT_NATIVE_LIBS = 0x010104EA


def enumerate_so_files(apk_path: str) -> Dict[str, List[str]]:
    """
    枚举 APK 中按 ABI 分组的 .so 文件。

    遍历 zip 条目中匹配 ``lib/<abi>/*.so`` 的文件，按 ABI 名称分组，
    值仅包含 .so 文件名（不含 ``lib/<abi>/`` 前缀）。

    Args:
        apk_path: APK 文件路径。

    Returns:
        形如 ``{"arm64-v8a": ["libfoo.so", "libbar.so"], ...}`` 的字典。
        若 APK 不存在或没有 lib/ 目录则返回 ``{}``。
    """
    result: Dict[str, List[str]] = {}

    if not apk_path or not os.path.exists(apk_path):
        _logger.warning("APK not found: %s", apk_path)
        return result

    try:
        with zipfile.ZipFile(apk_path, 'r') as zf:
            for name in zf.namelist():
                # Match pattern: lib/<abi>/*.so
                if not name.startswith('lib/') or not name.endswith('.so'):
                    continue

                # Split into parts: ['lib', '<abi>', '<filename>.so']
                parts = name.split('/')
                if len(parts) < 3:
                    continue

                abi = parts[1]
                so_file = parts[-1]

                if abi not in result:
                    result[abi] = []
                result[abi].append(so_file)
    except Exception:
        _logger.warning("Failed to enumerate SO files from %s", apk_path, exc_info=True)
        return {}

    return result


def compare_so_across_arches(so_map: Dict) -> Dict:
    """
    比较不同架构间 .so 文件的差异。

    以所有架构的 .so 文件名并集为基线，报告每个架构缺失的文件名。

    Args:
        so_map: ``enumerate_so_files`` 的返回结果。

    Returns:
        - 若 ``so_map`` 为空，返回 ``{"no_native": True}``
        - 若仅一种架构，返回 ``{"single_arch": True}``
        - 否则返回:
          ``{"baseline": [...], "arches": {"arm64-v8a": {"so_files": [...], "missing": [...], "count": N}, ...}}``
    """
    if not so_map:
        return {"no_native": True}

    arch_names = list(so_map.keys())
    if len(arch_names) == 1:
        return {"single_arch": True}

    # Build baseline: union of all .so filenames
    baseline: List[str] = sorted(set(
        so_file for so_list in so_map.values() for so_file in so_list
    ))

    arches: Dict = {}
    for arch, so_files in so_map.items():
        so_set = set(so_files)
        missing = sorted(baseline_set - so_set) if (baseline_set := set(baseline)) else []
        arches[arch] = {
            "so_files": sorted(so_files),
            "missing": missing,
            "count": len(so_files),
        }

    return {
        "baseline": baseline,
        "arches": arches,
    }


def analyze_compression(apk_path: str) -> Dict:
    """
    分析 APK 条目的压缩方式，按类别分组统计。

    类别分组规则：
    - ``assets/`` 前缀 → ``"assets"``
    - ``lib/`` 前缀 → ``"lib"``
    - 文件名匹配 ``classes<N>.dex`` → ``"dex"``
    - 其他条目忽略

    每个类别统计：
    - ``stored``: 未压缩条目数（compress_type == 0）
    - ``deflated``: Deflate 压缩条目数（compress_type == 8）
    - ``stored_size``: 未压缩条目的原始大小总和（字节）
    - ``uncompressed``: 该类别所有条目的原始大小总和（字节，含已压缩与未压缩）
    - ``compressed``: 该类别所有条目的压缩后大小总和（字节，即 ZIP 内占用的实际体积；
      STORED 条目的 compress_size == file_size，故对体积无贡献缩减）

    Args:
        apk_path: APK 文件路径。

    Returns:
        形如 ``{"assets": {"stored": N, "deflated": M, "stored_size": B,
        "uncompressed": U, "compressed": C}, ...}`` 的字典。
        不存在某类别的条目时，对应值为零。
    """
    categories = {
        "assets": {"stored": 0, "deflated": 0, "stored_size": 0, "uncompressed": 0, "compressed": 0},
        "lib": {"stored": 0, "deflated": 0, "stored_size": 0, "uncompressed": 0, "compressed": 0},
        "dex": {"stored": 0, "deflated": 0, "stored_size": 0, "uncompressed": 0, "compressed": 0},
    }

    if not apk_path or not os.path.exists(apk_path):
        _logger.warning("APK not found for compression analysis: %s", apk_path)
        return categories

    try:
        with zipfile.ZipFile(apk_path, 'r') as zf:
            for info in zf.infolist():
                category = _classify_entry(info.filename)
                if category is None:
                    continue

                entry = categories[category]
                entry["uncompressed"] += info.file_size
                entry["compressed"] += info.compress_size
                if info.compress_type == 0:  # ZIP_STORED
                    entry["stored"] += 1
                    entry["stored_size"] += info.file_size
                elif info.compress_type == 8:  # ZIP_DEFLATED
                    entry["deflated"] += 1
                # Other compression methods are silently ignored
    except Exception:
        _logger.warning("Failed to analyze compression for %s", apk_path, exc_info=True)

    return categories


def _classify_entry(filename: str) -> Optional[str]:
    """根据文件名归类到 assets/lib/dex，否则返回 None。"""
    if filename.startswith('assets/'):
        return "assets"
    if filename.startswith('lib/'):
        return "lib"
    basename = filename.rsplit('/', 1)[-1] if '/' in filename else filename
    if _DEX_NAME_RE.match(basename):
        return "dex"
    return None


def _parse_bundletool_version(version_text) -> Optional[tuple]:
    """把 ``"1.17.2"`` / ``"1.0.0-dev"`` 解析成 ``(1, 17, 2)``；无法解析返回 None。"""
    if not version_text:
        return None
    match = _BUNDLETOOL_VERSION_RE.match(str(version_text))
    if not match:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


def _bundletool_defaults(version_text=None) -> Dict:
    """
    计算 BundleConfig 缺省项在 bundletool 生成 APK 时的默认值。

    bundletool 依据 bundle 中记录的 ``bundletool.version`` 查表取默认值
    （``ApkOptimizations.getDefaultOptimizationsForVersion``）：
    - ``uncompressNativeLibraries.enabled`` 默认 true（>= 0.6.0）；
    - ``alignment`` 默认 ``PAGE_ALIGNMENT_16K``（>= 1.17.0），否则按 4K 生成。

    bundle 未记录版本时 bundletool 改用自身当前版本，这里按现代版本处理。

    Returns:
        ``{"version": str | None, "uncompress_enabled": bool, "alignment": str,
        "from_version": bool}``
    """
    version = _parse_bundletool_version(version_text)
    if version is None:
        return {
            "version": None,
            "uncompress_enabled": True,
            "alignment": "PAGE_ALIGNMENT_16K",
            "from_version": False,
        }
    return {
        "version": str(version_text).strip(),
        "uncompress_enabled": version >= _BUNDLETOOL_VERSION_UNCOMPRESS_DEFAULT,
        "alignment": (
            "PAGE_ALIGNMENT_16K"
            if version >= _BUNDLETOOL_VERSION_16K_DEFAULT
            else "PAGE_ALIGNMENT_4K"
        ),
        "from_version": True,
    }


# 极少数 JVM/序列化实现会把枚举打印成数值（proto 枚举值），做一层兜底映射
_PAGE_ALIGNMENT_BY_VALUE = {
    1: "PAGE_ALIGNMENT_4K",
    2: "PAGE_ALIGNMENT_16K",
    3: "PAGE_ALIGNMENT_64K",
}


def parse_bundle_config(config_text: str) -> Dict:
    """
    解析 ``bundletool dump config --bundle=<aab>`` 的 JSON 输出，并折算成
    bundletool 生成 APK 时实际生效的"未压缩原生库开关 + ZIP 页对齐"。

    判定语义与 bundletool 的 ``OptimizationsMerger.mergeWithDefaults`` 对齐：
    - ``optimizations.uncompressNativeLibraries`` 消息存在时取其 ``enabled``；
      消息不存在时取版本默认值（>= 0.6.0 为 true）；
    - ``alignment`` 为 4K/16K/64K 时直接采用；缺省或 ``UNSPECIFIED`` 时取
      ``bundletool.version`` 对应的默认值（>= 1.17.0 为 16K，否则 4K）。
      不能一律按 4K 处理：用 bundletool 1.17.0+ 构建的 bundle 默认就是 16K。
    - ``dump config`` 用 protobuf ``JsonFormat`` 默认格式输出，值为 false 的
      ``enabled`` 会被省略：消息存在但没有 ``enabled`` 字段按"未启用"处理。
    - 原生库被压缩时不需要 ZIP 对齐（安装时解压后仍按 ELF 对齐映射），此时
      ``ok`` 记 True；只有未压缩原生库才要求 ZIP 起始偏移 16KB 对齐。

    Args:
        config_text: ``bundletool dump config`` 的 stdout。

    Returns:
        ``{"alignment": str | None, "alignment_declared": str | None,
        "alignment_source": str | None, "bundletool_version": str | None,
        "uncompress_enabled": bool, "uncompress_source": str | None,
        "zip_alignment_16k": bool, "ok": bool, "error": str | None}``

        - ``alignment``: 实际生效的页对齐（64K 是 16K 的整数倍，同样满足 16KB）；
        - ``alignment_source``: ``declared`` / ``default_by_bundletool_version`` /
          ``default_current_tool``；
        - ``zip_alignment_16k``: 生效对齐是否 >= 16KB；
        - ``ok``: ZIP 对齐要求是否满足（压缩原生库时天然满足）；
        - 读取/解析失败时 ``ok=False`` 且 ``error`` 给出原因（fail closed）。
    """
    result: Dict = {
        "bundletool_version": None,
        "alignment": None,
        "alignment_declared": None,
        "alignment_source": None,
        "uncompress_enabled": False,
        "uncompress_source": None,
        "zip_alignment_16k": False,
        "ok": False,
        "error": None,
    }
    if not config_text or not config_text.strip():
        result["error"] = "empty_config"
        return result

    payload = None
    try:
        payload = json.loads(config_text)
    except Exception:
        # 个别 JVM 会把启动警告混进 stdout，从第一个 '{' 起重试
        start = config_text.find('{')
        if start >= 0:
            try:
                payload = json.loads(config_text[start:])
            except Exception:
                payload = None

    if not isinstance(payload, dict):
        result["error"] = "invalid_json"
        return result

    version_text = (payload.get("bundletool") or {}).get("version") or None
    result["bundletool_version"] = version_text
    defaults = _bundletool_defaults(version_text)

    uncompress = (payload.get("optimizations") or {}).get(
        "uncompressNativeLibraries"
    )
    declared_alignment = None
    if isinstance(uncompress, dict):
        if "enabled" in uncompress:
            enabled = bool(uncompress.get("enabled"))
        else:
            # JsonFormat 省略 false：消息存在但没 enabled ⇒ 未启用未压缩原生库
            enabled = False
        result["uncompress_enabled"] = enabled
        result["uncompress_source"] = "declared"
        declared_alignment = uncompress.get("alignment")
    else:
        result["uncompress_enabled"] = bool(defaults["uncompress_enabled"])
        result["uncompress_source"] = "default"

    if isinstance(declared_alignment, int):
        declared_alignment = _PAGE_ALIGNMENT_BY_VALUE.get(declared_alignment)
    if declared_alignment and declared_alignment != "PAGE_ALIGNMENT_UNSPECIFIED":
        alignment = declared_alignment
        alignment_source = "declared"
    else:
        alignment = defaults["alignment"]
        alignment_source = (
            "default_by_bundletool_version"
            if defaults["from_version"]
            else "default_current_tool"
        )

    zip_alignment_16k = alignment in (
        "PAGE_ALIGNMENT_16K",
        "PAGE_ALIGNMENT_64K",
    )
    result["alignment_declared"] = declared_alignment
    result["alignment"] = alignment
    result["alignment_source"] = alignment_source
    result["zip_alignment_16k"] = zip_alignment_16k
    # 压缩的原生库在安装时解压，不需要 ZIP 对齐；只有未压缩时才强制 16KB。
    result["ok"] = zip_alignment_16k or not result["uncompress_enabled"]
    return result


def _parse_native_lib_entry(entry_name: str, container: str):
    """
    解析 zip 条目为 ``(abi, so 文件名)``；不是目标布局的 .so 时返回 None。

    - APK: ``lib/<abi>/<file>.so``
    - AAB: ``<module>/lib/<abi>/<file>.so``
    """
    if not entry_name.endswith('.so'):
        return None
    parts = entry_name.split('/')
    if container == 'aab':
        if len(parts) < 4 or parts[1] != 'lib':
            return None
        return parts[2], parts[-1]
    if not entry_name.startswith('lib/') or len(parts) < 3:
        return None
    return parts[1], parts[-1]


def check_16kb_page_support(file_path: str, container: str = 'apk',
                            bundle_config: Optional[Dict] = None) -> Dict:
    """
    检测 APK / AAB 的 16KB 页面兼容性。

    ``container='apk'``（默认）检查 4 个位置：
    1. ``<application android:extractNativeLibs>``：``true`` → 不通过；
    2. 64 位 .so 的 PT_LOAD 段 p_align >= 16384（或 0）；
    3. 64 位 .so 的 PT_GNU_RELRO 结束地址运行期风险（见 ``_relro_verdict``）：
       只统计"RELRO 结束地址所在 16KB 页内还有可写数据"的情况，属于运行期
       SIGSEGV 风险，**不影响 Play 上传门禁**（``gate_ok`` 不包含它）；
    4. APK zipalign：STORED 条目 4 字节、.so 16KB、且无压缩的 64 位 .so。

    ``container='aab'`` 时（.so 位于 ``<module>/lib/<abi>/``）：
    - 位置 2/3 同上；
    - AAB 本身不做 zipalign（由 bundletool 生成 APK 时做），改为使用
      ``bundle_config``（``parse_bundle_config`` 的返回）判断生效的未压缩
      原生库开关与页对齐，结果放在 ``"bundle"``；
    - 没有 64 位原生库时（纯 Java/Kotlin 应用）该对齐检查项不适用，
      ``bundle.applied=False``，不参与汇总判定（官方明确这类应用已兼容 16KB）；
    - ``"manifest"`` / ``"zipalign"`` 为 None。

    Args:
        file_path: APK / AAB 文件路径。
        container: ``'apk'`` 或 ``'aab'``。
        bundle_config: AAB 的 ``parse_bundle_config`` 结果。

    Returns:
        逐 ABI 明细 + 分项（向上兼容旧版持久化 payload）：

        - ``"arm64-v8a"`` / ``"x86_64"``: ``{<so 文件名>: {
          supports_16kb, load_ok, relro_ok, relro_status, relro_risk_sections,
          max_align, pt_load_aligns, gnu_relro_align, gnu_relro_present,
          gnu_relro_end_aligned}}``
        - ``"skipped"``: 非 ELF / 32 位等被跳过的条目 ``[{file, arch, reason}]``
        - ``"manifest"``: ``{present, extract_native_libs, ok}``（AAB 为 None）
        - ``"zipalign"``: ``{ok, checked, ...}``（AAB 为 None）
        - ``"bundle"``: ``parse_bundle_config`` 的结果 + ``"applied"``
          （是否有 64 位原生库让该检查项生效）
        - ``"relro_risk"`` / ``"relro_unknown"``: RELRO 结束地址有运行风险 /
          无法确认的 ``[{arch, file, sections?}]``
        - ``"gate_ok"``: ELF LOAD + 整包对齐（Play 上传门禁）是否满足
        - ``"no_64bit_native"`` / ``"supported"``: 汇总判定（supported = gate_ok
          且无 RELRO 运行风险）
        - 若文件无法打开，返回 ``{}``
    """
    result: Dict = {}

    if not file_path or not os.path.exists(file_path):
        _logger.warning("File not found for 16KB analysis: %s", file_path)
        return result

    is_aab = container == 'aab'
    skipped: List[Dict] = []

    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            for name in zf.namelist():
                lib_entry = _parse_native_lib_entry(name, container)
                if lib_entry is None:
                    continue

                abi, so_file = lib_entry
                if abi not in _64BIT_ABIS:
                    continue

                try:
                    analysis = _parse_elf_page_align(zf, name)
                    if analysis is None:
                        continue

                    if "error" in analysis:
                        skipped.append({"file": so_file, "arch": abi, "reason": analysis["error"]})
                        continue
                    if analysis.get("skipped"):
                        skipped.append({"file": so_file, "arch": abi, "reason": analysis["skipped"]})
                        continue

                    if abi not in result:
                        result[abi] = {}
                    result[abi][so_file] = {
                        "supports_16kb": analysis["supports_16kb"],
                        "load_ok": analysis["load_ok"],
                        "relro_ok": analysis["relro_ok"],
                        "relro_status": analysis["relro_status"],
                        "relro_risk_sections": analysis["relro_risk_sections"],
                        "max_align": analysis["max_align"],
                        "pt_load_aligns": analysis["pt_load_aligns"],
                        "gnu_relro_align": analysis["gnu_relro_align"],
                        "gnu_relro_present": analysis["gnu_relro_present"],
                        "gnu_relro_end_aligned": analysis["gnu_relro_end_aligned"],
                    }
                except Exception as exc:
                    _logger.warning("Error processing %s in container: %s", name, exc)
                    skipped.append({"file": so_file, "arch": abi, "reason": "error"})

    except Exception:
        _logger.warning("Failed to open container for 16KB analysis: %s", file_path, exc_info=True)
        return result

    if skipped:
        result["skipped"] = skipped

    # 只有 64 位 .so 才受 16KB 页面影响（32 位 ABI 不参与），先算出来：
    # 没有 64 位原生库的包（纯 Java/Kotlin 应用）本身就兼容 16KB，
    # 此时 APK zipalign / BundleConfig 对齐都无需参与判定。
    so_entries = [
        entry
        for abi in _64BIT_ABIS
        for entry in result.get(abi, {}).values()
    ]

    if is_aab:
        result["container"] = "aab"
        result["manifest"] = None
        result["zipalign"] = None
        if isinstance(bundle_config, dict):
            bundle = dict(bundle_config)
        else:
            bundle = {
                "alignment": None,
                "alignment_declared": None,
                "alignment_source": None,
                "bundletool_version": None,
                # 未知（而非"已压缩"）：UI 不应据此显示压缩说明
                "uncompress_enabled": None,
                "uncompress_source": None,
                "zip_alignment_16k": None,
                "ok": False,
                "error": "bundle_config_unavailable",
            }
        # applied=False 表示该检查项对本次判定不适用（没有 64 位原生库）。
        bundle["applied"] = bool(so_entries)
        result["bundle"] = bundle
        package_ok = bool(bundle.get("ok")) if so_entries else True
    else:
        # 4 个检查位置中的两个整包检查：manifest 压缩开关 + APK zipalign。
        # 分项失败不应让整个分析失败，各自捕获异常；无法判定时按不通过处理
        # （避免把"检查不了"误报成"检查通过"）。
        try:
            result["manifest"] = check_manifest_native_extract(file_path)
        except Exception:
            _logger.warning("Manifest native-libs check failed: %s", file_path, exc_info=True)
            result["manifest"] = {
                "present": False,
                "extract_native_libs": None,
                "ok": False,
                "error": "check_failed",
            }

        try:
            result["zipalign"] = check_apk_alignment(file_path)
        except Exception:
            _logger.warning("APK zipalign check failed: %s", file_path, exc_info=True)
            result["zipalign"] = {
                "ok": False,
                "checked": 0,
                "so_checked": 0,
                "compressed_so": 0,
                "unreadable": 0,
                "misaligned_count": 0,
                "misaligned": [],
                "error": "check_failed",
            }
        package_ok = bool(
            result["manifest"].get("ok", True)
            and result["zipalign"].get("ok", True)
        )

    result["no_64bit_native"] = not so_entries

    # 拆分两类结论：
    # - gate_ok：安装/映射/上架所需的对齐（ELF LOAD + 整包 ZIP 对齐）。
    #   这正是 Google Play 16KB 校验关注的部分。
    # - supported：在前面基础上，RELRO 结束地址也没有运行期崩溃风险。
    #   RELRO 风险项不影响 Play 上传门禁，但 16KB 设备上可能 SIGSEGV。
    relro_risk: List[Dict] = []
    relro_unknown: List[Dict] = []
    for abi in _64BIT_ABIS:
        for so_file, entry in (result.get(abi) or {}).items():
            status = entry.get("relro_status")
            if status == "risk":
                relro_risk.append({
                    "arch": abi,
                    "file": so_file,
                    "sections": entry.get("relro_risk_sections") or [],
                })
            elif status == "unknown":
                relro_unknown.append({"arch": abi, "file": so_file})

    result["relro_risk"] = relro_risk
    result["relro_unknown"] = relro_unknown
    result["gate_ok"] = bool(
        package_ok and all(entry.get("load_ok", True) for entry in so_entries)
    )
    result["supported"] = bool(result["gate_ok"] and not relro_risk)

    return result


def check_manifest_native_extract(apk_path: str) -> Dict:
    """
    检查 AndroidManifest.xml 中 ``<application android:extractNativeLibs>``。

    纯 Python 解析编译后的二进制 XML（AXML），不调用 aapt。
    该属性为 ``true`` 时原生库在 APK 内被压缩/抽取，无法保证 16KB 页面，
    判定失败；``false`` 或未声明（``present=False``）判定通过。
    读取失败 / manifest 缺失 / 解析失败时 ``ok=False``（无法判定按不通过处理）。

    Args:
        apk_path: APK 文件路径。

    Returns:
        ``{"present": bool, "extract_native_libs": bool | None, "ok": bool}``
        - ``present``: 是否找到该属性（属性存在但值类型无法识别时也为 True）
        - ``extract_native_libs``: 解析出的布尔值；未声明/无法识别时为 None
        - ``ok``: ``extract_native_libs is not True``；读取/解析失败时为 False
        - ``error``: 仅在失败时出现（apk_missing / manifest_missing /
          manifest_unreadable / manifest_too_large / not_axml / truncated /
          parse_failed）
    """
    result: Dict = {"present": False, "extract_native_libs": None, "ok": True}
    if not apk_path or not os.path.exists(apk_path):
        _logger.warning("APK not found for manifest native-libs check: %s", apk_path)
        result["ok"] = False
        result["error"] = "apk_missing"
        return result

    try:
        with zipfile.ZipFile(apk_path, 'r') as zf:
            with zf.open("AndroidManifest.xml") as entry:
                manifest = entry.read(MAX_MANIFEST_BYTES + 1)
    except KeyError:
        result["ok"] = False
        result["error"] = "manifest_missing"
        return result
    except Exception:
        _logger.warning("Failed to read AndroidManifest.xml from %s", apk_path, exc_info=True)
        result["ok"] = False
        result["error"] = "manifest_unreadable"
        return result

    if len(manifest) > MAX_MANIFEST_BYTES:
        result["ok"] = False
        result["error"] = "manifest_too_large"
        return result

    present, value, error = _parse_axml_application_attr(
        manifest, AXML_ATTR_EXTRACT_NATIVE_LIBS, "extractNativeLibs"
    )
    if error:
        result["ok"] = False
        result["error"] = error
        return result

    result["present"] = present
    result["extract_native_libs"] = value
    result["ok"] = value is not True
    return result


def check_apk_alignment(apk_path: str) -> Dict:
    """
    APK 对齐检查：对齐部分等价于 ``zipalign -c -P 16 4``。

    - 所有 STORED 条目的数据偏移必须是 4 的倍数；
    - STORED 的 ``.so`` 条目数据偏移必须是 16384 的倍数；
    - 额外统计被压缩的 64 位 .so（压缩后无法在 APK 内按 16KB 映射）。
      因此 ``ok`` 比 zipalign 更严格：压缩的 64 位 .so 也会判为不通过。

    Args:
        apk_path: APK 文件路径。

    Returns:
        ``{"ok": bool, "checked": int, "so_checked": int, "compressed_so": int,
        "unreadable": int, "misaligned_count": int,
        "misaligned": [{"entry", "required", "offset"}]}``
        ``ok`` = 无未对齐条目 且 无被压缩的 64 位 .so 且 无不可解析条目。
    """
    result: Dict = {
        "ok": True,
        "checked": 0,
        "so_checked": 0,
        "compressed_so": 0,
        "unreadable": 0,
        "misaligned_count": 0,
        "misaligned": [],
    }
    if not apk_path or not os.path.exists(apk_path):
        _logger.warning("APK not found for zipalign check: %s", apk_path)
        result["ok"] = False
        result["error"] = "apk_missing"
        return result

    try:
        with zipfile.ZipFile(apk_path, 'r') as zf, open(apk_path, 'rb') as raw:
            for info in zf.infolist():
                is_so = info.filename.endswith('.so')
                if info.compress_type != 0:  # 仅 STORED 条目参与 zipalign 对齐检查
                    if is_so and _is_64bit_so_entry(info.filename):
                        result["compressed_so"] += 1
                    continue
                if info.flag_bits & 0x1:  # 加密条目无法映射，跳过
                    continue

                offset = _zip_entry_data_offset(raw, info.header_offset)
                if offset is None:
                    result["unreadable"] += 1
                    continue

                required = PAGE_16KB if is_so else ZIP_DEFAULT_ALIGN
                result["checked"] += 1
                if is_so:
                    result["so_checked"] += 1
                if offset % required != 0:
                    result["misaligned_count"] += 1
                    if len(result["misaligned"]) < ZIP_MISALIGNED_SAMPLE:
                        result["misaligned"].append({
                            "entry": info.filename,
                            "required": required,
                            "offset": offset,
                        })
    except Exception:
        _logger.warning("Failed to verify APK alignment: %s", apk_path, exc_info=True)
        result["ok"] = False
        result["error"] = "read_failed"
        return result

    result["ok"] = (
        result["misaligned_count"] == 0
        and result["compressed_so"] == 0
        and result["unreadable"] == 0
    )
    return result


def _is_64bit_so_entry(entry_name: str) -> bool:
    """判断 zip 条目是否为 ``lib/<64 位 ABI>/*.so``。"""
    if not entry_name.startswith('lib/') or not entry_name.endswith('.so'):
        return False
    parts = entry_name.split('/')
    return len(parts) >= 3 and parts[1] in _64BIT_ABIS


def _zip_entry_data_offset(raw_file, header_offset: int) -> Optional[int]:
    """读取 zip local file header，计算条目数据区的绝对偏移。"""
    try:
        raw_file.seek(header_offset)
        header = raw_file.read(30)
        if len(header) < 30 or header[:4] != b'PK\x03\x04':
            return None
        name_len = struct.unpack_from('<H', header, 26)[0]
        extra_len = struct.unpack_from('<H', header, 28)[0]
        return header_offset + 30 + name_len + extra_len
    except Exception:
        return None


def _parse_axml_application_attr(data: bytes, attr_resource_id: int, attr_name: str):
    """
    在编译后的 AndroidManifest.xml（AXML）中查找 <application> 的指定属性。

    Args:
        data: AndroidManifest.xml 原始字节。
        attr_resource_id: 目标属性的 framework 资源 ID（如 extractNativeLibs）。
        attr_name: 目标属性的字符串名（部分 APK 会保留字符串名）。

    Returns:
        ``(present, value, error)``
        - ``present``: 是否找到该属性
        - ``value``: bool 或 None（属性存在但值无法识别）
        - ``error``: 解析失败时的原因（not_axml / truncated / parse_failed），
          成功返回 None
    """
    if len(data) < 8:
        return False, None, "too_small"

    try:
        chunk_type, _header_size, _size = struct.unpack_from('<HHI', data, 0)
        if chunk_type != AXML_TYPE:
            return False, None, "not_axml"

        strings: List[str] = []
        resource_ids: List[int] = []
        pos = 8
        total = len(data)

        while pos + 8 <= total:
            ctype, header_size, chunk_size = struct.unpack_from('<HHI', data, pos)
            if chunk_size < 8 or pos + chunk_size > total:
                return False, None, "truncated"

            if ctype == AXML_STRING_POOL:
                strings = _axml_string_pool(data, pos)
            elif ctype == AXML_RESOURCE_MAP:
                resource_ids = _axml_resource_map(data, pos)
            elif ctype == AXML_START_ELEMENT:
                body = pos + header_size
                chunk_end = pos + chunk_size
                if body + 20 > chunk_end:
                    return False, None, "truncated"
                # ResXMLTree_attrExt: ns(4) name(4) attrStart(2) attrSize(2)
                #   attrCount(2) idIndex(2) classIndex(2) styleIndex(2)
                (_ns, name_idx, attr_start, attr_size, attr_count,
                 _id_idx, _class_idx, _style_idx) = struct.unpack_from(
                    '<IIHHHHHH', data, body
                )
                if _axml_string(strings, name_idx) == 'application':
                    attrs_base = body + attr_start
                    for i in range(attr_count):
                        attr_offset = attrs_base + i * attr_size
                        if attr_offset + 20 > chunk_end:
                            return False, None, "truncated"
                        (_a_ns, a_name_idx, a_raw,
                         _a_size, _a_res0, a_type, a_data) = struct.unpack_from(
                            '<IIIHBBI', data, attr_offset
                        )
                        resource_id = (
                            resource_ids[a_name_idx]
                            if a_name_idx < len(resource_ids)
                            else 0
                        )
                        if (resource_id != attr_resource_id
                                and _axml_string(strings, a_name_idx) != attr_name):
                            continue
                        return True, _axml_attr_bool(strings, a_raw, a_type, a_data), None

            pos += chunk_size
    except Exception:
        _logger.warning("Failed to parse binary AndroidManifest.xml", exc_info=True)
        return False, None, "parse_failed"

    return False, None, None


def _axml_attr_bool(strings: List[str], raw_value_index: int,
                    value_type: int, value_data: int):
    """把 AXML 属性值转换为 bool（无法识别时返回 None）。"""
    if value_type == AXML_TYPE_INT_BOOLEAN:
        return bool(value_data)
    if value_type == AXML_TYPE_STRING:
        idx = raw_value_index if raw_value_index != AXML_NO_INDEX else value_data
        text = _axml_string(strings, idx)
        if text == 'true':
            return True
        if text == 'false':
            return False
    return None


def _axml_string(strings: List[str], index: int) -> str:
    """安全索引 AXML 字符串池（越界返回空串）。"""
    if 0 <= index < len(strings):
        return strings[index]
    return ""


def _axml_string_pool(data: bytes, offset: int) -> List[str]:
    """解析 RES_STRING_POOL 分块（支持 UTF-8 / UTF-16 两种编码）。"""
    _ctype, header_size, chunk_size = struct.unpack_from('<HHI', data, offset)
    if chunk_size < 8:
        return []
    string_count = struct.unpack_from('<I', data, offset + 8)[0]
    flags = struct.unpack_from('<I', data, offset + 16)[0]
    strings_start = struct.unpack_from('<I', data, offset + 20)[0]
    offsets_base = offset + header_size
    strings_base = offset + strings_start
    utf8 = bool(flags & AXML_UTF8_FLAG)

    strings: List[str] = []
    for i in range(string_count):
        try:
            str_offset = struct.unpack_from('<I', data, offsets_base + 4 * i)[0]
            pos = strings_base + str_offset
            if utf8:
                length = data[pos]
                pos += 1
                if length & 0x80:
                    length = ((length & 0x7F) << 8) | data[pos]
                    pos += 1
                byte_len = data[pos]
                pos += 1
                if byte_len & 0x80:
                    byte_len = ((byte_len & 0x7F) << 8) | data[pos]
                    pos += 1
                strings.append(data[pos:pos + byte_len].decode('utf-8', 'replace'))
            else:
                length = struct.unpack_from('<H', data, pos)[0]
                pos += 2
                if length & 0x8000:
                    length = ((length & 0x7FFF) << 16) | struct.unpack_from('<H', data, pos)[0]
                    pos += 2
                strings.append(data[pos:pos + length * 2].decode('utf-16-le', 'replace'))
        except Exception:
            strings.append('')
    return strings


def _axml_resource_map(data: bytes, offset: int) -> List[int]:
    """解析 RES_XML_RESOURCE_MAP 分块：字符串池下标 → 资源 ID。"""
    _ctype, header_size, chunk_size = struct.unpack_from('<HHI', data, offset)
    count = (chunk_size - header_size) // 4
    if count <= 0:
        return []
    ids: List[int] = []
    for i in range(count):
        ids.append(struct.unpack_from('<I', data, offset + header_size + 4 * i)[0])
    return ids


def _align_up(value: int, alignment: int) -> int:
    """向上对齐到 ``alignment`` 的整数倍。"""
    return (value + alignment - 1) // alignment * alignment


def _read_elf_writable_sections(f, elf_header: bytes) -> Dict:
    """
    读取 ELF 段表（section headers）中的可写段（SHF_ALLOC|SHF_WRITE）。

    RELRO 判定需要知道"16KB 页边界内是否还有可写数据"，这一点程序头无法表达：
    可写 LOAD 段可能包含只读数据/对齐填充。段表被裁剪（加固/壳常见）时无法
    确认，调用方按 unknown 处理，不误报为风险。

    Args:
        f: 可 seek 的 ELF 文件对象。
        elf_header: 已读出的 64 字节 ELF 头。

    Returns:
        ``{"usable": bool, "reason": str | None, "writable": [{"name", "start", "end"}]}``
    """

    def _fail(reason: str) -> Dict:
        return {"usable": False, "reason": reason, "writable": []}

    e_shoff = struct.unpack_from('<Q', elf_header, 40)[0]
    e_shentsize = struct.unpack_from('<H', elf_header, 58)[0]
    e_shnum = struct.unpack_from('<H', elf_header, 60)[0]
    e_shstrndx = struct.unpack_from('<H', elf_header, 62)[0]

    if e_shoff == 0:
        return _fail("no_section_headers")
    if e_shentsize < ELF64_SHDR_SIZE:
        return _fail("bad_shentsize")

    try:
        f.seek(e_shoff)
        if e_shnum == 0:
            # ELF 扩展编号：真实数量存在 section 0 的 sh_size
            first = f.read(ELF64_SHDR_SIZE)
            if len(first) < ELF64_SHDR_SIZE:
                return _fail("shdr_truncated")
            e_shnum = struct.unpack_from('<Q', first, 32)[0]
            if e_shnum <= 0 or e_shnum > 65535:
                return _fail("bad_shnum")
            table = first + f.read((e_shnum - 1) * e_shentsize)
        else:
            table = f.read(e_shnum * e_shentsize)
    except Exception:
        return _fail("shdr_unreadable")

    if len(table) < e_shnum * e_shentsize:
        return _fail("shdr_truncated")

    shdrs = []
    for i in range(e_shnum):
        base = i * e_shentsize
        shdrs.append({
            "name_i": struct.unpack_from('<I', table, base)[0],
            "flags": struct.unpack_from('<Q', table, base + 8)[0],
            "addr": struct.unpack_from('<Q', table, base + 16)[0],
            "offset": struct.unpack_from('<Q', table, base + 24)[0],
            "size": struct.unpack_from('<Q', table, base + 32)[0],
        })

    if e_shstrndx == 0 or e_shstrndx >= e_shnum:
        return _fail("no_shstrtab")
    shstr = shdrs[e_shstrndx]
    try:
        f.seek(shstr["offset"])
        shstr_data = f.read(min(shstr["size"], 1 << 20))
    except Exception:
        return _fail("shstrtab_unreadable")

    names_ok = False
    writable: List[Dict] = []
    for sec in shdrs:
        name = ""
        idx = sec["name_i"]
        if 0 <= idx < len(shstr_data):
            end = shstr_data.find(b'\0', idx)
            if end > idx:
                name = shstr_data[idx:end].decode('ascii', 'replace')
        if name.startswith('.'):
            names_ok = True
        # 可写且占用运行时内存、有实际地址的段才是"可能被写入"的区域
        if (
            (sec["flags"] & (SHF_ALLOC | SHF_WRITE)) == (SHF_ALLOC | SHF_WRITE)
            and sec["addr"] > 0
            and sec["size"] > 0
        ):
            writable.append({
                "name": name or "?",
                "start": sec["addr"],
                "end": sec["addr"] + sec["size"],
            })

    if not names_ok:
        # 段名被裁掉说明段表不完整（或被人为剥离），不能据此断言"无可写数据"
        return _fail("stripped_section_names")
    return {"usable": True, "reason": None, "writable": writable}


def _relro_verdict(relro: Dict[str, int], load_segments: List[Dict[str, int]],
                   section_info: Optional[Dict] = None) -> Dict:
    """
    按 Android linker 的真实行为判定单个 GNU_RELRO 段的 16KB 风险。

    bionic ``_phdr_table_set_gnu_relro_prot`` 对 RELRO 段做
    ``mprotect(page_start(vaddr), page_end(vaddr + memsz))``：结束地址未按
    0x4000 对齐时，该页内**属于同一映射**的可写数据也会被置为只读，运行期写入
    即 SIGSEGV。因此判定不是"RELRO 结尾必须等于 LOAD 结尾"，而是：

    - RELRO 结束地址已按 0x4000 对齐 → 无风险；
    - 否则检查危险窗口 ``[relro_end, align_up(relro_end, 0x4000))``：
      - 没有可写 PT_LOAD 覆盖该窗口 → 无风险（中间是段间空隙）；
      - 有可写 LOAD 覆盖，但段表可读且没有可写段落进窗口 → 无风险（只是填充）；
      - 有可写 LOAD 覆盖，段表被裁剪 → ``unknown``（无法确认，不误判为风险）；
      - 段表缺失（无法枚举可写段）或确有可写段落进窗口 → ``risk``。

    Args:
        relro: ``{"vaddr": int, "memsz": int, "align": int}``。
        load_segments: ``[{"vaddr", "memsz", "flags"}]``。
        section_info: ``_read_elf_writable_sections`` 的返回（惰性读取，可为 None）。

    Returns:
        ``{"status": "ok" | "risk" | "unknown", "end_aligned": bool,
        "relro_end": int, "risk_sections": [str]}``
    """
    relro_start = relro.get("vaddr", 0)
    relro_end = relro_start + relro.get("memsz", 0)
    verdict: Dict = {
        "status": "ok",
        "end_aligned": relro_end % PAGE_16KB == 0,
        "relro_end": relro_end,
        "relro_start": relro_start,
        "risk_sections": [],
    }
    if verdict["end_aligned"]:
        return verdict

    window_start = relro_end
    window_end = _align_up(relro_end, PAGE_16KB)
    writable_load_before_window = any(
        (seg.get("flags", 0) & PF_W)
        and seg.get("vaddr", 0) < window_end
        and seg.get("vaddr", 0) + seg.get("memsz", 0) > window_start
        for seg in load_segments
    )
    if not writable_load_before_window:
        return verdict

    info = section_info or {"usable": False, "reason": "no_section_headers"}
    if info.get("usable"):
        hits = [
            sec["name"]
            for sec in info.get("writable", [])
            if sec["start"] < window_end and sec["end"] > window_start
        ]
        if hits:
            verdict["status"] = "risk"
            verdict["risk_sections"] = hits
        return verdict

    # 段表不可用：段表完全没有时保守视为风险；仅名称被剥离时标记为无法确认
    verdict["status"] = (
        "risk" if info.get("reason") == "no_section_headers" else "unknown"
    )
    return verdict


def _parse_elf_page_align(zf: zipfile.ZipFile, entry_name: str) -> Optional[Dict]:
    """
    从 zip 条目中读取 ELF 头并解析 16KB 对齐判定所需的程序头。

    收集 PT_LOAD 的 p_align / VirtAddr / MemSiz / 可写标志，以及 PT_GNU_RELRO 的
    VirtAddr / MemSiz / p_align（p_align 仅作展示）。使用增量读取：先读 64 字节
    ELF 头，再读剩余部分到程序头表末尾；只有 RELRO 结束地址未对齐且危险窗口
    内存在可写 LOAD 时，才额外读取段表确认窗口内是否真的有可写数据
    （大 .so 的段表读取需要额外解压，避免无谓开销）。

    Args:
        zf: 已打开的 ZipFile 对象。
        entry_name: zip 条目名称。

    Returns:
        解析结果字典，或 None（表示应跳过此文件）：

        ``{supports_16kb, load_ok, relro_ok, relro_status, relro_risk_sections,
        relro_unknown, max_align, pt_load_aligns, gnu_relro_align,
        gnu_relro_present, gnu_relro_end_aligned}``

        - ``relro_status``: ``ok`` / ``risk`` / ``unknown`` / ``none``；
        - ``relro_ok``: risk → False，unknown → None，其余 True；
        - ``supports_16kb``: LOAD 对齐通过且 RELRO 无风险（unknown 不判失败）。
    """
    with zf.open(entry_name) as f:
        # Read ELF header (64 bytes)
        elf_header = f.read(ELF64_EHDR_SIZE)
        if len(elf_header) < 4:
            return {"error": "too_small"}

        # Check ELF magic
        if elf_header[:4] != ELF_MAGIC:
            return {"skipped": "non_elf"}

        # Check 64-bit class (byte at offset 4)
        if len(elf_header) < 5 or elf_header[4] != ELFCLASS64:
            return {"skipped": "32bit"}

        # Ensure we have enough header data
        if len(elf_header) < ELF64_EHDR_SIZE:
            return {"error": "truncated_elf_header"}

        # Parse program header table offsets from ELF header
        # e_phoff at offset 32 (uint64 little-endian)
        e_phoff = struct.unpack_from('<Q', elf_header, 32)[0]
        # e_phentsize at offset 54 (uint16 little-endian)
        e_phentsize = struct.unpack_from('<H', elf_header, 54)[0]
        # e_phnum at offset 56 (uint16 little-endian)
        e_phnum = struct.unpack_from('<H', elf_header, 56)[0]

        if e_phnum == 0 or e_phentsize == 0:
            return {"skipped": "no_phdrs"}

        # Calculate total bytes needed for header + program headers
        ph_end = e_phoff + e_phnum * e_phentsize
        remaining = ph_end - ELF64_EHDR_SIZE

        if remaining > 0:
            ph_data = f.read(remaining)
        else:
            ph_data = b''

        # Combine for unified buffer access
        buf = elf_header + ph_data

        pt_load_aligns: List[int] = []
        load_segments: List[Dict[str, int]] = []
        relro_segments: List[Dict[str, int]] = []
        max_align = 0
        truncated_phdrs = False

        for i in range(e_phnum):
            ph_offset = e_phoff + i * e_phentsize
            if ph_offset + ELF64_PHDR_SIZE > len(buf):
                truncated_phdrs = True
                break  # Truncated, stop processing

            # p_type at offset 0 (uint32), p_flags at offset 4 (uint32)
            p_type = struct.unpack_from('<I', buf, ph_offset)[0]
            p_flags = struct.unpack_from('<I', buf, ph_offset + 4)[0]
            # uint64 fields: p_vaddr at 16, p_memsz at 40, p_align at 48
            if p_type == PT_LOAD:
                p_vaddr = struct.unpack_from('<Q', buf, ph_offset + 16)[0]
                p_memsz = struct.unpack_from('<Q', buf, ph_offset + 40)[0]
                p_align = struct.unpack_from('<Q', buf, ph_offset + 48)[0]
                pt_load_aligns.append(p_align)
                load_segments.append({
                    "vaddr": p_vaddr,
                    "memsz": p_memsz,
                    "flags": p_flags,
                })
                if p_align > max_align:
                    max_align = p_align
            elif p_type == PT_GNU_RELRO:
                relro_segments.append({
                    "vaddr": struct.unpack_from('<Q', buf, ph_offset + 16)[0],
                    "memsz": struct.unpack_from('<Q', buf, ph_offset + 40)[0],
                    "align": struct.unpack_from('<Q', buf, ph_offset + 48)[0],
                })

        if truncated_phdrs:
            return {"error": "truncated_phdrs"}

        # LOAD：所有 PT_LOAD 的 p_align 必须 >= 16KB 或为 0
        load_ok = (
            all(a >= PAGE_16KB or a == 0 for a in pt_load_aligns)
            if pt_load_aligns else True
        )

        # RELRO：按 linker 的真实 mprotect 范围判定结束地址风险
        relro_verdicts: List[Dict] = []
        if relro_segments:
            # 仅当"未对齐 + 危险窗口内存在可写 LOAD"时才需要段表
            needs_sections = False
            for seg in relro_segments:
                end = seg["vaddr"] + seg["memsz"]
                if end % PAGE_16KB == 0:
                    continue
                window_end = _align_up(end, PAGE_16KB)
                if any(
                    (load.get("flags", 0) & PF_W)
                    and load["vaddr"] < window_end
                    and load["vaddr"] + load["memsz"] > end
                    for load in load_segments
                ):
                    needs_sections = True
                    break
            section_info = (
                _read_elf_writable_sections(f, elf_header)
                if needs_sections else None
            )
            relro_verdicts = [
                _relro_verdict(seg, load_segments, section_info)
                for seg in relro_segments
            ]

        statuses = [item["status"] for item in relro_verdicts]
        if "risk" in statuses:
            relro_status = "risk"
        elif "unknown" in statuses:
            relro_status = "unknown"
        elif relro_segments:
            relro_status = "ok"
        else:
            relro_status = "none"
        relro_ok = (
            False if relro_status == "risk"
            else (None if relro_status == "unknown" else True)
        )
        risk_sections: List[str] = []
        for item in relro_verdicts:
            for name in item.get("risk_sections", []):
                if name not in risk_sections:
                    risk_sections.append(name)
        relro_end_aligned = (
            all(item["end_aligned"] for item in relro_verdicts)
            if relro_verdicts else True
        )

        return {
            "supports_16kb": load_ok and relro_status != "risk",
            "load_ok": load_ok,
            "relro_ok": relro_ok,
            "relro_status": relro_status,
            "relro_risk_sections": risk_sections,
            "max_align": max_align,
            "pt_load_aligns": pt_load_aligns,
            "gnu_relro_align": max((seg["align"] for seg in relro_segments), default=0),
            "gnu_relro_present": bool(relro_segments),
            "gnu_relro_end_aligned": relro_end_aligned,
        }
