import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the typed API accessor — AutomationService resolves callBackendAPI
// through requireApiMethod at call time.
vi.mock('@/renderer/api/apiAccess', () => ({
  requireApiMethod: vi.fn(() => mockCallBackendAPI),
}))

vi.mock('@utils/logger', () => ({
  log: { error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}))

import AutomationService, {
  INSTALL_IDLE_TIMEOUT,
  INSTALL_IDLE_TIMEOUT_MS,
} from '@/renderer/services/AutomationService'

const mockCallBackendAPI = vi.fn()

describe('AutomationService', () => {
  let service: InstanceType<typeof AutomationService>

  beforeEach(() => {
    vi.clearAllMocks()
    service = new AutomationService()
  })

  describe('getTrafficStatus', () => {
    it('returns the backend capability report', async () => {
      mockCallBackendAPI.mockResolvedValue({
        installed: true,
        ready: true,
        lib_path: 'D:/runtime/mitmproxy/lib',
        python_mismatch: null,
      })

      const status = await service.getTrafficStatus()
      expect(status).toEqual({
        installed: true,
        ready: true,
        lib_path: 'D:/runtime/mitmproxy/lib',
        python_mismatch: null,
      })
      expect(mockCallBackendAPI).toHaveBeenCalledWith('automation.traffic_status', {})
    })

    it('caches the probe unless force=true', async () => {
      mockCallBackendAPI.mockResolvedValue({
        installed: false, ready: false, lib_path: 'x', python_mismatch: null,
      })

      await service.getTrafficStatus()
      await service.getTrafficStatus()
      expect(mockCallBackendAPI).toHaveBeenCalledTimes(1)

      await service.getTrafficStatus(true)
      expect(mockCallBackendAPI).toHaveBeenCalledTimes(2)
    })

    it('returns null (unknown state) when the probe fails', async () => {
      mockCallBackendAPI.mockRejectedValue(new Error('backend down'))
      const status = await service.getTrafficStatus(true)
      expect(status).toBeNull()
    })
  })

  describe('getImeStatus', () => {
    it('probes the requested device', async () => {
      mockCallBackendAPI.mockResolvedValue({
        device_id: 'emulator-5554',
        package: 'com.android.adbkeyboard/.AdbIME',
        installed: true,
        active: true,
      })

      const status = await service.getImeStatus('emulator-5554')
      expect(status?.installed).toBe(true)
      expect(status?.active).toBe(true)
      expect(mockCallBackendAPI).toHaveBeenCalledWith(
        'automation.ime_status', { device_id: 'emulator-5554' },
      )
    })

    it('returns null for an empty device id without calling the backend', async () => {
      const status = await service.getImeStatus('')
      expect(status).toBeNull()
      expect(mockCallBackendAPI).not.toHaveBeenCalled()
    })

    it('returns null when the probe fails', async () => {
      mockCallBackendAPI.mockRejectedValue(new Error('adb not found'))
      const status = await service.getImeStatus('emulator-5554')
      expect(status).toBeNull()
    })
  })

  // ------------------------------------------------------------------
  // Streaming installs — envelope contract (anchor: RecordingService.test.ts):
  //   { stream_id, data: { type, payload, task_id } }
  // ------------------------------------------------------------------

  function envelope(taskId: string | number, type: string, payload: any) {
    return { stream_id: 's', data: { type, payload, task_id: taskId } }
  }

  describe('initialize', () => {
    it('subscribes to onStreamEvent exactly once (idempotent)', async () => {
      let subscribeCount = 0
      ;(window as any).electronAPI = {
        onStreamEvent: (cb: (raw: any) => void) => {
          subscribeCount++
          return () => {}
        },
      }
      await service.initialize()
      await service.initialize()
      expect(subscribeCount).toBe(1)
    })

    it('does not throw when onStreamEvent is unavailable', async () => {
      ;(window as any).electronAPI = {}
      await expect(service.initialize()).resolves.toBeUndefined()
    })
  })

  describe('installMitmproxy', () => {
    let capturedCb: ((raw: any) => void) | null

    beforeEach(async () => {
      capturedCb = null
      ;(window as any).electronAPI = {
        onStreamEvent: (cb: (raw: any) => void) => {
          capturedCb = cb
          return () => {}
        },
        callBackendAPI: mockCallBackendAPI,
      }
      mockCallBackendAPI.mockResolvedValue(undefined)
      await service.initialize()
    })

    it('issues automation.install_mitmproxy with a toolinstall-<uuid> task_id', async () => {
      const promise = service.installMitmproxy()
      expect(mockCallBackendAPI).toHaveBeenCalledTimes(1)
      expect(mockCallBackendAPI).toHaveBeenCalledWith(
        'automation.install_mitmproxy',
        expect.objectContaining({ task_id: expect.stringMatching(/^toolinstall-[0-9a-f-]{36}$/) }),
      )

      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id
      capturedCb!(envelope(taskId, 'complete', { success: true, ready: true }))
      await expect(promise).resolves.toEqual({ success: true, ready: true })
    })

    it('routes log events for the matching task_id to onLog', async () => {
      const onLog = vi.fn()
      const promise = service.installMitmproxy({ onLog })
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id

      capturedCb!(envelope(taskId, 'log', { line: 'pip install start' }))

      expect(onLog).toHaveBeenCalledWith('pip install start')
      capturedCb!(envelope(taskId, 'complete', { success: true }))
      await promise
    })

    it('drops events with a different task_id', async () => {
      const onLog = vi.fn()
      const promise = service.installMitmproxy({ onLog })
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id

      capturedCb!(envelope('toolinstall-OTHER', 'log', { line: 'foreign' }))

      expect(onLog).not.toHaveBeenCalled()
      capturedCb!(envelope(taskId, 'complete', { success: true }))
      await promise
    })

    it('resolves with the exact degraded payload (not a rejection)', async () => {
      const degraded = {
        success: false,
        degraded: true,
        manual_command: '"C:/rt/python/python.exe" -m pip install --target "D:/rt/mitmproxy/lib" --upgrade mitmproxy',
        lib_path: 'D:/rt/mitmproxy/lib',
        python_bin: 'C:/rt/python/python.exe',
      }
      const promise = service.installMitmproxy()
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id

      capturedCb!(envelope(taskId, 'complete', degraded))

      await expect(promise).resolves.toEqual(degraded)
    })

    it('rejects with an Error carrying payload.message on the error event', async () => {
      const promise = service.installMitmproxy()
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id

      capturedCb!(envelope(taskId, 'error', { message: 'capture is active' }))

      await expect(promise).rejects.toThrow('capture is active')
    })

    it('removes the slot on the terminal event — later events for that task_id fire nothing', async () => {
      const onLog = vi.fn()
      const promise = service.installMitmproxy({ onLog })
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id

      capturedCb!(envelope(taskId, 'complete', { success: true }))
      await promise

      capturedCb!(envelope(taskId, 'log', { line: 'stale after terminal' }))

      expect(onLog).not.toHaveBeenCalled()
    })

    it('removes the slot and rejects when callBackendAPI itself rejects', async () => {
      let rejectedTaskId = ''
      mockCallBackendAPI.mockImplementation(async (_method: string, params: any) => {
        rejectedTaskId = params.task_id
        throw new Error('backend down')
      })
      const onLog = vi.fn()

      await expect(service.installMitmproxy({ onLog })).rejects.toThrow('backend down')

      capturedCb!(envelope(rejectedTaskId, 'log', { line: 'late' }))
      expect(onLog).not.toHaveBeenCalled()
    })
  })

  describe('installIme', () => {
    let capturedCb: ((raw: any) => void) | null

    beforeEach(async () => {
      capturedCb = null
      ;(window as any).electronAPI = {
        onStreamEvent: (cb: (raw: any) => void) => {
          capturedCb = cb
          return () => {}
        },
        callBackendAPI: mockCallBackendAPI,
      }
      mockCallBackendAPI.mockResolvedValue(undefined)
      await service.initialize()
    })

    it('issues automation.install_ime with device_id + task_id', async () => {
      const promise = service.installIme('emulator-5554')
      expect(mockCallBackendAPI).toHaveBeenCalledWith(
        'automation.install_ime',
        expect.objectContaining({ device_id: 'emulator-5554', task_id: expect.stringMatching(/^toolinstall-/) }),
      )

      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id
      capturedCb!(envelope(taskId, 'complete', { success: true, installed: true }))
      await expect(promise).resolves.toEqual({ success: true, installed: true })
    })

    it('includes apk_path only when a local APK path is supplied', async () => {
      const p1 = service.installIme('emulator-5554')
      const onlineParams = mockCallBackendAPI.mock.calls[0][1]
      expect(onlineParams).not.toHaveProperty('apk_path')
      const taskId1 = onlineParams.task_id
      capturedCb!(envelope(taskId1, 'complete', { success: true }))
      await p1

      const p2 = service.installIme('emulator-5554', undefined, 'D:/offline/ADBKeyBoard.apk')
      const offlineParams = mockCallBackendAPI.mock.calls[1][1]
      expect(offlineParams.apk_path).toBe('D:/offline/ADBKeyBoard.apk')
      const taskId2 = offlineParams.task_id
      expect(taskId2).not.toBe(taskId1)
      capturedCb!(envelope(taskId2, 'complete', { success: true }))
      await p2
    })

    it('routes progress events for the matching task_id to onProgress', async () => {
      const onProgress = vi.fn()
      const promise = service.installIme('emulator-5554', { onProgress })
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id

      const progress = { progress: 42, downloaded: 4200, total: 10000, speed: '1.2MB/s' }
      capturedCb!(envelope(taskId, 'progress', progress))

      expect(onProgress).toHaveBeenCalledWith(progress)
      capturedCb!(envelope(taskId, 'complete', { success: true }))
      await promise
    })

    it('re-invocation after a failed call mints a fresh task_id', async () => {
      mockCallBackendAPI.mockImplementationOnce(async () => {
        throw new Error('download failed')
      })
      await expect(service.installIme('emulator-5554')).rejects.toThrow('download failed')

      mockCallBackendAPI.mockResolvedValue(undefined)
      const p2 = service.installIme('emulator-5554')
      const freshId = mockCallBackendAPI.mock.calls[1][1].task_id
      expect(freshId).toMatch(/^toolinstall-/)
      capturedCb!(envelope(freshId, 'complete', { success: true }))
      await expect(p2).resolves.toEqual({ success: true })
    })
  })

  // ------------------------------------------------------------------
  // R2 install-stream watchdog: 180s of TOTAL SILENCE (no stream event
  // for the task_id) rejects the promise with the sentinel message.
  // The main-process per-request timeout deletes the request entry
  // mid-stream, so the terminal `complete` may never arrive — without
  // the watchdog the install promise never settles and the modal's
  // buttons stay wedged until app reload.
  // ------------------------------------------------------------------
  describe('install stream watchdog (inactivity)', () => {
    let capturedCb: ((raw: any) => void) | null

    beforeEach(async () => {
      capturedCb = null
      ;(window as any).electronAPI = {
        onStreamEvent: (cb: (raw: any) => void) => {
          capturedCb = cb
          return () => {}
        },
        callBackendAPI: mockCallBackendAPI,
      }
      mockCallBackendAPI.mockResolvedValue(undefined)
      vi.useFakeTimers()
      await service.initialize()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    /** Attach settle-observation BEFORE advancing time (no unhandled rejection). */
    function pendingFlag(promise: Promise<unknown>): { settled: boolean } {
      const flag = { settled: false }
      promise.then(() => { flag.settled = true }, () => { flag.settled = true })
      return flag
    }

    it('rejects with the EXACT sentinel message after 180s of total silence and clears the slot', async () => {
      const onLog = vi.fn()
      const promise = service.installMitmproxy({ onLog })
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id
      const observation = expect(promise).rejects.toMatchObject({ message: INSTALL_IDLE_TIMEOUT })

      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS)

      await observation
      // slot gone: late events for the same task_id fire nothing
      capturedCb!(envelope(taskId, 'log', { line: 'late after watchdog' }))
      capturedCb!(envelope(taskId, 'complete', { success: true }))
      expect(onLog).not.toHaveBeenCalled()
    })

    it('resets on every routed stream event — inactivity, not total-duration semantics', async () => {
      const promise = service.installMitmproxy()
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id
      const flag = pendingFlag(promise)

      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS - 1000) // 179s silent
      capturedCb!(envelope(taskId, 'log', { line: 'activity resets the watchdog' }))
      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS - 1000) // another 179s
      await Promise.resolve()

      // 358s total elapsed, but never 180s IDLE — still pending
      expect(flag.settled).toBe(false)

      capturedCb!(envelope(taskId, 'complete', { success: true }))
      await expect(promise).resolves.toEqual({ success: true })
    })

    it('clears the watchdog on the terminal complete — no timer left, no late effects', async () => {
      const timersBefore = vi.getTimerCount()
      const promise = service.installMitmproxy()
      expect(vi.getTimerCount()).toBe(timersBefore + 1) // armed at slot registration

      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id
      capturedCb!(envelope(taskId, 'complete', { success: true, ready: true }))
      await expect(promise).resolves.toEqual({ success: true, ready: true })

      expect(vi.getTimerCount()).toBe(timersBefore) // cleared on terminal
      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS)
      expect(vi.getTimerCount()).toBe(timersBefore) // nothing left to fire
    })

    it('disarms the watchdog when callBackendAPI itself rejects', async () => {
      mockCallBackendAPI.mockRejectedValueOnce(new Error('backend down'))
      await expect(service.installMitmproxy()).rejects.toThrow('backend down')

      const timersAfterRejection = vi.getTimerCount()
      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS)
      expect(vi.getTimerCount()).toBe(timersAfterRejection)
    })

    it('ime install: progress resets the watchdog, then silence rejects with the sentinel', async () => {
      const onProgress = vi.fn()
      const promise = service.installIme('emulator-5554', { onProgress })
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id
      const observation = expect(promise).rejects.toMatchObject({ message: INSTALL_IDLE_TIMEOUT })

      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS - 1000)
      capturedCb!(envelope(taskId, 'progress', { progress: 10, downloaded: 1, total: 10, speed: '1B/s' }))
      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS - 1000)
      expect(onProgress).toHaveBeenCalledTimes(1)

      // full silence from here on fires the watchdog
      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS)
      await observation
    })

    it('two successive installs get independent watchdogs — a fired one cannot affect the next', async () => {
      const p1 = service.installMitmproxy()
      const id1 = mockCallBackendAPI.mock.calls[0][1].task_id
      const observation1 = expect(p1).rejects.toMatchObject({ message: INSTALL_IDLE_TIMEOUT })
      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS)
      await observation1

      const p2 = service.installMitmproxy()
      const id2 = mockCallBackendAPI.mock.calls[1][1].task_id
      expect(id2).not.toBe(id1)
      // stale event from the fired install 1 resets nothing
      capturedCb!(envelope(id1, 'log', { line: 'stale from install 1' }))
      await vi.advanceTimersByTimeAsync(INSTALL_IDLE_TIMEOUT_MS - 1000)
      capturedCb!(envelope(id2, 'complete', { success: true }))
      await expect(p2).resolves.toEqual({ success: true })
    })
  })

  describe('malformed stream events', () => {
    let capturedCb: ((raw: any) => void) | null

    beforeEach(async () => {
      capturedCb = null
      ;(window as any).electronAPI = {
        onStreamEvent: (cb: (raw: any) => void) => {
          capturedCb = cb
          return () => {}
        },
        callBackendAPI: mockCallBackendAPI,
      }
      mockCallBackendAPI.mockResolvedValue(undefined)
      await service.initialize()
    })

    it('no throw and no callback for null / no-data / no-task_id / numeric / null-payload events', async () => {
      const onLog = vi.fn()
      const onProgress = vi.fn()
      const promise = service.installMitmproxy({ onLog, onProgress })
      const taskId = mockCallBackendAPI.mock.calls[0][1].task_id

      expect(() => capturedCb!(null)).not.toThrow()
      expect(() => capturedCb!({ stream_id: 's' })).not.toThrow()
      expect(() => capturedCb!({ stream_id: 's', data: { type: 'log', payload: { line: 'x' } } })).not.toThrow()
      expect(() => capturedCb!(envelope(42, 'log', { line: 'numeric' }))).not.toThrow()
      expect(() => capturedCb!(envelope(taskId, 'log', null))).not.toThrow()
      expect(() => capturedCb!(envelope(taskId, 'unknown_type', { whatever: 1 }))).not.toThrow()

      expect(onLog).not.toHaveBeenCalled()
      expect(onProgress).not.toHaveBeenCalled()

      capturedCb!(envelope(taskId, 'complete', { success: true }))
      await promise
    })
  })

  describe('installCa', () => {
    it('issues automation.install_ca with device_id and passes the result through', async () => {
      mockCallBackendAPI.mockResolvedValue({ success: true, already_installed: false, error: null })

      await expect(service.installCa('emulator-5554')).resolves.toEqual({
        success: true,
        already_installed: false,
        error: null,
      })
      expect(mockCallBackendAPI).toHaveBeenCalledWith('automation.install_ca', { device_id: 'emulator-5554' })
    })
  })

  describe('clearTrafficCache', () => {
    it('forces the next getTrafficStatus to re-probe the backend', async () => {
      mockCallBackendAPI.mockResolvedValue({
        installed: true, ready: true, lib_path: 'x', python_mismatch: null, ca_cert_exists: false,
      })

      await service.getTrafficStatus()
      await service.getTrafficStatus()
      expect(mockCallBackendAPI).toHaveBeenCalledTimes(1)

      service.clearTrafficCache()
      await service.getTrafficStatus()
      expect(mockCallBackendAPI).toHaveBeenCalledTimes(2)
    })
  })
})
