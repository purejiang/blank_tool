import { beforeEach, describe, expect, it, vi } from 'vitest'

type AnyRecord = Record<string, any>

// Hoisted shared state so the mocked factory can reach it: `seed` is re-seeded
// per test before dynamically importing appStore.ts (which runs migrations +
// defaults sync at module load). The mock is a Map-backed fake supporting
// get/set/has/delete/store (the `store` getter returns all data).
const mocks = vi.hoisted(() => {
  let seed: AnyRecord = {}

  class MockElectronStore {
    private data: AnyRecord = seed

    get store(): AnyRecord {
      return this.data
    }

    set store(value: AnyRecord) {
      this.data = value
    }

    get(key: string): any {
      if (key.includes('.')) {
        let cur: any = this.data
        for (const part of key.split('.')) {
          if (cur === undefined || cur === null) return undefined
          cur = cur[part]
        }
        return cur
      }
      return this.data[key]
    }

    set(key: string, value: any): void {
      if (key.includes('.')) {
        const parts = key.split('.')
        let cur: any = this.data
        for (let i = 0; i < parts.length - 1; i++) {
          if (cur[parts[i]] === undefined || cur[parts[i]] === null) {
            cur[parts[i]] = {}
          }
          cur = cur[parts[i]]
        }
        cur[parts[parts.length - 1]] = value
        return
      }
      this.data[key] = value
    }

    has(key: string): boolean {
      return this.get(key) !== undefined
    }

    delete(key: string): void {
      if (key.includes('.')) {
        const parts = key.split('.')
        let cur: any = this.data
        for (let i = 0; i < parts.length - 1; i++) {
          if (cur === undefined || cur === null) return
          cur = cur[parts[i]]
        }
        if (cur) delete cur[parts[parts.length - 1]]
        return
      }
      delete this.data[key]
    }
  }

  return { getSeed: () => seed, setSeed: (value: AnyRecord) => { seed = value }, MockElectronStore }
})

vi.mock('electron-store', () => ({
  default: mocks.MockElectronStore,
}))

describe('appStore config migrations', () => {
  beforeEach(() => {
    mocks.setSeed({})
    vi.resetModules()
  })

  it('MIGRATIONS[5] deletes stale app.theme/app.language but preserves app.autoStart/minimizeToTray', async () => {
    // Pre-seed a store that still carries the stale nested keys, at configVersion 1 so
    // runConfigMigrations executes the FULL chain 1→5. Deliberately NO top-level
    // theme/language keys — MIGRATIONS[1] drains app.* → top-level only when
    // !appStore.has('theme') / !appStore.has('language').
    // NOTE: a real store at configVersion 5 would have already run MIGRATIONS[1]
    // (loop only runs migrations >= currentVersion), so the drain is only
    // observable from an old-version seed.
    mocks.setSeed({
      configVersion: 1,
      app: {
        theme: 'dark',
        language: 'zh-CN',
        autoStart: false,
        minimizeToTray: false,
      },
    })

    const { default: appStore } = await import('../../../src/main/stores/appStore')

    // MIGRATIONS[1]: app.theme/app.language drained to top-level (theme 'dark'
    // is a valid value; language 'zh-CN' carried over).
    expect(appStore.get('theme')).toBe('dark')
    expect(appStore.get('language')).toBe('zh-CN')

    // MIGRATIONS[5]: stale nested keys deleted from app.
    expect(appStore.get('app').theme).toBeUndefined()
    expect(appStore.get('app').language).toBeUndefined()

    // Surviving app keys untouched.
    expect(appStore.get('app').autoStart).toBe(false)
    expect(appStore.get('app').minimizeToTray).toBe(false)

    // Version bumped 1 → 6.
    expect(appStore.get('configVersion')).toBe(6)
  })

  it('empty store gets canonical top-level defaults without throwing', async () => {
    mocks.setSeed({})

    const { default: appStore } = await import('../../../src/main/stores/appStore')

    expect(appStore.get('theme')).toBe('auto')
    expect(appStore.get('language')).toBe('zh-CN')
    expect(appStore.get('configVersion')).toBe(6)
    expect(appStore.get('app')).toEqual({ autoStart: false, minimizeToTray: false })
  })
})
