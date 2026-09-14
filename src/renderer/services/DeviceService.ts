import { useDeviceStore } from '@stores/deviceStore'
import { optionalApiMethod, requireApiMethod } from '../api/apiAccess'
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
  appsLoaded: boolean
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
      const onLogcatOutput = optionalApiMethod('onLogcatOutput')
      if (onLogcatOutput) {
        this.attachLogcatOutputListener(deviceStore)
      }
      const onLogcatStarted = optionalApiMethod('onLogcatStarted')
      if (onLogcatStarted) {
        onLogcatStarted((payload: unknown) => {
          // The 'started' event carries the real backend process_id — capture
          // it here instead of waiting for the first log line.
          const p = toLogcatPayload(payload)
          if (p.process_id) deviceStore.logcatProcessId = String(p.process_id)
          deviceStore.isLogcatRunning = true
        })
      }
      const onLogcatFinished = optionalApiMethod('onLogcatFinished')
      if (onLogcatFinished) {
        onLogcatFinished(() => {
          deviceStore.isLogcatRunning = false
        })
      }
    } catch {}
  }

  attachLogcatOutputListener(deviceStore: DeviceStoreLike) {
    try {
      optionalApiMethod('removeLogcatListener')?.()
      const onLogcatOutput = optionalApiMethod('onLogcatOutput')
      if (onLogcatOutput) {
        onLogcatOutput((output: unknown) => {
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
      const list = await requireApiMethod('getAdbDevices')()
      const safeList = Array.isArray(list) ? list : []
      store.updateDevices(safeList)
      return { success: true, devices: safeList }
    } catch (e) {
      store.updateDevices([])
      return { success: false, error: getErrorMessage(e) }
    }
  }

  async getDeviceInfo(deviceId: string) {
    if (!deviceId) return { success: false }
    const store = getDeviceStore()
    try {
      const info = await requireApiMethod('getDeviceInfo')(deviceId)
      store.updateDeviceInfo(info)
      return { success: true, device: info }
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
      await requireApiMethod('rebootDevice')(dev.id, mode)
      return { success: true }
    } catch (e) {
      return { success: false, error: getErrorMessage(e) }
    }
  }

  async executeShell(command: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !command) return
    try {
      const result = await requireApiMethod('executeShell')(dev.id, command)
      store.shellOutput = (result && result.output) || ''
      return
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

    store.logcatOutput = []
    // Drop any stale PID (e.g. persisted from a previous session) so the new
    // process_id from the 'started'/first log event is always captured —
    // otherwise "stop" targets a dead PID and the real stream keeps running.
    store.logcatProcessId = ''
    if (optionalApiMethod('onLogcatOutput')) {
      this.attachLogcatOutputListener(store)
    }
    try {
      await requireApiMethod('startLogcat')(dev.id)
      store.isLogcatRunning = true
    } catch (e) {
      log.error('[logcat] startLogcat error:', e)
      store.isLogcatRunning = false
      return false
    }
    return true
  }

  async stopLogcat() {
    const store = getDeviceStore()
    const stopLogcat = optionalApiMethod('stopLogcat')
    if (stopLogcat) {
      if (store.logcatProcessId) {
        await stopLogcat(store.logcatProcessId)
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
    const dev = store.selectedDevice
    if (!dev || !dev.id) return

    // 先不动 store.apps：拉取期间保留旧列表 + loading 遮罩，比先清空再填好，
    // 不会闪一下空态。换设备的作废由 deviceStore 的 watch 负责。
    try {
      const resp = await requireApiMethod('getInstalledApps')(dev.id, store.appType)
      const list: unknown[] = Array.isArray(resp) ? (resp as unknown[]) : []

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
    } finally {
      // 成功、失败都算「已尝试过获取」——空态文案据此区分
      // 「还没点获取」和「获取到了 0 条」。
      store.appsLoaded = true
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

    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
    const def = `logcat-${ts}.txt`
    let filePath = ''
    const showSaveDialog = optionalApiMethod('showSaveDialog')
    if (showSaveDialog) {
      const res = await showSaveDialog({ title: 'Export Logcat', defaultPath: def, filters: [{ name: 'Text', extensions: ['txt', 'log'] }] })
      if (!res || res.canceled) return false
      filePath = res.filePath || ''
    }
    if (!filePath) return false

    const callBackendAPI = optionalApiMethod('callBackendAPI')
    if (callBackendAPI) {
      try {
        const result = await callBackendAPI('adb.export_logcat', { device_id: dev.id, file_path: filePath })
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
        await optionalApiMethod('writeClipboardText')?.(pkg)
      }
    } catch {}
  }

  async exportApp(pkg: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false

    let outputDir = ''
    const selectDirectory = optionalApiMethod('selectDirectory')
    if (selectDirectory) {
      const res = await selectDirectory({ title: 'Select export directory' })
      if (!res || res.canceled) return false
      outputDir = res.directoryPath || (res.filePaths && res.filePaths[0]) || ''
    }

    if (!outputDir) return false

    const resp = await requireApiMethod('exportApk')(pkg, dev.id, outputDir)
    return !!resp
  }

  async uninstallApp(pkg: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false
    const resp = await requireApiMethod('uninstallApp')(pkg, dev.id)
    await this.refreshAppList()
    return !!resp
  }

  async launchApp(pkg: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false
    const resp = await requireApiMethod('launchApp')(pkg, dev.id)
    return !!resp
  }

  async clearAppData(pkg: string) {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false
    const resp = await requireApiMethod('clearAppData')(pkg, dev.id)
    return !!resp
  }

  /**
   * Capture device screenshot. Returns the saved file path, or false when
   * no device selected / user canceled the save dialog.
   */
  async screenshotDevice(): Promise<string | false> {
    const store = getDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id) return false

    let filePath = ''
    const showSaveDialog = optionalApiMethod('showSaveDialog')
    if (showSaveDialog) {
      const now = new Date()
      const pad = (n: number) => String(n).padStart(2, '0')
      const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
      const res = await showSaveDialog({
        title: 'Screenshot',
        defaultPath: `screenshot-${ts}.png`,
        filters: [{ name: 'PNG', extensions: ['png'] }],
      })
      if (!res || res.canceled) return false
      filePath = res.filePath || ''
    }

    const resp = (await requireApiMethod('screenshot')(dev.id, filePath || undefined)) as { file_path?: string } | null
    return resp?.file_path || filePath || false
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
    const isAab = /\.aab$/i.test(apkPath)
    const taskId = typeof options.task_id === 'string' ? options.task_id : ''

    const resp = isAab
      ? await requireApiMethod('installAab')(apkPath, dev.id, taskId)
      : await requireApiMethod('installApk')(apkPath, dev.id, taskId)

    const cancelled = !!(resp && (resp as any).cancelled)
    return { success: !cancelled, cancelled, payload: resp }
  }
}

export default DeviceService
