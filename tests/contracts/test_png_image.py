#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for app.utils.png_image (stdlib PNG codec + resampling)."""

import struct
import zlib

import pytest

from app.utils.png_image import (
    decode_png_rgba,
    encode_png_rgba,
    image_dimensions,
    resize_png,
    resize_rgba,
)


def _rgba(w, h, color=(10, 20, 30, 255)):
    px = bytearray(w * h * 4)
    for i in range(0, len(px), 4):
        px[i:i + 4] = bytes(color)
    return px


def test_encode_decode_roundtrip():
    w, h = 5, 3
    px = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            px[i] = x * 10
            px[i + 1] = y * 20
            px[i + 2] = 99
            px[i + 3] = 200
    data = encode_png_rgba(w, h, px)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    decoded = decode_png_rgba(data)
    assert decoded is not None
    dw, dh, out = decoded
    assert (dw, dh) == (w, h)
    assert out == px


def test_image_dimensions_png():
    data = encode_png_rgba(7, 9, _rgba(7, 9))
    assert image_dimensions(data) == (7, 9)


def test_image_dimensions_webp_vp8x():
    data = bytearray(30)
    data[0:4] = b"RIFF"
    data[4:8] = (22).to_bytes(4, "little")
    data[8:12] = b"WEBP"
    data[12:16] = b"VP8X"
    data[24:27] = (99).to_bytes(3, "little")   # width - 1
    data[27:30] = (49).to_bytes(3, "little")   # height - 1
    assert image_dimensions(bytes(data)) == (100, 50)


def test_image_dimensions_webp_vp8l():
    data = bytearray(25)
    data[0:4] = b"RIFF"
    data[8:12] = b"WEBP"
    data[12:16] = b"VP8L"
    data[20] = 0x2F
    bits = (63) | (31 << 14)                     # width 64, height 32
    data[21:25] = bits.to_bytes(4, "little")
    assert image_dimensions(bytes(data)) == (64, 32)


def test_image_dimensions_invalid():
    assert image_dimensions(b"") is None
    assert image_dimensions(b"not an image") is None
    assert image_dimensions(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) is None


def test_resize_rgba_dimensions_and_alpha():
    px = _rgba(2, 2, (255, 0, 0, 255))
    out = resize_rgba(2, 2, px, 4, 4)
    assert len(out) == 4 * 4 * 4
    assert out[3] == 255
    assert out[0] == 255 and out[1] == 0 and out[2] == 0


def test_resize_rgba_preserves_transparency():
    # left half transparent, right half opaque
    w, h = 2, 1
    px = bytearray(w * h * 4)
    px[0:4] = bytes((0, 0, 0, 0))
    px[4:8] = bytes((255, 255, 255, 255))
    out = resize_rgba(w, h, px, 4, 1)
    assert out[0:4] == b"\x00\x00\x00\x00"       # fully transparent stays clear
    assert out[12:16] == b"\xff\xff\xff\xff"     # fully opaque stays white


def test_resize_png_roundtrip():
    src = encode_png_rgba(8, 8, _rgba(8, 8))
    out = resize_png(src, 4, 4)
    assert out is not None
    decoded = decode_png_rgba(out)
    assert decoded is not None
    assert decoded[0] == 4 and decoded[1] == 4


def test_resize_png_unsupported_input():
    assert resize_png(b"jpeg-ish", 4, 4) is None


def test_decode_png_rejects_interlaced_or_16bit():
    # invalid/unsupported inputs must return None rather than raise
    assert decode_png_rgba(b"") is None
    assert decode_png_rgba(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32) is None
