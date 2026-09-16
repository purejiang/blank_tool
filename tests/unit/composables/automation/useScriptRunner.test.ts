/**
 * useScriptRunner — run lifecycle bounds (P2-7 状态收敛).
 *
 * Two leaks lived here:
 *  - the live console array grew without limit for the whole run (a long
 *    element-polling script can emit tens of thousands of lines), and
 *  - an IPC-level failure left the task registered in TaskStreamService for
 *    the rest of the session, because no stream event ever arrives to unbind
 *    it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const taskStream = {
  bindTask: vi.fn(),
  setCallbacks: vi.fn(),
  setPhase: vi.fn(),
  waitForPhase: vi.fn(async () => {}),
  unbindTask: vi.fn(),
}

vi.mock('@services/ServiceManager', () => ({
  default: { getService: vi.fn(async () => taskStream) },
}))

import { useScriptRunner, LOG_LIMIT } from '@/renderer/composables/automation/useScriptRunner'

let callbacks: any = null
const callBackendAPI = vi.fn(async () => ({}))
const cancelRequest = vi.fn(async () => ({}))

function setup() {
  ;(window as any).electronAPI = { callBackendAPI, cancelRequest }
  taskStream.setCallbacks.mockImplementation((_id: string, cb: any) => {
    callbacks = cb
  })
  return useScriptRunner()
}

const payload = () => ({
  device_id: 'dev',
  package_name: 'com.demo',
  steps: [{ action: 'back' }],
  capture_traffic: false,
})

beforeEach(() => {
  callbacks = null
  vi.clearAllMocks()
  taskStream.waitForPhase.mockResolvedValue(undefined)
  callBackendAPI.mockResolvedValue({})
})

describe('useScriptRunner — live log ring buffer', () => {
  it('keeps the newest LOG_LIMIT lines and drops the oldest', async () => {
    const r = setup()
    const run = r.runScript(payload())
    await vi.waitFor(() => expect(callbacks).toBeTruthy())

    for (let i = 0; i < LOG_LIMIT + 200; i++) callbacks.onLog(`line-${i}`)
    expect(r.logs.length).toBe(LOG_LIMIT)
    expect(r.logs[r.logs.length - 1].text).toBe(`line-${LOG_LIMIT + 199}`)
    expect(r.logs[0].text).toBe('line-200')
    expect(r.droppedLogs).toBe(true)
    await run
  })

  it('does not flag truncation for a run that stays under the cap', async () => {
    const r = setup()
    const run = r.runScript(payload())
    await vi.waitFor(() => expect(callbacks).toBeTruthy())
    callbacks.onLog('only line')
    expect(r.logs.length).toBe(1)
    expect(r.droppedLogs).toBe(false)
    await run
  })

  it('resets the buffer and the flag for every run', async () => {
    const r = setup()
    const first = r.runScript(payload())
    await vi.waitFor(() => expect(callbacks).toBeTruthy())
    for (let i = 0; i < LOG_LIMIT + 1; i++) callbacks.onLog(`x${i}`)
    expect(r.droppedLogs).toBe(true)
    await first

    const second = r.runScript(payload())
    expect(r.logs).toEqual([])
    expect(r.droppedLogs).toBe(false)
    await second
  })
})

describe('useScriptRunner — task release', () => {
  it('keeps the task bound on the happy path (the stream unbinds it)', async () => {
    const r = setup()
    await r.runScript(payload())
    expect(taskStream.bindTask).toHaveBeenCalledTimes(1)
    expect(taskStream.unbindTask).not.toHaveBeenCalled()
    expect(r.running).toBe(false)
  })

  it('unbinds the task when the IPC call itself fails', async () => {
    const r = setup()
    callBackendAPI.mockRejectedValue(new Error('backend down'))
    await expect(r.runScript(payload())).rejects.toThrow('backend down')
    expect(taskStream.unbindTask).toHaveBeenCalledWith(r.taskId)
    expect(r.running).toBe(false)
    expect(r.logs[r.logs.length - 1].text).toBe('[ERROR] backend down')
  })

  it('does not unbind again when the stream already reported cancelled/unbound', async () => {
    const r = setup()
    callBackendAPI.mockRejectedValue(new Error('cancelled'))
    await expect(r.runScript(payload())).resolves.toBeUndefined()
    expect(taskStream.unbindTask).not.toHaveBeenCalled()
    expect(r.logs).toEqual([])
    expect(r.running).toBe(false)
  })
})

describe('useScriptRunner — stop', () => {
  it('cancels through request.cancel (the only path that signals stop_event)', async () => {
    const r = setup()
    const run = r.runScript(payload())
    await vi.waitFor(() => expect(r.taskId).toBeTruthy())
    await r.stopRun()
    expect(cancelRequest).toHaveBeenCalledWith(r.taskId)
    await run
  })

  it('is a no-op before any run', async () => {
    const r = setup()
    await r.stopRun()
    expect(cancelRequest).not.toHaveBeenCalled()
  })
})
