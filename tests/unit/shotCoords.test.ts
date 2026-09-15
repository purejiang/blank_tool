import { describe, it, expect } from 'vitest'
import {
  mapClickToPanel,
  isPickSafe,
  parseSize,
  displayToPanel,
  captureMatchesRotation,
  clampPanel,
} from '@components/automation/shotCoords'

/**
 * Screenshot point-pick coordinate math.
 *
 * Steps store PANEL-NATIVE pixels; screencap captures the CURRENT display
 * image, so at rotation 0 the mapping is a plain display→panel scale and at
 * rotation 1/3 the capture is the panel rotated 90° (displayToPanel inverts
 * the backend's rotate_to_display).
 */

describe('mapClickToPanel', () => {
  it('maps 1:1 when the image is displayed at native size', () => {
    // 1080x2400 screenshot rendered at exactly 1080x2400
    const c = mapClickToPanel({
      clickX: 100, clickY: 200,
      rectLeft: 0, rectTop: 0, rectWidth: 1080, rectHeight: 2400,
      panelW: 1080, panelH: 2400,
    })
    expect(c).toEqual({ x: 100, y: 200 })
  })

  it('scales a downscaled display up to panel pixels', () => {
    // 1080-wide image shown at 540 px: click at 270 → device 540
    const c = mapClickToPanel({
      clickX: 270, clickY: 480,
      rectLeft: 0, rectTop: 0, rectWidth: 540, rectHeight: 1200,
      panelW: 1080, panelH: 2400,
    })
    expect(c).toEqual({ x: 540, y: 960 })
  })

  it('accounts for the image rect being offset inside the viewport', () => {
    // image starts at (20, 30) in the viewport; click at viewport (70, 530)
    // is 50/500 into a 100x1000 display of a 200x2000 panel
    const c = mapClickToPanel({
      clickX: 70, clickY: 530,
      rectLeft: 20, rectTop: 30, rectWidth: 100, rectHeight: 1000,
      panelW: 200, panelH: 2000,
    })
    expect(c).toEqual({ x: 100, y: 1000 })
  })

  it('rounds to integer device pixels', () => {
    // 5 px display of a 10 px panel: click at 1 → 2.0001-ish
    const c = mapClickToPanel({
      clickX: 1, clickY: 1,
      rectLeft: 0, rectTop: 0, rectWidth: 5, rectHeight: 5,
      panelW: 10, panelH: 10,
    })
    expect(c).toEqual({ x: 2, y: 2 })
    expect(Number.isInteger(c.x)).toBe(true)
    expect(Number.isInteger(c.y)).toBe(true)
  })

  it('clamps clicks outside the image to the panel edges', () => {
    const tl = mapClickToPanel({
      clickX: -50, clickY: -50,
      rectLeft: 0, rectTop: 0, rectWidth: 100, rectHeight: 100,
      panelW: 400, panelH: 800,
    })
    expect(tl).toEqual({ x: 0, y: 0 })

    const br = mapClickToPanel({
      clickX: 500, clickY: 500,
      rectLeft: 0, rectTop: 0, rectWidth: 100, rectHeight: 100,
      panelW: 400, panelH: 800,
    })
    expect(br).toEqual({ x: 399, y: 799 })
  })
})

describe('isPickSafe', () => {
  it('accepts a capture at the physical panel size (rotation 0)', () => {
    expect(isPickSafe(1080, 2400, 1080, 2400)).toBe(true)
  })

  it('rejects swapped dimensions (rotation 90/270)', () => {
    expect(isPickSafe(2400, 1080, 1080, 2400)).toBe(false)
  })

  it('rejects any other size mismatch', () => {
    expect(isPickSafe(1080, 2340, 1080, 2400)).toBe(false)
  })
})

describe('parseSize', () => {
  it('parses a wm-size "1080x2400" string', () => {
    expect(parseSize('1080x2400')).toEqual({ w: 1080, h: 2400 })
  })

  it('returns null on garbage', () => {
    expect(parseSize('unknown')).toBeNull()
    expect(parseSize('')).toBeNull()
  })
})

describe('displayToPanel', () => {
  it('is identity at rotation 0', () => {
    expect(displayToPanel({ x: 100, y: 200 }, 0, 1080, 2400)).toEqual({ x: 100, y: 200 })
  })

  it('inverts the 90° mapping (r=1)', () => {
    // forward: rotate_to_display(100, 200, 1, 1080, 2400) = (200, 1080-100=980)
    expect(displayToPanel({ x: 200, y: 980 }, 1, 1080, 2400)).toEqual({ x: 100, y: 200 })
  })

  it('inverts the 180° mapping (r=2)', () => {
    // forward: rotate_to_display(100, 200, 2, 1080, 2400) = (980, 2200)
    expect(displayToPanel({ x: 980, y: 2200 }, 2, 1080, 2400)).toEqual({ x: 100, y: 200 })
  })

  it('inverts the 270° mapping (r=3)', () => {
    // forward: rotate_to_display(100, 200, 3, 1080, 2400) = (2400-200=2200, 100)
    expect(displayToPanel({ x: 2200, y: 100 }, 3, 1080, 2400)).toEqual({ x: 100, y: 200 })
  })

  it('normalizes out-of-range rotation values', () => {
    // 5 % 4 === 1 → same as the r=1 case above
    expect(displayToPanel({ x: 200, y: 980 }, 5, 1080, 2400)).toEqual({ x: 100, y: 200 })
    // -4 % 4 === 0 → identity
    expect(displayToPanel({ x: 100, y: 200 }, -4, 1080, 2400)).toEqual({ x: 100, y: 200 })
  })
})

describe('displayToPanel round-trip (contract with backend rotate_to_display)', () => {
  // Reference copy of backend/app/automation/coords.py rotate_to_display —
  // pins the renderer's inverse to the backend's forward formula.
  function rotateToDisplay(x: number, y: number, rotation: number, panelW: number, panelH: number): [number, number] {
    if (rotation === 1) return [y, panelW - x]
    if (rotation === 2) return [panelW - x, panelH - y]
    if (rotation === 3) return [panelH - y, x]
    return [x, y]
  }

  const points = [
    { x: 0, y: 0 },
    { x: 540, y: 1200 },
    { x: 1079, y: 2399 },
    { x: 123, y: 456 },
  ]

  for (const r of [0, 1, 2, 3]) {
    it(`round-trips every point at rotation ${r}`, () => {
      for (const p of points) {
        const [dx, dy] = rotateToDisplay(p.x, p.y, r, 1080, 2400)
        expect(displayToPanel({ x: dx, y: dy }, r, 1080, 2400)).toEqual(p)
      }
    })
  }
})

describe('displayToPanel real device data', () => {
  it('maps a landscape click on the 900x1600 emulator (rotation 1)', () => {
    // Observed emulator: wm size 900x1600, SurfaceOrientation 1, so the
    // screencap PNG is 1600x900. Click at display (800, 588):
    // x = panelW - d.y = 900 - 588 = 312; y = d.x = 800.
    expect(displayToPanel({ x: 800, y: 588 }, 1, 900, 1600)).toEqual({ x: 312, y: 800 })
  })
})

describe('captureMatchesRotation', () => {
  it('accepts image == panel at rotation 0', () => {
    expect(captureMatchesRotation(900, 1600, 0, 900, 1600)).toBe(true)
  })

  it('accepts image == panel at rotation 2', () => {
    expect(captureMatchesRotation(900, 1600, 2, 900, 1600)).toBe(true)
  })

  it('accepts swapped image at rotation 1 (landscape capture)', () => {
    expect(captureMatchesRotation(1600, 900, 1, 900, 1600)).toBe(true)
  })

  it('accepts swapped image at rotation 3', () => {
    expect(captureMatchesRotation(1600, 900, 3, 900, 1600)).toBe(true)
  })

  it('rejects a size that does not match the rotation', () => {
    // swapped image but rotation says portrait
    expect(captureMatchesRotation(1600, 900, 0, 900, 1600)).toBe(false)
    // matching image but rotation says landscape
    expect(captureMatchesRotation(900, 1600, 1, 900, 1600)).toBe(false)
    // rescaled capture
    expect(captureMatchesRotation(800, 1422, 1, 900, 1600)).toBe(false)
  })
})

describe('clampPanel', () => {
  it('clamps a point that the rotation pushed past the panel edge', () => {
    // display (x=0..) at rotation 1 maps to panel x = panelW - d.y; a
    // d.y of 0 yields panel x = panelW — one past the last pixel.
    expect(clampPanel(900, 800, 900, 1600)).toEqual({ x: 899, y: 800 })
    expect(clampPanel(-1, 1600, 900, 1600)).toEqual({ x: 0, y: 1599 })
  })

  it('leaves interior points untouched', () => {
    expect(clampPanel(312, 800, 900, 1600)).toEqual({ x: 312, y: 800 })
  })
})
