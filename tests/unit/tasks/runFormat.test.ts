import { describe, expect, it } from 'vitest'

import {
  formatMs,
  isPathLike,
  isTruncatedOutput,
  nodeDepth,
  nodeStatusOf,
  parseNodePath,
  prettyValue,
  runStatusOf,
  statusI18nKey,
  statusTagType,
  truncationNote,
} from '@/renderer/components/tasks/runFormat'

/**
 * Run/node status presentation (docs/08 §5-3) plus the duration, node-path and
 * truncated-output helpers the run list and detail drawer share.
 */

describe('runStatusOf', () => {
  it('lets the cancelled flag outrank a failed status', () => {
    expect(runStatusOf({ success: false, status: 'failed', cancelled: true })).toBe('cancelled')
    expect(runStatusOf({ status: 'cancelled' })).toBe('cancelled')
    expect(runStatusOf({ status: 'canceled' })).toBe('cancelled')
  })

  it('reads the status string', () => {
    expect(runStatusOf({ status: 'succeeded' })).toBe('succeeded')
    expect(runStatusOf({ status: 'failed' })).toBe('failed')
    expect(runStatusOf({ status: 'running' })).toBe('running')
  })

  it('falls back to the coarse success boolean for pre-WP2 records', () => {
    expect(runStatusOf({ success: true, status: null, cancelled: null })).toBe('succeeded')
    expect(runStatusOf({ success: false, status: null, cancelled: null })).toBe('failed')
  })

  it('returns unknown for empty or missing records', () => {
    expect(runStatusOf(null)).toBe('unknown')
    expect(runStatusOf({})).toBe('unknown')
    expect(runStatusOf({ status: 'weird' })).toBe('unknown')
  })
})

describe('nodeStatusOf', () => {
  it('maps the engine node vocabulary', () => {
    expect(nodeStatusOf('ok')).toBe('succeeded')
    expect(nodeStatusOf('failed')).toBe('failed')
    expect(nodeStatusOf('skipped')).toBe('skipped')
    expect(nodeStatusOf('cancelled')).toBe('cancelled')
    expect(nodeStatusOf('nonsense')).toBe('unknown')
    expect(nodeStatusOf(undefined)).toBe('unknown')
  })
})

describe('status presentation', () => {
  it('maps statuses to i18n keys and tag types', () => {
    expect(statusI18nKey('cancelled')).toBe('tasks.status.cancelled')
    expect(statusTagType('succeeded')).toBe('success')
    expect(statusTagType('failed')).toBe('error')
    expect(statusTagType('cancelled')).toBe('warning')
    expect(statusTagType('running')).toBe('info')
    expect(statusTagType('unknown')).toBe('default')
  })
})

describe('formatMs', () => {
  it('renders seconds, minutes and hours', () => {
    expect(formatMs(1200)).toBe('1.2s')
    expect(formatMs(63_000)).toBe('1m 3.0s')
    expect(formatMs(3_723_000)).toBe('1h 2m 3.0s')
  })

  it('renders an em dash when there is no duration', () => {
    expect(formatMs(null)).toBe('—')
    expect(formatMs(undefined)).toBe('—')
    expect(formatMs(-1)).toBe('—')
    expect(formatMs(Number.NaN)).toBe('—')
  })
})

describe('node paths', () => {
  it('splits nested paths and derives depth', () => {
    expect(parseNodePath('scan')).toEqual(['scan'])
    expect(parseNodePath('loop/0/step')).toEqual(['loop', '0', 'step'])
    expect(parseNodePath('')).toEqual([])
    expect(nodeDepth('scan')).toBe(0)
    expect(nodeDepth('loop/0/step')).toBe(2)
  })
})

describe('truncated outputs', () => {
  it('recognises the shrink_outputs marker and never treats it as text', () => {
    const marker = { _truncated: true, _chars: 9000, _preview: 'abc…' }
    expect(isTruncatedOutput(marker)).toBe(true)
    expect(truncationNote(marker)).toBe('9000 chars')
    expect(truncationNote({ _truncated: true, _chars: 10, _reason: 'per-node cap' })).toBe(
      '10 chars · per-node cap',
    )
  })

  it('does not flag ordinary values', () => {
    expect(isTruncatedOutput('plain')).toBe(false)
    expect(isTruncatedOutput({ path: '/tmp/x' })).toBe(false)
    expect(isTruncatedOutput(null)).toBe(false)
  })
})

describe('isPathLike / prettyValue', () => {
  it('only offers 「打开」 for real-ish paths', () => {
    expect(isPathLike('C:\\Users\\me\\a.apk')).toBe(true)
    expect(isPathLike('/tmp/x.txt')).toBe(true)
    expect(isPathLike('./rel.json')).toBe(true)
    expect(isPathLike('hello')).toBe(false)
    expect(isPathLike('')).toBe(false)
    expect(isPathLike(42)).toBe(false)
  })

  it('pretty-prints objects and passes strings through', () => {
    expect(prettyValue('text')).toBe('text')
    expect(prettyValue({ a: 1 })).toBe('{\n  "a": 1\n}')
    expect(prettyValue(null)).toBe('')
  })
})
