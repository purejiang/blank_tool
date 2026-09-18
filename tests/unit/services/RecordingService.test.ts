/**
 * RecordingService — stream-event subscription router for adb_auto
 * recording sessions (plan: .omo/plans/adb-auto-test.md, Todo 3).
 *
 * Envelope contract (anchor: TaskStreamService.string-payload.test.ts:22-26):
 *   { stream_id, data: { type, payload, task_id } }
 *
 * `automation.record_start` is a streaming init: the renderer-side unwrap
 * returns `undefined` for a result without a `type` field
 * (src/preload/core/unwrapBackendResponse.ts:7), so a resolved
 * unifiedApi.call means the backend accepted the session. A stream_id is
 * never read (known defect in OtherToolsPage.runScript — do not imitate).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import RecordingService from '@services/RecordingService'
import unifiedApi from '@/renderer/api/unifiedApi'

type StreamCb = (raw: any) => void

function envelope(taskId: string, type: string, payload: any) {
  // Matches the main process: sender.send(streamEvent, { stream_id, data: result })
  // where result = { type, payload, task_id } (the backend event).
  return { stream_id: 's', data: { type, payload, task_id: taskId } }
}

describe('RecordingService', () => {
  let svc: InstanceType<typeof RecordingService>
  let capturedCb: StreamCb | null
  let subscribeCount: number
  let callBackendAPI: ReturnType<typeof vi.fn>

  beforeEach(() => {
    capturedCb = null
    subscribeCount = 0
    // Programmable backend call — default resolves `undefined`, exactly what
    // the renderer sees for a streaming init (no `type` field → unwrap → undefined).
    callBackendAPI = vi.fn().mockResolvedValue(undefined)
    ;(window as any).electronAPI = {
      onStreamEvent: (cb: StreamCb) => {
        subscribeCount++
        capturedCb = cb
        return () => {}
      },
      callBackendAPI,
    }
    // Re-capture the test's electronAPI (the module singleton captured
    // whatever was on window at import time).
    unifiedApi.initialize()
    svc = new RecordingService()
  })

  describe('initialize', () => {
    it('subscribes to onStreamEvent exactly once (idempotent)', async () => {
      await svc.initialize()
      await svc.initialize()
      expect(subscribeCount).toBe(1)
      expect(typeof capturedCb).toBe('function')
    })

    it('does not throw when onStreamEvent is unavailable', async () => {
      ;(window as any).electronAPI = { callBackendAPI }
      unifiedApi.initialize()
      const degraded = new RecordingService()
      await expect(degraded.initialize()).resolves.toBeUndefined()
      // Callback registration stays harmless without a live subscription
      expect(() => degraded.onStep('rec-x', vi.fn())).not.toThrow()
    })
  })

  describe('startRecording', () => {
    it('issues automation.record_start with device_id/task_id and resolves a rec-<uuid> id', async () => {
      const recId = await svc.startRecording('dev-1')
      expect(recId).toMatch(/^rec-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
      expect(callBackendAPI).toHaveBeenCalledTimes(1)
      expect(callBackendAPI).toHaveBeenCalledWith('automation.record_start', {
        device_id: 'dev-1',
        task_id: recId,
      })
    })

    it('resolves even though the streaming init unwraps to undefined (no stream_id check)', async () => {
      // callBackendAPI resolves `undefined` by default in this suite —
      // exactly what a streaming init produces after unwrapping.
      await expect(svc.startRecording('dev-1')).resolves.toMatch(/^rec-/)
    })

    it('registers the stream subscription before issuing record_start', async () => {
      let subscribedAtCall: boolean | null = null
      callBackendAPI.mockImplementation(async () => {
        subscribedAtCall = typeof capturedCb === 'function'
        return undefined
      })
      await svc.initialize()
      await svc.startRecording('dev-1')
      expect(subscribedAtCall).toBe(true)
    })

    it('delivers events emitted while the start call is in flight (callbacks registered before the call)', async () => {
      await svc.initialize()
      const onStep = vi.fn()
      callBackendAPI.mockImplementation(async (_method: string, params: any) => {
        // Simulate the backend emitting a record_event while the start call
        // is in flight: the event reflows through the stream subscription
        // synchronously DURING the unifiedApi.call await window.
        capturedCb!(envelope(params.task_id, 'record_event', { step: { action: 'tap', x: 1, y: 2 } }))
        return undefined
      })

      await svc.startRecording('dev-1', { onStep })

      // Only passes if onStep was wired before unifiedApi.call was issued.
      expect(onStep).toHaveBeenCalledTimes(1)
      expect(onStep).toHaveBeenCalledWith({ action: 'tap', x: 1, y: 2 })
    })

    it('cleans up the callback slot when record_start rejects (no leak)', async () => {
      await svc.initialize()
      const onStep = vi.fn()
      let abortedTaskId = ''
      callBackendAPI.mockImplementation(async (_method: string, params: any) => {
        abortedTaskId = params.task_id
        throw new Error('start failed')
      })

      await expect(svc.startRecording('dev-1', { onStep })).rejects.toThrow('start failed')

      // The slot was deleted on failure — a late event for the aborted
      // task_id is no longer routable (no callback closure leak).
      capturedCb!(envelope(abortedTaskId, 'record_event', { step: { action: 'tap', x: 1, y: 2 } }))
      expect(onStep).not.toHaveBeenCalled()
    })
  })

  describe('event routing', () => {
    beforeEach(async () => {
      await svc.initialize()
    })

    it('routes record_event to onStep for the matching task_id', () => {
      const onStep = vi.fn()
      svc.onStep('rec-1', onStep)

      capturedCb!(envelope('rec-1', 'record_event', { step: 'tap:login' }))

      expect(onStep).toHaveBeenCalledTimes(1)
      expect(onStep).toHaveBeenCalledWith('tap:login')
    })

    it('ignores record_event for another task_id', () => {
      const onStep = vi.fn()
      svc.onStep('rec-1', onStep)

      capturedCb!(envelope('rec-OTHER', 'record_event', { step: 'x' }))

      expect(onStep).not.toHaveBeenCalled()
    })

    it('ignores events without a task_id', () => {
      const onStep = vi.fn()
      svc.onStep('rec-1', onStep)

      capturedCb!({ stream_id: 's', data: { type: 'record_event', payload: { step: 'x' } } })

      expect(onStep).not.toHaveBeenCalled()
    })

    it('routes error events to onError (payload.message)', () => {
      const onError = vi.fn()
      svc.onError('rec-1', onError)

      capturedCb!(envelope('rec-1', 'error', { message: 'device offline' }))

      expect(onError).toHaveBeenCalledTimes(1)
      expect(onError).toHaveBeenCalledWith('device offline')
    })

    it('routes error events with a bare string payload to onError (String(payload))', () => {
      const onError = vi.fn()
      svc.onError('rec-1', onError)

      capturedCb!(envelope('rec-1', 'error', '[adb_auto] boom'))

      expect(onError).toHaveBeenCalledWith('[adb_auto] boom')
    })

    it('routes record_stopped to onStopped with the full payload', () => {
      const onStopped = vi.fn()
      const payload = { steps: ['s1', 's2'], record_device: 'dev-1' }
      svc.onStopped('rec-1', onStopped)

      capturedCb!(envelope('rec-1', 'record_stopped', payload))

      expect(onStopped).toHaveBeenCalledTimes(1)
      expect(onStopped).toHaveBeenCalledWith(payload)
    })

    it('ignores unknown event types and malformed envelopes without throwing', () => {
      const onStep = vi.fn()
      const onError = vi.fn()
      const onStopped = vi.fn()
      svc.onStep('rec-1', onStep)
      svc.onError('rec-1', onError)
      svc.onStopped('rec-1', onStopped)

      expect(() => capturedCb!(null)).not.toThrow()
      expect(() => capturedCb!({ stream_id: 's' })).not.toThrow() // no data
      expect(() => capturedCb!(envelope('rec-1', 'progress', {}))).not.toThrow() // unknown type
      expect(() => capturedCb!(envelope('rec-1', 'record_event', undefined))).not.toThrow() // empty payload

      expect(onStep).not.toHaveBeenCalled()
      expect(onError).not.toHaveBeenCalled()
      expect(onStopped).not.toHaveBeenCalled()
    })
  })

  describe('finish', () => {
    beforeEach(async () => {
      await svc.initialize()
    })

    it('clears all three callbacks — later events for that id are ignored', () => {
      const onStep = vi.fn()
      const onError = vi.fn()
      const onStopped = vi.fn()
      svc.onStep('rec-1', onStep)
      svc.onError('rec-1', onError)
      svc.onStopped('rec-1', onStopped)

      svc.finish('rec-1')

      capturedCb!(envelope('rec-1', 'record_event', { step: 'x' }))
      capturedCb!(envelope('rec-1', 'error', { message: 'e' }))
      capturedCb!(envelope('rec-1', 'record_stopped', { steps: [] }))

      expect(onStep).not.toHaveBeenCalled()
      expect(onError).not.toHaveBeenCalled()
      expect(onStopped).not.toHaveBeenCalled()
    })
  })

  describe('stopRecording', () => {
    beforeEach(async () => {
      await svc.initialize()
    })

    it('issues automation.record_stop and passes the unwrapped result through', async () => {
      const result = { steps: ['s1', 's2'], record_device: 'dev-1' }
      callBackendAPI.mockResolvedValueOnce(result)

      await expect(svc.stopRecording('dev-1')).resolves.toEqual(result)
      expect(callBackendAPI).toHaveBeenCalledWith('automation.record_stop', { device_id: 'dev-1' })
    })
  })
})
