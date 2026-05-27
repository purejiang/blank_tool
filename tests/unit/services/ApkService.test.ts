import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock unifiedApi
vi.mock('@/renderer/api/unifiedApi', () => ({
  default: {
    getAPI: vi.fn(),
  },
}))

import ApkService from '@/renderer/services/ApkService'
import unifiedApi from '@/renderer/api/unifiedApi'

const mockApi = {
  analyzeApk: vi.fn(),
  decompileApk: vi.fn(),
  recompileApk: vi.fn(),
  signApk: vi.fn(),
  getApkProgress: vi.fn(),
  cancelApkTask: vi.fn(),
  writeFile: vi.fn(),
}

describe('ApkService', () => {
  let service: ApkService

  beforeEach(() => {
    vi.clearAllMocks()
    ;(unifiedApi.getAPI as ReturnType<typeof vi.fn>).mockReturnValue(mockApi)
    service = new ApkService()
  })

  describe('analyzeApk', () => {
    it('analyzes APK and returns result', async () => {
      mockApi.analyzeApk.mockResolvedValue({
        package_name: 'com.test.app',
        version_code: '1',
        version_name: '1.0',
        min_sdk_version: '21',
        target_sdk_version: '33',
        permissions: ['android.permission.INTERNET'],
        application_label: 'Test App',
      })

      const result = await service.analyzeApk('/test.apk')
      expect(result.success).toBe(true)
      expect(result.data.packageName).toBe('com.test.app')
      expect(result.data.versionCode).toBe('1')
    })

    it('returns failure for invalid result', async () => {
      mockApi.analyzeApk.mockResolvedValue({})
      const result = await service.analyzeApk('/test.apk')
      expect(result.success).toBe(false)
      expect(result.error).toBeTruthy()
    })

    it('throws when API not available', async () => {
      ;(unifiedApi.getAPI as ReturnType<typeof vi.fn>).mockReturnValue(null)
      await expect(service.analyzeApk('/test.apk')).rejects.toThrow()
    })
  })

  describe('getApkBasicInfo', () => {
    it('extracts basic info from analysis', () => {
      const analysis = {
        packageName: 'com.test.app',
        versionName: '1.0',
        versionCode: '1',
        minSdkVersion: '21',
        targetSdkVersion: '33',
        applicationLabel: 'Test',
        fileSize: 1024,
      }
      const info = service.getApkBasicInfo(analysis)
      expect(info?.packageName).toBe('com.test.app')
      expect(info?.versionName).toBe('1.0')
      expect(info?.fileSize).toBe(1024)
    })

    it('handles snake_case keys', () => {
      const analysis = {
        package_name: 'com.test.snake',
        version_name: '2.0',
      }
      const info = service.getApkBasicInfo(analysis)
      expect(info?.packageName).toBe('com.test.snake')
      expect(info?.versionName).toBe('2.0')
    })

    it('returns null for null input', () => {
      expect(service.getApkBasicInfo(null)).toBeNull()
    })
  })

  describe('getPermissionLevel', () => {
    it('identifies dangerous permissions', () => {
      expect(service.getPermissionLevel('android.permission.CAMERA')).toBe('dangerous')
    })

    it('identifies normal permissions', () => {
      expect(service.getPermissionLevel('android.permission.INTERNET')).toBe('normal')
    })

    it('identifies custom permissions', () => {
      expect(service.getPermissionLevel('com.custom.permission')).toBe('custom')
    })
  })

  describe('getPermissionDescription', () => {
    it('returns description for known permission', () => {
      const desc = service.getPermissionDescription('android.permission.INTERNET')
      expect(desc).toBeTruthy()
    })

    it('returns custom for unknown permission', () => {
      const desc = service.getPermissionDescription('com.unknown.perm')
      expect(desc).toBe('自定义权限')
    })
  })

  describe('formatFileSize', () => {
    it('formats bytes correctly', () => {
      expect(service.formatFileSize(0)).toBe('0 B')
      expect(service.formatFileSize(1024)).toBe('1 KB')
      expect(service.formatFileSize(1048576)).toBe('1 MB')
    })
  })

  describe('generateAnalysisReport', () => {
    it('returns null for null input', () => {
      expect(service.generateAnalysisReport(null)).toBeNull()
    })

    it('generates report from analysis', () => {
      const analysis = {
        packageName: 'com.test',
        versionName: '1.0',
        versionCode: '1',
        permissions: ['android.permission.INTERNET'],
        activities: ['MainActivity'],
        services: ['TestService'],
        fileSize: 2048,
      }
      const report = service.generateAnalysisReport(analysis)
      expect(report).not.toBeNull()
      expect(report?.basicInfo.packageName).toBe('com.test')
      expect(report?.summary.totalPermissions).toBe(1)
      expect(report?.summary.totalActivities).toBe(1)
    })
  })

  describe('getAnalysisHistory', () => {
    it('returns empty array initially', () => {
      expect(service.getAnalysisHistory()).toEqual([])
    })
  })

  describe('clearAnalysisHistory', () => {
    it('clears history', () => {
      service.clearAnalysisHistory()
      expect(service.getAnalysisHistory()).toEqual([])
      expect(service.getCurrentApk()).toBeNull()
    })
  })

  describe('decompileApk', () => {
    it('throws when API not available', async () => {
      ;(unifiedApi.getAPI as ReturnType<typeof vi.fn>).mockReturnValue(null)
      await expect(service.decompileApk('/test.apk')).rejects.toThrow()
    })
  })

  describe('addListener / removeListener', () => {
    it('notifies listeners', () => {
      const listener = vi.fn()
      service.addListener(listener)
      service.notifyListeners('test-event', { data: 1 })
      expect(listener).toHaveBeenCalledWith('test-event', { data: 1 })

      service.removeListener(listener)
      service.notifyListeners('test-event', { data: 2 })
      expect(listener).toHaveBeenCalledTimes(1) // Not called again
    })
  })
})
