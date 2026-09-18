/**
 * Page glue regression: `assert_activity`「抓取当前」 → device.current_activity.
 *
 * Contract under test (src/renderer/views/OtherToolsPage.vue):
 *   - the page owns the backend call + the device id (the step form only
 *     emits `grabActivity`; StepListEditor forwards it with the row index);
 *   - on success the returned `activity` string is written back into the
 *     edited step through the SAME path the element pick uses
 *     (`store.editor.steps` rebuild), with the exact value;
 *   - on failure the existing error-toast idiom fires and the field is NOT
 *     touched.
 *
 * Mount setup mirrors tests/unit/views/OtherToolsPage.toolInstall.test.ts
 * (same ServiceManager / naive-ui / vue-i18n mocks, same electronAPI stub);
 * it seeds a project + script + assert_activity step so the editor renders.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'

const { mockMessage, cfgStore, backend } = vi.hoisted(() => ({
  mockMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  cfgStore: { automation: { version: 2, projects: [] as any[] } },
  backend: {
    currentActivity: { success: true, activity: '', error: '' } as any,
    calls: [] as Array<{ method: string; params: any }>,
  },
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
      clearTrafficCache: vi.fn(),
      getTrafficStatus: vi.fn(async () => ({ ready: true })),
      getImeStatus: vi.fn(async () => ({ installed: true })),
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
import ProjectTree from '@components/automation/ProjectTree.vue'
import StepListEditor from '@components/automation/StepListEditor.vue'
import { useDeviceStore } from '@stores/deviceStore'

const DEVICE_ID = 'emulator-5554'
const STEP = { id: 'st1', action: 'assert_activity', activity: '' }

function seedConfig() {
  cfgStore.automation = {
    version: 2,
    projects: [
      {
        id: 'p1',
        name: 'P',
        scripts: [
          { id: 's1', name: 'S', updated_at: '', steps: [{ ...STEP }] },
        ],
      },
    ],
  }
}

function mountPage() {
  ;(window as any).electronAPI = {
    appConfig: {
      get: async (key?: string) => (key ? (cfgStore as any)[key] : cfgStore),
      set: async () => ({ success: true }),
      setMany: async () => ({ success: true }),
      getAll: async () => cfgStore,
      reset: async () => undefined,
    },
    callBackendAPI: async (method: string, params: any) => {
      backend.calls.push({ method, params })
      if (method === 'automation.list_runs') return { runs: [] }
      if (method === 'device.current_activity') return backend.currentActivity
      return {}
    },
    onStreamEvent: () => () => {},
  }
  const pinia = createPinia()
  useDeviceStore(pinia).updateDevices([{ id: DEVICE_ID, status: 'device' }])
  localStorage.setItem('bt:automationDeviceId', DEVICE_ID)
  return mount(OtherToolsPage, { global: { plugins: [pinia] } })
}

/** Select the seeded project/script so the step editor + list row render. */
async function openSeededScript(wrapper: any) {
  const store = wrapper.findComponent(ProjectTree).props('store')
  store.selectScript('p1', 's1')
  await flushPromises()
  const sle = wrapper.findComponent(StepListEditor)
  expect(sle.exists()).toBe(true)
  return sle
}

describe('OtherToolsPage — grab current activity', () => {
  beforeEach(() => {
    backend.calls.length = 0
    backend.currentActivity = { success: true, activity: '', error: '' }
    localStorage.clear()
    vi.clearAllMocks()
    seedConfig()
  })

  it('writes the returned activity back into the edited step (exact value)', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const sle = await openSeededScript(wrapper)
    expect(sle.props('modelValue')).toHaveLength(1)

    backend.currentActivity = {
      success: true,
      activity: 'com.example.app/.MainActivity',
      error: '',
    }
    sle.vm.$emit('grabActivity', { index: 0 })
    await flushPromises()

    expect(sle.props('modelValue')[0]).toMatchObject({
      id: 'st1',
      action: 'assert_activity',
      activity: 'com.example.app/.MainActivity',
    })
    const call = backend.calls.find((c) => c.method === 'device.current_activity')
    expect(call).toBeTruthy()
    expect(call!.params).toEqual({ device_id: DEVICE_ID, timeout_ms: 3000 })
    expect(mockMessage.error).not.toHaveBeenCalled()
  })

  it('surfaces the backend error and leaves the field unchanged on failure', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const sle = await openSeededScript(wrapper)

    backend.currentActivity = { success: false, activity: '', error: 'boom-activity' }
    sle.vm.$emit('grabActivity', { index: 0 })
    await flushPromises()

    expect(mockMessage.error).toHaveBeenCalledWith('boom-activity')
    expect(sle.props('modelValue')[0].activity).toBe('')
  })
})
