/**
 * useAppBootstrap — startup ordering.
 *
 * The splash used to wait for `config + tools` in series, and the tools stage
 * forced a full re-probe of every tool on every launch. These tests lock in the
 * two properties that made startup slow: the probe must overlap the other
 * stages, and it must never be awaited past its guard.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

const appConfigStore = {
  initialize: vi.fn(async () => {}),
  get: vi.fn(() => undefined),
}
const systemStore = {
  fetchSystemInfo: vi.fn(async () => {}),
  fetchBuildInfo: vi.fn(async () => {}),
}
const toolStore = {
  fetchTools: vi.fn(async () => []),
}

const themeService = {
  setTheme: vi.fn(async () => null),
  applyTheme: vi.fn(async () => null),
  getActualTheme: vi.fn(() => 'light'),
  onChange: vi.fn(),
}
const settingsService = { loadSettingsModel: vi.fn(async () => ({ settings: { theme: 'light' } })) }
const deviceService = { refreshDevices: vi.fn(async () => {}), startMonitoring: vi.fn() }

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: ref('zh-CN') }),
}))

vi.mock('@/renderer/services/registry', () => ({ registerServices: vi.fn() }))

vi.mock('@/renderer/services/ServiceManager', () => ({
  default: {
    getService: vi.fn(async (name: string) => {
      if (name === 'theme') return themeService
      if (name === 'settings') return settingsService
      if (name === 'device') return deviceService
      if (name === 'cache') throw new Error('cache must not be touched during bootstrap')
      return {}
    }),
  },
}))

vi.mock('@/renderer/stores/index', () => ({
  useAppConfigStore: () => appConfigStore,
  useSystemStore: () => systemStore,
  useToolStore: () => toolStore,
}))

vi.mock('@/renderer/stores/rendererLogStore', () => ({
  useRendererLogStore: () => ({ push: vi.fn() }),
}))

vi.mock('@/renderer/api/unifiedApi', () => ({
  default: { getAPI: () => ({ appConfig: { get: async () => null } }) },
}))

vi.mock('@/renderer/utils/logger', () => ({
  log: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
  setLogLevel: vi.fn(),
  _setRingPusher: vi.fn(),
}))

vi.mock('@/renderer/services/TaskExecutionService', () => ({ setMaxConcurrent: vi.fn() }))

import { useAppBootstrap } from '@/renderer/composables/useAppBootstrap'
import { log } from '@/renderer/utils/logger'

interface Bootstrap {
  isLoading: Ref<boolean>
  progress: Ref<number>
  step: Ref<string>
  error: Ref<string>
}

let bootstrap: Bootstrap | null = null

const Host = defineComponent({
  setup() {
    bootstrap = useAppBootstrap(ref(null)) as unknown as Bootstrap
    return () => null
  },
})

function mountHost() {
  bootstrap = null
  mount(Host, { global: { plugins: [createPinia()] } })
  return () => bootstrap!
}

/** Let queued microtasks/timers settle. */
const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  vi.clearAllMocks()
  appConfigStore.get.mockReturnValue(undefined)
  appConfigStore.initialize.mockResolvedValue(undefined)
  systemStore.fetchSystemInfo.mockResolvedValue(undefined)
  systemStore.fetchBuildInfo.mockResolvedValue(undefined)
  toolStore.fetchTools.mockResolvedValue([])
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useAppBootstrap — tool probing is overlapped, not inline', () => {
  it('starts the probe while the config stage is still in flight', async () => {
    let releaseConfig!: () => void
    appConfigStore.initialize.mockReturnValue(
      new Promise<void>((resolve) => {
        releaseConfig = resolve
      })
    )

    const get = mountHost()
    await vi.waitFor(() => expect(toolStore.fetchTools).toHaveBeenCalled())

    // Config has not resolved yet — but the probe is already running, which is
    // the whole point: `max(config, tools)` instead of `config + tools`.
    expect(vi.mocked(log.debug).mock.calls.some(([m]) => String(m).includes('[startup] config'))).toBe(false)
    expect(get().isLoading.value).toBe(true)

    releaseConfig()
    await vi.waitFor(() => expect(get().isLoading.value).toBe(false))
    expect(get().progress.value).toBe(100)
  })

  it('does not force a cache-invalidating refresh', async () => {
    const get = mountHost()
    await vi.waitFor(() => expect(get().isLoading.value).toBe(false))

    expect(toolStore.fetchTools).toHaveBeenCalledWith(false)
  })

  it('records one startup line per stage', async () => {
    const get = mountHost()
    await vi.waitFor(() => expect(get().isLoading.value).toBe(false))

    const lines = vi.mocked(log.debug).mock.calls.map(([m]) => String(m))
    for (const key of ['services', 'config', 'tools', 'ui']) {
      expect(lines.some((line) => line.startsWith(`[startup] ${key} `))).toBe(true)
    }
  })
})

describe('useAppBootstrap — tool probe guard', () => {
  it('opens the app when the probe outlives the guard', async () => {
    vi.useFakeTimers()
    // A probe that never settles: the splash must not wait forever.
    toolStore.fetchTools.mockReturnValue(new Promise<never>(() => {}))

    const get = mountHost()
    await vi.advanceTimersByTimeAsync(5000)
    await vi.advanceTimersByTimeAsync(100)

    expect(get().isLoading.value).toBe(false)
    expect(vi.mocked(log.warn).mock.calls.some(([m]) => String(m).includes('still running'))).toBe(true)
  })

  it('keeps the probe failure out of the splash error path', async () => {
    toolStore.fetchTools.mockRejectedValue(new Error('backend down'))

    const get = mountHost()
    await vi.waitFor(() => expect(get().isLoading.value).toBe(false))

    // tools is non-critical: a dead probe must not surface as an init failure.
    expect(get().error.value).toBe('')
    expect(log.error).toHaveBeenCalled()
  })
})

describe('useAppBootstrap — critical stages', () => {
  it('reports a failed critical stage and keeps the splash up', async () => {
    appConfigStore.initialize.mockRejectedValue(new Error('config exploded'))

    const get = mountHost()
    await vi.waitFor(() => expect(get().error.value).not.toBe(''))

    expect(get().error.value).toContain('config exploded')
    expect(get().isLoading.value).toBe(true)
  })
})
