/**
 * Direct unit tests for recorded-gap → wait-step synthesis (`withWaits`).
 *
 * Defaults: a 500 ms jitter floor drops hand-speed pauses (120 ms → no
 * wait), and cap 0 means uncapped — a 700 ms pause replays as 700 ms and
 * an 8 s pause replays as 8000 ms (the old Math.min cap clamped it to a
 * fixed 5000 ms, replacing the true recorded interval).
 *
 * `ts` semantics: device-time seconds of the touch END marker (backend
 * getevent parser); the current step's own swipe duration is subtracted,
 * so the wait measures true idle time (touch END prev → touch START cur).
 */
import { describe, it, expect } from 'vitest'
import { withWaits } from '@/renderer/composables/automation/useAutomationStore'
import type { Step } from '@components/automation/stepTypes'

/** Faithful stand-in for toV2Step output (ts omitted when unmeasured). */
function tap(id: string, ts?: number): Step {
  const s: any = { id, action: 'tap', mode: 'coord', coord: { x: 10, y: 20 } }
  if (ts !== undefined) s.ts = ts
  return s
}

function swipe(id: string, ts: number, durationMs = 300): Step {
  return {
    id, action: 'swipe',
    path: { x1: 0, y1: 0, x2: 5, y2: 5, duration_ms: durationMs },
    ts,
  }
}

/** Default gap config: 500 ms jitter floor, cap 0 = uncapped. */
const DEFAULT_GAP = { enabled: true, thresholdMs: 500, maxMs: 0 }

/** The `ms` of every synthesized wait step, in order. */
function waitValues(steps: Step[]): number[] {
  return (steps.filter((s) => s.action === 'wait') as Array<Step & { ms?: number }>)
    .map((s) => s.ms as number)
}

describe('withWaits (recorded gap → wait step)', () => {
  it('filters a real 120 ms gap as hand-speed jitter (500 ms floor)', () => {
    const out = withWaits([tap('a', 10.0), tap('b', 10.12)], DEFAULT_GAP)
    expect(out.map((s) => s.action)).toEqual(['tap', 'tap'])
    expect(waitValues(out)).toEqual([])
  })

  it('keeps a real 700 ms gap as a 700 ms wait (above floor, uncapped)', () => {
    const out = withWaits([tap('a', 10.0), tap('b', 10.7)], DEFAULT_GAP)
    expect(out.map((s) => s.action)).toEqual(['tap', 'wait', 'tap'])
    expect(out[1]).toMatchObject({ action: 'wait', mode: 'time', ms: 700 })
  })

  it('does not clamp an 8000 ms gap (cap 0 = uncapped; old clamp was 5000)', () => {
    const out = withWaits([tap('a', 100.0), tap('b', 108.0)], DEFAULT_GAP)
    expect(waitValues(out)).toEqual([8000])
  })

  it('measures touch END of prev → touch START of cur (swipe duration subtracted)', () => {
    // swipe ts = touch END (50.82); its 300 ms stroke means it STARTED at
    // 50.52 → idle gap after the 50.0 tap is 520 ms (820 ms without the
    // subtraction).
    const out = withWaits([tap('a', 50.0), swipe('b', 50.82, 300)], DEFAULT_GAP)
    expect(waitValues(out)).toEqual([520])
  })

  it('inserts nothing when auto-wait is off', () => {
    const steps = [tap('a', 10.0), tap('b', 18.0)]
    const out = withWaits(steps, { ...DEFAULT_GAP, enabled: false })
    expect(out).toEqual(steps)
    expect(out.every((s) => s.action !== 'wait')).toBe(true)
  })

  it('skips a gap whose ts is missing or non-numeric on either side', () => {
    // prev ts missing (cur at 10.6 would be a 600 ms wait if measured)
    expect(waitValues(withWaits([tap('a'), tap('b', 10.6)], DEFAULT_GAP))).toEqual([])
    // cur ts missing
    expect(waitValues(withWaits([tap('a', 10.0), tap('b')], DEFAULT_GAP))).toEqual([])
    // non-numeric ts
    const bad: any = tap('b', 'nope')
    expect(waitValues(withWaits([tap('a', 10.0), bad], DEFAULT_GAP))).toEqual([])
  })

  it('never emits a zero or negative wait (gap <= 0 → no wait step)', () => {
    // identical ts → 0 ms gap
    expect(waitValues(withWaits([tap('a', 10.0), tap('b', 10.0)], DEFAULT_GAP))).toEqual([])
    // cur before prev (clock skew) → clamped to 0 → no wait
    expect(waitValues(withWaits([tap('a', 10.5), tap('b', 10.0)], DEFAULT_GAP))).toEqual([])
  })

  it('rounds to whole milliseconds before the floor check', () => {
    // 500.6 ms rounds to 501 → above the 500 floor → kept
    expect(waitValues(withWaits([tap('a', 10.0), tap('b', 10.5006)], DEFAULT_GAP))).toEqual([501])
    // 500.4 ms rounds to 500 → 500 > 500 is false → dropped
    expect(waitValues(withWaits([tap('a', 10.0), tap('b', 10.5004)], DEFAULT_GAP))).toEqual([])
  })

  it('still honours a user-raised floor and an explicit cap', () => {
    // 700 ms below a raised 1000 ms floor → filtered out
    expect(waitValues(withWaits(
      [tap('a', 10.0), tap('b', 10.7)],
      { enabled: true, thresholdMs: 1000, maxMs: 0 },
    ))).toEqual([])
    // 700 ms above a lowered 200 ms floor → kept as-is (cap 0 = uncapped)
    expect(waitValues(withWaits(
      [tap('a', 10.0), tap('b', 10.7)],
      { enabled: true, thresholdMs: 200, maxMs: 0 },
    ))).toEqual([700])
    // 8000 ms clamped by an explicit 5000 ms cap
    expect(waitValues(withWaits(
      [tap('a', 100.0), tap('b', 108.0)],
      { enabled: true, thresholdMs: 500, maxMs: 5000 },
    ))).toEqual([5000])
  })
})
