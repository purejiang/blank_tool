import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import serviceManager from '../services/ServiceManager'

export const useSystemStore = defineStore('system', () => {
  const systemInfo = reactive({
    platform: '',
    platform_version: '',
    platform_release: '',
    architecture: '',
    hostname: '',
    cpuCount: '',
    processor: '',
    memoryTotal: '',
    memoryUsed: '',
    memoryPercent: '',
    diskTotal: '',
    diskUsed: '',
    diskPercent: ''
  })

  const buildInfo = reactive({
    appName: '',
    appVersion: '',
    appDescription: '',
    electronVersion: '',
    nodeVersion: '',
    chromeVersion: '',
    javaVersion: '',
    pythonVersion: ''
  })

  const loading = ref(false)
  const error = ref(null)

  // Helper to format file size
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const fetchSystemInfo = async () => {
    try {
      loading.value = true
      const systemService = await serviceManager.getService('system')
      const systemResult = await systemService.getSystemInfo()

      if (systemResult && systemResult.system_info) {
        const sysInfo = systemResult.system_info
        const cpu = sysInfo.cpu || {}
        const memory = sysInfo.memory || {}
        
        systemInfo.platform = sysInfo.platform || '未知'
        systemInfo.platform_version = sysInfo.platform_version || '未知'
        systemInfo.platform_release = sysInfo.platform_release || '未知'
        systemInfo.architecture = sysInfo.architecture || '未知'
        systemInfo.hostname = sysInfo.hostname || '未知'
        systemInfo.cpuCount = sysInfo.cpu_count || cpu.count_logical || cpu.count_physical || '未知'
        systemInfo.processor = sysInfo.processor || '未知'

        // Memory info
        const memoryTotal = sysInfo.memoryTotal || memory.total
        const memoryUsed = sysInfo.memoryUsed || memory.used
        const memoryPercent = sysInfo.memoryPercent ?? memory.percent

        if (memoryTotal) systemInfo.memoryTotal = formatFileSize(memoryTotal)
        if (memoryUsed) systemInfo.memoryUsed = formatFileSize(memoryUsed)
        if (memoryPercent !== undefined && memoryPercent !== null && memoryPercent !== '') {
          const pct = typeof memoryPercent === 'number' ? memoryPercent : parseFloat(memoryPercent)
          if (!Number.isNaN(pct)) systemInfo.memoryPercent = `${pct.toFixed(1)}%`
        }

        // Disk info
        if (sysInfo.diskTotal) systemInfo.diskTotal = formatFileSize(sysInfo.diskTotal)
        if (sysInfo.diskUsed) systemInfo.diskUsed = formatFileSize(sysInfo.diskUsed)
        if (sysInfo.diskPercent !== undefined) systemInfo.diskPercent = `${sysInfo.diskPercent.toFixed(1)}%`
      }
    } catch (err) {
      console.error('Failed to fetch system info:', err)
      error.value = err.message
    } finally {
      loading.value = false
    }
  }

  const fetchBuildInfo = async () => {
    try {
      const systemService = await serviceManager.getService('system')
      const frontendInfo = await systemService.getFontendBuildInfo()
      const backendInfo = await systemService.getBackendBuildInfo()


      if (frontendInfo) {
        buildInfo.electronVersion = frontendInfo.electronVersion || '未知'
        buildInfo.nodeVersion = frontendInfo.nodeVersion || '未知'
        buildInfo.chromeVersion = frontendInfo.chromeVersion || '未知'
        buildInfo.appName = frontendInfo.appName || '未知'
        buildInfo.appVersion = frontendInfo.appVersion || '未知'
        buildInfo.appDescription = frontendInfo.appDescription || '未知'
      }
      
      if (backendInfo) {
        buildInfo.pythonVersion = backendInfo.python_version || '未知'
        buildInfo.javaVersion = backendInfo.java_version || '未知'
      }
    } catch (err) {
      console.error('Failed to fetch build info:', err)
    }
  }

  return {
    systemInfo,
    buildInfo,
    loading,
    error,
    fetchSystemInfo,
    fetchBuildInfo
  }
})
