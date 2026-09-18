#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lossless PNG recompression (stdlib only).

``adb shell screencap -p`` writes PNGs deflated at zlib's default level;
re-deflating the IDAT stream at level 9 with ``Z_FILTERED`` (which suits
PNG's per-scanline filtered data) typically shaves ~10% off device
screenshots — bit-for-bit lossless: the new stream is verified to
decompress to the identical scanlines before the file is replaced, and
every non-IDAT chunk is copied through byte-for-byte.

The helper NEVER raises: any parse/IO failure leaves the original file
untouched, so callers can invoke it unconditionally after a capture.
"""

import os
import struct
import threading
import zlib

_SIG = b"\x89PNG\r\n\x1a\n"
_MIN_PNG = 45  # signature + IHDR + IEND, the smallest valid PNG


def recompress_png_lossless(path: str) -> dict:
    """Rewrite ``path`` in place with a maximally-deflated IDAT stream.

    Returns ``{"ok", "before", "after", "saved", "rewritten"}``.
    ``ok`` False (file untouched) for non-PNG / corrupt input or IO errors;
    ``rewritten`` False when the file is valid but already small enough.
    """
    before = 0
    try:
        with open(path, "rb") as f:
            raw = f.read()
        before = len(raw)
        result = _recompress_bytes(raw)
        if result is None:
            return {"ok": False, "before": before, "after": before,
                    "saved": 0, "rewritten": False}
        if len(result) >= before:
            return {"ok": True, "before": before, "after": before,
                    "saved": 0, "rewritten": False}
        tmp = path + ".recompress.tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(result)
            os.replace(tmp, path)  # atomic: same directory → same filesystem
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        return {"ok": True, "before": before, "after": len(result),
                "saved": before - len(result), "rewritten": True}
    except Exception:
        return {"ok": False, "before": before, "after": before,
                "saved": 0, "rewritten": False}


def recompress_png_lossless_async(path: str, logger=None) -> None:
    """Fire-and-forget ``recompress_png_lossless`` on a daemon thread.

    Level-9 deflate of a ~6 MB scanline stream takes seconds — far too
    long to run inside a capture step (or even a background thread doing
    one giant GIL-holding zlib call). The chunked feed inside
    ``_deflate_best`` keeps each GIL hold ~40 ms, so the backend stays
    responsive to other requests while the shrink runs. The file is
    replaced atomically, so concurrent readers always see a complete PNG.
    """
    def _run():
        r = recompress_png_lossless(path)
        if logger is not None and r["rewritten"]:
            logger.info(
                f"screenshot losslessly recompressed: "
                f"{r['before']} -> {r['after']} bytes "
                f"(-{100 * r['saved'] // r['before']}%)"
            )
    threading.Thread(target=_run, daemon=True, name="png-recompress").start()


def _recompress_bytes(raw: bytes):
    """Return the recompressed PNG, or None when input isn't a clean PNG.

    Every non-IDAT chunk (IHDR, ancillary, IEND...) is kept byte-for-byte
    in its original position; the IDAT run is replaced by a single chunk
    holding the re-deflated stream. Original chunk CRCs are validated —
    corrupt input is left alone rather than "laundered".
    """
    if len(raw) < _MIN_PNG or not raw.startswith(_SIG):
        return None
    pos = 8
    out = bytearray(raw[:8])
    idat = bytearray()
    idat_seen = False
    idat_flushed = False
    while pos + 12 <= len(raw):
        (length,) = struct.unpack(">I", raw[pos:pos + 4])
        ctype = raw[pos + 4:pos + 8]
        end = pos + 8 + length
        if end + 4 > len(raw):
            return None  # truncated chunk
        data = raw[pos + 8:end]
        if struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF) != raw[end:end + 4]:
            return None  # corrupt chunk — do not touch
        if ctype == b"IDAT":
            if idat_flushed:
                return None  # IDAT chunks must be consecutive
            idat_seen = True
            idat += data
        else:
            if idat_seen and not idat_flushed:
                new = _deflate_best(bytes(idat))
                if new is None:
                    return None
                _append_chunk(out, b"IDAT", new)
                idat_flushed = True
            _append_chunk(out, ctype, data)
        pos = end + 4
    if pos != len(raw) or not idat_seen:
        return None  # trailing garbage / no image data
    if not idat_flushed:
        new = _deflate_best(bytes(idat))
        if new is None:
            return None
        _append_chunk(out, b"IDAT", new)
    return bytes(out)


def _deflate_best(idat: bytes):
    """Re-deflate the IDAT zlib stream; None when not provably identical."""
    scanlines = zlib.decompress(idat)
    comp = zlib.compressobj(9, zlib.DEFLATED, 15, 8, zlib.Z_FILTERED)
    # Feed in 64 KiB pieces: zlib's compress() holds the GIL for the whole
    # call, and one 3 s+ call on a full-size screenshot would stall every
    # other thread in the backend (IPC dispatch included). Chunk boundaries
    # may shift block edges slightly vs a single call — losslessness is
    # enforced by the decode check below, not by byte-identical streams.
    parts = []
    for i in range(0, len(scanlines), 65536):
        parts.append(comp.compress(scanlines[i:i + 65536]))
    parts.append(comp.flush())
    new = b"".join(parts)
    # lossless guarantee: the replacement stream must decode to the
    # exact same bytes (guards against any coding error above)
    if zlib.decompress(new) != scanlines:
        return None
    return new


def _append_chunk(out: bytearray, ctype: bytes, data: bytes) -> None:
    out += struct.pack(">I", len(data))
    out += ctype
    out += data
    out += struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
