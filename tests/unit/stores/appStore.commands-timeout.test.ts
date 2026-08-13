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

describe('appStore commands.timeout default', () => {
  beforeEach(() => {
    mocks.setSeed({})
    vi.resetModules()
  })

  it('schema default for commands.timeout is 300000ms (5min), matching commandHandlers.ts', async () => {
    const { default: appStore } = await import('../../../src/main/stores/appStore')

    // Empty store => schema default applied. Old default was 30000; the IPC
    // timeout at commandHandlers.ts:31 is 300000, so the schema now matches.
    expect(appStore.get('commands.timeout')).toBe(300000)
    expect(appStore.get('commands')).toEqual({ timeout: 300000, maxHistory: 100, outputFormat: 'json' })
  })
})
