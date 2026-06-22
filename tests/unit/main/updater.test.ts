import { describe, it, expect, beforeEach, vi } from 'vitest'

const mockOn = vi.fn()
const mockAutoUpdater = {
  on: mockOn,
  checkForUpdates: vi.fn(),
  quitAndInstall: vi.fn(),
  logger: null as unknown,
  autoDownload: false,
  allowDowngrade: false,
  allowPrerelease: false,
}

vi.mock('electron-updater', () => ({
  autoUpdater: mockAutoUpdater,
}))

vi.mock('electron', () => ({
  app: { isPackaged: true },
  BrowserWindow: {
    getAllWindows: vi.fn(() => []),
  },
}))

describe('updater', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  describe('initAutoUpdater', () => {
    it('configures updater with correct settings', async () => {
      const { initAutoUpdater } = await import('@/main/updater/updater')
      initAutoUpdater()

      expect(mockAutoUpdater.autoDownload).toBe(true)
      expect(mockAutoUpdater.allowDowngrade).toBe(false)
      expect(mockAutoUpdater.allowPrerelease).toBe(false)
    })

    it('registers all event listeners', async () => {
      const { initAutoUpdater } = await import('@/main/updater/updater')
      initAutoUpdater()

      const eventNames = mockOn.mock.calls.map((c: any[]) => c[0])
      expect(eventNames).toContain('update-available')
      expect(eventNames).toContain('update-not-available')
      expect(eventNames).toContain('download-progress')
      expect(eventNames).toContain('update-downloaded')
      expect(eventNames).toContain('error')
    })

    it('skips in dev mode', async () => {
      const { app: electronApp } = await import('electron')
      ;(electronApp as any).isPackaged = false

      const { initAutoUpdater } = await import('@/main/updater/updater')
      initAutoUpdater()

      expect(mockOn).not.toHaveBeenCalled()
    })

    it('does not re-initialize if already initialized', async () => {
      const { initAutoUpdater } = await import('@/main/updater/updater')
      initAutoUpdater()
      const callCount = mockOn.mock.calls.length
      initAutoUpdater()
      expect(mockOn.mock.calls.length).toBe(callCount)
    })
  })

  describe('quitAndInstall', () => {
    it('calls autoUpdater.quitAndInstall', async () => {
      const { quitAndInstall } = await import('@/main/updater/updater')
      quitAndInstall()
      expect(mockAutoUpdater.quitAndInstall).toHaveBeenCalledWith(false, true)
    })
  })
})
