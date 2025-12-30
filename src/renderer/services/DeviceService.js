import unifiedAPI from '../api/unifiedAPI.js'

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
        console.log("api.onLogcatOutput")
        api.onLogcatOutput((event, payload) => {
          // 如果 Logcat 已停止，直接忽略后续到达的日志包
          if (!deviceStore.isLogcatRunning) return

          const p = payload || {}
          if (p.process_id && !deviceStore.logcatProcessId) {
            deviceStore.logcatProcessId = String(p.process_id)
          }
          const line = p.line || ''
          const lines = p.lines || []
          
          if (lines && lines.length > 0) {
            // Batch update for better performance
            deviceStore.logcatOutput.push(...lines)
            
            // Limit buffer size to prevent memory issues (keep last 5000 lines)
            const maxLines = 5000
            const excess = deviceStore.logcatOutput.length - maxLines
            if (excess > 0) {
               // Use splice to remove from start (modify in place)
               deviceStore.logcatOutput.splice(0, excess)
            }
          } else if (line) {
            deviceStore.logcatOutput.push(line)
             // Limit buffer size
            if (deviceStore.logcatOutput.length > 5000) {
               deviceStore.logcatOutput.shift()
            }
          }
        })
      }
    } catch {}
  }

  async refreshDevices() {
    const store = await this.storeService.ensureDeviceStore()
    try {
      const api = unifiedAPI.getAPI()
      if (api && typeof api.getAdbDevices === 'function') {
        const list = await api.getAdbDevices()
        const safeList = Array.isArray(list) ? list : []
        store.updateDevices(safeList)
        return { success: true, devices: safeList }
      }
      throw new Error('getAdbDevices API not implemented')
    } catch (e) {
      store.updateDevices([])
      return { success: false, error: e.message }
    }
  }

  async getDeviceInfo(deviceId) {
    if (!deviceId) return { success: false }
    const store = await this.storeService.ensureDeviceStore()
    try {
      const api = unifiedAPI.getAPI()
      if (api && typeof api.getDeviceInfo === 'function') {
        const info = await api.getDeviceInfo(deviceId)
        store.updateDeviceInfo(info)
        return { success: true, device: info }
      }
      throw new Error('getDeviceInfo API not implemented')
    } catch (e) {
      return { success: false, error: e.message }
    }
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
    try {
      const api = unifiedAPI.getAPI()
      if (api && typeof api.rebootDevice === 'function') {
        await api.rebootDevice(dev.id, mode)
        return { success: true }
      }
      throw new Error('rebootDevice API not implemented')
    } catch (e) {
      return { success: false, error: e.message }
    }
  }

  async executeShell(command) {
    const store = await this.storeService.ensureDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !command) return
    try {
      const api = unifiedAPI.getAPI()
      if (api && typeof api.executeShell === 'function') {
        const result = await api.executeShell(dev.id, command)
        store.shellOutput = (result && result.output) || ''
        return
      }
      throw new Error('executeShell API not implemented')
    } catch (e) {
      store.shellOutput = e.message || '执行失败'
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
      if (api && typeof api.startLogcat === 'function') {
        api.startLogcat(dev.id)
      } else {
        throw new Error('startLogcat API not implemented')
      }
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
      // 抛出异常或仅记录错误
      console.error('stopLogcat API not implemented or process ID missing')
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

    try {
      const api = unifiedAPI.getAPI()
      let list = []
      
      if (api && typeof api.getInstalledApps === 'function') {
        const resp = await api.getInstalledApps(dev.id, store.appType)
        // preload.js 已经解包，resp 应该直接是列表
        if (Array.isArray(resp)) {
          list = resp
        }
      } else {
         throw new Error('getInstalledApps API not implemented')
      }

      store.apps = list.map(item => (typeof item === 'string' ? { packageName: item } : { packageName: item.packageName || item.package_name || '' })).filter(a => a.packageName)
    } catch (e) {
      console.error('刷新应用列表失败:', e)
      store.apps = []
    }
  }

  async exportAppList() {
    const store = await this.storeService.ensureDeviceStore()
    return store.apps && store.apps.length > 0
  }

  async exportLogcat() {
    const store = await this.storeService.ensureDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id) return false

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

    if (api && typeof api.callBackendAPI === 'function') {
      try {
        const result = await api.callBackendAPI('adb.export_logcat', { device_id: dev.id, file_path: filePath })
        return result && result.success
      } catch (e) {
        console.error('Export logcat failed:', e)
        return false
      }
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
    
    // 需要先让用户选择保存目录
    const api = unifiedAPI.getAPI()
    let outputDir = ''
    if (api && typeof api.selectDirectory === 'function') {
      const res = await api.selectDirectory({ title: '选择导出目录' })
      if (!res || res.canceled) return false
      outputDir = res.directoryPath || (res.filePaths && res.filePaths[0]) || ''
    }

    if (!outputDir) return false

    if (api && typeof api.exportApk === 'function') {
      const resp = await api.exportApk(pkg, dev.id, outputDir)
      // preload.js 已解包，如果没报错就是成功
      return !!resp
    }
    
    // throw new Error('exportApk API not implemented')
    // 为了不破坏现有逻辑，如果 API 不存在，暂时返回 false，或者抛出异常
    // 根据用户指令 "如果没有方法就抛出异常"
    throw new Error('exportApk API not implemented')
  }

  async uninstallApp(pkg) {
    const store = await this.storeService.ensureDeviceStore()
    const dev = store.selectedDevice
    if (!dev || !dev.id || !pkg) return false
    const api = unifiedAPI.getAPI()
    if (api && typeof api.uninstallApp === 'function') {
      const resp = await api.uninstallApp(pkg, dev.id)
      await this.refreshAppList()
      // preload.js 已解包
      return !!resp
    }
    throw new Error('uninstallApp API not implemented')
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
      if (isAab) {
        if (typeof api.installAab === 'function') {
          resp = await api.installAab(apkPath, dev.id)
        } else {
           throw new Error('installAab API not implemented')
        }
      } else {
        if (typeof api.installApk === 'function') {
          resp = await api.installApk(apkPath, dev.id)
        } else {
           throw new Error('installApk API not implemented')
        }
      }
    } else {
       throw new Error('Unified API not available')
    }

    if (resp) return { success: true, payload: resp }
    return { success: false, error: '安装失败' }
  }
}

export default DeviceService
