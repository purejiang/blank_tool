import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import TaskStreamService from '@services/TaskStreamService'
import type { TaskCallbacks } from '@services/TaskStreamService'

// ------------------------------------------------------------------
// Mock helpers
// ------------------------------------------------------------------

let streamHandler: ((data: any) => void) | null = null
let subscribeCount = 0
let mockOnStreamEvent: ReturnType<typeof vi.fn>

function setupMock() {
  subscribeCount = 0
  streamHandler = null
  mockOnStreamEvent = vi.fn((callback: (data: any) => void) => {
    streamHandler = callback
    subscribeCount++
    return () => {
      streamHandler = null
    }
  })
  ;(window as any).electronAPI = {
    onStreamEvent: mockOnStreamEvent,
  }
}

/** Fire a stream event into the service via the mocked onStreamEvent callback. */
function fireStreamEvent(event: any) {
  if (!streamHandler) throw new Error('onStreamEvent not subscribed — call initialize() first')
  streamHandler(event)
}

// ------------------------------------------------------------------
// Tests
// ------------------------------------------------------------------

describe('TaskStreamService', () => {
  let service: TaskStreamService

  beforeEach(() => {
    setupMock()
    service = new TaskStreamService()
  })

  afterEach(() => {
    service.destroy()
    vi.restoreAllMocks()
  })

  // 1. initialize calls onStreamEvent once
  it('1. initialize calls onStreamEvent once', async () => {
    await service.initialize()
    expect(mockOnStreamEvent).toHaveBeenCalledTimes(1)
    expect(subscribeCount).toBe(1)
  })

  // 2. Double initialize is idempotent
  it('2. Double initialize is idempotent', async () => {
    await service.initialize()
    await service.initialize()
    expect(mockOnStreamEvent).toHaveBeenCalledTimes(1)
    expect(subscribeCount).toBe(1)
  })

  // 3. bindTask + simulate progress event → onDownloadProgress called with correct args
  it('3. bindTask + progress event → onDownloadProgress called with correct args', async () => {
    await service.initialize()
    service.bindTask('1')

    const onDownloadProgress = vi.fn()
    service.setCallbacks('1', { onDownloadProgress })

    fireStreamEvent({
      data: {
        type: 'progress',
        task_id: '1',
        payload: { progress: 50, downloaded: 1024, total: 2048, speed: 100 },
      },
    })

    expect(onDownloadProgress).toHaveBeenCalledTimes(1)
    expect(onDownloadProgress).toHaveBeenCalledWith(50, 1024, 2048, 100)
  })

  // 4. Unbound task_id events ignored
  it('4. Unbound task_id events ignored', async () => {
    await service.initialize()
    const onComplete = vi.fn()
    service.bindTask('1')
    service.setCallbacks('1', { onComplete })

    // Event with unbound task_id — should be silently ignored
    fireStreamEvent({
      data: { type: 'complete', task_id: '999', payload: {} },
    })

    expect(onComplete).not.toHaveBeenCalled()
  })

  // 5. unbindTask stops event routing
  it('5. unbindTask stops event routing', async () => {
    await service.initialize()
    service.bindTask('1')
    const onDownloadProgress = vi.fn()
    service.setCallbacks('1', { onDownloadProgress })
    service.unbindTask('1')

    fireStreamEvent({
      data: {
        type: 'progress',
        task_id: '1',
        payload: { progress: 50, downloaded: 1024, total: 2048, speed: 100 },
      },
    })

    expect(onDownloadProgress).not.toHaveBeenCalled()
  })

  // 6. Latch: bindTask → complete event (no await) → waitForPhase resolves immediately
  it('6. Latch: complete arrives before waitForPhase → immediately resolves', async () => {
    await service.initialize()
    service.bindTask('1')

    // Simulate complete event BEFORE any await
    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: '1',
        payload: { file_path: '/tmp/app.apk', size: 1024 },
      },
    })

    // waitForPhase should resolve immediately with stashed result
    const result = await service.waitForPhase('1', 'download')
    expect(result).toEqual({ file_path: '/tmp/app.apk', size: 1024 })
  })

  // 7. Normal await: bindTask → waitForPhase → complete event → resolves
  it('7. Normal await: waitForPhase before complete → resolves on event', async () => {
    await service.initialize()
    service.bindTask('1')

    const phasePromise = service.waitForPhase('1', 'download')

    // Now simulate the complete event
    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: '1',
        payload: { file_path: '/tmp/app.apk' },
      },
    })

    const result = await phasePromise
    expect(result).toEqual({ file_path: '/tmp/app.apk' })
  })

  // 8. Error event rejects waitForPhase
  it('8. Error event rejects waitForPhase', async () => {
    await service.initialize()
    service.bindTask('1')
    service.setPhase('1', 'operation')

    const phasePromise = service.waitForPhase('1', 'operation')

    fireStreamEvent({
      data: {
        type: 'error',
        task_id: '1',
        payload: { message: 'Download failed' },
      },
    })

    await expect(phasePromise).rejects.toThrow('Download failed')
  })

  // 9. Cancelled event rejects waitForPhase
  it('9. Cancelled event rejects waitForPhase', async () => {
    await service.initialize()
    service.bindTask('1')

    const phasePromise = service.waitForPhase('1', 'operation')

    fireStreamEvent({
      data: { type: 'cancelled', task_id: '1', payload: { task_id: '1' } },
    })

    await expect(phasePromise).rejects.toThrow('cancelled')
  })

  // 10. Phase routing: setPhase('operation') → complete → onComplete(phase='operation')
  it('10. Phase routing: setPhase operation → complete routes to correct phase', async () => {
    await service.initialize()
    service.bindTask('1')
    service.setPhase('1', 'operation')

    const onComplete = vi.fn()
    service.setCallbacks('1', { onComplete })

    const opPromise = service.waitForPhase('1', 'operation')
    const dlPromise = service.waitForPhase('1', 'download')

    fireStreamEvent({
      data: {
        type: 'complete',
        task_id: '1',
        payload: { output_apk: '/tmp/app.apk' },
      },
    })

    // onComplete called with phase='operation'
    expect(onComplete).toHaveBeenCalledWith(
      { output_apk: '/tmp/app.apk' },
      'operation',
    )

    // Operation phase resolves
    await expect(opPromise).resolves.toEqual({ output_apk: '/tmp/app.apk' })

    // Download phase should still be pending (auto-unbind rejects it with 'unbound')
    // After auto-unbind, the download slot is settled with error 'unbound'
    await expect(dlPromise).rejects.toThrow('unbound')
  })

  // 11. Auto-unbind after complete
  it('11. Auto-unbind after complete → listeners removed', async () => {
    await service.initialize()
    service.bindTask('1')

    fireStreamEvent({
      data: { type: 'complete', task_id: '1', payload: {} },
    })

    // After auto-unbind, subsequent events should be ignored
    const onDownloadProgress = vi.fn()
    // Cannot setCallbacks on unbound task (listeners deleted), but let's try
    // re-bind and check old listener is gone
    service.bindTask('1')
    service.setCallbacks('1', { onDownloadProgress })

    // This should route to the NEW binding
    fireStreamEvent({
      data: {
        type: 'progress',
        task_id: '1',
        payload: { progress: 50, downloaded: 0, total: 0, speed: 0 },
      },
    })
    expect(onDownloadProgress).toHaveBeenCalledTimes(1)
  })

  // 12. bindTask idempotent (second call auto-unbinds first)
  it('12. bindTask idempotent — second call auto-unbinds first', async () => {
    await service.initialize()
    service.bindTask('1')

    const firstDlPromise = service.waitForPhase('1', 'download')

    // Second bind auto-unbinds first, rejecting its promises
    service.bindTask('1')

    await expect(firstDlPromise).rejects.toThrow('unbound')

    // New bind creates fresh promises
    const secondDlPromise = service.waitForPhase('1', 'download')

    fireStreamEvent({
      data: { type: 'complete', task_id: '1', payload: { fresh: true } },
    })

    await expect(secondDlPromise).resolves.toEqual({ fresh: true })
  })

  // 13. startFakeProgress calls onUpdate within ~150ms
  it('13. startFakeProgress calls onUpdate within ~150ms', async () => {
    vi.useFakeTimers()
    await service.initialize()

    const onUpdate = vi.fn()
    service.startFakeProgress('1', 50, onUpdate)

    // Advance 150ms (3 ticks at 50ms each)
    vi.advanceTimersByTime(150)

    expect(onUpdate).toHaveBeenCalled()
    const firstCall = onUpdate.mock.calls[0][0] as number
    expect(firstCall).toBeGreaterThanOrEqual(2)
    expect(firstCall).toBeLessThanOrEqual(85)

    vi.useRealTimers()
  })

  // 14. stopFakeProgress stops updates
  it('14. stopFakeProgress stops updates', async () => {
    vi.useFakeTimers()
    await service.initialize()

    const onUpdate = vi.fn()
    service.startFakeProgress('1', 50, onUpdate)

    // Advance enough to get a few calls
    vi.advanceTimersByTime(100)
    const callsBeforeStop = onUpdate.mock.calls.length
    expect(callsBeforeStop).toBeGreaterThan(0)

    service.stopFakeProgress('1')

    // Advance more — no additional calls
    vi.advanceTimersByTime(500)
    expect(onUpdate.mock.calls.length).toBe(callsBeforeStop)

    vi.useRealTimers()
  })

  // 15. unbindTask rejects pending promise with 'unbound'
  it("15. unbindTask rejects pending promise with 'unbound'", async () => {
    await service.initialize()
    service.bindTask('1')

    const phasePromise = service.waitForPhase('1', 'download')

    service.unbindTask('1')

    await expect(phasePromise).rejects.toThrow('unbound')
  })

  // 16. destroy calls unsubscribe + clears state
  it('16. destroy calls unsubscribe + clears state', async () => {
    await service.initialize()
    service.bindTask('1')

    const phasePromise = service.waitForPhase('1', 'download')

    service.destroy()

    // unsubscribe was called (streamHandler set to null by the mock's cleanup)
    expect(streamHandler).toBeNull()

    // Pending promise rejected
    await expect(phasePromise).rejects.toThrow('destroyed')
  })
})
