#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests for the lossless PNG recompression (app.utils.png).

Screenshots arrive as ``adb shell screencap -p`` PNGs deflated at zlib's
default level; ``recompress_png_lossless`` re-deflates the IDAT stream at
level 9 / Z_FILTERED. These tests pin the safety properties: bit-for-bit
losslessness, non-IDAT chunks preserved, and the never-raises /
never-touches-on-failure contract the capture paths rely on.
"""

import shutil
import struct
import zlib

import pytest

from app.utils.png import recompress_png_lossless

_SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(ctype: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + ctype + data
            + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF))


def _make_png(level=1, split_idat=False, extra_chunks=(), width=32, height=8):
    """Build a small valid RGB PNG; returns (png_bytes, raw_scanlines)."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b""
    for y in range(height):
        row = bytearray()
        for x in range(width):
            row += bytes(((x * 7) % 256, (y * 13) % 256, (x * y) % 256))
        rows += b"\x00" + bytes(row)
    idat = zlib.compress(rows, level)
    png = _SIG + _chunk(b"IHDR", ihdr)
    for ctype, data in extra_chunks:
        png += _chunk(ctype, data)
    if split_idat and len(idat) > 2:
        mid = len(idat) // 2
        png += _chunk(b"IDAT", idat[:mid]) + _chunk(b"IDAT", idat[mid:])
    else:
        png += _chunk(b"IDAT", idat)
    png += _chunk(b"IEND", b"")
    return png, rows


def _parse_chunks(png: bytes):
    assert png.startswith(_SIG)
    pos, chunks = 8, []
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos:pos + 4])
        chunks.append((png[pos + 4:pos + 8], png[pos + 8:pos + 8 + length]))
        pos += 12 + length
    return chunks


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_shrinks_loosely_compressed_png(tmp_path):
    png, _ = _make_png(level=1)
    p = _write(tmp_path, "loose.png", png)
    r = recompress_png_lossless(p)
    assert r["ok"] is True
    assert r["rewritten"] is True
    assert 0 < r["after"] < r["before"]
    assert r["saved"] == r["before"] - r["after"]


def test_lossless_and_chunks_preserved(tmp_path):
    """Recompressed file decodes to identical pixels; every non-IDAT chunk
    (including a custom ancillary one) survives byte-for-byte, in order;
    a split IDAT run comes back as a single chunk."""
    text_chunk = (b"tEXt", b"Comment\x00screenshot")
    png, rows = _make_png(level=1, split_idat=True, extra_chunks=[text_chunk])
    p = _write(tmp_path, "split.png", png)
    r = recompress_png_lossless(p)
    assert r["rewritten"] is True

    with open(p, "rb") as f:
        out = f.read()
    chunks = _parse_chunks(out)
    # IDAT collapsed to exactly one chunk, IHDR/tEXt/IEND preserved as-is
    idats = [c for c in chunks if c[0] == b"IDAT"]
    assert len(idats) == 1
    assert [c[0] for c in chunks] == [b"IHDR", b"tEXt", b"IDAT", b"IEND"]
    assert chunks[1] == text_chunk
    # bit-for-bit lossless: same decompressed scanlines as the original
    assert zlib.decompress(idats[0][1]) == rows


def test_already_optimal_png_untouched(tmp_path):
    """A PNG deflated at level 9 + Z_FILTERED is the target encoding — the
    helper must leave the file byte-identical rather than churn it."""
    rows_scanlines = None
    comp = zlib.compressobj(9, zlib.DEFLATED, 15, 9, zlib.Z_FILTERED)
    # build via _make_png then re-encode manually to control the IDAT level
    png, rows = _make_png(level=1)
    stream = comp.compress(rows) + comp.flush()
    ihdr = _parse_chunks(png)[0][1]
    optimal = _SIG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", stream) + _chunk(b"IEND", b"")
    p = _write(tmp_path, "optimal.png", optimal)
    r = recompress_png_lossless(p)
    assert r["ok"] is True
    assert r["rewritten"] is False
    assert r["saved"] == 0
    with open(p, "rb") as f:
        assert f.read() == optimal


def test_non_png_rejected_untouched(tmp_path):
    p = _write(tmp_path, "not.png", b"this is not a png at all")
    r = recompress_png_lossless(p)
    assert r["ok"] is False
    assert r["rewritten"] is False
    with open(p, "rb") as f:
        assert f.read() == b"this is not a png at all"


def test_truncated_png_rejected_untouched(tmp_path):
    png, _ = _make_png(level=1)
    p = _write(tmp_path, "cut.png", png[: len(png) // 2])
    r = recompress_png_lossless(p)
    assert r["ok"] is False
    with open(p, "rb") as f:
        assert f.read() == png[: len(png) // 2]


def test_corrupt_crc_rejected_untouched(tmp_path):
    """A chunk with a broken CRC means corruption — leave it, never
    rewrite a possibly-broken file into something that looks valid."""
    png, _ = _make_png(level=1)
    bad = bytearray(png)
    bad[-6] ^= 0xFF  # inside IEND data
    p = _write(tmp_path, "badcrc.png", bytes(bad))
    r = recompress_png_lossless(p)
    assert r["ok"] is False
    with open(p, "rb") as f:
        assert f.read() == bytes(bad)


def test_missing_file_never_raises():
    r = recompress_png_lossless("Z:/definitely/not/here.png")
    assert r["ok"] is False
    assert r["rewritten"] is False


def test_take_screenshot_recompresses(tmp_path, monkeypatch):
    """End-to-end on the automation capture path: a 'pulled' loose PNG
    ends up recompressed on disk with identical pixels. The shrink runs
    on a daemon thread, so poll for it (bounded) instead of asserting
    synchronously."""
    import time as _time

    import app.automation.apps as apps

    loose_png, rows = _make_png(level=1, width=64, height=16)
    loose_src = _write(tmp_path, "device_side.png", loose_png)

    def fake_run_adb(device_id, args):
        if args and args[0] == "pull":
            shutil.copyfile(loose_src, args[2])
        return {"returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(apps, "run_adb", fake_run_adb)
    monkeypatch.setattr(apps, "logger", type("L", (), {
        "info": staticmethod(lambda *a, **k: None),
        "warning": staticmethod(lambda *a, **k: None),
    })())

    out_dir = tmp_path / "run" / "screenshots"
    r = apps.take_screenshot("emulator-5554", "env", out_dir=str(out_dir))
    assert r["success"] is True, r.get("error")

    # the handler returns before the background shrink finishes; wait for it
    deadline = _time.time() + 10
    final = None
    while _time.time() < deadline:
        with open(r["file_path"], "rb") as f:
            final = f.read()
        if len(final) < len(loose_png):
            break
        _time.sleep(0.05)
    assert final is not None and len(final) < len(loose_png), \
        "background recompression did not shrink the screenshot in time"
    idats = [c for c in _parse_chunks(final) if c[0] == b"IDAT"]
    assert zlib.decompress(idats[0][1]) == rows
