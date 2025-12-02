import unifiedAPI from '../api/unifiedApi.js'

class DeviceService {
  constructor(storeService) {
    this.storeService = storeService
    this.monitoringTimer = null
  }

  async initialize() {
    try {
      const deviceStore = await this.storeService.ensureDeviceStore()
      const api = unifiedAPI.getAPI()
      if (api && typeof api.onLogcatOutput === 'function') {
        this.attachLogcatOutputListener(deviceStore, api)
      }
      if (api && typeof api.onLogcatStarted === 'function') {
        api.onLogcatStarted((event, payload) => {
          const p = payload || {}
          if (p.process_id) deviceStore.logcatProcessId = String(p.process_id)
          deviceStore.isLogcatRunning = true
        })
      }
      if (api && typeof api.onLogcatFinished === 'function') {
        api.onLogcatFinished(() => {
          deviceStore.isLogcatRunning = false
        })
      }
      if (api && typeof api.onLogcatError === 'function') {
        api.onLogcatError(() => {
          deviceStore.isLogcatRunning = false
        })
      }
    } catch {}
  }

  attachLogcatOutputListener(deviceStore, api) {
    try {
      if (api && typeof api.removeLogcatListener === 'function') {
        api.removeLogcatListener()
      }
      if (api && typeof api.onLogcatOutput === 'function') {
        api.onLogcatOutput((event, payload) => {
          const p = payload || {}
          if (p.process_id && !deviceStore.logcatProcessId) {
            deviceStore.logcatProcessId = String(p.process_id)
          }
          const line = p.line || ''
          if (line) {
            deviceStore.logcatOutput.push(line)
          }
        })
      }
    } catch {}
  }

  async refreshDevices() {
    const store = await this.storeService.ensureDeviceStore()
    const resp = await unifiedAPI.call('adb.devices')
    if (resp && resp.type === 'success') {
      const list = Array.isArray(resp.payload) ? resp.payload : []
      store.updateDevices(list)
      return { success: true, devices: list }
    }
    store.updateDevices([])
    return { success: false }
  }

  async getDeviceInfo(deviceId) {
    if (!deviceId) return { success: false }
    const store = await this.storeService.ensureDeviceStore()
    const resp = await unifiedAPI.call('device.info', { device_id: deviceId })
    if (resp && resp.type === 'success') {
      store.updateDeviceInfo(resp.payload)
      return { success: true, device: resp.payload }
    }
    return { success: false }
  }

  async startMonitoring(intervalMs = 5000) {
    if (this.monitoringTimer) return { success: true }
    const store = await this.storeService.ensureDeviceStore()
    store.isMonitoring = true
    this.monitoringTimer = setInterval(async () => {
      try {
        await this.refreshDevices()
        const dev = store.selectedDevice
        if (dev && dev.id) {
          await this.getDeviceInfo(dev.id)
        }
      } catch {}
    }, intervalMs)
    return { success: true }
  }

  async stopMonitoring() {
    const store = await this.storeService.ensureDeviceStore()
    store.isMonitoring = false
    if (this.monitoringTimer) {
      clearInterval(this.monitoringTimer)
      this.monitoringTimer = null
    }
    return { success: true }
  }

  async toggleMonitoring() {
    const store = await this.storeService.ensureDeviceStore()
    if (store.isMonitoring) return await this.stopMonitoring()
    return await this.startMonitoring()
  }

  async rebootDevice(mode = 'normal') {
    const store = await this.storeService.ensureDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id) return { success: false, error: '未选择设备' }
    return await unifiedAPI.call('device.reboot', { device_id: dev.id, mode })
  }

  async executeShell(command) {
    const store = await this.storeService.ensureDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !command) return
    const resp = await unifiedAPI.call('device.shell', { device_id: dev.id, command })
    if (resp && resp.type === 'success') {
      store.shellOutput = (resp.payload && resp.payload.output) || ''
    } else {
      store.shellOutput = (resp && resp.payload && resp.payload.message) || '执行失败'
    }
  }

  async toggleLogcat() {
    const store = await this.storeService.ensureDeviceStore()
    if (store.isLogcatRunning) return await this.stopLogcat()
    return await this.startLogcat()
  }

  async startLogcat() {
    const store = await this.storeService.ensureDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id) return false
    const api = unifiedAPI.getAPI()
    // 启动前清理旧输出，避免重复显示旧缓冲日志
    store.logcatOutput = []
    if (api && typeof api.onLogcatOutput === 'function') {
      this.attachLogcatOutputListener(store, api)
    }
    // 统一走后端流式接口，并请求 fresh 启动（后端将清空 logcat 缓冲）
    try {
      unifiedAPI.call('adb.logcat', { device_id: dev.id })
    } catch {}
    // 状态由 onLogcatStarted 事件驱动；为避免等待阻塞，直接标记为运行中
    store.isLogcatRunning = true
    return true
  }

  async stopLogcat() {
    const store = await this.storeService.ensureDeviceStore()
    const api = unifiedAPI.getAPI()
    if (api && typeof api.stopLogcat === 'function' && store.logcatProcessId) {
      await api.stopLogcat(store.logcatProcessId)
    } else {
      await unifiedAPI.call('device.logcat_stop', { process_id: store.logcatProcessId })
    }
    store.isLogcatRunning = false
    store.logcatProcessId = ''
    return true
  }

  clearLogcat() {
    return this.storeService.ensureDeviceStore().then(store => { store.logcatOutput = [] })
  }

  async refreshAppList() {
    const store = await this.storeService.ensureDeviceStore()
    store.apps = []
    const dev = store.selectedDevice
    if (!dev || !dev.id) return
    const resp = await unifiedAPI.call('device.list_apps', { device_id: dev.id, type: store.appType })
    if (resp && resp.type === 'success') {
      const list = Array.isArray(resp.payload) ? resp.payload : []
      store.apps = list.map(item => (typeof item === 'string' ? { packageName: item } : { packageName: item.packageName || item.package_name || '' })).filter(a => a.packageName)
    }
  }

  async exportAppList() {
    const store = await this.storeService.ensureDeviceStore()
    return store.apps && store.apps.length > 0
  }

  async exportLogcat() {
    const store = await this.storeService.ensureDeviceStore()
    const lines = Array.isArray(store.logcatOutput) ? store.logcatOutput : []
    if (lines.length === 0) return false
    const api = unifiedAPI.getAPI()
    const now = new Date()
    const pad = (n) => String(n).padStart(2, '0')
    const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
    const def = `logcat-${ts}.txt`
    let filePath = ''
    if (api && typeof api.showSaveDialog === 'function') {
      const res = await api.showSaveDialog({ title: '导出 Logcat', defaultPath: def, filters: [{ name: 'Text', extensions: ['txt', 'log'] }] })
      if (!res || res.canceled) return false
      filePath = res.filePath || ''
    }
    if (!filePath) return false
    const content = lines.join('\n')
    if (api && typeof api.writeFile === 'function') {
      await api.writeFile(filePath, content)
      return true
    }
    return false
  }

  async copyPackageName(pkg) {
    if (!pkg) return
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(pkg)
      } else if (typeof window !== 'undefined' && window.electronAPI && window.electronAPI.writeClipboardText) {
        await window.electronAPI.writeClipboardText(pkg)
      }
    } catch {}
  }

  async exportApp(pkg) {
    const store = await this.storeService.ensureDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false
    const resp = await unifiedAPI.call('device.export_app', { device_id: dev.id, package_name: pkg })
    return !!resp
  }

  async uninstallApp(pkg) {
    const store = await this.storeService.ensureDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false
    const resp = await unifiedAPI.call('device.uninstall_app', { device_id: dev.id, package_name: pkg })
    await this.refreshAppList()
    return !!resp
  }

  async installApp(apkPath, options = {}) {
    if (!apkPath) return { success: false, error: '未选择安装文件' }
    const store = await this.storeService.ensureDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id) return { success: false, error: '未选择设备' }
    const api = unifiedAPI.getAPI()
    const isAab = /\.aab$/i.test(apkPath)
    let resp = null
    if (api) {
      try {
        if (isAab && typeof api.installAab === 'function') {
          resp = await api.installAab(apkPath, dev.id)
        } else if (typeof api.installApk === 'function') {
          resp = await api.installApk(apkPath, dev.id)
        }
      } catch {}
    }
    if (!resp) {
      if (isAab) {
        resp = await unifiedAPI.call('device.install_aab', { aab_path: apkPath, device_id: dev.id, options })
      } else {
        resp = await unifiedAPI.call('device.install_apk', { apk_path: apkPath, device_id: dev.id, options })
      }
    }
    if (resp && resp.type === 'success') return { success: true, payload: resp.payload }
    return { success: false, error: (resp && resp.error) || (resp && resp.payload && resp.payload.message) || '安装失败' }
  }
}

export default DeviceService
