import { describe, it, expect } from 'vitest'
import { IPC_CHANNEL_NAMES } from '@/shared/ipc/channels'

describe('IPC Channel Consistency', () => {
  describe('channel definitions', () => {
    it('all channels have unique names', () => {
      const names = Object.values(IPC_CHANNEL_NAMES)
      const uniqueNames = new Set(names)
      expect(uniqueNames.size).toBe(names.length)
    })

    it('all channel values are non-empty strings', () => {
      for (const [key, name] of Object.entries(IPC_CHANNEL_NAMES)) {
        expect(typeof name).toBe('string')
        expect(name.length).toBeGreaterThan(0)
      }
    })
  })

  describe('renderer-to-main channels', () => {
    it('includes callBackendApi', () => {
      expect(IPC_CHANNEL_NAMES).toHaveProperty('callBackendApi')
    })

    it('includes config channels', () => {
      expect(IPC_CHANNEL_NAMES).toHaveProperty('getAppConfig')
      expect(IPC_CHANNEL_NAMES).toHaveProperty('setAppConfig')
      expect(IPC_CHANNEL_NAMES).toHaveProperty('getAllAppConfig')
      expect(IPC_CHANNEL_NAMES).toHaveProperty('resetAppConfig')
    })

    it('includes user config channels', () => {
      expect(IPC_CHANNEL_NAMES).toHaveProperty('getUserConfig')
      expect(IPC_CHANNEL_NAMES).toHaveProperty('setUserConfig')
      expect(IPC_CHANNEL_NAMES).toHaveProperty('getAllUserConfig')
      expect(IPC_CHANNEL_NAMES).toHaveProperty('resetUserConfig')
    })
  })

  describe('main-to-renderer channels', () => {
    it('includes device change channel', () => {
      expect(IPC_CHANNEL_NAMES).toHaveProperty('deviceChange')
    })

    it('includes logcat channels', () => {
      expect(IPC_CHANNEL_NAMES).toHaveProperty('logcatOutput')
      expect(IPC_CHANNEL_NAMES).toHaveProperty('logcatStarted')
      expect(IPC_CHANNEL_NAMES).toHaveProperty('logcatFinished')
    })

    it('includes stream event channel', () => {
      expect(IPC_CHANNEL_NAMES).toHaveProperty('streamEvent')
    })

    it('includes config changed channels', () => {
      expect(IPC_CHANNEL_NAMES).toHaveProperty('appConfigChanged')
      expect(IPC_CHANNEL_NAMES).toHaveProperty('userConfigChanged')
    })
  })

  describe('IPC_CHANNEL_NAMES channel values', () => {
    it('maps callBackendApi to correct name', () => {
      expect(IPC_CHANNEL_NAMES.callBackendApi).toBe('call-backend-api')
    })

    it('maps getAppConfig to correct name', () => {
      expect(IPC_CHANNEL_NAMES.getAppConfig).toBe('get-app-config')
    })

    it('maps setAppConfig to correct name', () => {
      expect(IPC_CHANNEL_NAMES.setAppConfig).toBe('set-app-config')
    })

    it('maps resetAppConfig to correct name', () => {
      expect(IPC_CHANNEL_NAMES.resetAppConfig).toBe('reset-app-config')
    })
  })

  describe('total channel count', () => {
    it('has expected number of channels', () => {
      const count = Object.keys(IPC_CHANNEL_NAMES).length
      expect(count).toBeGreaterThanOrEqual(20)
      expect(count).toBeLessThanOrEqual(60) // 51 channels after T16 added 18 new ones
    })
  })
})
