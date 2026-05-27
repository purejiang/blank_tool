import { describe, it, expect, vi, beforeEach } from 'vitest'

// We cannot run real Electron IPC tests without Electron, but we can verify
// that the config handler functions produce correct shapes when isolated.
// This test verifies the channel mapping and config key validation.

// Mock electron modules
vi.mock('electron', () => ({
  ipcMain: {
    handle: vi.fn(),
  },
  BrowserWindow: {
    getAllWindows: vi.fn(() => []),
  },
  app: {
    isPackaged: false,
    getAppPath: vi.fn(() => '/fake/app'),
  },
}))

import { IPC_CHANNELS, IPC_CHANNEL_NAMES } from '@/shared/ipc/channels'
import { APP_CONFIG_KEYS } from '@/shared/config/pathConfig'

describe('Config Handler Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('channel name consistency', () => {
    it('IPC_CHANNEL_NAMES values match IPC_CHANNELS name values', () => {
      for (const key of Object.keys(IPC_CHANNELS) as Array<keyof typeof IPC_CHANNELS>) {
        expect(IPC_CHANNEL_NAMES[key]).toBe(IPC_CHANNELS[key].name)
      }
    })
  })

  describe('app config key constants', () => {
    it('APP_CONFIG_KEYS has expected keys', () => {
      expect(APP_CONFIG_KEYS).toHaveProperty('runtime')
      expect(APP_CONFIG_KEYS).toHaveProperty('server')
    })

    it('APP_CONFIG_KEYS values are strings', () => {
      for (const value of Object.values(APP_CONFIG_KEYS)) {
        expect(typeof value).toBe('string')
      }
    })
  })

  describe('config channel mapping', () => {
    it('getAppConfig maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.getAppConfig).toBe(IPC_CHANNELS.getAppConfig.name)
    })

    it('setAppConfig maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.setAppConfig).toBe(IPC_CHANNELS.setAppConfig.name)
    })

    it('getAllAppConfig maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.getAllAppConfig).toBe(IPC_CHANNELS.getAllAppConfig.name)
    })

    it('setManyAppConfig maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.setManyAppConfig).toBe(IPC_CHANNELS.setManyAppConfig.name)
    })

    it('resetAppConfig maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.resetAppConfig).toBe(IPC_CHANNELS.resetAppConfig.name)
    })

    it('getUserConfig maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.getUserConfig).toBe(IPC_CHANNELS.getUserConfig.name)
    })

    it('setUserConfig maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.setUserConfig).toBe(IPC_CHANNELS.setUserConfig.name)
    })

    it('getAllUserConfig maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.getAllUserConfig).toBe(IPC_CHANNELS.getAllUserConfig.name)
    })

    it('resetUserConfig maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.resetUserConfig).toBe(IPC_CHANNELS.resetUserConfig.name)
    })

    it('getSettingsViewModel maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.getSettingsViewModel).toBe(IPC_CHANNELS.getSettingsViewModel.name)
    })

    it('resolveSettingsPaths maps to valid channel name', () => {
      expect(IPC_CHANNEL_NAMES.resolveSettingsPaths).toBe(IPC_CHANNELS.resolveSettingsPaths.name)
    })
  })

  describe('broadcast channels', () => {
    it('appConfigChanged is a main-to-renderer channel', () => {
      expect(IPC_CHANNELS.appConfigChanged.direction).toBe('main-to-renderer')
    })

    it('userConfigChanged is a main-to-renderer channel', () => {
      expect(IPC_CHANNELS.userConfigChanged.direction).toBe('main-to-renderer')
    })
  })
})
