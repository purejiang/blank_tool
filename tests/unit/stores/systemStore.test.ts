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

import { useSystemStore } from '@/renderer/stores/systemStore'

describe('systemStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('has empty system info', () => {
      const store = useSystemStore()
      expect(store.systemInfo.platform).toBe('')
      expect(store.systemInfo.architecture).toBe('')
    })

    it('has empty build info', () => {
      const store = useSystemStore()
      expect(store.buildInfo.appName).toBe('')
      expect(store.buildInfo.electronVersion).toBe('')
    })

    it('is not loading', () => {
      const store = useSystemStore()
      expect(store.loading).toBe(false)
    })

    it('has null error', () => {
      const store = useSystemStore()
      expect(store.error).toBeNull()
    })
  })

  describe('fetchSystemInfo', () => {
    it('sets loading to true during fetch', async () => {
      const store = useSystemStore()
      const mockService = {
        getSystemInfo: vi.fn().mockResolvedValue({ system_info: {} }),
      }
      const { default: serviceManager } = await import('@/renderer/services/ServiceManager')
      ;(serviceManager.getService as ReturnType<typeof vi.fn>).mockResolvedValue(mockService)

      const promise = store.fetchSystemInfo()
      expect(store.loading).toBe(true)
      await promise
      expect(store.loading).toBe(false)
    })

    it('updates system info on success', async () => {
      const store = useSystemStore()
      const mockService = {
        getSystemInfo: vi.fn().mockResolvedValue({
          system_info: {
            platform: 'win32',
            architecture: 'x64',
            hostname: 'test-pc',
            cpu: { count_logical: '8' },
            memory: { total: 17179869184, used: 8589934592, percent: 50 },
            diskTotal: 512110190592,
            diskUsed: 256055095296,
            diskPercent: 50.0,
          },
        }),
      }
      const { default: serviceManager } = await import('@/renderer/services/ServiceManager')
      ;(serviceManager.getService as ReturnType<typeof vi.fn>).mockResolvedValue(mockService)

      await store.fetchSystemInfo()

      expect(store.systemInfo.platform).toBe('win32')
      expect(store.systemInfo.architecture).toBe('x64')
      expect(store.systemInfo.hostname).toBe('test-pc')
      expect(store.systemInfo.cpuCount).toBe('8')
      expect(store.systemInfo.memoryTotal).toBeTruthy()
      expect(store.systemInfo.memoryPercent).toBeTruthy()
    })

    it('handles errors gracefully', async () => {
      const store = useSystemStore()
      const mockService = {
        getSystemInfo: vi.fn().mockRejectedValue(new Error('Failed')),
      }
      const { default: serviceManager } = await import('@/renderer/services/ServiceManager')
      ;(serviceManager.getService as ReturnType<typeof vi.fn>).mockResolvedValue(mockService)

      await store.fetchSystemInfo()

      expect(store.loading).toBe(false)
      expect(store.error).toBe('Failed')
    })
  })

  describe('fetchBuildInfo', () => {
    it('updates build info on success', async () => {
      const store = useSystemStore()
      const mockService = {
        getFontendBuildInfo: vi.fn().mockResolvedValue({
          electronVersion: '28.0.0',
          nodeVersion: '20.0.0',
          chromeVersion: '120.0',
          appName: 'TestApp',
          appVersion: '1.0.0',
          appDescription: 'Test Description',
        }),
        getBackendBuildInfo: vi.fn().mockResolvedValue({
          python_version: '3.12.0',
          java_version: '17.0.0',
        }),
      }
      const { default: serviceManager } = await import('@/renderer/services/ServiceManager')
      ;(serviceManager.getService as ReturnType<typeof vi.fn>).mockResolvedValue(mockService)

      await store.fetchBuildInfo()

      expect(store.buildInfo.electronVersion).toBe('28.0.0')
      expect(store.buildInfo.pythonVersion).toBe('3.12.0')
      expect(store.buildInfo.javaVersion).toBe('17.0.0')
    })
  })
})
