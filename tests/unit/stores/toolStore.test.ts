import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock ServiceManager
vi.mock('@/renderer/services/ServiceManager', () => ({
  default: {
    getService: vi.fn(),
    getServiceSync: vi.fn(),
    register: vi.fn(),
  },
}))

import { useToolStore } from '@/renderer/stores/toolStore'

describe('toolStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('has empty tools array', () => {
      const store = useToolStore()
      expect(store.tools).toEqual([])
    })

    it('is not loading', () => {
      const store = useToolStore()
      expect(store.loading).toBe(false)
    })

    it('has null error', () => {
      const store = useToolStore()
      expect(store.error).toBeNull()
    })

    it('has null lastFetched', () => {
      const store = useToolStore()
      expect(store.lastFetched).toBeNull()
    })
  })

  describe('getTool', () => {
    it('finds tool by name', () => {
      const store = useToolStore()
      store.tools = [
        { name: 'adb', status: 'available', version: '1.0' },
        { name: 'aapt', status: 'available', version: '2.0' },
      ]
      const tool = store.getTool('adb')
      expect(tool).toEqual({ name: 'adb', status: 'available', version: '1.0' })
    })

    it('finds tool by key', () => {
      const store = useToolStore()
      store.tools = [{ key: 'bundletool', name: 'bundletool', status: 'available' }]
      const tool = store.getTool('bundletool')
      expect(tool).toBeDefined()
    })

    it('returns undefined for missing tool', () => {
      const store = useToolStore()
      expect(store.getTool('nonexistent')).toBeUndefined()
    })
  })

  describe('availableTools', () => {
    it('filters only available tools', () => {
      const store = useToolStore()
      store.tools = [
        { name: 'adb', status: 'available' },
        { name: 'aapt', status: 'unavailable' },
        { name: 'zipalign', status: 'available' },
        { name: 'jarsigner', status: 'unavailable' },
      ]
      const available = store.availableTools
      expect(available).toHaveLength(2)
      expect(available.every((t: { status: string }) => t.status === 'available')).toBe(true)
    })
  })

  describe('fetchTools', () => {
    it('fetches tools and updates state', async () => {
      const store = useToolStore()
      const mockTools = [
        { name: 'adb', status: 'available', version: '1.0' },
        { name: 'aapt', status: 'available', version: '2.0' },
      ]
      const mockService = {
        checkTools: vi.fn().mockResolvedValue(mockTools),
      }
      const { default: serviceManager } = await import('@/renderer/services/ServiceManager')
      ;(serviceManager.getService as ReturnType<typeof vi.fn>).mockResolvedValue(mockService)

      await store.fetchTools(true)

      expect(store.tools).toEqual(mockTools)
      expect(store.lastFetched).toBeTruthy()
      expect(store.loading).toBe(false)
    })

    it('skips fetch if tools already loaded and not forced', async () => {
      const store = useToolStore()
      store.tools = [{ name: 'adb', status: 'available' }]
      const mockService = {
        checkTools: vi.fn(),
      }
      const { default: serviceManager } = await import('@/renderer/services/ServiceManager')
      ;(serviceManager.getService as ReturnType<typeof vi.fn>).mockResolvedValue(mockService)

      await store.fetchTools(false)

      // Should not have called checkTools
      expect(mockService.checkTools).not.toHaveBeenCalled()
    })

    it('handles errors', async () => {
      const store = useToolStore()
      const mockService = {
        checkTools: vi.fn().mockRejectedValue(new Error('Fetch failed')),
      }
      const { default: serviceManager } = await import('@/renderer/services/ServiceManager')
      ;(serviceManager.getService as ReturnType<typeof vi.fn>).mockResolvedValue(mockService)

      await store.fetchTools(true)

      expect(store.error).toBe('Fetch failed')
      expect(store.loading).toBe(false)
    })
  })

  describe('updateTool', () => {
    it('updates existing tool', () => {
      const store = useToolStore()
      store.tools = [{ name: 'adb', status: 'unavailable', version: '1.0' }]
      store.updateTool({ name: 'adb', status: 'available' })
      expect(store.tools[0].status).toBe('available')
      expect(store.tools[0].version).toBe('1.0')
    })

    it('adds new tool if not found', () => {
      const store = useToolStore()
      store.tools = [{ name: 'adb', status: 'available' }]
      store.updateTool({ name: 'newtool', status: 'available', version: '1.0' })
      expect(store.tools).toHaveLength(2)
    })
  })
})
