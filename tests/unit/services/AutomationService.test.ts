import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the typed API accessor — AutomationService resolves callBackendAPI
// through requireApiMethod at call time.
vi.mock('@/renderer/api/apiAccess', () => ({
  requireApiMethod: vi.fn(() => mockCallBackendAPI),
}))

vi.mock('@utils/logger', () => ({
  log: { error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}))

import AutomationService from '@/renderer/services/AutomationService'

const mockCallBackendAPI = vi.fn()

describe('AutomationService', () => {
  let service: InstanceType<typeof AutomationService>

  beforeEach(() => {
    vi.clearAllMocks()
    service = new AutomationService()
  })

  describe('getTrafficStatus', () => {
    it('returns the backend capability report', async () => {
      mockCallBackendAPI.mockResolvedValue({
        installed: true,
        ready: true,
        lib_path: 'D:/runtime/mitmproxy/lib',
        python_mismatch: null,
      })

      const status = await service.getTrafficStatus()
      expect(status).toEqual({
        installed: true,
        ready: true,
        lib_path: 'D:/runtime/mitmproxy/lib',
        python_mismatch: null,
      })
      expect(mockCallBackendAPI).toHaveBeenCalledWith('automation.traffic_status', {})
    })

    it('caches the probe unless force=true', async () => {
      mockCallBackendAPI.mockResolvedValue({
        installed: false, ready: false, lib_path: 'x', python_mismatch: null,
      })

      await service.getTrafficStatus()
      await service.getTrafficStatus()
      expect(mockCallBackendAPI).toHaveBeenCalledTimes(1)

      await service.getTrafficStatus(true)
      expect(mockCallBackendAPI).toHaveBeenCalledTimes(2)
    })

    it('returns null (unknown state) when the probe fails', async () => {
      mockCallBackendAPI.mockRejectedValue(new Error('backend down'))
      const status = await service.getTrafficStatus(true)
      expect(status).toBeNull()
    })
  })

  describe('getImeStatus', () => {
    it('probes the requested device', async () => {
      mockCallBackendAPI.mockResolvedValue({
        device_id: 'emulator-5554',
        package: 'com.android.adbkeyboard/.AdbIME',
        installed: true,
        active: true,
      })

      const status = await service.getImeStatus('emulator-5554')
      expect(status?.installed).toBe(true)
      expect(status?.active).toBe(true)
      expect(mockCallBackendAPI).toHaveBeenCalledWith(
        'automation.ime_status', { device_id: 'emulator-5554' },
      )
    })

    it('returns null for an empty device id without calling the backend', async () => {
      const status = await service.getImeStatus('')
      expect(status).toBeNull()
      expect(mockCallBackendAPI).not.toHaveBeenCalled()
    })

    it('returns null when the probe fails', async () => {
      mockCallBackendAPI.mockRejectedValue(new Error('adb not found'))
      const status = await service.getImeStatus('emulator-5554')
      expect(status).toBeNull()
    })
  })
})
