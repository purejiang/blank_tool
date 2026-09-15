/**
 * Screenshot point-pick coordinate math — pure functions, no Vue/backend
 * deps (same split as uiDump.ts: math here, DOM/API work in the modal).
 *
 * Coordinate space (critical): automation steps store PANEL-NATIVE
 * (natural orientation) absolute pixels; the backend replay runs every
 * coord through `rotate_to_display` before `input tap`. `screencap`
 * captures the CURRENT display image, so at rotation 1/3 the PNG is the
 * panel rotated 90°. Picking therefore works in two steps: scale the
 * click into the capture's pixels (mapClickToPanel), then invert the
 * backend's rotation (displayToPanel). Without a known rotation the
 * dimension-based fallback (isPickSafe) still refuses anything that is
 * not a plain 1:1 panel capture.
 * NOTE: a 180° rotation is NOT detectable from dimensions alone — the
 * screenshot would be upside down while sizes still match. Accepted
 * limitation when the display transform is unavailable; with the
 * transform the 180° inverse is applied exactly like the replay does.
 */

export interface PickDisplay {
  /** click position in viewport coordinates */
  clickX: number
  clickY: number
  /** bounding rect of the DISPLAYED <img> (viewport coordinates) */
  rectLeft: number
  rectTop: number
  rectWidth: number
  rectHeight: number
  /** size to scale the click into — the CAPTURE's pixel size (at rotation
   *  0 the capture == panel; when rotated, displayToPanel maps the capture
   *  px on to panel px afterwards) */
  panelW: number
  panelH: number
}

/** Clamp a point to `[0, panelW-1] × [0, panelH-1]`. */
export function clampPanel(x: number, y: number, panelW: number, panelH: number): { x: number; y: number } {
  return {
    x: Math.min(Math.max(x, 0), panelW - 1),
    y: Math.min(Math.max(y, 0), panelH - 1),
  }
}

/**
 * Map a click on the displayed (possibly scaled) screenshot to real
 * device panel pixels, clamped to the panel bounds.
 */
export function mapClickToPanel(p: PickDisplay): { x: number; y: number } {
  const x = Math.round(((p.clickX - p.rectLeft) * p.panelW) / p.rectWidth)
  const y = Math.round(((p.clickY - p.rectTop) * p.panelH) / p.rectHeight)
  return clampPanel(x, y, p.panelW, p.panelH)
}

/**
 * Inverse of the backend's rotate_to_display: display px → panel-native px.
 */
export function displayToPanel(
  d: { x: number; y: number }, rotation: number, panelW: number, panelH: number,
): { x: number; y: number } {
  const r = ((Math.trunc(rotation) % 4) + 4) % 4
  if (r === 1) return { x: panelW - d.y, y: d.x }
  if (r === 2) return { x: panelW - d.x, y: panelH - d.y }
  if (r === 3) return { x: d.y, y: panelH - d.x }
  return { x: d.x, y: d.y }
}

/**
 * The capture is only usable when its size matches what this rotation implies:
 * rotation 0/2 → image == panel; rotation 1/3 → image == swapped panel.
 */
export function captureMatchesRotation(imgW: number, imgH: number, rotation: number, panelW: number, panelH: number): boolean {
  const r = ((Math.trunc(rotation) % 4) + 4) % 4
  if (r === 1 || r === 3) return imgW === panelH && imgH === panelW
  return imgW === panelW && imgH === panelH
}

/**
 * Picking is only exact when the captured image size equals the device's
 * physical panel size — any mismatch (swapped dims = rotation 90/270, or
 * a rescaled capture) makes the naive mapping wrong.
 *
 * Fallback-path only (display transform unavailable); with a known
 * rotation use captureMatchesRotation instead.
 */
export function isPickSafe(imgW: number, imgH: number, panelW: number, panelH: number): boolean {
  return imgW === panelW && imgH === panelH
}

/** Parse a `"1080x2400"` (wm size) string into `{ w, h }`, null on failure. */
export function parseSize(s: string): { w: number; h: number } | null {
  const m = /(\d+)\s*[x×]\s*(\d+)/.exec(s || '')
  if (!m) return null
  return { w: Number(m[1]), h: Number(m[2]) }
}
