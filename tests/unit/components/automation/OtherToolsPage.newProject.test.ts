/**
 * Automation page project creation — regression guard.
 *
 * Every tree mutation (new project / new script / rename / delete) calls
 * persist(), which ships `{ projects: projects.value }` over IPC. That value
 * is a Vue reactive proxy and used to make `ipcRenderer.invoke` reject with
 * "could not be cloned", which popped a red toast on each click. ConfigService
 * now normalizes writes to plain data; these tests cover the page-level path.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import v8 from 'node:v8'

const { mockMessage, cfgStore, setCalls } = vi.hoisted(() => ({
  mockMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  cfgStore: { automation: { projects: [] as any[] } },
  setCalls: [] as Array<{ key: string; value: any }>,
}))

vi.mock('@services/ServiceManager', () => ({
  default: {
    getService: vi.fn(() => Promise.resolve({
      initialize: vi.fn(async () => {}),
      startRecording: vi.fn(async () => 'rec-1'),
      stopRecording: vi.fn(async () => ({ steps: [] })),
      finish: vi.fn(),
      bindTask: vi.fn(),
      setCallbacks: vi.fn(),
      setPhase: vi.fn(),
      waitForPhase: vi.fn(async () => {}),
    })),
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

/** Electron clones IPC arguments; a reactive proxy fails this. */
function cloneable(value: unknown): boolean {
  try {
    v8.serialize(value)
    return true
  } catch {
    return false
  }
}

function mountPage(setImpl?: (key: string, value: any) => any) {
  ;(window as any).electronAPI = {
    appConfig: {
      get: async (key?: string) => (key ? (cfgStore as any)[key] : cfgStore),
      set: async (key: string, value: any) => {
        setCalls.push({ key, value })
        if (setImpl) return setImpl(key, value)
        ;(cfgStore as any)[key] = value
        return { success: true }
      },
      setMany: async () => ({ success: true }),
      getAll: async () => cfgStore,
      reset: async () => undefined,
    },
    onStreamEvent: () => () => {},
  }
  return mount(OtherToolsPage, { global: { plugins: [createPinia()] } })
}

async function click(wrapper: any, selector: string) {
  await wrapper.find(selector).trigger('click')
  await flushPromises()
}

describe('OtherToolsPage — project creation', () => {
  beforeEach(() => {
    setCalls.length = 0
    cfgStore.automation = { projects: [] }
    vi.clearAllMocks()
  })

  it('new project: no error toast, persisted payload is IPC-cloneable', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await click(wrapper, '.col-left .col-head button')

    expect(mockMessage.error).not.toHaveBeenCalled()
    expect(cfgStore.automation.projects).toHaveLength(1)
    const last = setCalls[setCalls.length - 1]
    expect(last.key).toBe('automation')
    expect(cloneable(last.value)).toBe(true)
  })

  it('new script: appended under the selected project, still no toast', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await click(wrapper, '.col-left .col-head button')
    await click(wrapper, '.scripts button')

    expect(mockMessage.error).not.toHaveBeenCalled()
    expect(cfgStore.automation.projects[0].scripts).toHaveLength(1)
  })

  it('a failing persist surfaces as an error toast (failures stay visible)', async () => {
    const wrapper = mountPage(() => {
      throw new Error('boom-ipc')
    })
    await flushPromises()

    await click(wrapper, '.col-left .col-head button')

    expect(mockMessage.error).toHaveBeenCalledWith('boom-ipc')
  })
})
