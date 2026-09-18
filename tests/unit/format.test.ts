import { describe, it, expect } from 'vitest'
import { formatBytes } from '@utils/format'

/**
 * formatBytes unit tests.
 *
 * Locks the canonical behaviour that replaced three divergent copies. The first
 * case is the contract ApkService's own test already asserted; the rest cover
 * the places the copies disagreed on (trailing zeros, unit list, guards).
 */

describe('formatBytes', () => {
  it('satisfies the ApkService contract', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1024)).toBe('1 KB')
    expect(formatBytes(1048576)).toBe('1 MB')
  })

  it('drops trailing zeros (the SettingsPage copy printed "1.00 MB")', () => {
    expect(formatBytes(1572864)).toBe('1.5 MB')
    expect(formatBytes(2 * 1024 * 1024)).toBe('2 MB')
  })

  it('climbs to TB and clamps beyond it (the ApkService copy had no TB)', () => {
    expect(formatBytes(1024 ** 4)).toBe('1 TB')
    expect(formatBytes(1024 ** 5)).toBe('1024 TB')
  })

  it('guards non-numeric / non-positive input instead of emitting "NaN B"', () => {
    expect(formatBytes(Number.NaN)).toBe('0 B')
    expect(formatBytes(-1)).toBe('0 B')
    expect(formatBytes(Number.POSITIVE_INFINITY)).toBe('0 B')
    expect(formatBytes(undefined as unknown as number)).toBe('0 B')
  })
})
