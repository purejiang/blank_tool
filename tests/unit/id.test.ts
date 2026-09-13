import { describe, it, expect } from 'vitest'
import { genId } from '@utils/id'

/**
 * genId unit tests.
 *
 * Replaced five near-identical `crypto.randomUUID()` copies. Note the prefix
 * contract: RecordingService forwards its id to the backend as `task_id`, so
 * `genId('rec')` must always yield a `rec-` prefixed value.
 */

describe('genId', () => {
  it('returns a bare id by default', () => {
    const id = genId()
    expect(typeof id).toBe('string')
    expect(id.length).toBeGreaterThan(0)
  })

  it('honours an explicit prefix', () => {
    const id = genId('rec')
    expect(id.startsWith('rec-')).toBe(true)
    expect(id.length).toBeGreaterThan('rec-'.length)
  })

  it('produces distinct ids', () => {
    const ids = new Set(Array.from({ length: 50 }, () => genId()))
    expect(ids.size).toBe(50)
  })
})
