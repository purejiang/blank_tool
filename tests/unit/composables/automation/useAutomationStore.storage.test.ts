/**
 * `automation` app-config storage v3 — the `ui` bag.
 *
 * v2 kept six page preferences in ad-hoc `bt:*` localStorage keys and wrote
 * `{version: 2, projects}` to app-config. v3 moves them into the SAME document
 * as `ui`, so one schema owns the whole feature. The two things that can go
 * wrong here are expensive and invisible:
 *
 *  - `persist()` writes the whole document, so a project save that forgets
 *    `ui` silently resets the user's page preferences;
 *  - the v2→v3 upgrade must keep `projects` AND the user's preferences
 *    (adopted from the legacy keys exactly once).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const setAppConfig = vi.fn()
const getAppConfig = vi.fn()

vi.mock('@services/ConfigService', () => ({
  ConfigService: class {
    setAppConfig = setAppConfig
    getAppConfig = getAppConfig
  },
}))

vi.mock('naive-ui', () => ({
  useMessage: () => ({ error: () => {}, success: () => {}, warning: () => {} }),
  useDialog: () => ({ warning: () => {}, error: () => {} }),
}))

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import {
  useAutomationStore,
  sanitizeUi,
  AUTOMATION_UI_DEFAULTS,
  LEGACY_UI_KEYS,
} from '@/renderer/composables/automation/useAutomationStore'

const V2_PROJECT = {
  id: 'p1',
  name: 'demo',
  scripts: [{ id: 's1', name: 'main', updated_at: '2024-01-01T00:00:00Z', steps: [] }],
}

function store() {
  return useAutomationStore()
}

/** `loadConfig` fires the upgrade write without awaiting it. */
async function flush() {
  await vi.waitFor(() => expect(setAppConfig).toHaveBeenCalled())
}

beforeEach(() => {
  setAppConfig.mockReset()
  setAppConfig.mockResolvedValue(undefined)
  getAppConfig.mockReset()
  localStorage.clear()
})

describe('sanitizeUi', () => {
  it('returns the defaults for junk input', () => {
    for (const junk of [null, undefined, 42, 'nope', []]) {
      expect(sanitizeUi(junk)).toEqual(AUTOMATION_UI_DEFAULTS)
    }
  })

  it('keeps valid values and rejects invalid ones field by field', () => {
    const ui = sanitizeUi({
      deviceId: 'emulator-5554',
      captureTraffic: true,
      trafficHostFilter: 'a.com,b.com',
      elementTimeoutMs: 2500,
      colLeft: 300,
      colRight: 400,
      continueOnError: true,
      abortOnCrash: false,
      // ignored
      bogus: 'x',
      colLeft_: 1,
    })
    expect(ui).toMatchObject({
      deviceId: 'emulator-5554',
      captureTraffic: true,
      trafficHostFilter: 'a.com,b.com',
      elementTimeoutMs: 2500,
      colLeft: 300,
      colRight: 400,
      continueOnError: true,
      abortOnCrash: false,
    })
    expect('bogus' in ui).toBe(false)
  })

  it('falls back per-field, never wholesale', () => {
    const ui = sanitizeUi({
      deviceId: 7,                 // wrong type → default
      elementTimeoutMs: -5,        // non-positive → default
      colLeft: 'abc',              // NaN → default
      captureTraffic: true,        // survives
    })
    expect(ui.deviceId).toBe('')
    expect(ui.elementTimeoutMs).toBe(AUTOMATION_UI_DEFAULTS.elementTimeoutMs)
    expect(ui.colLeft).toBe(AUTOMATION_UI_DEFAULTS.colLeft)
    expect(ui.captureTraffic).toBe(true)
  })

  it('accepts numeric strings (app-config hands numbers back as-is, but a hand-edited file may not)', () => {
    const ui = sanitizeUi({ colLeft: '333', elementTimeoutMs: '8000' })
    expect(ui.colLeft).toBe(333)
    expect(ui.elementTimeoutMs).toBe(8000)
  })

  /**
   * 步骤间隔（stepIntervalMs）是唯一允许为 0 的数值项（0 = 不插入等待），
   * 所以它不能并进上面那条 `n > 0` 的循环里 —— 0 必须原样保留，而这正是
   * 「我在设置里关掉了间隔」最容易丢的一个值。
   */
  it('stepIntervalMs: 0 是合法值（不插入间隔），缺失才退回默认', () => {
    expect(sanitizeUi({ stepIntervalMs: 0 }).stepIntervalMs).toBe(0)
    expect(sanitizeUi({ stepIntervalMs: '150' }).stepIntervalMs).toBe(150)
    expect(sanitizeUi({ stepIntervalMs: -1 }).stepIntervalMs).toBe(AUTOMATION_UI_DEFAULTS.stepIntervalMs)
    expect(sanitizeUi({ stepIntervalMs: null }).stepIntervalMs).toBe(AUTOMATION_UI_DEFAULTS.stepIntervalMs)
    expect(sanitizeUi({ stepIntervalMs: 'soon' }).stepIntervalMs).toBe(AUTOMATION_UI_DEFAULTS.stepIntervalMs)
    expect(sanitizeUi({}).stepIntervalMs).toBe(AUTOMATION_UI_DEFAULTS.stepIntervalMs)
    expect(AUTOMATION_UI_DEFAULTS.stepIntervalMs).toBe(300)
  })
})

describe('loadConfig — v3 document', () => {
  it('loads projects and the ui bag', async () => {
    getAppConfig.mockResolvedValue({
      version: 3,
      projects: [V2_PROJECT],
      ui: { deviceId: 'dev-1', captureTraffic: true, colLeft: 444 },
    })
    const s = store()
    await s.loadConfig()
    expect(s.projects).toHaveLength(1)
    expect(s.ui.deviceId).toBe('dev-1')
    expect(s.ui.captureTraffic).toBe(true)
    expect(s.ui.colLeft).toBe(444)
    // missing ui keys come from the defaults, not from `undefined`
    expect(s.ui.abortOnCrash).toBe(true)
    expect(setAppConfig).not.toHaveBeenCalled()
  })

  it('does not eat legacy keys when a ui bag already exists', async () => {
    localStorage.setItem('bt:automationDeviceId', 'legacy-dev')
    getAppConfig.mockResolvedValue({ version: 3, projects: [], ui: {} })
    const s = store()
    await s.loadConfig()
    expect(s.ui.deviceId).toBe('')
    expect(localStorage.getItem('bt:automationDeviceId')).toBe('legacy-dev')
  })
})

describe('loadConfig — v2 → v3 upgrade', () => {
  it('keeps the projects (the whole point of the migration)', async () => {
    getAppConfig.mockResolvedValue({ version: 2, projects: [V2_PROJECT] })
    const s = store()
    await s.loadConfig()
    expect(s.projects).toHaveLength(1)
    expect(s.projects[0].id).toBe('p1')
    expect(s.projects[0].scripts[0].id).toBe('s1')
  })

  it('adopts every legacy key, then deletes it', async () => {
    localStorage.setItem('bt:automationDeviceId', 'emulator-5554')
    localStorage.setItem('bt:autoCaptureTraffic', '1')
    localStorage.setItem('bt:autoTrafficHostFilter', 'example.com')
    localStorage.setItem('bt:autoElementTimeoutMs', '7000')
    localStorage.setItem('bt:autoColLeft', '280')
    localStorage.setItem('bt:autoColRight', '360')
    getAppConfig.mockResolvedValue({ version: 2, projects: [V2_PROJECT] })

    const s = store()
    await s.loadConfig()

    expect(s.ui).toMatchObject({
      deviceId: 'emulator-5554',
      captureTraffic: true,
      trafficHostFilter: 'example.com',
      elementTimeoutMs: 7000,
      colLeft: 280,
      colRight: 360,
    })
    for (const key of Object.keys(LEGACY_UI_KEYS)) {
      expect(localStorage.getItem(key)).toBeNull()
    }
  })

  it('writes the upgraded document back once', async () => {
    getAppConfig.mockResolvedValue({ version: 2, projects: [V2_PROJECT] })
    localStorage.setItem('bt:autoColLeft', '300')
    const s = store()
    await s.loadConfig()
    await flush()
    expect(setAppConfig).toHaveBeenCalledTimes(1)
    const [key, doc] = setAppConfig.mock.calls[0]
    expect(key).toBe('automation')
    expect(doc.version).toBe(3)
    expect(doc.projects).toHaveLength(1)
    expect(doc.ui.colLeft).toBe(300)
  })

  it('leaves the stored booleans alone for absent keys', async () => {
    localStorage.setItem('bt:autoCaptureTraffic', '0')
    getAppConfig.mockResolvedValue({ version: 2, projects: [] })
    const s = store()
    await s.loadConfig()
    expect(s.ui.captureTraffic).toBe(false)
  })

  it('drops v1 / unversioned documents but still adopts the ui keys', async () => {
    localStorage.setItem('bt:automationDeviceId', 'dev-x')
    getAppConfig.mockResolvedValue({ projects: [{ ...V2_PROJECT, id: 'legacy' }] })
    const s = store()
    await s.loadConfig()
    // the v2 step model is not backwards compatible — no project adoption
    expect(s.projects).toHaveLength(0)
    expect(s.ui.deviceId).toBe('dev-x')
  })

  /**
   * The main process' appStore runs `syncStoreDefaults()` at startup, which
   * MERGES the schema defaults into the stored document. A stored v2 document
   * therefore arrives at the renderer as `{version: 2, projects, ui: DEFAULT}`
   * — `version` stays 2 (the merge never overwrites an existing number) while
   * the `ui` bag appears fully populated. Keying the upgrade off "does a ui
   * bag exist?" would then silently reset every preference; the version is the
   * only trustworthy discriminator.
   */
  it('adopts the legacy keys even when the schema merge already injected a default ui bag', async () => {
    localStorage.setItem('bt:automationDeviceId', 'kept-device')
    localStorage.setItem('bt:autoColLeft', '299')
    localStorage.setItem('bt:autoCaptureTraffic', '1')
    getAppConfig.mockResolvedValue({
      version: 2,
      projects: [V2_PROJECT],
      ui: {
        deviceId: '',
        captureTraffic: false,
        trafficHostFilter: '',
        elementTimeoutMs: 10000,
        colLeft: 240,
        colRight: 320,
        continueOnError: false,
        abortOnCrash: true,
      },
    })

    const s = store()
    await s.loadConfig()

    expect(s.projects).toHaveLength(1)
    expect(s.ui.deviceId).toBe('kept-device')
    expect(s.ui.colLeft).toBe(299)
    expect(s.ui.captureTraffic).toBe(true)
  })
})

describe('persist — one document, never one without the other', () => {
  it('round-trips projects and ui through one write', async () => {
    getAppConfig.mockResolvedValue({ version: 3, projects: [], ui: {} })
    const s = store()
    await s.loadConfig()
    s.ui.colLeft = 411
    s.ui.continueOnError = true
    await s.persist()
    const doc = setAppConfig.mock.calls.at(-1)![1]
    expect(doc).toEqual({
      version: 3,
      projects: [],
      ui: expect.objectContaining({ colLeft: 411, continueOnError: true }),
    })
  })

  it('debounces ui writes so a column drag is not one write per pixel', async () => {
    vi.useFakeTimers()
    try {
      getAppConfig.mockResolvedValue({ version: 3, projects: [], ui: {} })
      const s = store()
      // loadConfig under fake timers: the promise resolution still needs a tick
      const loading = s.loadConfig()
      await vi.advanceTimersByTimeAsync(0)
      await loading
      setAppConfig.mockClear()

      for (let i = 0; i < 30; i++) s.persistUiSoon(200)
      expect(setAppConfig).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(250)
      expect(setAppConfig).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('survives a config write failure without throwing', async () => {
    getAppConfig.mockResolvedValue({ version: 3, projects: [], ui: {} })
    const s = store()
    await s.loadConfig()
    setAppConfig.mockRejectedValue(new Error('disk full'))
    await expect(s.persist()).resolves.toBeUndefined()
  })
})
