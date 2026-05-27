import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock unifiedApi
vi.mock('@/renderer/api/unifiedApi', () => ({
  default: {
    getAPI: vi.fn(),
  },
}))

// Mock deviceStore
const mockStore = {
  devices: [] as unknown[],
  selectedDevice: null as { id: string } | null,
  isMonitoring: false,
  isLogcatRunning: false,
  logcatProcessId: '',
  logcatOutput: [] as string[],
  shellOutput: '',
  apps: [] as { packageName: string }[],
  appType: 'all',
  updateDevices: vi.fn(),
  updateDeviceInfo: vi.fn(),
}

vi.mock('@stores/deviceStore', () => ({
  useDeviceStore: vi.fn(() => mockStore),
}))

import DeviceService from '@/renderer/services/DeviceService'
import unifiedApi from '@/renderer/api/unifiedApi'

const mockApi = {
  getAdbDevices: vi.fn(),
  getDeviceInfo: vi.fn(),
  rebootDevice: vi.fn(),
  executeShell: vi.fn(),
  startLogcat: vi.fn(),
  stopLogcat: vi.fn(),
  getInstalledApps: vi.fn(),
  onLogcatOutput: vi.fn(),
  onLogcatStarted: vi.fn(),
  onLogcatFinished: vi.fn(),
  onLogcatError: vi.fn(),
  removeLogcatListener: vi.fn(),
  showSaveDialog: vi.fn(),
  callBackendAPI: vi.fn(),
  writeClipboardText: vi.fn(),
  selectDirectory: vi.fn(),
  exportApk: vi.fn(),
  uninstallApp: vi.fn(),
  installApk: vi.fn(),
  installAab: vi.fn(),
}

describe('DeviceService', () => {
  let service: DeviceService

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    ;(unifiedApi.getAPI as ReturnType<typeof vi.fn>).mockReturnValue(mockApi)
    mockApi.getAdbDevices.mockResolvedValue([{ id: 'device1', name: 'Test' }])
    mockApi.getDeviceInfo.mockResolvedValue({ model: 'Pixel', brand: 'Google' })
    mockStore.selectedDevice = { id: 'device1' }
    mockStore.isMonitoring = false
    mockStore.isLogcatRunning = false
    mockStore.logcatOutput = []
    service = new DeviceService()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('refreshDevices', () => {
    it('returns devices on success', async () => {
      const result = await service.refreshDevices()
      expect(result.success).toBe(true)
      expect(result.devices).toEqual([{ id: 'device1', name: 'Test' }])
      expect(mockStore.updateDevices).toHaveBeenCalled()
    })

    it('returns error when API not available', async () => {
      ;(unifiedApi.getAPI as ReturnType<typeof vi.fn>).mockReturnValue(null)
      const result = await service.refreshDevices()
      expect(result.success).toBe(false)
      expect(mockStore.updateDevices).toHaveBeenCalledWith([])
    })
  })

  describe('getDeviceInfo', () => {
    it('returns device info on success', async () => {
      const result = await service.getDeviceInfo('device1')
      expect(result.success).toBe(true)
      expect(result.device).toEqual({ model: 'Pixel', brand: 'Google' })
    })

    it('returns false for empty deviceId', async () => {
      const result = await service.getDeviceInfo('')
      expect(result).toEqual({ success: false })
    })
  })

  describe('startMonitoring / stopMonitoring', () => {
    it('sets monitoring state', async () => {
      const result = await service.startMonitoring(1000)
      expect(result.success).toBe(true)
      expect(mockStore.isMonitoring).toBe(true)
    })

    it('does not start duplicate monitoring', async () => {
      mockStore.isMonitoring = true
      const result = await service.startMonitoring()
      expect(result).toEqual({ success: true })
    })

    it('stops monitoring', async () => {
      await service.startMonitoring(1000)
      const result = await service.stopMonitoring()
      expect(result.success).toBe(true)
      expect(mockStore.isMonitoring).toBe(false)
    })
  })

  describe('rebootDevice', () => {
    it('returns error when no device selected', async () => {
      mockStore.selectedDevice = null
      const result = await service.rebootDevice()
      expect(result.success).toBe(false)
      expect(result.error).toBe('No device selected')
    })

    it('reboots device successfully', async () => {
      mockApi.rebootDevice.mockResolvedValue(true)
      const result = await service.rebootDevice('bootloader')
      expect(result.success).toBe(true)
    })
  })

  describe('executeShell', () => {
    it('executes shell command', async () => {
      mockApi.executeShell.mockResolvedValue({ output: 'hello' })
      await service.executeShell('echo hello')
      expect(mockStore.shellOutput).toBe('hello')
    })

    it('does nothing with empty command', async () => {
      await service.executeShell('')
      expect(mockApi.executeShell).not.toHaveBeenCalled()
    })
  })

  describe('clearLogcat', () => {
    it('clears logcat output', async () => {
      mockStore.logcatOutput = ['line1', 'line2']
      await service.clearLogcat()
      expect(mockStore.logcatOutput).toEqual([])
    })
  })

  describe('installApp', () => {
    it('returns error when no apkPath', async () => {
      const result = await service.installApp('')
      expect(result.success).toBe(false)
    })

    it('returns error when no device selected', async () => {
      mockStore.selectedDevice = null
      const result = await service.installApp('/test.apk')
      expect(result.success).toBe(false)
      expect(result.error).toBe('No device selected')
    })

    it('installs APK successfully', async () => {
      mockApi.installApk.mockResolvedValue({ success: true })
      const result = await service.installApp('/test.apk')
      expect(result.success).toBe(true)
      expect(mockApi.installApk).toHaveBeenCalledWith('/test.apk', 'device1')
    })

    it('installs AAB successfully', async () => {
      mockApi.installAab.mockResolvedValue({ success: true })
      const result = await service.installApp('/test.aab')
      expect(result.success).toBe(true)
      expect(mockApi.installAab).toHaveBeenCalledWith('/test.aab', 'device1')
    })
  })
})
