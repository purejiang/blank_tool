#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Display rotation / coordinate-space helpers.

Recorded scripts store touch-panel RAW coordinates (getevent native
orientation) while ``input tap`` expects DISPLAY coordinates for the
CURRENT rotation — ``rotate_to_display`` maps between the two.
"""

from typing import Dict, Any, Tuple

from app.automation.adb import run_adb, logger


def get_display_transform(device_id: str) -> Dict[str, Any]:
    """Query the current surface rotation and natural (panel) size.

    Returns ``{"rotation": 0..3, "width": int, "height": int}`` where
    width/height are the natural (unrotated) dimensions.
    """
    rotation = 0
    width = height = 0
    try:
        r = run_adb(device_id, ["shell", "dumpsys", "input"])
        for line in (r.get("stdout") or "").splitlines():
            if "SurfaceOrientation" in line:
                try:
                    rotation = int(line.split(":", 1)[1].strip() or 0) % 4
                except ValueError:
                    rotation = 0
                break
        r2 = run_adb(device_id, ["shell", "wm", "size"])
        for line in (r2.get("stdout") or "").splitlines():
            if "Physical size" in line:
                part = line.split("Physical size:", 1)[1].strip().split()[0]
                try:
                    width, height = (int(v) for v in part.lower().split("x"))
                except ValueError:
                    width = height = 0
                break
    except Exception as e:  # defensive: never crash a run over metadata
        logger.warning(f"get_display_transform failed: {e}")
    return {"rotation": rotation, "width": width, "height": height}


def rotate_to_display(
    x: int, y: int, rotation: int, panel_w: int, panel_h: int
) -> Tuple[int, int]:
    """Map panel-native raw coords to display coords for ``input tap``."""
    x, y = int(x), int(y)
    if rotation == 1:
        return y, panel_w - x
    if rotation == 2:
        return panel_w - x, panel_h - y
    if rotation == 3:
        return panel_h - y, x
    return x, y
