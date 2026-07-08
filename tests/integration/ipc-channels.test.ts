import { describe, it, expect } from 'vitest'
import { IPC_CHANNELS, IPC_CHANNEL_NAMES } from '@/shared/ipc/channels'

describe('IPC Channel Consistency', () => {
  describe('channel definitions', () => {
    it('all channels have unique names', () => {
      const names = Object.values(IPC_CHANNELS).map((c) => c.name)
      const uniqueNames = new Set(names)
      expect(uniqueNames.size).toBe(names.length)
    })

    it('all channels have a direction', () => {
      for (const [key, def] of Object.entries(IPC_CHANNELS)) {
        expect(def.direction).toMatch(/^(renderer-to-main|main-to-renderer)$/)
      }
    })

    it('all channel keys have a flat name mapping', () => {
      const keys = Object.keys(IPC_CHANNELS) as Array<keyof typeof IPC_CHANNELS>
      for (const key of keys) {
        expect(IPC_CHANNEL_NAMES[key]).toBeDefined()
        expect(typeof IPC_CHANNEL_NAMES[key]).toBe('string')
        expect(IPC_CHANNEL_NAMES[key].length).toBeGreaterThan(0)
      }
    })
  })

  describe('renderer-to-main channels', () => {
    const rmChannels = Object.entries(IPC_CHANNELS)
      .filter(([, def]) => def.direction === 'renderer-to-main')
      .map(([key]) => key)

    it('includes callBackendApi', () => {
      expect(rmChannels).toContain('callBackendApi')
    })

    it('includes config channels', () => {
      expect(rmChannels).toContain('getAppConfig')
      expect(rmChannels).toContain('setAppConfig')
      expect(rmChannels).toContain('getAllAppConfig')
      expect(rmChannels).toContain('resetAppConfig')
    })

    it('includes user config channels', () => {
      expect(rmChannels).toContain('getUserConfig')
      expect(rmChannels).toContain('setUserConfig')
      expect(rmChannels).toContain('getAllUserConfig')
      expect(rmChannels).toContain('resetUserConfig')
    })
  })

  describe('main-to-renderer channels', () => {
    const mrChannels = Object.entries(IPC_CHANNELS)
      .filter(([, def]) => def.direction === 'main-to-renderer')
      .map(([key]) => key)

    it('includes device change channel', () => {
      expect(mrChannels).toContain('deviceChange')
    })

    it('includes logcat channels', () => {
      expect(mrChannels).toContain('logcatOutput')
      expect(mrChannels).toContain('logcatStarted')
      expect(mrChannels).toContain('logcatFinished')
      expect(mrChannels).toContain('logcatError')
    })

    it('includes stream event channel', () => {
      expect(mrChannels).toContain('streamEvent')
    })

    it('includes config changed channels', () => {
      expect(mrChannels).toContain('appConfigChanged')
      expect(mrChannels).toContain('userConfigChanged')
    })
  })

  describe('IPC_CHANNEL_NAMES backward compatibility', () => {
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
      const count = Object.keys(IPC_CHANNELS).length
      expect(count).toBeGreaterThanOrEqual(20)
      expect(count).toBeLessThanOrEqual(40)
    })
  })
})
