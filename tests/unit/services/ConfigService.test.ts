import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock window.electronAPI before importing the module under test
const mockAppConfig = {
  get: vi.fn(),
  set: vi.fn(),
  setMany: vi.fn(),
  getAll: vi.fn(),
  reset: vi.fn(),
}

const mockUserConfig = {
  get: vi.fn(),
  set: vi.fn(),
  getAll: vi.fn(),
  reset: vi.fn(),
}

// Must use a getter so that ConfigService constructor reads it at instantiation time
Object.defineProperty(globalThis, 'window', {
  value: {
    electronAPI: {
      appConfig: mockAppConfig,
      userConfig: mockUserConfig,
    },
  },
  writable: true,
})

import { ConfigService } from '@/renderer/services/ConfigService'

describe('ConfigService', () => {
  let service: ConfigService

  beforeEach(() => {
    vi.clearAllMocks()
    mockAppConfig.get.mockResolvedValue('test-value')
    mockAppConfig.set.mockResolvedValue(undefined)
    mockAppConfig.getAll.mockResolvedValue({ key: 'value' })
    mockAppConfig.reset.mockResolvedValue(undefined)
    mockAppConfig.setMany.mockResolvedValue(undefined)

    mockUserConfig.get.mockResolvedValue('user-value')
    mockUserConfig.set.mockResolvedValue(undefined)
    mockUserConfig.getAll.mockResolvedValue({ theme: 'dark' })
    mockUserConfig.reset.mockResolvedValue(undefined)

    service = new ConfigService()
  })

  // --- App config ---
  describe('getAppConfig', () => {
    it('delegates to appConfig.get with key', async () => {
      const result = await service.getAppConfig('theme')
      expect(mockAppConfig.get).toHaveBeenCalledWith('theme')
      expect(result).toBe('test-value')
    })

    it('delegates to appConfig.get without key', async () => {
      await service.getAppConfig()
      expect(mockAppConfig.get).toHaveBeenCalledWith(undefined)
    })
  })

  describe('setAppConfig', () => {
    it('delegates to appConfig.set', async () => {
      await service.setAppConfig('theme', 'dark')
      expect(mockAppConfig.set).toHaveBeenCalledWith('theme', 'dark')
    })
  })

  describe('getAllAppConfig', () => {
    it('delegates to appConfig.getAll', async () => {
      const result = await service.getAllAppConfig()
      expect(result).toEqual({ key: 'value' })
      expect(mockAppConfig.getAll).toHaveBeenCalled()
    })
  })

  describe('resetAppConfig', () => {
    it('delegates to appConfig.reset', async () => {
      await service.resetAppConfig()
      expect(mockAppConfig.reset).toHaveBeenCalled()
    })
  })

  // --- User config ---
  describe('getUserConfig', () => {
    it('delegates to userConfig.get with key', async () => {
      const result = await service.getUserConfig('theme')
      expect(mockUserConfig.get).toHaveBeenCalledWith('theme')
      expect(result).toBe('user-value')
    })
  })

  describe('setUserConfig', () => {
    it('delegates to userConfig.set', async () => {
      await service.setUserConfig('theme', 'light')
      expect(mockUserConfig.set).toHaveBeenCalledWith('theme', 'light')
    })
  })

  describe('getAllUserConfig', () => {
    it('delegates to userConfig.getAll', async () => {
      const result = await service.getAllUserConfig()
      expect(result).toEqual({ theme: 'dark' })
    })
  })

  describe('resetUserConfig', () => {
    it('delegates to userConfig.reset', async () => {
      await service.resetUserConfig()
      expect(mockUserConfig.reset).toHaveBeenCalled()
    })
  })
})
