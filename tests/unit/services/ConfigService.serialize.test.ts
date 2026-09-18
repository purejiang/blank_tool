/**
 * Regression guard: Electron serializes IPC arguments with structured clone,
 * and Vue reactive proxies are NOT cloneable (`v8.serialize` throws
 * "[object Array] could not be cloned"). Every `setAppConfig` /
 * `setUserConfig` write must therefore reach the preload as plain data —
 * otherwise the automation page's persist() rejects and pops a red toast
 * on each "new project" / "new script" / delete / rename.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, reactive } from 'vue'
import v8 from 'node:v8'

const mockAppConfig = { get: vi.fn(), set: vi.fn(), setMany: vi.fn(), getAll: vi.fn(), reset: vi.fn() }
const mockUserConfig = { get: vi.fn(), set: vi.fn(), getAll: vi.fn(), reset: vi.fn() }

Object.defineProperty(globalThis, 'window', {
  value: { electronAPI: { appConfig: mockAppConfig, userConfig: mockUserConfig } },
  writable: true,
})

import { ConfigService } from '@/renderer/services/ConfigService'

/** Mirrors what Electron does with an IPC argument before sending it. */
function mustBeCloneable(value: unknown): void {
  v8.serialize(value)
}

describe('ConfigService IPC-safety', () => {
  let service: ConfigService

  beforeEach(() => {
    vi.clearAllMocks()
    service = new ConfigService()
  })

  it('strips Vue reactivity from a reactive array payload (automation projects)', async () => {
    const projects = ref<any[]>([])
    projects.value.push({ id: 'p1', name: 'proj', package_name: '', scripts: [] })

    // Proof of the underlying trap: the raw proxy cannot cross IPC.
    expect(() => mustBeCloneable({ projects: projects.value })).toThrow()

    await service.setAppConfig('automation', { projects: projects.value })

    const [key, value] = mockAppConfig.set.mock.calls[0]
    expect(key).toBe('automation')
    expect(() => mustBeCloneable(value)).not.toThrow()
    expect((value as any).projects[0].name).toBe('proj')
  })

  it('strips reactivity from nested reactive objects (user config)', async () => {
    const state = reactive({ nested: { list: reactive([{ a: 1 }]) } })
    await service.setUserConfig('automation', state)
    const [, value] = mockUserConfig.set.mock.calls[0]
    expect(() => mustBeCloneable(value)).not.toThrow()
  })

  it('passes primitives and undefined through untouched', async () => {
    await service.setAppConfig('theme', 'dark')
    expect(mockAppConfig.set).toHaveBeenLastCalledWith('theme', 'dark')

    await service.setAppConfig('maxConcurrentTasks', 4)
    expect(mockAppConfig.set).toHaveBeenLastCalledWith('maxConcurrentTasks', 4)

    // undefined keeps its "delete the key" meaning in the main process.
    await service.setAppConfig('adbPath', undefined)
    expect(mockAppConfig.set).toHaveBeenLastCalledWith('adbPath', undefined)
  })
})
