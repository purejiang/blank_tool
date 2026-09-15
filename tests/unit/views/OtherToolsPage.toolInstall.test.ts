/**
 * R4 — page glue regression: ToolInstallModal `changed` → page refresh.
 *
 * Contract under test (src/renderer/views/OtherToolsPage.vue, committed in
 * bb8d9b9): when the tool-install modal reports a successful install, the
 * page must, in order:
 *   1. automationService.clearTrafficCache()   (drop cached probe results)
 *   2. refreshTrafficStatus(true)              (forced re-probe → getTrafficStatus(true))
 *   3. refreshImeStatus(autoDeviceId.value)    (getImeStatus(current device))
 *
 * Setup mirrors tests/unit/components/automation/OtherToolsPage.newProject.test.ts
 * (same ServiceManager / naive-ui / vue-i18n mocks, same electronAPI stub);
 * it only adds a pre-populated device store so `autoDeviceId` survives the
 * page's "drop vanished device" watch and holds a real id.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'

const { mockMessage, cfgStore, setCalls, automationSvc } = vi.hoisted(() => ({
  mockMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  cfgStore: { automation: { projects: [] as any[] } },
  setCalls: [] as Array<{ key: string; value: any }>,
  automationSvc: {
    // runner/recording surface (same stub methods as the newProject reference)
    initialize: vi.fn(async () => {}),
    startRecording: vi.fn(async () => 'rec-1'),
    stopRecording: vi.fn(async () => ({ steps: [] })),
    finish: vi.fn(),
    bindTask: vi.fn(),
    setCallbacks: vi.fn(),
    setPhase: vi.fn(),
    waitForPhase: vi.fn(async () => {}),
    // probe-cache glue under test
    clearTrafficCache: vi.fn(),
    getTrafficStatus: vi.fn(async () => ({ ready: true })),
    getImeStatus: vi.fn(async () => ({ installed: true })),
  },
}))

vi.mock('@services/ServiceManager', () => ({
  default: {
    getService: vi.fn(() => Promise.resolve(automationSvc)),
    getServiceSync: vi.fn(),
    register: vi.fn(),
  },
}))

vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return {
    ...actual,
    useMessage: () => mockMessage,
    useDialog: () => ({ warning: vi.fn() }),
  }
})

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import OtherToolsPage from '@views/OtherToolsPage.vue'
import ToolInstallModal from '@components/automation/ToolInstallModal.vue'
import { useDeviceStore } from '@stores/deviceStore'

function mountPage(opts?: { deviceId?: string }) {
  ;(window as any).electronAPI = {
    appConfig: {
      get: async (key?: string) => (key ? (cfgStore as any)[key] : cfgStore),
      set: async (key: string, value: any) => {
        setCalls.push({ key, value })
        ;(cfgStore as any)[key] = value
        return { success: true }
      },
      setMany: async () => ({ success: true }),
      getAll: async () => cfgStore,
      reset: async () => undefined,
    },
    onStreamEvent: () => () => {},
  }
  const pinia = createPinia()
  if (opts?.deviceId) {
    // The page keeps autoDeviceId only while it exists in the live device
    // list; seed both sources before mount so the id survives setup.
    useDeviceStore(pinia).updateDevices([{ id: opts.deviceId, status: 'device' }])
    localStorage.setItem('bt:automationDeviceId', opts.deviceId)
  }
  return mount(OtherToolsPage, { global: { plugins: [pinia] } })
}

async function click(wrapper: any, selector: string) {
  await wrapper.find(selector).trigger('click')
  await flushPromises()
}

/** The header entry button — no data-testid, bound to automation.toolsInstall. */
const TOOLS_INSTALL_BTN = 'button[aria-label="automation.toolsInstall"]'

describe('OtherToolsPage — tool install changed → refresh glue', () => {
  beforeEach(() => {
    setCalls.length = 0
    cfgStore.automation = { projects: [] }
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('header button opens the modal; changed → clearTrafficCache then forced re-probe of traffic + ime', async () => {
    const wrapper = mountPage({ deviceId: 'emulator-5554' })
    await flushPromises()

    // modal starts closed, header button drives v-model:show
    const modal = wrapper.findComponent(ToolInstallModal)
    expect(modal.props('show')).toBe(false)
    await click(wrapper, TOOLS_INSTALL_BTN)
    expect(modal.props('show')).toBe(true)

    // drop the mount/open-probe noise so only the changed handler remains
    automationSvc.clearTrafficCache.mockClear()
    automationSvc.getTrafficStatus.mockClear()
    automationSvc.getImeStatus.mockClear()

    modal.vm.$emit('changed')
    await flushPromises()

    expect(automationSvc.clearTrafficCache).toHaveBeenCalledTimes(1)

    // Order binds: the re-probes must happen AFTER the cache clear, and with
    // exact arguments (force=true traffic re-probe, current device id for ime).
    const clearOrder = automationSvc.clearTrafficCache.mock.invocationCallOrder[0]
    const trafficIdx = automationSvc.getTrafficStatus.mock.invocationCallOrder
      .findIndex(o => o > clearOrder)
    expect(trafficIdx).toBeGreaterThan(-1)
    expect(automationSvc.getTrafficStatus.mock.calls[trafficIdx]).toEqual([true])
    const imeIdx = automationSvc.getImeStatus.mock.invocationCallOrder
      .findIndex(o => o > clearOrder)
    expect(imeIdx).toBeGreaterThan(-1)
    expect(automationSvc.getImeStatus.mock.calls[imeIdx]).toEqual(['emulator-5554'])
  })

  it('opening the modal alone does not clear the probe cache (negative control)', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await click(wrapper, TOOLS_INSTALL_BTN)
    expect(wrapper.findComponent(ToolInstallModal).props('show')).toBe(true)

    expect(automationSvc.clearTrafficCache).not.toHaveBeenCalled()
  })

  it('no once-latch: every changed emission re-runs the refresh glue', async () => {
    const wrapper = mountPage({ deviceId: 'emulator-5554' })
    await flushPromises()

    await click(wrapper, TOOLS_INSTALL_BTN)
    const modal = wrapper.findComponent(ToolInstallModal)
    await flushPromises()

    modal.vm.$emit('changed')
    await flushPromises()
    expect(automationSvc.clearTrafficCache).toHaveBeenCalledTimes(1)

    modal.vm.$emit('changed')
    await flushPromises()
    expect(automationSvc.clearTrafficCache).toHaveBeenCalledTimes(2)
    // the second emission forced a fresh re-probe with exact arguments
    expect(automationSvc.getTrafficStatus.mock.lastCall).toEqual([true])
    expect(automationSvc.getImeStatus.mock.lastCall).toEqual(['emulator-5554'])
  })
})
