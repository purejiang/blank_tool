"""
Contract tests for apk_inspector module — synthetic-APK fixtures only.
All tests use BytesIO + zipfile writemode with temp files; no real APK needed.
"""
import io
import os
import struct
import tempfile
import zipfile

import pytest

# backend/ is already on sys.path via conftest.py
from app.utils.apk_inspector import (
    analyze_compression,
    check_16kb_page_support,
    compare_so_across_arches,
    enumerate_so_files,
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


def make_elf64(pt_load_aligns: list) -> bytes:
    """Create minimal ELF64 bytes with the given PT_LOAD p_align values.

    Each PT_LOAD segment has p_type=1, p_flags=RWX.
    Returns a bytes object suitable for writestr inside a zip.
    """
    e_phoff = 64
    e_phentsize = 56
    e_phnum = len(pt_load_aligns)

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
    for align in pt_load_aligns:
        ph_entry = bytearray(56)
        struct.pack_into('<I', ph_entry, 0, 1)       # p_type = PT_LOAD
        struct.pack_into('<I', ph_entry, 4, 7)       # p_flags = RWX
        struct.pack_into('<Q', ph_entry, 48, align)  # p_align
        ph += ph_entry

    return bytes(buf) + bytes(ph)


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
