/**
 * TaskStreamService state bounds (P2-7 状态收敛).
 *
 * `unbindTask` intentionally keeps the phase slots so a late `waitForPhase`
 * can still latch onto the result — but nothing ever removed them, so every
 * task the app streamed stayed in `phaseState` for the rest of the session
 * (a slow leak that also kept listeners' closures alive). The latch is now
 * bounded by a TTL + a hard cap, and an aborted run releases its listener.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import TaskStreamService, {
  MAX_PHASE_ENTRIES,
  PHASE_LATCH_TTL_MS,
} from '@services/TaskStreamService'

function makeService(captor: { cb?: (raw: any) => void }) {
  const svc = new TaskStreamService()
  ;(window as any).electronAPI = {
    onStreamEvent: (cb: (raw: any) => void) => {
      captor.cb = cb
    },
  }
  return svc
}

function event(taskId: string, type: string, payload: any) {
  return { stream_id: 's', data: { type, payload, task_id: taskId } }
}

describe('TaskStreamService — latch retention', () => {
  let captor: { cb?: (raw: any) => void }
  let svc: TaskStreamService

  beforeEach(() => {
    captor = {}
    svc = makeService(captor)
  })

  afterEach(() => {
    svc.destroy()
  })

  it('keeps the latch of a just-finished task so a late waitForPhase resolves', async () => {
    await svc.initialize()
    svc.bindTask('T1')
    svc.setCallbacks('T1', {})
    svc.setPhase('T1', 'operation')
    captor.cb!(event('T1', 'complete', { ok: true }))
    // completes → auto-unbind, but the result must stay readable
    await expect(svc.waitForPhase('T1', 'operation')).resolves.toEqual({ ok: true })
  })

  it('rejects with "unbound" once the latch is pruned by TTL', async () => {
    vi.useFakeTimers()
    try {
      await svc.initialize()
      svc.bindTask('T1')
      svc.setCallbacks('T1', {})
      svc.setPhase('T1', 'operation')
      captor.cb!(event('T1', 'complete', { ok: true }))
      expect(svc._phaseEntryCount()).toBe(1)

      // a later run (much later) triggers the prune
      vi.setSystemTime(Date.now() + PHASE_LATCH_TTL_MS + 1000)
      svc.bindTask('T2')
      expect(svc._phaseEntryCount()).toBe(1)   // T1 gone, T2 present
      await expect(svc.waitForPhase('T1', 'operation')).rejects.toThrow('unbound')
    } finally {
      vi.useRealTimers()
    }
  })

  it('never prunes a task that is still bound', async () => {
    vi.useFakeTimers()
    try {
      await svc.initialize()
      svc.bindTask('LIVE')
      svc.setPhase('LIVE', 'operation')
      vi.setSystemTime(Date.now() + PHASE_LATCH_TTL_MS * 3)
      svc.bindTask('OTHER')
      // the live task still has no settled slots, so it is never evictable
      expect(svc._phaseEntryCount()).toBe(2)
      expect(svc.waitForPhase('LIVE', 'operation')).toBeInstanceOf(Promise)
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps a settled latch readable right up to the TTL boundary', async () => {
    vi.useFakeTimers()
    try {
      await svc.initialize()
      svc.bindTask('T1')
      svc.setCallbacks('T1', {})
      svc.setPhase('T1', 'operation')
      captor.cb!(event('T1', 'complete', { ok: true }))

      // just inside the TTL → still there
      vi.setSystemTime(Date.now() + PHASE_LATCH_TTL_MS - 50)
      svc.bindTask('T2')
      await expect(svc.waitForPhase('T1', 'operation')).resolves.toEqual({ ok: true })

      // just past it → gone, and the rejection is the 'unbound' the callers
      // already handle
      vi.setSystemTime(Date.now() + PHASE_LATCH_TTL_MS + 50)
      svc.bindTask('T3')
      await expect(svc.waitForPhase('T1', 'operation')).rejects.toThrow('unbound')
    } finally {
      vi.useRealTimers()
    }
  })

  it('caps the map at MAX_PHASE_ENTRIES, dropping the oldest first', async () => {
    await svc.initialize()
    for (let i = 0; i < MAX_PHASE_ENTRIES + 25; i++) {
      const id = `T${i}`
      svc.bindTask(id)
      svc.setCallbacks(id, {})
      svc.setPhase(id, 'operation')
      captor.cb!(event(id, 'complete', { i }))
    }
    expect(svc._phaseEntryCount()).toBeLessThanOrEqual(MAX_PHASE_ENTRIES)
    // the newest latch survives so the last run's result is still readable
    const last = `T${MAX_PHASE_ENTRIES + 24}`
    await expect(svc.waitForPhase(last, 'operation')).resolves.toEqual({
      i: MAX_PHASE_ENTRIES + 24,
    })
    // the oldest were dropped
    await expect(svc.waitForPhase('T0', 'operation')).rejects.toThrow('unbound')
  })

  it('clears the aging stamps on destroy', async () => {
    await svc.initialize()
    svc.bindTask('T1')
    svc.unbindTask('T1')
    svc.destroy()
    expect(svc._phaseEntryCount()).toBe(0)
  })

  it('does not leak an aging stamp when a task id is re-bound', async () => {
    vi.useFakeTimers()
    try {
      await svc.initialize()
      svc.bindTask('T1')
      svc.unbindTask('T1')
      vi.setSystemTime(Date.now() + PHASE_LATCH_TTL_MS * 2)
      // re-bind the same id (retry): the fresh state must not be pruned by the
      // stale stamp of the previous attempt
      svc.bindTask('T1')
      svc.setPhase('T1', 'operation')
      expect(svc._phaseEntryCount()).toBe(1)
      expect(svc.waitForPhase('T1', 'operation')).toBeInstanceOf(Promise)
    } finally {
      vi.useRealTimers()
    }
  })
})
