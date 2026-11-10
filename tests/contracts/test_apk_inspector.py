"""
Contract tests for apk_inspector module — synthetic-APK fixtures only.
All tests use BytesIO + zipfile writemode with temp files; no real APK needed.
"""
import io
import json
import os
import struct
import tempfile
import zipfile
import zlib

import pytest

# backend/ is already on sys.path via conftest.py
from app.utils.apk_inspector import (
    analyze_compression,
    check_16kb_page_support,
    check_apk_alignment,
    check_manifest_native_extract,
    compare_so_across_arches,
    enumerate_so_files,
    parse_bundle_config,
)


# ---------------------------------------------------------------------------
# Synthetic-fixture helpers
# ---------------------------------------------------------------------------

def make_apk(entries: dict) -> str:
    """Create a temp APK file.

    ``entries`` maps filename → (content: bytes, compress_type: int).
    compress_type 0 = stored, 8 = deflated.

    Returns the temp file path.
    """
    fd, path = tempfile.mkstemp(suffix='.apk')
    os.close(fd)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, (data, ctype) in entries.items():
            zf.writestr(name, data, compress_type=ctype)
    return path


def make_elf64_segments(segments: list) -> bytes:
    """Create minimal ELF64 bytes from explicit program-header specs.

    ``segments``: list of dicts with keys ``p_type``, ``p_flags``, ``p_align``
    and optional ``vaddr`` / ``memsz`` (both ``0`` by default). Field offsets
    inside a 64-bit program header: p_type=0, p_flags=4, p_vaddr=16,
    p_filesz=32, p_memsz=40, p_align=48.
    """
    e_phoff = 64
    e_phentsize = 56
    e_phnum = len(segments)

    # ELF64 header — 64 bytes
    buf = bytearray(64)
    buf[0:4] = b'\x7fELF'            # e_ident magic
    buf[4] = 2                        # EI_CLASS = ELFCLASS64
    buf[5] = 1                        # EI_DATA = ELFDATA2LSB
    buf[6] = 1                        # EI_VERSION = EV_CURRENT

    # e_phoff at offset 32  (uint64 LE)
    struct.pack_into('<Q', buf, 32, e_phoff)
    # e_phentsize at offset 54 (uint16 LE)
    struct.pack_into('<H', buf, 54, e_phentsize)
    # e_phnum at offset 56     (uint16 LE)
    struct.pack_into('<H', buf, 56, e_phnum)

    # Program headers — each 56 bytes
    ph = bytearray()
    for seg in segments:
        ph_entry = bytearray(56)
        struct.pack_into('<I', ph_entry, 0, seg['p_type'])
        struct.pack_into('<I', ph_entry, 4, seg.get('p_flags', 0))
        vaddr = seg.get('vaddr', 0)
        struct.pack_into('<Q', ph_entry, 8, vaddr)    # p_offset
        struct.pack_into('<Q', ph_entry, 16, vaddr)   # p_vaddr
        struct.pack_into('<Q', ph_entry, 24, vaddr)   # p_paddr
        struct.pack_into('<Q', ph_entry, 32, seg.get('memsz', 0))  # p_filesz
        struct.pack_into('<Q', ph_entry, 40, seg.get('memsz', 0))  # p_memsz
        struct.pack_into('<Q', ph_entry, 48, seg.get('p_align', 0))  # p_align
        ph += ph_entry

    return bytes(buf) + bytes(ph)


def make_elf64(pt_load_aligns: list, gnu_relro_align=None, *,
               load_vaddr=0, load_memsz=0,
               relro_vaddr=0, relro_memsz=0) -> bytes:
    """Create minimal ELF64 bytes with the given PT_LOAD p_align values.

    When ``gnu_relro_align`` is not None a PT_GNU_RELRO header is appended.
    ``load_vaddr/load_memsz/relro_vaddr/relro_memsz`` let tests model the
    official RELRO end-address rule (VirtAddr + MemSiz).
    """
    segments = [
        {'p_type': 1, 'p_flags': 7, 'p_align': align,
         'vaddr': load_vaddr, 'memsz': load_memsz}
        for align in pt_load_aligns
    ]
    if gnu_relro_align is not None:
        segments.append({
            'p_type': 0x6474E552, 'p_flags': 4, 'p_align': gnu_relro_align,
            'vaddr': relro_vaddr, 'memsz': relro_memsz,
        })
    return make_elf64_segments(segments)


def make_compliant_elf64() -> bytes:
    """Synthetic 16KB-compliant .so: LOAD p_align 0x4000 and a 16KB-aligned
    GNU_RELRO end address (RELRO occupies the whole RW LOAD segment here)."""
    return make_elf64(
        [0x4000], gnu_relro_align=1,
        load_vaddr=0, load_memsz=0x8000,
        relro_vaddr=0, relro_memsz=0x8000,
    )


def _align8(value: int) -> int:
    return (value + 7) & ~7


def make_elf64_with_sections(segments: list, sections: list,
                             strip_section_names: bool = False) -> bytes:
    """Create a minimal ELF64 with program headers AND a section header table.

    ``sections``: ``[{name, flags, addr, size}]`` — real section headers so the
    RELRO 判定可以查看 SHF_ALLOC|SHF_WRITE 区间（可写数据是否落在危险窗口）。
    ``strip_section_names=True`` 复刻加固/加壳 .so（段名表为空），用于验证
    "段表不可信时标记为无法确认而不是误报风险" 的行为。
    """
    e_phoff = 64
    e_phentsize = 56
    e_phnum = len(segments)

    header = bytearray(64)
    header[0:4] = b'\x7fELF'
    header[4] = 2            # ELFCLASS64
    header[5] = 1            # ELFDATA2LSB
    header[6] = 1            # EV_CURRENT
    struct.pack_into('<Q', header, 32, e_phoff)
    struct.pack_into('<H', header, 54, e_phentsize)
    struct.pack_into('<H', header, 56, e_phnum)

    ph = bytearray()
    for seg in segments:
        entry = bytearray(56)
        struct.pack_into('<I', entry, 0, seg['p_type'])
        struct.pack_into('<I', entry, 4, seg.get('p_flags', 0))
        vaddr = seg.get('vaddr', 0)
        struct.pack_into('<Q', entry, 8, vaddr)
        struct.pack_into('<Q', entry, 16, vaddr)
        struct.pack_into('<Q', entry, 24, vaddr)
        struct.pack_into('<Q', entry, 32, seg.get('memsz', 0))
        struct.pack_into('<Q', entry, 40, seg.get('memsz', 0))
        struct.pack_into('<Q', entry, 48, seg.get('p_align', 0))
        ph += entry

    # shstrtab: 以空名开头，然后是各 section 名（strip 时只保留空名）
    shstr = bytearray(b'\x00')
    name_off = {}
    if strip_section_names:
        shstrtab_name_off = 0
    else:
        for sec in sections:
            name_off[sec['name']] = len(shstr)
            shstr += sec['name'].encode('ascii') + b'\x00'
        shstrtab_name_off = len(shstr)
        shstr += b'.shstrtab\x00'

    ph_end = 64 + e_phnum * e_phentsize
    shstr_off = ph_end
    shoff = _align8(shstr_off + len(shstr))
    shnum = len(sections) + 2  # section 0 (null) + .shstrtab + sections

    table = bytearray(shnum * 64)
    # index 1 = .shstrtab
    struct.pack_into('<I', table, 64, shstrtab_name_off)
    struct.pack_into('<I', table, 64 + 4, 3)  # SHT_STRTAB
    struct.pack_into('<Q', table, 64 + 24, shstr_off)
    struct.pack_into('<Q', table, 64 + 32, len(shstr))
    for i, sec in enumerate(sections):
        base = (i + 2) * 64
        struct.pack_into('<I', table, base,
                         name_off.get(sec['name'], 0) if not strip_section_names else 0)
        struct.pack_into('<I', table, base + 4, 1)  # SHT_PROGBITS
        struct.pack_into('<Q', table, base + 8, sec.get('flags', 0))
        struct.pack_into('<Q', table, base + 16, sec['addr'])
        struct.pack_into('<Q', table, base + 32, sec['size'])

    struct.pack_into('<Q', header, 40, shoff)   # e_shoff
    struct.pack_into('<H', header, 58, 64)      # e_shentsize
    struct.pack_into('<H', header, 60, shnum)   # e_shnum
    struct.pack_into('<H', header, 62, 1)       # e_shstrndx

    data = bytearray()
    data += header + ph + shstr
    while len(data) < shoff:
        data += b'\x00'
    data += table
    return bytes(data)



def make_elf32() -> bytes:
    """Create minimal ELF32 bytes (only header, no program headers).

    EI_CLASS = 1 triggers the "32bit" skip inside check_16kb_page_support.
    """
    buf = bytearray(52)          # ELF32 header size
    buf[0:4] = b'\x7fELF'
    buf[4] = 1                    # EI_CLASS = ELFCLASS32
    buf[5] = 1                    # ELFDATA2LSB
    buf[6] = 1                    # EV_CURRENT
    return bytes(buf)


# --- Android binary XML (AXML) fixture builder ------------------------------

AXML_ATTR_EXTRACT_NATIVE_LIBS = 0x010104EA


def _axml_string_pool(strings: list, utf8: bool = False) -> bytes:
    """Build a RES_STRING_POOL chunk (UTF-16 by default, UTF-8 when utf8=True)."""
    offsets = []
    payload = bytearray()

    def enc_len(n: int) -> bytes:
        if n < 0x80:
            return bytes([n])
        return bytes([0x80 | (n >> 8), n & 0xFF])

    for s in strings:
        offsets.append(len(payload))
        if utf8:
            raw = s.encode('utf-8')
            char_len = len(s.encode('utf-16-le')) // 2
            payload += enc_len(char_len) + enc_len(len(raw)) + raw + b'\x00'
        else:
            raw = s.encode('utf-16-le')
            payload += struct.pack('<H', len(raw) // 2) + raw + b'\x00\x00'
        while len(payload) % 4:  # 每个字符串 4 字节对齐（与 aapt 输出一致）
            payload += b'\x00'

    header_size = 28
    strings_start = header_size + 4 * len(strings)
    chunk = bytearray()
    chunk += struct.pack('<HHI', 0x0001, header_size, strings_start + len(payload))
    chunk += struct.pack('<IIIII', len(strings), 0, 0x100 if utf8 else 0,
                         strings_start, 0)
    for off in offsets:
        chunk += struct.pack('<I', off)
    chunk += payload
    return bytes(chunk)


def _axml_resource_map(resource_ids: list) -> bytes:
    """Build a RES_XML_RESOURCE_MAP chunk (string index → framework attr id)."""
    chunk = bytearray(struct.pack('<HHI', 0x0180, 8, 8 + 4 * len(resource_ids)))
    for rid in resource_ids:
        chunk += struct.pack('<I', rid)
    return bytes(chunk)


def _axml_start_element(name_index: int, attrs=()) -> bytes:
    """Build a RES_XML_START_ELEMENT chunk.

    ``attrs`` items are ``(ns_idx, name_idx, raw_idx, value_type, value_data)``.
    """
    chunk_size = 16 + 20 + 20 * len(attrs)
    chunk = bytearray(struct.pack('<HHI', 0x0102, 16, chunk_size))
    chunk += struct.pack('<II', 0, 0xFFFFFFFF)  # lineNumber, comment
    chunk += struct.pack('<IIHHHHHH', 0xFFFFFFFF, name_index, 20, 20,
                         len(attrs), 0, 0, 0)
    for ns, nm, raw, vtype, vdata in attrs:
        chunk += struct.pack('<IIIHBBI', ns, nm, raw, 8, 0, vtype, vdata)
    return bytes(chunk)


def _axml_end_element(name_index: int) -> bytes:
    return (
        struct.pack('<HHI', 0x0103, 16, 24)
        + struct.pack('<II', 0, 0xFFFFFFFF)
        + struct.pack('<II', 0xFFFFFFFF, name_index)
    )


def make_manifest_axml(extract_native_libs=None, use_resource_id: bool = True,
                       utf8: bool = False) -> bytes:
    """Build a minimal binary AndroidManifest.xml with an <application> element.

    The attribute is emitted either as a framework resource id (aapt-style,
    name string empty + RES_XML_RESOURCE_MAP) or as a plain string name, to
    cover both lookup paths in the parser. ``utf8`` switches the string pool
    to the UTF-8 encoding used by aapt2.
    """
    strings = ['manifest', 'application']
    if use_resource_id:
        strings.insert(0, '')  # 空名字，靠 resource map 识别
        attr_name_index = 0
    else:
        strings.append('extractNativeLibs')
        attr_name_index = len(strings) - 1

    attrs = []
    if extract_native_libs is not None:
        attrs.append((0xFFFFFFFF, attr_name_index, 0xFFFFFFFF, 0x12,
                      1 if extract_native_libs else 0))

    chunks = _axml_string_pool(strings, utf8=utf8)
    if use_resource_id:
        chunks += _axml_resource_map([AXML_ATTR_EXTRACT_NATIVE_LIBS])
    chunks += _axml_start_element(strings.index('manifest'))
    chunks += _axml_start_element(strings.index('application'), attrs)
    chunks += _axml_end_element(strings.index('application'))
    chunks += _axml_end_element(strings.index('manifest'))

    total = 8 + len(chunks)
    return struct.pack('<HHI', 0x0003, 8, total) + chunks


# --- Stored-entry APK builder (controls local data offsets) -----------------

def make_stored_apk(entries: list) -> str:
    """Create a temp zip whose STORED entry data offsets are exactly controlled.

    ``entries``: list of dicts with keys:
    - ``name`` (str), ``data`` (bytes)
    - ``align`` (int, default 4), ``remainder`` (int, default 0): for STORED
      entries the local extra field is sized so the data offset ≡ remainder
      (mod align) — mirrors a zipaligned / intentionally misaligned APK.
    - ``compress`` (bool, default False): DEFLATE instead of STORED.

    Returns the temp file path.
    """
    local_parts = bytearray()
    central_records = []

    for entry in entries:
        name = entry['name'].encode('utf-8')
        data = entry['data']
        compress = entry.get('compress', False)
        method = 8 if compress else 0
        payload = zlib.compress(data) if compress else data

        header_offset = len(local_parts)
        extra_len = 0
        if method == 0:
            align = entry.get('align', 4)
            remainder = entry.get('remainder', 0)
            base = header_offset + 30 + len(name)
            extra_len = (remainder - base) % align
        extra = b'\x00' * extra_len

        crc = zlib.crc32(data) & 0xFFFFFFFF
        local_parts += struct.pack(
            '<IHHHHHIIIHH', 0x04034B50, 20, 0, method, 0, 0,
            crc, len(payload), len(data), len(name), extra_len,
        ) + name + extra + payload

        if method == 0:
            data_offset = header_offset + 30 + len(name) + extra_len
            assert data_offset % align == remainder % align, (
                'fixture offset mispredicted', data_offset, align, remainder)

        central_records.append(
            (name, extra_len, method, crc, len(payload), len(data), header_offset)
        )

    cd_offset = len(local_parts)
    central_parts = bytearray()
    for name, extra_len, method, crc, comp_size, raw_size, header_offset in central_records:
        central_parts += struct.pack(
            '<IHHHHHHIIIHHHHHII', 0x02014B50, 20, 20, 0, method, 0, 0,
            crc, comp_size, raw_size, len(name), extra_len, 0, 0, 0, 0,
            header_offset,
        ) + name + b'\x00' * extra_len

    eocd = struct.pack(
        '<IHHHHIIH', 0x06054B50, 0, 0, len(central_records),
        len(central_records), len(central_parts), cd_offset, 0,
    )

    fd, path = tempfile.mkstemp(suffix='.apk')
    os.close(fd)
    with open(path, 'wb') as f:
        f.write(bytes(local_parts) + bytes(central_parts) + eocd)
    return path


# ---------------------------------------------------------------------------
# enumerate_so_files
# ---------------------------------------------------------------------------

class TestEnumerateSoFiles:
    def test_multi_arch(self):
        """APK with lib/arm64-v8a/liba.so, lib/armeabi-v7a/liba.so,
        lib/armeabi-v7a/libb.so → grouped correctly."""
        path = None
        try:
            path = make_apk({
                'lib/arm64-v8a/liba.so':        (b'fake', 8),
                'lib/armeabi-v7a/liba.so':      (b'fake', 8),
                'lib/armeabi-v7a/libb.so':      (b'fake', 8),
            })
            result = enumerate_so_files(path)
            assert result == {
                'arm64-v8a':     ['liba.so'],
                'armeabi-v7a':   ['liba.so', 'libb.so'],
            }
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_empty(self):
        """APK with zero lib/ entries → {}."""
        path = None
        try:
            path = make_apk({
                'assets/icon.png': (b'png', 0),
                'classes.dex':     (b'dex', 8),
            })
            result = enumerate_so_files(path)
            assert result == {}
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_nonexistent(self):
        """Nonexistent path → {}."""
        result = enumerate_so_files('/no/such/path.apk')
        assert result == {}


# ---------------------------------------------------------------------------
# compare_so_across_arches
# ---------------------------------------------------------------------------

class TestCompareSoAcrossArches:
    def test_single_arch(self):
        """One architecture → {"single_arch": True}."""
        result = compare_so_across_arches({
            'arm64-v8a': ['liba.so', 'libb.so'],
        })
        assert result == {'single_arch': True}

    def test_multi_arch_missing(self):
        """arm64 has liba.so only, armeabi-v7a has liba.so + libb.so
        → arm64 missing = ['libb.so']."""
        result = compare_so_across_arches({
            'arm64-v8a':     ['liba.so'],
            'armeabi-v7a':   ['liba.so', 'libb.so'],
        })
        assert result['baseline'] == ['liba.so', 'libb.so']
        assert result['arches']['arm64-v8a']['missing'] == ['libb.so']
        assert result['arches']['armeabi-v7a']['missing'] == []

    def test_empty(self):
        """Empty so_map → {"no_native": True}."""
        result = compare_so_across_arches({})
        assert result == {'no_native': True}


# ---------------------------------------------------------------------------
# analyze_compression
# ---------------------------------------------------------------------------

class TestAnalyzeCompression:
    def test_mixed(self):
        """assets/a.txt (stored), lib/liba.so (deflated), classes.dex (deflated)."""
        path = None
        try:
            path = make_apk({
                'assets/a.txt':                (b'hello', 0),  # stored
                'lib/armeabi-v7a/liba.so':     (b'fake', 8),   # deflated
                'classes.dex':                 (b'dex', 8),    # deflated
            })
            result = analyze_compression(path)
            assert result['assets']['stored'] == 1
            assert result['assets']['deflated'] == 0
            assert result['lib']['stored'] == 0
            assert result['lib']['deflated'] == 1
            assert result['dex']['stored'] == 0
            assert result['dex']['deflated'] == 1
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_multidex(self):
        """classes.dex, classes2.dex, classes3.dex → dex group aggregates all 3."""
        path = None
        try:
            path = make_apk({
                'classes.dex':   (b'd1', 8),
                'classes2.dex':  (b'd2', 8),
                'classes3.dex':  (b'd3', 8),
            })
            result = analyze_compression(path)
            assert result['dex']['stored'] == 0
            assert result['dex']['deflated'] == 3
            # other categories should be zero
            assert result['assets']['stored'] == 0
            assert result['assets']['deflated'] == 0
            assert result['lib']['stored'] == 0
            assert result['lib']['deflated'] == 0
        finally:
            if path and os.path.exists(path):
                os.unlink(path)


# ---------------------------------------------------------------------------
# check_16kb_page_support
# ---------------------------------------------------------------------------

class TestCheck16kbPageSupport:
    def test_positive(self):
        """Single arm64-v8a .so with p_align=0x4000 → supports_16kb=True."""
        path = None
        try:
            elf = make_elf64([0x4000])  # 16384
            path = make_apk({
                'lib/arm64-v8a/libtest.so': (elf, 8),
            })
            result = check_16kb_page_support(path)
            so_result = result['arm64-v8a']['libtest.so']
            assert so_result['supports_16kb'] is True
            assert so_result['max_align'] == 0x4000
            assert so_result['pt_load_aligns'] == [0x4000]
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_negative(self):
        """Single arm64-v8a .so with p_align=0x1000 → supports_16kb=False."""
        path = None
        try:
            elf = make_elf64([0x1000])  # 4096
            path = make_apk({
                'lib/arm64-v8a/libtest.so': (elf, 8),
            })
            result = check_16kb_page_support(path)
            so_result = result['arm64-v8a']['libtest.so']
            assert so_result['supports_16kb'] is False
            assert so_result['max_align'] == 0x1000
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_multi_segment(self):
        """One .so with 2 PT_LOAD: first 0x4000, second 0x1000
        → supports_16kb=False (ALL must be >= 16KB)."""
        path = None
        try:
            elf = make_elf64([0x4000, 0x1000])
            path = make_apk({
                'lib/arm64-v8a/libmulti.so': (elf, 8),
            })
            result = check_16kb_page_support(path)
            so_result = result['arm64-v8a']['libmulti.so']
            assert so_result['supports_16kb'] is False
            assert so_result['pt_load_aligns'] == [0x4000, 0x1000]
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_skip_non_elf(self):
        """APK with a valid .so + a non-ELF fake.so → fake.so appears in skipped."""
        path = None
        try:
            elf = make_elf64([0x4000])
            path = make_apk({
                'lib/arm64-v8a/libgood.so':  (elf, 8),
                'lib/arm64-v8a/fake.so':     (b'not an elf', 8),
            })
            result = check_16kb_page_support(path)
            # Valid arm64-v8a entry present
            assert 'arm64-v8a' in result
            assert 'libgood.so' in result['arm64-v8a']
            # Skipped list present
            skipped = result.get('skipped', [])
            fake_entries = [s for s in skipped
                            if s['file'] == 'fake.so'
                            and s['arch'] == 'arm64-v8a'
                            and s['reason'] == 'non_elf']
            assert len(fake_entries) == 1, f'skipped={skipped!r}'
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_skip_32bit(self):
        """APK with a valid .so + an ELF32 .so → ELF32 file appears in skipped."""
        path = None
        try:
            elf64 = make_elf64([0x4000])
            elf32 = make_elf32()
            path = make_apk({
                'lib/arm64-v8a/libgood.so': (elf64, 8),
                'lib/arm64-v8a/lib32.so':    (elf32, 8),
            })
            result = check_16kb_page_support(path)
            assert 'arm64-v8a' in result
            assert 'libgood.so' in result['arm64-v8a']
            skipped = result.get('skipped', [])
            entry = [s for s in skipped
                     if s['file'] == 'lib32.so'
                     and s['arch'] == 'arm64-v8a'
                     and s['reason'] == '32bit']
            assert len(entry) == 1, f'skipped={skipped!r}'
        finally:
            if path and os.path.exists(path):
                os.unlink(path)


# ---------------------------------------------------------------------------
# GNU_RELRO 16KB rule (new 16KB check position)
#
# https://developer.android.com/guide/practices/page-sizes#relro-flag
# LLD always emits GNU_RELRO p_align = 1, so the official rule is about the
# segment's END address, not p_align.
# ---------------------------------------------------------------------------

class TestGnuRelroAlignment:
    def _check(self, elf: bytes) -> dict:
        path = None
        try:
            path = make_apk({'lib/arm64-v8a/libtest.so': (elf, 8)})
            result = check_16kb_page_support(path)
            return result['arm64-v8a']['libtest.so']
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    @staticmethod
    def _elf(load_align, load_vaddr, load_memsz, relro_vaddr, relro_memsz,
             relro_align=1) -> bytes:
        return make_elf64(
            [load_align], gnu_relro_align=relro_align,
            load_vaddr=load_vaddr, load_memsz=load_memsz,
            relro_vaddr=relro_vaddr, relro_memsz=relro_memsz,
        )

    def test_relro_p_align_one_is_not_a_failure(self):
        """Real toolchains emit GNU_RELRO p_align=1 — it must not fail by itself."""
        so = self._check(self._elf(0x4000, 0x0, 0x8000, 0x0, 0x8000))
        assert so['gnu_relro_align'] == 1
        assert so['gnu_relro_present'] is True
        assert so['relro_ok'] is True
        assert so['supports_16kb'] is True

    def test_relro_end_aligned_passes(self):
        """Doc example 2: RELRO end 0xdfaf0 + 0x510 = 0xE0000 (16KB aligned)."""
        so = self._check(self._elf(0x4000, 0xDFAF0, 0x03510, 0xDFAF0, 0x00510))
        assert so['gnu_relro_end_aligned'] is True
        assert so['relro_ok'] is True
        assert so['supports_16kb'] is True

    def test_relro_end_unaligned_with_writable_data_fails(self):
        """Doc example 1: RELRO end 0xE1000, containing LOAD ends 0xE4000."""
        so = self._check(self._elf(0x4000, 0xDFAF0, 0x04510, 0xDFAF0, 0x01510))
        assert so['load_ok'] is True
        assert so['gnu_relro_end_aligned'] is False
        assert so['relro_ok'] is False
        assert so['supports_16kb'] is False

    def test_relro_fills_containing_load_segment_passes(self):
        """Doc example 4: RELRO end unaligned but no writable data follows it."""
        so = self._check(self._elf(0x4000, 0x4680, 0x0980, 0x4680, 0x0980))
        assert so['gnu_relro_end_aligned'] is False
        assert so['relro_ok'] is True
        assert so['supports_16kb'] is True

    def test_no_relro_segment_is_ok(self):
        so = self._check(make_elf64([0x4000]))
        assert so['supports_16kb'] is True
        assert so['gnu_relro_present'] is False
        assert so['gnu_relro_align'] == 0
        assert so['relro_ok'] is True

    def test_load_bad_relro_ok(self):
        so = self._check(self._elf(0x1000, 0x0, 0x8000, 0x0, 0x8000))
        assert so['supports_16kb'] is False
        assert so['load_ok'] is False
        assert so['relro_ok'] is True

    def test_relro_end_unaligned_but_no_writable_segment_in_window_passes(self):
        """场景同 libdatastore：RELRO 结束 0x6000，危险窗口内没有可写 LOAD。

        RELRO 段按 4KB 页对齐（旧 NDK 常见），旧规则"RELRO 结尾必须等于 LOAD
        结尾"会误报；按 linker 的真实 mprotect 范围，窗口 [0x6000,0x8000) 是
        段间空隙，没有可写数据 → 无风险。
        """
        elf = make_elf64_segments([
            {'p_type': 1, 'p_flags': 5, 'p_align': 0x4000, 'vaddr': 0, 'memsz': 0x51C0},
            {'p_type': 1, 'p_flags': 6, 'p_align': 0x4000, 'vaddr': 0x51C0, 'memsz': 0x268},
            {'p_type': 0x6474E552, 'p_flags': 4, 'p_align': 1, 'vaddr': 0x51C0, 'memsz': 0xE40},
        ])
        so = self._check(elf)
        assert so['gnu_relro_end_aligned'] is False
        assert so['relro_status'] == 'ok'
        assert so['relro_ok'] is True
        assert so['supports_16kb'] is True

    @staticmethod
    def _window_elf(writable_sections, strip_names=False) -> bytes:
        """RELRO 结束 0x41000 未对齐，危险窗口 [0x41000,0x44000) 被 RW LOAD 覆盖。"""
        return make_elf64_with_sections(
            [
                {'p_type': 1, 'p_flags': 7, 'p_align': 0x4000,
                 'vaddr': 0, 'memsz': 0x30000},
                {'p_type': 1, 'p_flags': 6, 'p_align': 0x4000,
                 'vaddr': 0x30000, 'memsz': 0x20000},
                {'p_type': 0x6474E552, 'p_flags': 4, 'p_align': 1,
                 'vaddr': 0x3FFF0, 'memsz': 0x1010},
            ],
            writable_sections,
            strip_section_names=strip_names,
        )

    def test_relro_window_covered_by_writable_load_without_writable_sections_passes(self):
        """危险窗口落在可写 LOAD 内，但段表显示窗口内没有可写段（只是填充）→ 通过。"""
        so = self._check(self._window_elf(
            [{'name': '.got', 'flags': 0x3, 'addr': 0x40000, 'size': 0x100}]
        ))
        assert so['relro_status'] == 'ok'
        assert so['supports_16kb'] is True

    def test_relro_writable_section_in_window_fails(self):
        """危险窗口内有可写段（.data/.bss）→ 运行期崩溃风险，判定不支持。"""
        so = self._check(self._window_elf([
            {'name': '.data', 'flags': 0x3, 'addr': 0x41000, 'size': 0x100},
            {'name': '.bss', 'flags': 0x3, 'addr': 0x42000, 'size': 0x10},
        ]))
        assert so['relro_status'] == 'risk'
        assert so['relro_ok'] is False
        assert so['relro_risk_sections'] == ['.data', '.bss']
        assert so['supports_16kb'] is False

    def test_relro_stripped_section_names_is_unknown(self):
        """段名被剥离（加固/加壳）→ 无法确认，不误报为风险。"""
        so = self._check(self._window_elf(
            [{'name': '.data', 'flags': 0x3, 'addr': 0x41000, 'size': 0x100}],
            strip_names=True,
        ))
        assert so['relro_status'] == 'unknown'
        assert so['relro_ok'] is None
        assert so['supports_16kb'] is True
        assert so['relro_risk_sections'] == []


# ---------------------------------------------------------------------------
# check_manifest_native_extract (AXML)
# ---------------------------------------------------------------------------

class TestCheckManifestNativeExtract:
    def _check(self, axml: bytes) -> dict:
        path = None
        try:
            path = make_apk({'AndroidManifest.xml': (axml, 8)})
            return check_manifest_native_extract(path)
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_false_via_resource_id(self):
        result = self._check(make_manifest_axml(False))
        assert result['present'] is True
        assert result['extract_native_libs'] is False
        assert result['ok'] is True

    def test_true_fails(self):
        result = self._check(make_manifest_axml(True))
        assert result['present'] is True
        assert result['extract_native_libs'] is True
        assert result['ok'] is False

    def test_absent_is_ok(self):
        result = self._check(make_manifest_axml(None))
        assert result['present'] is False
        assert result['extract_native_libs'] is None
        assert result['ok'] is True

    def test_name_based_attribute(self):
        result = self._check(make_manifest_axml(False, use_resource_id=False))
        assert result['present'] is True
        assert result['extract_native_libs'] is False

    def test_utf8_string_pool(self):
        """aapt2 emits UTF-8 string pools; exercise that decoder branch."""
        result = self._check(make_manifest_axml(False, utf8=True))
        assert result['present'] is True
        assert result['extract_native_libs'] is False
        assert result['ok'] is True

    def test_missing_manifest_fails_closed(self):
        path = None
        try:
            path = make_apk({'classes.dex': (b'dex', 8)})
            result = check_manifest_native_extract(path)
            assert result['present'] is False
            assert result['ok'] is False
            assert result.get('error') == 'manifest_missing'
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_non_axml_manifest_fails_closed(self):
        result = self._check(b'not a binary xml manifest')
        assert result['ok'] is False
        assert result.get('error') == 'not_axml'

    def test_nonexistent_apk_fails_closed(self):
        assert check_manifest_native_extract('/no/such/path.apk') == {
            'present': False,
            'extract_native_libs': None,
            'ok': False,
            'error': 'apk_missing',
        }


# ---------------------------------------------------------------------------
# check_apk_alignment (zipalign equivalent)
# ---------------------------------------------------------------------------

class TestCheckApkAlignment:
    def test_aligned_so_and_dex(self):
        path = None
        try:
            path = make_stored_apk([
                {'name': 'lib/arm64-v8a/liba.so', 'data': b'x' * 32,
                 'align': 16384, 'remainder': 0},
                {'name': 'classes.dex', 'data': b'y' * 16,
                 'align': 4, 'remainder': 0},
            ])
            result = check_apk_alignment(path)
            assert result['ok'] is True
            assert result['checked'] == 2
            assert result['so_checked'] == 1
            assert result['compressed_so'] == 0
            assert result['misaligned'] == []
            assert result['misaligned_count'] == 0
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_so_not_16kb_aligned(self):
        path = None
        try:
            path = make_stored_apk([
                {'name': 'lib/arm64-v8a/liba.so', 'data': b'x' * 32,
                 'align': 16384, 'remainder': 4096},
            ])
            result = check_apk_alignment(path)
            assert result['ok'] is False
            assert result['misaligned_count'] == 1
            entry = result['misaligned'][0]
            assert entry['entry'] == 'lib/arm64-v8a/liba.so'
            assert entry['required'] == 16384
            assert entry['offset'] % 16384 == 4096
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_stored_entry_not_4byte_aligned(self):
        path = None
        try:
            path = make_stored_apk([
                {'name': 'assets/a.txt', 'data': b'x' * 8,
                 'align': 4, 'remainder': 2},
            ])
            result = check_apk_alignment(path)
            assert result['ok'] is False
            assert result['misaligned'][0]['required'] == 4
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_compressed_so_is_not_16kb_ready(self):
        path = None
        try:
            path = make_stored_apk([
                {'name': 'lib/arm64-v8a/liba.so', 'data': b'z' * 64,
                 'compress': True},
                {'name': 'classes.dex', 'data': b'd' * 16,
                 'align': 4, 'remainder': 0},
            ])
            result = check_apk_alignment(path)
            assert result['compressed_so'] == 1
            assert result['so_checked'] == 0
            assert result['ok'] is False
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_zipfile_written_apk_smoke(self):
        path = None
        try:
            path = make_apk({'classes.dex': (b'x' * 8, 0)})  # stored by zipfile
            result = check_apk_alignment(path)
            assert result['checked'] == 1
        finally:
            if path and os.path.exists(path):
                os.unlink(path)


# ---------------------------------------------------------------------------
# check_16kb_page_support — aggregate (manifest + ELF + zipalign)
# ---------------------------------------------------------------------------

class TestCheck16kbPageSupportComposite:
    def test_supported(self):
        elf = make_compliant_elf64()
        path = None
        try:
            path = make_stored_apk([
                {'name': 'AndroidManifest.xml',
                 'data': make_manifest_axml(False), 'align': 4, 'remainder': 0},
                {'name': 'lib/arm64-v8a/liba.so', 'data': elf,
                 'align': 16384, 'remainder': 0},
            ])
            result = check_16kb_page_support(path)
            assert result['no_64bit_native'] is False
            assert result['supported'] is True
            assert result['manifest']['ok'] is True
            assert result['zipalign']['ok'] is True
            assert result['arm64-v8a']['liba.so']['supports_16kb'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_not_supported_when_extract_native_libs_true(self):
        elf = make_compliant_elf64()
        path = None
        try:
            path = make_stored_apk([
                {'name': 'AndroidManifest.xml',
                 'data': make_manifest_axml(True), 'align': 4, 'remainder': 0},
                {'name': 'lib/arm64-v8a/liba.so', 'data': elf,
                 'align': 16384, 'remainder': 0},
            ])
            result = check_16kb_page_support(path)
            assert result['manifest']['extract_native_libs'] is True
            assert result['manifest']['ok'] is False
            assert result['supported'] is False
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_not_supported_when_apk_misaligned(self):
        elf = make_compliant_elf64()
        path = None
        try:
            path = make_stored_apk([
                {'name': 'AndroidManifest.xml',
                 'data': make_manifest_axml(False), 'align': 4, 'remainder': 0},
                {'name': 'lib/arm64-v8a/liba.so', 'data': elf,
                 'align': 16384, 'remainder': 4096},
            ])
            result = check_16kb_page_support(path)
            assert result['zipalign']['ok'] is False
            assert result['supported'] is False
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_no_64bit_native_still_checks_package(self):
        path = None
        try:
            path = make_stored_apk([
                {'name': 'AndroidManifest.xml',
                 'data': make_manifest_axml(False), 'align': 4, 'remainder': 0},
                {'name': 'lib/armeabi-v7a/liba.so', 'data': b'fake',
                 'align': 16384, 'remainder': 0},
            ])
            result = check_16kb_page_support(path)
            assert result['no_64bit_native'] is True
            assert 'arm64-v8a' not in result
            assert result['manifest']['ok'] is True
            assert result['supported'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    @staticmethod
    def _relro_risk_elf() -> bytes:
        return make_elf64_with_sections(
            [
                {'p_type': 1, 'p_flags': 7, 'p_align': 0x4000,
                 'vaddr': 0, 'memsz': 0x30000},
                {'p_type': 1, 'p_flags': 6, 'p_align': 0x4000,
                 'vaddr': 0x30000, 'memsz': 0x20000},
                {'p_type': 0x6474E552, 'p_flags': 4, 'p_align': 1,
                 'vaddr': 0x3FFF0, 'memsz': 0x1010},
            ],
            [{'name': '.data', 'flags': 0x3, 'addr': 0x41000, 'size': 0x100}],
        )

    def _apk_with_so(self, elf: bytes) -> str:
        return make_stored_apk([
            {'name': 'AndroidManifest.xml',
             'data': make_manifest_axml(False), 'align': 4, 'remainder': 0},
            {'name': 'lib/arm64-v8a/librisk.so', 'data': elf,
             'align': 16384, 'remainder': 0},
        ])

    def test_relro_risk_reported_separately_from_gate(self):
        """RELRO 运行风险不阻断 gate_ok（Play 上传门禁），但 supported=False。"""
        path = None
        try:
            path = self._apk_with_so(self._relro_risk_elf())
            result = check_16kb_page_support(path)
            assert result['gate_ok'] is True
            assert result['supported'] is False
            assert [item['file'] for item in result['relro_risk']] == ['librisk.so']
            assert result['relro_risk'][0]['sections'] == ['.data']
            assert result['relro_unknown'] == []
            assert result['zipalign']['ok'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_relro_unknown_does_not_fail_supported(self):
        """段表被剥离无法确认时：gate_ok/supported 均通过，但单独列出 unknown。"""
        elf = make_elf64_with_sections(
            [
                {'p_type': 1, 'p_flags': 7, 'p_align': 0x4000,
                 'vaddr': 0, 'memsz': 0x30000},
                {'p_type': 1, 'p_flags': 6, 'p_align': 0x4000,
                 'vaddr': 0x30000, 'memsz': 0x20000},
                {'p_type': 0x6474E552, 'p_flags': 4, 'p_align': 1,
                 'vaddr': 0x3FFF0, 'memsz': 0x1010},
            ],
            [{'name': '.data', 'flags': 0x3, 'addr': 0x41000, 'size': 0x100}],
            strip_section_names=True,
        )
        path = None
        try:
            path = self._apk_with_so(elf)
            result = check_16kb_page_support(path)
            assert result['gate_ok'] is True
            assert result['supported'] is True
            assert [item['file'] for item in result['relro_unknown']] == ['librisk.so']
            assert result['relro_risk'] == []
        finally:
            if path and os.path.exists(path):
                os.unlink(path)


# ---------------------------------------------------------------------------
# parse_bundle_config (bundletool dump config JSON)
# ---------------------------------------------------------------------------

class TestParseBundleConfig:
    @staticmethod
    def _json(enabled=True, alignment='PAGE_ALIGNMENT_16K', version='1.18.1'):
        uncompress = {}
        if enabled is not None:
            uncompress['enabled'] = enabled
        if alignment is not None:
            uncompress['alignment'] = alignment
        payload = {'optimizations': {'uncompressNativeLibraries': uncompress}}
        if version is not None:
            payload['bundletool'] = {'version': version}
        return json.dumps(payload)

    def test_16k_ok(self):
        result = parse_bundle_config(self._json(True, 'PAGE_ALIGNMENT_16K'))
        assert result['alignment'] == 'PAGE_ALIGNMENT_16K'
        assert result['alignment_source'] == 'declared'
        assert result['uncompress_enabled'] is True
        assert result['ok'] is True

    def test_4k_fails(self):
        result = parse_bundle_config(self._json(True, 'PAGE_ALIGNMENT_4K'))
        assert result['alignment'] == 'PAGE_ALIGNMENT_4K'
        assert result['zip_alignment_16k'] is False
        assert result['ok'] is False

    def test_64k_ok(self):
        result = parse_bundle_config(self._json(True, 'PAGE_ALIGNMENT_64K'))
        assert result['zip_alignment_16k'] is True
        assert result['ok'] is True

    def test_alignment_missing_new_bundletool_defaults_to_16k(self):
        # bundletool 1.17.0 起默认页对齐为 16KB：缺省 alignment 不等于 4K
        result = parse_bundle_config(self._json(True, None, '1.17.0'))
        assert result['alignment'] == 'PAGE_ALIGNMENT_16K'
        assert result['alignment_source'] == 'default_by_bundletool_version'
        assert result['ok'] is True

    def test_alignment_missing_old_bundletool_defaults_to_4k(self):
        result = parse_bundle_config(self._json(True, None, '1.15.6'))
        assert result['alignment'] == 'PAGE_ALIGNMENT_4K'
        assert result['alignment_source'] == 'default_by_bundletool_version'
        assert result['ok'] is False

    def test_alignment_unspecified_uses_version_default(self):
        result = parse_bundle_config(
            self._json(True, 'PAGE_ALIGNMENT_UNSPECIFIED', '1.18.0')
        )
        assert result['alignment'] == 'PAGE_ALIGNMENT_16K'
        assert result['ok'] is True

    def test_version_missing_defaults_to_current_tool(self):
        result = parse_bundle_config(self._json(True, None, None))
        assert result['bundletool_version'] is None
        assert result['alignment'] == 'PAGE_ALIGNMENT_16K'
        assert result['alignment_source'] == 'default_current_tool'
        assert result['ok'] is True

    def test_message_missing_defaults_to_uncompressed(self):
        # 消息不存在时按版本默认值：bundletool >= 0.6.0 默认启用未压缩原生库
        result = parse_bundle_config(
            '{"bundletool":{"version":"1.18.1"},"optimizations":{}}'
        )
        assert result['uncompress_enabled'] is True
        assert result['uncompress_source'] == 'default'
        assert result['ok'] is True

    def test_empty_message_is_compressed_and_zip_not_required(self):
        # JsonFormat 省略 false：消息存在但没有 enabled ⇒ 未启用（压缩）
        result = parse_bundle_config(
            '{"bundletool":{"version":"1.15.6"},'
            '"optimizations":{"uncompressNativeLibraries":{}}}'
        )
        assert result['uncompress_enabled'] is False
        assert result['uncompress_source'] == 'declared'
        assert result['zip_alignment_16k'] is False
        assert result['ok'] is True  # 压缩原生库在安装时解压，不需要 ZIP 对齐

    def test_uncompress_disabled_ok(self):
        result = parse_bundle_config(self._json(False, 'PAGE_ALIGNMENT_4K'))
        assert result['uncompress_enabled'] is False
        assert result['ok'] is True

    def test_declared_4k_wins_over_version_default(self):
        # 显式声明的 4K 优先于新版本的 16K 默认值
        result = parse_bundle_config(self._json(True, 'PAGE_ALIGNMENT_4K', '1.18.1'))
        assert result['alignment'] == 'PAGE_ALIGNMENT_4K'
        assert result['alignment_source'] == 'declared'
        assert result['ok'] is False

    def test_warning_prefix_tolerated(self):
        text = 'Picked up JAVA_TOOL_OPTIONS: -Dfile.encoding=UTF-8\n' + self._json()
        result = parse_bundle_config(text)
        assert result['ok'] is True

    def test_invalid_json(self):
        result = parse_bundle_config('not json')
        assert result['ok'] is False
        assert result['error'] == 'invalid_json'

    def test_empty(self):
        result = parse_bundle_config('')
        assert result['ok'] is False
        assert result['error'] == 'empty_config'


# ---------------------------------------------------------------------------
# check_16kb_page_support — AAB container
# ---------------------------------------------------------------------------

def _bundle_16k() -> dict:
    return parse_bundle_config(
        '{"bundletool":{"version":"1.18.1"},'
        '"optimizations":{"uncompressNativeLibraries":'
        '{"enabled":true,"alignment":"PAGE_ALIGNMENT_16K"}}}'
    )


def _bundle_4k() -> dict:
    return parse_bundle_config(
        '{"bundletool":{"version":"1.15.6"},'
        '"optimizations":{"uncompressNativeLibraries":'
        '{"enabled":true,"alignment":"PAGE_ALIGNMENT_4K"}}}'
    )


def _bundle_4k_by_default() -> dict:
    """旧 bundletool 构建、未显式声明对齐 ⇒ 生效 4K。"""
    return parse_bundle_config(
        '{"bundletool":{"version":"1.15.6"},'
        '"optimizations":{"uncompressNativeLibraries":{"enabled":true}}}'
    )


def _bundle_compressed() -> dict:
    return parse_bundle_config(
        '{"bundletool":{"version":"1.15.6"},'
        '"optimizations":{"uncompressNativeLibraries":{}}}'
    )


class TestCheck16kbAabSupport:
    def _aab(self, elf: bytes, extra_entries=None) -> str:
        entries = {
            'base/lib/arm64-v8a/liba.so': (elf, 8),
            'BundleConfig.pb': (b'', 0),  # 占位，解析由 bundletool 完成
        }
        if extra_entries:
            entries.update(extra_entries)
        return make_apk(entries)

    def test_supported_with_16k_bundle_config(self):
        path = None
        try:
            path = self._aab(make_compliant_elf64())
            result = check_16kb_page_support(
                path, container='aab', bundle_config=_bundle_16k()
            )
            assert result['container'] == 'aab'
            assert result['no_64bit_native'] is False
            assert result['supported'] is True
            assert result['bundle']['ok'] is True
            assert result['bundle']['applied'] is True
            assert result['manifest'] is None
            assert result['zipalign'] is None
            assert result['arm64-v8a']['liba.so']['supports_16kb'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_4k_bundle_config_unsupported(self):
        path = None
        try:
            path = self._aab(make_compliant_elf64())
            result = check_16kb_page_support(
                path, container='aab', bundle_config=_bundle_4k()
            )
            assert result['bundle']['ok'] is False
            assert result['bundle']['applied'] is True
            assert result['supported'] is False
            # ELF 本身仍通过
            assert result['arm64-v8a']['liba.so']['supports_16kb'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_old_bundletool_default_alignment_unsupported(self):
        # 旧 bundletool 构建且未显式配置对齐：生成 APK 时按 4K 对齐 ⇒ 不通过
        path = None
        try:
            path = self._aab(make_compliant_elf64())
            result = check_16kb_page_support(
                path, container='aab', bundle_config=_bundle_4k_by_default()
            )
            assert result['bundle']['alignment'] == 'PAGE_ALIGNMENT_4K'
            assert result['supported'] is False
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_compressed_native_libs_zip_alignment_not_required(self):
        # 压缩原生库在安装时解压，不需要 ZIP 对齐；ELF 16KB 对齐即视为兼容
        path = None
        try:
            path = self._aab(make_compliant_elf64())
            result = check_16kb_page_support(
                path, container='aab', bundle_config=_bundle_compressed()
            )
            assert result['bundle']['uncompress_enabled'] is False
            assert result['bundle']['ok'] is True
            assert result['supported'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_no_64bit_native_supported_with_4k_bundle_config(self):
        # 回归：纯 Java/Kotlin 应用（无 64 位 .so）天然兼容 16KB，
        # 不能因为 BundleConfig 的对齐是 4K 就判不通过。
        path = None
        try:
            path = make_apk({'BundleConfig.pb': (b'', 0)})
            result = check_16kb_page_support(
                path, container='aab', bundle_config=_bundle_4k()
            )
            assert result['no_64bit_native'] is True
            assert result['bundle']['ok'] is False
            assert result['bundle']['applied'] is False
            assert result['supported'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_no_64bit_native_supported_without_bundle_config(self):
        # 无原生库时即使 BundleConfig 读取失败也不该判不通过
        path = None
        try:
            path = make_apk({'BundleConfig.pb': (b'', 0)})
            result = check_16kb_page_support(path, container='aab')
            assert result['bundle']['error'] == 'bundle_config_unavailable'
            assert result['bundle']['applied'] is False
            assert result['supported'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_bad_elf_unsupported(self):
        path = None
        try:
            path = self._aab(make_elf64([0x1000]))
            result = check_16kb_page_support(
                path, container='aab', bundle_config=_bundle_16k()
            )
            assert result['arm64-v8a']['liba.so']['supports_16kb'] is False
            assert result['supported'] is False
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_missing_bundle_config_fails_closed(self):
        path = None
        try:
            path = self._aab(make_compliant_elf64())
            result = check_16kb_page_support(path, container='aab')
            assert result['bundle']['ok'] is False
            assert result['bundle']['error'] == 'bundle_config_unavailable'
            assert result['bundle']['applied'] is True
            assert result['supported'] is False
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_apk_style_lib_entry_ignored_in_aab(self):
        path = None
        try:
            path = make_apk({
                'lib/arm64-v8a/libapk.so': (make_compliant_elf64(), 8),
                'BundleConfig.pb': (b'', 0),
            })
            result = check_16kb_page_support(
                path, container='aab', bundle_config=_bundle_16k()
            )
            assert result['no_64bit_native'] is True
            assert 'arm64-v8a' not in result
            assert result['bundle']['applied'] is False
            assert result['supported'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_libs_from_multiple_modules(self):
        path = None
        try:
            path = make_apk({
                'base/lib/arm64-v8a/libbase.so': (make_compliant_elf64(), 8),
                'feature/lib/arm64-v8a/libfeature.so': (make_compliant_elf64(), 8),
                'BundleConfig.pb': (b'', 0),
            })
            result = check_16kb_page_support(
                path, container='aab', bundle_config=_bundle_16k()
            )
            assert sorted(result['arm64-v8a'].keys()) == ['libbase.so', 'libfeature.so']
            assert result['bundle']['applied'] is True
            assert result['supported'] is True
        finally:
            if path and os.path.exists(path):
                os.unlink(path)
