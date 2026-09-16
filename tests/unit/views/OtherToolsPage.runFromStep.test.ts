/**
 * Page glue regression: 「从此步开始运行」 + 步骤间隔要真的进 automation.run。
 *
 * Contract under test (src/renderer/views/OtherToolsPage.vue):
 *   - StepListEditor 的 `runFrom` 事件带着行下标到页面 → runScript(index)
 *     → `start_index` 原样上行（后端从这一步开始跑，前面的步骤不执行）；
 *   - 头部运行按钮永远是「从头跑」：`@run="() => runScript(0)"`，
 *     不因为事件参数而改变起点；
 *   - 步骤间隔来自页面偏好 `ui.stepIntervalMs`，每次运行都上行；
 *   - 起点下标会夹到 [0, steps.length - 1]（行菜单构建后步骤可能被删过）。
 *
 * Mount setup mirrors OtherToolsPage.grabActivity.test.ts (same
 * ServiceManager / naive-ui / vue-i18n mocks, same electronAPI stub).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'

const { mockMessage, cfgStore, backend } = vi.hoisted(() => ({
  mockMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  cfgStore: { automation: { version: 3, projects: [] as any[], ui: {} as any } },
  backend: { calls: [] as Array<{ method: string; params: any }> },
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
import RunControls from '@components/automation/RunControls.vue'
import StepListEditor from '@components/automation/StepListEditor.vue'
import { useDeviceStore } from '@stores/deviceStore'

const DEVICE_ID = 'emulator-5554'
const STEPS = [
  { id: 'st1', action: 'back' },
  { id: 'st2', action: 'home' },
  { id: 'st3', action: 'back' },
]

function seedConfig(ui: Record<string, unknown> = {}) {
  cfgStore.automation = {
    version: 3,
    projects: [
      {
        id: 'p1',
        name: 'P',
        scripts: [{ id: 's1', name: 'S', updated_at: '', steps: STEPS.map((s) => ({ ...s })) }],
      },
    ],
    ui: { deviceId: DEVICE_ID, stepIntervalMs: 300, ...ui },
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
      return {}
    },
    onStreamEvent: () => () => {},
    cancelRequest: async () => ({}),
  }
  const pinia = createPinia()
  useDeviceStore(pinia).updateDevices([{ id: DEVICE_ID, status: 'device' }])
  return mount(OtherToolsPage, { global: { plugins: [pinia] } })
}

async function openSeededScript(wrapper: any) {
  const store = wrapper.findComponent(ProjectTree).props('store')
  store.selectScript('p1', 's1')
  await flushPromises()
  return wrapper.findComponent(StepListEditor)
}

function runCalls() {
  return backend.calls.filter((c) => c.method === 'automation.run')
}

describe('OtherToolsPage — 从某一步开始运行', () => {
  beforeEach(() => {
    backend.calls.length = 0
    localStorage.clear()
    vi.clearAllMocks()
    seedConfig()
  })

  it('行菜单的 runFrom(index) → start_index，并且只跑这一步之后的步骤', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const sle = await openSeededScript(wrapper)
    expect(sle.props('modelValue')).toHaveLength(3)

    sle.vm.$emit('runFrom', 2)
    await flushPromises()

    const call = runCalls().at(-1)
    expect(call).toBeTruthy()
    expect(call!.params.start_index).toBe(2)
    // 完整脚本依旧上行 —— 起点是运行参数，不改写脚本内容
    expect(call!.params.steps).toHaveLength(3)
    expect(mockMessage.info).toHaveBeenCalledWith('automation.runFromStepHint')
  })

  it('头部运行按钮永远从第 0 步开始（不被事件参数带偏）', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await openSeededScript(wrapper)

    wrapper.findComponent(RunControls).vm.$emit('run')
    await flushPromises()

    expect(runCalls().at(-1)!.params.start_index).toBe(0)
    // 从头跑不给「从第 N 步开始」的提示
    expect(mockMessage.info).not.toHaveBeenCalledWith('automation.runFromStepHint')
  })

  it('起点下标夹到合法范围（行菜单构建后步骤被删过）', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const sle = await openSeededScript(wrapper)

    sle.vm.$emit('runFrom', 99)
    await flushPromises()
    expect(runCalls().at(-1)!.params.start_index).toBe(2)

    sle.vm.$emit('runFrom', -3)
    await flushPromises()
    expect(runCalls().at(-1)!.params.start_index).toBe(0)
  })

  it('步骤间隔跟着页面偏好走（含 0 = 不插入等待）', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await openSeededScript(wrapper)

    wrapper.findComponent(RunControls).vm.$emit('run')
    await flushPromises()
    expect(runCalls().at(-1)!.params.step_interval_ms).toBe(300)

    // 运行配置里把间隔改成 120：写进 ui 并持久化，下一次运行就用新值
    const controls = wrapper.findComponent(RunControls)
    controls.vm.$emit('update:stepIntervalMs', 120)
    await flushPromises()
    expect(controls.props('stepIntervalMs')).toBe(120)

    controls.vm.$emit('run')
    await flushPromises()
    expect(runCalls().at(-1)!.params.step_interval_ms).toBe(120)

    controls.vm.$emit('update:stepIntervalMs', 0)
    await flushPromises()
    controls.vm.$emit('run')
    await flushPromises()
    // 0 必须原样上行（不能被 || 兜成默认值）
    expect(runCalls().at(-1)!.params.step_interval_ms).toBe(0)
  })
})
