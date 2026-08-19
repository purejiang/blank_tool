import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock unifiedApi.call before importing the module under test.
const { mockCall } = vi.hoisted(() => ({ mockCall: vi.fn() }))

vi.mock('@/renderer/api/unifiedApi', () => ({
  default: {
    call: mockCall,
    getAPI: vi.fn(),
    safeCall: vi.fn(),
  },
}))

import PluginService from '@/renderer/services/PluginService'

describe('PluginService', () => {
  let service: PluginService

  beforeEach(() => {
    vi.clearAllMocks()
    service = new PluginService()
  })

  describe('list', () => {
    it('calls plugin.list with empty params and returns result', async () => {
      mockCall.mockResolvedValue({ plugins: [] })
      const result = await service.list()
      expect(mockCall).toHaveBeenCalledWith('plugin.list', {})
      expect(result).toEqual({ plugins: [] })
    })
  })

  describe('add', () => {
    it('calls plugin.add with module only when path/config omitted', async () => {
      mockCall.mockResolvedValue({ plugins: [] })
      await service.add('foo')
      expect(mockCall).toHaveBeenCalledWith('plugin.add', { module: 'foo' })
    })

    it('calls plugin.add with module, path and config', async () => {
      mockCall.mockResolvedValue({ plugins: [] })
      await service.add('foo', '/x/y', { k: 'v' })
      expect(mockCall).toHaveBeenCalledWith('plugin.add', {
        module: 'foo',
        path: '/x/y',
        config: { k: 'v' },
      })
    })
  })

  describe('delete', () => {
    it('calls plugin.delete with module', async () => {
      mockCall.mockResolvedValue({ plugins: [] })
      await service.delete('foo')
      expect(mockCall).toHaveBeenCalledWith('plugin.delete', { module: 'foo' })
    })
  })

  describe('reload', () => {
    it('calls plugin.reload with empty params and returns result', async () => {
      mockCall.mockResolvedValue({ ok: true })
      const result = await service.reload()
      expect(mockCall).toHaveBeenCalledWith('plugin.reload', {})
      expect(result).toEqual({ ok: true })
    })
  })
})
