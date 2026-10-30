#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal stdlib PNG codec + resampling for icon replacement.

The backend is stdlib-only (no PIL). Launcher icons in APKs/AABs are usually
8-bit PNG/WebP rasters at several density buckets; replacing them requires
decoding the source PNG, resizing the user's PNG to each target size and
encoding it back losslessly enough for Android's decoder.

Scope (matches what launcher icons use in practice):

* PNG: 8-bit colour type 2 (RGB) / 3 (palette) / 6 (RGBA), non-interlaced.
* Dimensions: PNG IHDR + WebP (VP8 / VP8X / VP8L) headers, so a WebP target
  can still be replaced with PNG bytes at the correct pixel size.
* Encode: 8-bit RGBA PNG (filter 0), deterministic output.

Anything outside that scope returns ``None`` so callers can skip the icon
instead of writing a corrupt resource.
"""

import struct
import zlib
from typing import Optional, Tuple

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

def image_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Best-effort intrinsic pixel size of a PNG or WebP, or None."""
    if not data:
        return None
    if len(data) >= 24 and data[:8] == _PNG_SIG:
        w = int.from_bytes(data[16:20], "big")
        h = int.from_bytes(data[20:24], "big")
        return (w, h) if w and h else None
    if len(data) >= 20 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        fmt = data[12:16]
        if fmt == b"VP8 " and len(data) >= 30:
            w = int.from_bytes(data[26:28], "little") & 0x3FFF
            h = int.from_bytes(data[28:30], "little") & 0x3FFF
            return (w, h) if w and h else None
        if fmt == b"VP8X" and len(data) >= 30:
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return (w, h) if w and h else None
        if fmt == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            # 14 bits width-1, 14 bits height-1, little-endian bit stream
            bits = int.from_bytes(data[21:25], "little")
            w = (bits & 0x3FFF) + 1
            h = ((bits >> 14) & 0x3FFF) + 1
            return (w, h) if w and h else None
    return None


# ---------------------------------------------------------------------------
# PNG decode / encode
# ---------------------------------------------------------------------------

def decode_png_rgba(data: bytes) -> Optional[Tuple[int, int, bytearray]]:
    """Decode a supported PNG to ``(width, height, RGBA pixels)`` or None."""
    if len(data) < 8 or data[:8] != _PNG_SIG:
        return None
    w = h = depth = ctype = interlace = None
    idat = bytearray()
    palette = None
    trns = None
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        chunk = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length:
            return None
        if chunk == b"IHDR":
            w, h, depth, ctype, _comp, _filt, interlace = struct.unpack(
                ">IIBBBBB", body
            )
        elif chunk == b"PLTE":
            palette = body
        elif chunk == b"tRNS":
            trns = body
        elif chunk == b"IDAT":
            idat += body
        elif chunk == b"IEND":
            break
        pos += 12 + length
    if not w or not h or depth != 8 or interlace != 0 or ctype not in (2, 3, 6):
        return None
    if ctype == 3 and not palette:
        return None
    bpp = {2: 3, 3: 1, 6: 4}[ctype]
    stride = w * bpp
    try:
        raw = zlib.decompress(bytes(idat))
    except Exception:
        return None
    if len(raw) < (stride + 1) * h:
        return None

    def _paeth(a: int, b: int, c: int) -> int:
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        if pb <= pc:
            return b
        return c

    rows = []
    prev = bytearray(stride)
    for y in range(h):
        off = y * (stride + 1)
        ftype = raw[off]
        line = bytearray(raw[off + 1:off + 1 + stride])
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                upleft = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], upleft)) & 0xFF
        rows.append(bytes(line))
        prev = line

    rgba = bytearray(w * h * 4)
    for y in range(h):
        row = rows[y]
        base = y * w * 4
        if ctype == 6:
            rgba[base:base + w * 4] = row
        elif ctype == 2:
            for x in range(w):
                s = x * 3
                d = base + x * 4
                rgba[d] = row[s]
                rgba[d + 1] = row[s + 1]
                rgba[d + 2] = row[s + 2]
                rgba[d + 3] = 255
        else:
            for x in range(w):
                idx = row[x]
                d = base + x * 4
                p = idx * 3
                rgba[d] = palette[p]
                rgba[d + 1] = palette[p + 1]
                rgba[d + 2] = palette[p + 2]
                rgba[d + 3] = trns[idx] if (trns and idx < len(trns)) else 255
    return w, h, rgba


def encode_png_rgba(w: int, h: int, rgba: bytearray) -> bytes:
    """Encode an 8-bit RGBA pixel buffer as a filter-0 PNG."""
    stride = w * 4
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 6)

    def _chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (_PNG_SIG + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", comp) + _chunk(b"IEND", b""))


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------

def resize_rgba(
    w: int, h: int, rgba: bytearray, out_w: int, out_h: int
) -> bytearray:
    """Bilinear-resize an RGBA buffer (premultiplied sampling).

    Icons are displayed with alpha, so sampling straight RGBA would bleed
    colour from fully-transparent pixels. Premultiply before interpolating,
    then unpremultiply — the standard fix for halo-free edges.
    """
    if out_w <= 0 or out_h <= 0:
        return bytearray()
    if w == out_w and h == out_h:
        return bytearray(rgba)

    def _sample(x: int, y: int) -> Tuple[int, int, int, int]:
        i = (y * w + x) * 4
        a = rgba[i + 3]
        if a == 0:
            return 0, 0, 0, 0
        return (rgba[i] * a, rgba[i + 1] * a, rgba[i + 2] * a, a)

    scale_x = w / out_w
    scale_y = h / out_h
    out = bytearray(out_w * out_h * 4)
    for oy in range(out_h):
        sy = (oy + 0.5) * scale_y - 0.5
        if sy < 0:
            sy = 0.0
        y0 = int(sy)
        if y0 > h - 1:
            y0 = h - 1
        y1 = y0 + 1 if y0 + 1 < h else y0
        fy = sy - y0
        for ox in range(out_w):
            sx = (ox + 0.5) * scale_x - 0.5
            if sx < 0:
                sx = 0.0
            x0 = int(sx)
            if x0 > w - 1:
                x0 = w - 1
            x1 = x0 + 1 if x0 + 1 < w else x0
            fx = sx - x0

            r00, g00, b00, a00 = _sample(x0, y0)
            r01, g01, b01, a01 = _sample(x1, y0)
            r10, g10, b10, a10 = _sample(x0, y1)
            r11, g11, b11, a11 = _sample(x1, y1)

            def _lerp(c00: int, c01: int, c10: int, c11: int) -> float:
                top = c00 + (c01 - c00) * fx
                bot = c10 + (c11 - c10) * fx
                return top + (bot - top) * fy

            a = _lerp(a00, a01, a10, a11)
            d = (oy * out_w + ox) * 4
            if a <= 0.0:
                continue
            # premultiplied channels -> unpremultiplied 0..255
            r = _lerp(r00, r01, r10, r11) / a
            g = _lerp(g00, g01, g10, g11) / a
            b = _lerp(b00, b01, b10, b11) / a
            out[d] = min(255, max(0, int(round(r))))
            out[d + 1] = min(255, max(0, int(round(g))))
            out[d + 2] = min(255, max(0, int(round(b))))
            out[d + 3] = min(255, max(0, int(round(a))))
    return out


def resize_png(
    png_bytes: bytes, out_w: int, out_h: int
) -> Optional[bytes]:
    """Decode + resize + re-encode a PNG; None when unsupported/corrupt."""
    decoded = decode_png_rgba(png_bytes)
    if not decoded:
        return None
    w, h, rgba = decoded
    if w <= 0 or h <= 0:
        return None
    resized = resize_rgba(w, h, rgba, out_w, out_h)
    if not resized:
        return None
    return encode_png_rgba(out_w, out_h, resized)
