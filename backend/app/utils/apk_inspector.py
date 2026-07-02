#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK 分析工具 - 纯 Python 标准库实现，无外部依赖。
提供 SO 文件枚举、架构对比、压缩分析和 16KB 页面对齐检测。
"""

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
PAGE_16KB = 16384  # 0x4000
ELF64_EHDR_SIZE = 64
ELF64_PHDR_SIZE = 56


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

    Args:
        apk_path: APK 文件路径。

    Returns:
        形如 ``{"assets": {"stored": N, "deflated": M, "stored_size": B}, ...}`` 的字典。
        不存在某类别的条目时，对应值为零。
    """
    categories = {
        "assets": {"stored": 0, "deflated": 0, "stored_size": 0},
        "lib": {"stored": 0, "deflated": 0, "stored_size": 0},
        "dex": {"stored": 0, "deflated": 0, "stored_size": 0},
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


def check_16kb_page_support(apk_path: str) -> Dict:
    """
    检测 APK 中 64 位 .so 文件是否兼容 16KB 页面对齐。

    仅检查 ``arm64-v8a`` 和 ``x86_64`` 架构的 .so 文件。
    对每个 .so 读取 ELF 头并解析 PT_LOAD 段的 p_align 值。
    若所有 PT_LOAD 段的 p_align >= 16384 或为 0，则认为支持 16KB 页面。

    Args:
        apk_path: APK 文件路径。

    Returns:
        - 若没有 64 位 .so 文件：``{"no_64bit_native": True}``
        - 否则返回：
          ``{"arm64-v8a": {"libfoo.so": {"supports_16kb": bool, "max_align": int, "pt_load_aligns": [...]}, ...}, "x86_64": {...}, "skipped": [...]}``
    """
    result: Dict = {}

    if not apk_path or not os.path.exists(apk_path):
        _logger.warning("APK not found for 16KB analysis: %s", apk_path)
        return result

    skipped: List[Dict] = []

    try:
        with zipfile.ZipFile(apk_path, 'r') as zf:
            for name in zf.namelist():
                if not name.startswith('lib/') or not name.endswith('.so'):
                    continue

                parts = name.split('/')
                if len(parts) < 3:
                    continue

                abi = parts[1]
                if abi not in _64BIT_ABIS:
                    continue

                so_file = parts[-1]

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
                        "max_align": analysis["max_align"],
                        "pt_load_aligns": analysis["pt_load_aligns"],
                    }
                except Exception as exc:
                    _logger.warning("Error processing %s in APK: %s", name, exc)
                    skipped.append({"file": so_file, "arch": abi, "reason": "error"})

    except Exception:
        _logger.warning("Failed to open APK for 16KB analysis: %s", apk_path, exc_info=True)
        return result

    if skipped:
        result["skipped"] = skipped

    if not any(k in _64BIT_ABIS for k in result):
        return {"no_64bit_native": True}

    return result


def _parse_elf_page_align(zf: zipfile.ZipFile, entry_name: str) -> Optional[Dict]:
    """
    从 zip 条目中读取 ELF 头并解析 PT_LOAD 段的 p_align。

    使用增量读取：先读 64 字节 ELF 头，再读剩余部分到程序头表末尾。

    Args:
        zf: 已打开的 ZipFile 对象。
        entry_name: zip 条目名称。

    Returns:
        解析结果字典，或 None（表示应跳过此文件）。
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
        max_align = 0

        for i in range(e_phnum):
            ph_offset = e_phoff + i * e_phentsize
            if ph_offset + ELF64_PHDR_SIZE > len(buf):
                break  # Truncated, stop processing

            # p_type at offset 0 (uint32)
            p_type = struct.unpack_from('<I', buf, ph_offset)[0]
            if p_type == PT_LOAD:
                # p_align at offset 48 (uint64)
                p_align = struct.unpack_from('<Q', buf, ph_offset + 48)[0]
                pt_load_aligns.append(p_align)
                if p_align > max_align:
                    max_align = p_align

        # Judge 16KB support: all PT_LOAD aligns >= 16KB or == 0
        if pt_load_aligns:
            supports_16kb = all(a >= PAGE_16KB or a == 0 for a in pt_load_aligns)
        else:
            supports_16kb = True  # No PT_LOAD segments → no constraint

        return {
            "supports_16kb": supports_16kb,
            "max_align": max_align,
            "pt_load_aligns": pt_load_aligns,
        }
