/**
 * RecordPanel mount tests (plan: .omo/plans/adb-auto-test.md, Todo 4).
 *
 * Mock strategy (mirrors Notification.test.ts):
 *  - @services/ServiceManager is module-mocked; getService resolves a
 *    programmable recording-service mock whose call order is recorded.
 *  - naive-ui's useMessage is replaced so message.error/warning are
 *    assertable without an <n-message-provider> ancestor.
 *  - vue-i18n's useI18n returns a loose identity t() — the
 *    automation.record* keys are added by a later task (T6); a missing
 *    key must never break these assertions (t renders the key itself).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia } from 'pinia'
import { useDeviceStore } from '@stores/deviceStore'

type AnyCb = (...args: any[]) => void

const { mockRecordingService, mockMessage, callOrder, callbacks } = vi.hoisted(() => {
  const callOrder: string[] = []
  const callbacks: Record<string, AnyCb> = {}
  return {
    callOrder,
    callbacks,
    mockMessage: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    },
    mockRecordingService: {
      initialize: vi.fn(async () => { callOrder.push('initialize') }),
      // Mirrors the real service: callbacks passed with the start call are
      // live BEFORE it resolves. Fires one in-flight step synchronously so
      // tests can observe subscription-precedes-launch.
      startRecording: vi.fn(async (_deviceId: string, cbs: any) => {
        callOrder.push('startRecording')
        Object.assign(callbacks, cbs)
        cbs?.onStep?.({ action: 'tap', x: 7, y: 8 })
        return 'rec-test-id'
      }),
      stopRecording: vi.fn(async () => ({ steps: [], record_device: 'dev-1' })),
      finish: vi.fn(),
    },
  }
})

vi.mock('@services/ServiceManager', () => ({
  default: {
    getService: vi.fn(() => Promise.resolve(mockRecordingService)),
    getServiceSync: vi.fn(),
    register: vi.fn(),
  },
}))

vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return { ...actual, useMessage: () => mockMessage }
})

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import RecordPanel from '@/renderer/components/automation/RecordPanel.vue'

function mountPanel(disabled = false) {
  const pinia = createPinia()
  const wrapper = mount(RecordPanel, {
    props: { disabled },
    global: { plugins: [pinia] },
  })
  return { wrapper, store: useDeviceStore(pinia) }
}

function findButton(wrapper: any, label: string) {
  return wrapper.findAll('button').find((b: any) => b.text().includes(label))
}

function isDisabled(btn: any): boolean {
  return (btn.element as HTMLButtonElement).disabled
}

async function selectDevice(store: any, id = 'dev-1') {
  store.selectedDeviceId = id
  await nextTick()
}

async function startRecording(wrapper: any) {
  await findButton(wrapper, 'automation.recordStart').trigger('click')
  await flushPromises()
}

describe('RecordPanel', () => {
  beforeEach(() => {
    callOrder.length = 0
    for (const k of Object.keys(callbacks)) delete callbacks[k]
    vi.clearAllMocks()
  })

  it('disables the start button and shows the empty state when no device is selected', async () => {
    const { wrapper } = mountPanel()
    await nextTick()

    const start = findButton(wrapper, 'automation.recordStart')
    expect(start).toBeTruthy()
    expect(isDisabled(start)).toBe(true)
    expect(wrapper.text()).toContain('automation.recordEmpty')

    await start.trigger('click')
    await flushPromises()
    expect(mockRecordingService.startRecording).not.toHaveBeenCalled()
    expect(mockRecordingService.initialize).not.toHaveBeenCalled()
  })

  it('disables the start button when props.disabled is true', async () => {
    const { wrapper, store } = mountPanel(true)
    await selectDevice(store)

    const start = findButton(wrapper, 'automation.recordStart')
    expect(isDisabled(start)).toBe(true)
  })

  it('starts a recording: callbacks live before launch — in-flight step survives, later steps appended', async () => {
    const { wrapper, store } = mountPanel()
    await selectDevice(store)
    await startRecording(wrapper)

    // Callbacks ride with the start call (the service registers them before
    // the backend call); initialize still precedes startRecording.
    expect(callOrder).toEqual(['initialize', 'startRecording'])
    expect(mockRecordingService.startRecording).toHaveBeenCalledWith('dev-1', {
      onStep: expect.any(Function),
      onError: expect.any(Function),
      onStopped: expect.any(Function),
    })

    expect(wrapper.emitted('recording-start')).toHaveLength(1)
    expect(findButton(wrapper, 'automation.recordStop')).toBeTruthy()
    expect(isDisabled(findButton(wrapper, 'automation.recordStart'))).toBe(true)

    // Observable proof of subscription-before-launch: the mock fired
    // cbs.onStep synchronously inside startRecording (before resolving);
    // that in-flight step must be rendered and must survive the await.
    const inflight = wrapper.findAll('.step-line')
    expect(inflight).toHaveLength(1)
    expect(inflight[0].text()).toContain('#1')
    expect(inflight[0].text()).toContain('7,8')

    // Two more live steps → rows with index + action label + coordinate summary
    callbacks.onStep({ action: 'tap', x: 100, y: 200 })
    await nextTick()
    callbacks.onStep({ action: 'swipe', x1: 30, y1: 40, x2: 80, y2: 120, duration_ms: 300 })
    await nextTick()

    const rows = wrapper.findAll('.step-line')
    expect(rows).toHaveLength(3)
    expect(rows[1].text()).toContain('#2')
    expect(rows[1].text()).toContain('tap')
    expect(rows[1].text()).toContain('100,200')
    expect(rows[2].text()).toContain('swipe')
    expect(rows[2].text()).toContain('30,40→80,120')
    expect(wrapper.find('.record-count').text()).toBe('3')
    expect(wrapper.text()).not.toContain('automation.recordEmpty')
  })

  it('stop via button: emits recorded with the stopRecording steps, resets, emits recording-end once', async () => {
    const { wrapper, store } = mountPanel()
    await selectDevice(store)
    await startRecording(wrapper)

    const steps = [
      { action: 'tap', x: 5, y: 6 },
      { action: 'swipe', x1: 1, y1: 2, x2: 3, y2: 4, duration_ms: 250 },
    ]
    mockRecordingService.stopRecording.mockResolvedValueOnce({ steps, record_device: 'dev-1' })

    await findButton(wrapper, 'automation.recordStop').trigger('click')
    await flushPromises()

    expect(mockRecordingService.stopRecording).toHaveBeenCalledWith('dev-1')
    const recorded = wrapper.emitted('recorded')
    expect(recorded).toHaveLength(1)
    // payload is now { steps, gap } — gap carries the auto-wait settings
    expect(recorded![0][0]).toEqual({
      steps,
      gap: { enabled: true, thresholdMs: 500, maxMs: 5000 },
    })
    expect(wrapper.emitted('recording-end')).toHaveLength(1)
    expect(mockRecordingService.finish).toHaveBeenCalledWith('rec-test-id')
    expect(isDisabled(findButton(wrapper, 'automation.recordStart'))).toBe(false)
  })

  it('startRecording rejection: error toast, recording-end emitted, start re-enabled', async () => {
    const { wrapper, store } = mountPanel()
    await selectDevice(store)
    mockRecordingService.startRecording.mockRejectedValueOnce(new Error('adb boom'))

    await findButton(wrapper, 'automation.recordStart').trigger('click')
    await flushPromises()

    expect(mockMessage.error).toHaveBeenCalledTimes(1)
    expect(mockMessage.error).toHaveBeenCalledWith('automation.recordFailed: adb boom')
    // State flips synchronously before the call (Finding 1 fix); the error
    // path rolls it back — exactly one recording-start, one recording-end.
    expect(wrapper.emitted('recording-start')).toHaveLength(1)
    expect(wrapper.emitted('recording-end')).toHaveLength(1)
    expect(isDisabled(findButton(wrapper, 'automation.recordStart'))).toBe(false)
  })

  it('onStopped (natural end): warns, emits recording-end once; recorded is never emitted from this path', async () => {
    const { wrapper, store } = mountPanel()
    await selectDevice(store)
    await startRecording(wrapper)

    callbacks.onStopped({ count: 0, record_device: 'dev-1' })
    await flushPromises()

    expect(mockMessage.warning).toHaveBeenCalledWith('automation.recordStopped')
    expect(wrapper.emitted('recorded')).toBeUndefined()
    expect(wrapper.emitted('recording-end')).toHaveLength(1)
    expect(isDisabled(findButton(wrapper, 'automation.recordStart'))).toBe(false)

    // Race: a late record_stopped event and a ref-driven stop() must not
    // emit recording-end a second time (idempotent reset via ended flag).
    callbacks.onStopped({ count: 0 })
    await flushPromises()
    await (wrapper.vm as any).stop()
    await flushPromises()
    expect(wrapper.emitted('recording-end')).toHaveLength(1)
  })

  it('onStopped ignores steps in the payload ({count} only) — recorded is not emitted', async () => {
    const { wrapper, store } = mountPanel()
    await selectDevice(store)
    await startRecording(wrapper)

    callbacks.onStopped({ count: 3, record_device: 'dev-1' })
    await flushPromises()

    expect(mockMessage.warning).toHaveBeenCalledWith('automation.recordStopped')
    expect(wrapper.emitted('recorded')).toBeUndefined()
    expect(wrapper.emitted('recording-end')).toHaveLength(1)
  })

  it('ignores a second start while the first startRecording call is still pending (reentry guard)', async () => {
    const { wrapper, store } = mountPanel()
    await selectDevice(store)

    let release!: (id: string) => void
    mockRecordingService.startRecording.mockImplementationOnce(
      () => new Promise<string>((resolve) => { release = resolve })
    )

    await findButton(wrapper, 'automation.recordStart').trigger('click')
    await flushPromises()

    // Recording state flipped synchronously while the call is in flight.
    expect(wrapper.emitted('recording-start')).toHaveLength(1)
    expect(isDisabled(findButton(wrapper, 'automation.recordStart'))).toBe(true)

    // Second click while pending → the reentry guard swallows it.
    await findButton(wrapper, 'automation.recordStart').trigger('click')
    await flushPromises()
    expect(mockRecordingService.startRecording).toHaveBeenCalledTimes(1)

    // Release the pending start — still exactly one call, one recording-start.
    release('rec-test-id')
    await flushPromises()
    expect(mockRecordingService.startRecording).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('recording-start')).toHaveLength(1)
  })

  it('stops an active recording on unmount (no orphaned backend session)', async () => {
    const { wrapper, store } = mountPanel()
    await selectDevice(store)
    await startRecording(wrapper)
    expect(mockRecordingService.stopRecording).not.toHaveBeenCalled()

    wrapper.unmount()
    await flushPromises()

    expect(mockRecordingService.stopRecording).toHaveBeenCalledWith('dev-1')
    expect(mockRecordingService.finish).toHaveBeenCalledWith('rec-test-id')
  })

  it('stopRecording rejection still resets and emits recording-end without crashing', async () => {
    const { wrapper, store } = mountPanel()
    await selectDevice(store)
    await startRecording(wrapper)

    mockRecordingService.stopRecording.mockRejectedValueOnce(new Error('device gone'))
    await (wrapper.vm as any).stop()
    await flushPromises()

    expect(mockMessage.error).toHaveBeenCalledWith('automation.recordFailed: device gone')
    expect(wrapper.emitted('recorded')).toBeUndefined()
    expect(wrapper.emitted('recording-end')).toHaveLength(1)
    expect(isDisabled(findButton(wrapper, 'automation.recordStart'))).toBe(false)
    expect(findButton(wrapper, 'automation.recordStop')).toBeUndefined()
  })
})
