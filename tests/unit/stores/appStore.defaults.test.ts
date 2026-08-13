import { beforeEach, describe, expect, it, vi } from 'vitest'

type AnyRecord = Record<string, any>

// Same electron-store mock pattern as appStore.migration.test.ts: a Map-backed
// fake reachable via vi.hoisted shared state. `seed` is re-seeded per test
// before dynamically importing appStore.ts (which runs migrations + defaults
// sync at module load). Empty seed ⇒ schema defaults should win for every key.
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

describe('appStore config defaults', () => {
  beforeEach(() => {
    mocks.setSeed({})
    vi.resetModules()
  })

  it('empty store falls back to canonical schema defaults for legacy settings keys', async () => {
    const { default: appStore } = await import('../../../src/main/stores/appStore')

    expect(appStore.get('language')).toBe('zh-CN')
    expect(appStore.get('theme')).toBe('auto')
    expect(appStore.get('enableNotifications')).toBe(true)
    expect(appStore.get('autoDeleteOutputOnTaskRemove')).toBe(false)
    expect(appStore.get('adbPath')).toBe('')
    expect(appStore.get('aaptPath')).toBe('')
    expect(appStore.get('apktoolPath')).toBe('')
    expect(appStore.get('bundletoolPath')).toBe('')
    expect(appStore.get('javaPath')).toBe('')
  })
})
