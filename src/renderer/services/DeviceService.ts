import { useDeviceStore } from '@stores/deviceStore'
import unifiedApi from '../api/unifiedApi'
import type { ElectronApi } from '../../shared/ipc/electronApi'
import { log } from '@utils/logger'

type DeviceLike = {
  id: string
  [key: string]: unknown
}

type InstalledApp = {
  packageName: string
}

type LogcatPayload = {
  process_id?: string | number
  line?: string
  lines?: string[]
}

interface DeviceStoreLike {
  logcatProcessId: string
  isLogcatRunning: boolean
  logcatOutput: string[]
  selectedDevice: DeviceLike | null
  shellOutput: string
  apps: InstalledApp[]
  appType: string
  isMonitoring: boolean
  updateDevices: (devices: unknown[]) => void
  updateDeviceInfo: (info: unknown) => void
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function toLogcatPayload(payload: unknown): LogcatPayload {
  if (!payload || typeof payload !== 'object') {
    return {}
  }
  return payload as LogcatPayload
}

function getDeviceStore(): DeviceStoreLike {
  return useDeviceStore() as unknown as DeviceStoreLike
}

class DeviceService {
  private monitoringTimer: ReturnType<typeof setInterval> | null

  constructor() {
    this.monitoringTimer = null
  }

  async initialize() {
    try {
      const deviceStore = getDeviceStore()
      // Transient logcat state must not survive an app restart: the backend
      // logcat process is gone, but the persisted store may still carry the
      // old PID and "running" flag — the stale PID then blocks capturing the
      // new one and "stop" kills nothing while logs keep streaming.
      deviceStore.logcatProcessId = ''
      deviceStore.isLogcatRunning = false
      const api = unifiedApi.getAPI()
      if (api && typeof api.onLogcatOutput === 'function') {
        this.attachLogcatOutputListener(deviceStore, api)
      }
      if (api && typeof api.onLogcatStarted === 'function') {
        api.onLogcatStarted((payload: unknown) => {
          // The 'started' event carries the real backend process_id — capture
          // it here instead of waiting for the first log line.
          const p = toLogcatPayload(payload)
          if (p.process_id) deviceStore.logcatProcessId = String(p.process_id)
          deviceStore.isLogcatRunning = true
        })
      }
      if (api && typeof api.onLogcatFinished === 'function') {
        api.onLogcatFinished(() => {
          deviceStore.isLogcatRunning = false
        })
      }
    } catch {}
  }

  attachLogcatOutputListener(deviceStore: DeviceStoreLike, api: ElectronApi) {
    try {
      if (api && typeof api.removeLogcatListener === 'function') {
        api.removeLogcatListener()
      }
      if (api && typeof api.onLogcatOutput === 'function') {
        api.onLogcatOutput((output: unknown) => {
          const p = toLogcatPayload(output)
          if (p.process_id && !deviceStore.logcatProcessId) {
            deviceStore.logcatProcessId = String(p.process_id)
          }
          const line = p.line || ''
          const lines = p.lines || []

          if (lines.length > 0) {
            const arr = [...deviceStore.logcatOutput, ...lines]
            if (arr.length > 5000) arr.splice(0, arr.length - 5000)
            deviceStore.logcatOutput = arr
          } else if (line) {
            const arr = [...deviceStore.logcatOutput, line]
            if (arr.length > 5000) arr.splice(0, arr.length - 5000)
            deviceStore.logcatOutput = arr
          }
        })
      }
    } catch {}
  }

  async refreshDevices() {
    const store = getDeviceStore()
    try {
      const api = unifiedApi.getAPI()
      if (api && typeof api.getAdbDevices === 'function') {
        const list = await api.getAdbDevices()
        const safeList = Array.isArray(list) ? list : []
        store.updateDevices(safeList)
        return { success: true, devices: safeList }
      }
      throw new Error('getAdbDevices API not implemented')
    } catch (e) {
      store.updateDevices([])
      return { success: false, error: getErrorMessage(e) }
    }
  }

  async getDeviceInfo(deviceId: string) {
    if (!deviceId) return { success: false }
    const store = getDeviceStore()
    try {
      const api = unifiedApi.getAPI()
      if (api && typeof api.getDeviceInfo === 'function') {
        const info = await api.getDeviceInfo(deviceId)
        store.updateDeviceInfo(info)
        return { success: true, device: info }
      }
      throw new Error('getDeviceInfo API not implemented')
    } catch (e) {
      return { success: false, error: getErrorMessage(e) }
    }
  }

  async startMonitoring(intervalMs = 5000, withInfo = false) {
    if (this.monitoringTimer) return { success: true }
    const store = getDeviceStore()
    store.isMonitoring = true
    this.monitoringTimer = setInterval(async () => {
      try {
        await this.refreshDevices()
        // Device-info refresh is dumpsys-heavy — only the Device page asks
        // for it; the global monitor just keeps the device list fresh.
        if (withInfo) {
          const dev = store.selectedDevice
          if (dev && dev.id) {
            await this.getDeviceInfo(dev.id)
          }
        }
      } catch {}
    }, intervalMs)
    return { success: true }
  }

  async stopMonitoring() {
    const store = getDeviceStore()
    store.isMonitoring = false
    if (this.monitoringTimer) {
      clearInterval(this.monitoringTimer)
      this.monitoringTimer = null
    }
    return { success: true }
  }

  async toggleMonitoring() {
    const store = getDeviceStore()
    if (store.isMonitoring) return await this.stopMonitoring()
    return await this.startMonitoring()
  }

  async rebootDevice(mode = 'normal') {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id) return { success: false, error: 'No device selected' }
    try {
      const api = unifiedApi.getAPI()
      if (api && typeof api.rebootDevice === 'function') {
        await api.rebootDevice(dev.id, mode)
        return { success: true }
      }
      throw new Error('rebootDevice API not implemented')
    } catch (e) {
      return { success: false, error: getErrorMessage(e) }
    }
  }

  async executeShell(command: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !command) return
    try {
      const api = unifiedApi.getAPI()
      if (api && typeof api.executeShell === 'function') {
        const result = await api.executeShell(dev.id, command)
        store.shellOutput = (result && result.output) || ''
        return
      }
      throw new Error('executeShell API not implemented')
    } catch (e) {
      store.shellOutput = getErrorMessage(e) || 'Execution failed'
    }
  }

  async toggleLogcat() {
    const store = getDeviceStore()
    if (store.isLogcatRunning) return await this.stopLogcat()
    return await this.startLogcat()
  }

  async startLogcat() {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id) { return false }
    const api = unifiedApi.getAPI()

    store.logcatOutput = []
    // Drop any stale PID (e.g. persisted from a previous session) so the new
    // process_id from the 'started'/first log event is always captured —
    // otherwise "stop" targets a dead PID and the real stream keeps running.
    store.logcatProcessId = ''
    if (api && typeof api.onLogcatOutput === 'function') {
      this.attachLogcatOutputListener(store, api)
    }
    try {
      if (api && typeof api.startLogcat === 'function') {
        const result = await api.startLogcat(dev.id)
        store.isLogcatRunning = true
      } else {
        log.warn('[logcat] startLogcat API not implemented')
        throw new Error('startLogcat API not implemented')
      }
    } catch (e) {
      log.error('[logcat] startLogcat error:', e)
      store.isLogcatRunning = false
      return false
    }
    return true
  }

  async stopLogcat() {
    const store = getDeviceStore()
    const api = unifiedApi.getAPI()
    if (api && typeof api.stopLogcat === 'function') {
      if (store.logcatProcessId) {
        await api.stopLogcat(store.logcatProcessId)
      }
    } else {
      log.error('stopLogcat API not implemented')
    }
    store.isLogcatRunning = false
    store.logcatProcessId = ''
    return true
  }

  clearLogcat() {
    const store = getDeviceStore()
    store.logcatOutput = []
    return Promise.resolve()
  }

  async refreshAppList() {
    const store = getDeviceStore()
    store.apps = []
    const dev = store.selectedDevice
    if (!dev || !dev.id) return

    try {
      const api = unifiedApi.getAPI()
      let list: unknown[] = []

      if (api && typeof api.getInstalledApps === 'function') {
        const resp = await api.getInstalledApps(dev.id, store.appType)
        if (Array.isArray(resp)) {
          list = resp as unknown[]
        }
      } else {
        throw new Error('getInstalledApps API not implemented')
      }

      store.apps = list
        .map(item => {
          if (typeof item === 'string') return { packageName: item } as InstalledApp
          if (item && typeof item === 'object') {
            const obj = item as { packageName?: unknown; package_name?: unknown }
            return {
              packageName: typeof obj.packageName === 'string'
                ? obj.packageName
                : (typeof obj.package_name === 'string' ? obj.package_name : '')
            } as InstalledApp
          }
          return { packageName: '' } as InstalledApp
        })
        .filter(a => a.packageName)
    } catch (e) {
      log.error('Failed to refresh app list:', e)
      store.apps = []
    }
  }

  async exportAppList() {
    const store = getDeviceStore()
    return store.apps && store.apps.length > 0
  }

  async exportLogcat() {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id) return false

    const api = unifiedApi.getAPI()
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
    const def = `logcat-${ts}.txt`
    let filePath = ''
    if (api && typeof api.showSaveDialog === 'function') {
      const res = await api.showSaveDialog({ title: 'Export Logcat', defaultPath: def, filters: [{ name: 'Text', extensions: ['txt', 'log'] }] })
      if (!res || res.canceled) return false
      filePath = res.filePath || ''
    }
    if (!filePath) return false

    if (api && typeof api.callBackendAPI === 'function') {
      try {
        const result = await api.callBackendAPI('adb.export_logcat', { device_id: dev.id, file_path: filePath })
        if (result && typeof result === 'object' && 'success' in result) {
          return (result as { success?: boolean }).success === true
        }
        return Boolean(result)
      } catch (e) {
        log.error('Export logcat failed:', e)
        return false
      }
    }
    return false
  }

  async copyPackageName(pkg: string) {
    if (!pkg) return
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(pkg)
      } else {
        const api = unifiedApi.getAPI()
        if (api && typeof api.writeClipboardText === 'function') {
          await api.writeClipboardText(pkg)
        }
      }
    } catch {}
  }

  async exportApp(pkg: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false

    const api = unifiedApi.getAPI()
    let outputDir = ''
    if (api && typeof api.selectDirectory === 'function') {
      const res = await api.selectDirectory({ title: 'Select export directory' })
      if (!res || res.canceled) return false
      outputDir = res.directoryPath || (res.filePaths && res.filePaths[0]) || ''
    }

    if (!outputDir) return false

    if (api && typeof api.exportApk === 'function') {
      const resp = await api.exportApk(pkg, dev.id, outputDir)
      return !!resp
    }

    throw new Error('exportApk API not implemented')
  }

  async uninstallApp(pkg: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false
    const api = unifiedApi.getAPI()
    if (api && typeof api.uninstallApp === 'function') {
      const resp = await api.uninstallApp(pkg, dev.id)
      await this.refreshAppList()
      return !!resp
    }
    throw new Error('uninstallApp API not implemented')
  }

  async launchApp(pkg: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false
    const api = unifiedApi.getAPI()
    if (api && typeof api.launchApp === 'function') {
      const resp = await api.launchApp(pkg, dev.id)
      return !!resp
    }
    throw new Error('launchApp API not implemented')
  }

  async clearAppData(pkg: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false
    const api = unifiedApi.getAPI()
    if (api && typeof api.clearAppData === 'function') {
      const resp = await api.clearAppData(pkg, dev.id)
      return !!resp
    }
    throw new Error('clearAppData API not implemented')
  }

  /**
   * Capture device screenshot. Returns the saved file path, or false when
   * no device selected / user canceled the save dialog.
   */
  async screenshotDevice(): Promise<string | false> {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id) return false
    const api = unifiedApi.getAPI()

    let filePath = ''
    if (api && typeof api.showSaveDialog === 'function') {
      const now = new Date()
      const pad = (n: number) => String(n).padStart(2, '0')
      const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
      const res = await api.showSaveDialog({
        title: 'Screenshot',
        defaultPath: `screenshot-${ts}.png`,
        filters: [{ name: 'PNG', extensions: ['png'] }],
      })
      if (!res || res.canceled) return false
      filePath = res.filePath || ''
    }

    if (api && typeof api.screenshot === 'function') {
      const resp = (await api.screenshot(dev.id, filePath || undefined)) as { file_path?: string } | null
      return resp?.file_path || filePath || false
    }
    throw new Error('screenshot API not implemented')
  }

  async installApp(apkPath: string, options: Record<string, unknown> = {}) {
    if (!apkPath) return { success: false, error: 'No install file selected' }
    const store = getDeviceStore()
    // 任务侧可显式指定目标设备（PackagePage 安装下拉）；未指定时回退到设备列表当前选中项
    const overrideId = typeof options.device_id === 'string' ? options.device_id : ''
    const dev: DeviceLike | null = overrideId
      ? { id: overrideId }
      : (store.selectedDevice as DeviceLike | null)
    if (!dev || !dev.id) return { success: false, error: 'No device selected' }
    const api = unifiedApi.getAPI()
    const isAab = /\.aab$/i.test(apkPath)
    const taskId = typeof options.task_id === 'string' ? options.task_id : ''
    let resp = null

    if (api) {
      if (isAab) {
        if (typeof api.installAab === 'function') {
          resp = await api.installAab(apkPath, dev.id, taskId)
        } else {
          throw new Error('installAab API not implemented')
        }
      } else {
        if (typeof api.installApk === 'function') {
          resp = await api.installApk(apkPath, dev.id, taskId)
        } else {
          throw new Error('installApk API not implemented')
        }
      }
    } else {
      throw new Error('Unified API not available')
    }

    const cancelled = !!(resp && (resp as any).cancelled)
    return { success: !cancelled, cancelled, payload: resp }
  }
}

export default DeviceService
