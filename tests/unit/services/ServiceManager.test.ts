import { describe, it, expect, vi } from 'vitest'
import serviceManager from '@/renderer/services/ServiceManager'

describe('ServiceManager', () => {
  // Reset before each test by creating a fresh instance
  // Since serviceManager is a singleton, we test methods without resetting

  describe('registration and lazy instantiation', () => {
    it('throws when getting unregistered service', async () => {
      await expect(
        serviceManager.getService('nonexistent_service')
      ).rejects.toThrow('not registered')
    })

    it('returns same instance on subsequent calls', async () => {
      class TestService {
        public initialized = false
        async initialize() {
          this.initialized = true
        }
      }

      serviceManager.register('test', TestService, [])
      const instance1 = await serviceManager.getService('test')
      const instance2 = await serviceManager.getService('test')

      expect(instance1).toBe(instance2)
      expect(instance1.initialized).toBe(true)
    })

    it('calls initialize if method exists', async () => {
      const initSpy = vi.fn()
      class InitService {
        async initialize() {
          initSpy()
        }
      }

      serviceManager.register('initSvc', InitService, [])
      await serviceManager.getService('initSvc')

      expect(initSpy).toHaveBeenCalledOnce()
    })

    it('injects dependencies', async () => {
      class DepA {
        name = 'depA'
      }
      class DepB {
        constructor(public depA: DepA) {}
      }

      serviceManager.register('depA', DepA, [])
      serviceManager.register('depB', DepB, ['depA'])

      const depB = await serviceManager.getService('depB')
      expect(depB).toBeInstanceOf(DepB)
      expect(depB.depA).toBeInstanceOf(DepA)
    })
  })

  describe('getServiceSync', () => {
    it('returns undefined for uninitialized service', () => {
      const result = serviceManager.getServiceSync('never_registered')
      expect(result).toBeUndefined()
    })
  })

  describe('hasService', () => {
    it('returns false for unregistered service', () => {
      expect(serviceManager.hasService('never_registered')).toBe(false)
    })

    it('returns true after service is initialized', async () => {
      class HasService {}
      serviceManager.register('hasTest', HasService, [])
      // Not initialized yet
      expect(serviceManager.hasService('hasTest')).toBe(false)
      await serviceManager.getService('hasTest')
      expect(serviceManager.hasService('hasTest')).toBe(true)
    })
  })

  describe('getServiceStatus', () => {
    it('returns status object', () => {
      const status = serviceManager.getServiceStatus()
      expect(status).toHaveProperty('initialized')
      expect(status).toHaveProperty('serviceCount')
      expect(status).toHaveProperty('services')
      expect(typeof status.serviceCount).toBe('number')
    })
  })

  describe('destroy', () => {
    it('clears services and calls destroy on each', async () => {
      const destroySpy = vi.fn()
      class DestroyService {
        async initialize() {}
        destroy() {
          destroySpy()
        }
      }

      serviceManager.register('destroyTest', DestroyService, [])
      await serviceManager.getService('destroyTest')
      serviceManager.destroy()

      expect(destroySpy).toHaveBeenCalledOnce()
      expect(serviceManager.hasService('destroyTest')).toBe(false)
    })
  })
})
