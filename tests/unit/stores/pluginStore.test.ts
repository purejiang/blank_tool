import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock ServiceManager so the store's getService('plugins') returns a fake service.
vi.mock('@/renderer/services/ServiceManager', () => ({
  default: {
    getService: vi.fn(),
    getServiceSync: vi.fn(),
    register: vi.fn(),
  },
}))

import { usePluginStore } from '@/renderer/stores/pluginStore'

const pluginFixture = {
  module: 'foo',
  kind: 'native',
  version: '1.0.0',
  loaded: true,
  error: '',
}

async function stubService(overrides: Record<string, ReturnType<typeof vi.fn>>) {
  const { default: serviceManager } = await import('@/renderer/services/ServiceManager')
  const getService = serviceManager.getService as ReturnType<typeof vi.fn>
  getService.mockResolvedValue(overrides)
  return getService
}

describe('pluginStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('has empty plugins array', () => {
      const store = usePluginStore()
      expect(store.plugins).toEqual([])
    })

    it('is not loading', () => {
      const store = usePluginStore()
      expect(store.loading).toBe(false)
    })

    it('has null error', () => {
      const store = usePluginStore()
      expect(store.error).toBeNull()
    })
  })

  describe('fetchPlugins', () => {
    it('loads plugin list into state', async () => {
      const store = usePluginStore()
      await stubService({ list: vi.fn().mockResolvedValue({ plugins: [pluginFixture] }) })

      await store.fetchPlugins()

      expect(store.plugins).toEqual([pluginFixture])
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
    })

    it('captures error on rejected call without throwing', async () => {
      const store = usePluginStore()
      await stubService({ list: vi.fn().mockRejectedValue(new Error('list failed')) })

      await expect(store.fetchPlugins()).resolves.toBeUndefined()

      expect(store.error).toBe('list failed')
      expect(store.loading).toBe(false)
    })
  })

  describe('addPlugin', () => {
    it('adds plugin and updates list', async () => {
      const store = usePluginStore()
      const add = vi.fn().mockResolvedValue({ plugins: [pluginFixture] })
      await stubService({ add })

      await store.addPlugin('foo')

      expect(add).toHaveBeenCalledWith('foo', undefined, undefined)
      expect(store.plugins).toEqual([pluginFixture])
    })

    it('captures error on rejected add', async () => {
      const store = usePluginStore()
      await stubService({ add: vi.fn().mockRejectedValue(new Error('add failed')) })

      await store.addPlugin('foo')

      expect(store.error).toBe('add failed')
      expect(store.loading).toBe(false)
    })
  })

  describe('deletePlugin', () => {
    it('deletes plugin and updates list', async () => {
      const store = usePluginStore()
      const del = vi.fn().mockResolvedValue({ plugins: [] })
      await stubService({ delete: del })

      await store.deletePlugin('foo')

      expect(del).toHaveBeenCalledWith('foo')
      expect(store.plugins).toEqual([])
    })

    it('captures error on rejected delete', async () => {
      const store = usePluginStore()
      await stubService({ delete: vi.fn().mockRejectedValue(new Error('delete failed')) })

      await store.deletePlugin('foo')

      expect(store.error).toBe('delete failed')
      expect(store.loading).toBe(false)
    })
  })

  describe('reloadPlugins', () => {
    it('reloads then refreshes list', async () => {
      const store = usePluginStore()
      const reload = vi.fn().mockResolvedValue({ ok: true })
      const list = vi.fn().mockResolvedValue({ plugins: [pluginFixture] })
      await stubService({ reload, list })

      await store.reloadPlugins()

      expect(reload).toHaveBeenCalled()
      expect(list).toHaveBeenCalled()
      expect(store.plugins).toEqual([pluginFixture])
    })

    it('captures error on rejected reload', async () => {
      const store = usePluginStore()
      await stubService({ reload: vi.fn().mockRejectedValue(new Error('reload failed')) })

      await store.reloadPlugins()

      expect(store.error).toBe('reload failed')
      expect(store.loading).toBe(false)
    })
  })
})
