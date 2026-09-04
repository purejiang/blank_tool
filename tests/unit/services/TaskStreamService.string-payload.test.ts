/**
 * TaskStreamService string-payload compatibility.
 *
 * Plugins (e.g. adb_auto via PluginContext.log/error) send the line/message
 * as a BARE STRING payload ({ type, payload: "[plugin] msg" }) rather than
 * { type, payload: { line } } / { type, payload: { message } }. The service
 * must route both shapes to the callbacks.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TaskStreamService from '@services/TaskStreamService'

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
  // Matches the main process: sender.send(streamEvent, { stream_id, data: result })
  // where result = { type, payload, task_id } (the backend event).
  return { stream_id: 's', data: { type, payload, task_id: taskId } }
}

describe('TaskStreamService string payload', () => {
  let captor: { cb?: (raw: any) => void }
  let svc: TaskStreamService

  beforeEach(() => {
    captor = {}
    svc = makeService(captor)
  })

  it('routes a log event with a bare string payload to onLog', async () => {
    const onLog = vi.fn()
    await svc.initialize()
    svc.bindTask('T1')
    svc.setCallbacks('T1', { onLog })

    captor.cb!(event('T1', 'log', '[adb_auto] step 1 done'))

    expect(onLog).toHaveBeenCalledTimes(1)
    expect(onLog).toHaveBeenCalledWith('[adb_auto] step 1 done')
  })

  it('still routes an object-payload log (data.line) to onLog', async () => {
    const onLog = vi.fn()
    await svc.initialize()
    svc.bindTask('T1')
    svc.setCallbacks('T1', { onLog })

    captor.cb!(event('T1', 'log', { line: 'legacy line' }))

    expect(onLog).toHaveBeenCalledWith('legacy line')
  })

  it('routes an error event with a bare string payload to onError', async () => {
    const onError = vi.fn()
    await svc.initialize()
    svc.bindTask('T1')
    svc.setCallbacks('T1', { onError })

    captor.cb!(event('T1', 'error', '[adb_auto] boom'))

    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0][0]).toBe('[adb_auto] boom')
  })

  it('still routes an object-payload error (payload.message) to onError', async () => {
    const onError = vi.fn()
    await svc.initialize()
    svc.bindTask('T1')
    svc.setCallbacks('T1', { onError })

    captor.cb!(event('T1', 'error', { message: 'legacy error' }))

    expect(onError).toHaveBeenCalledWith('legacy error', 'download')
  })
})
