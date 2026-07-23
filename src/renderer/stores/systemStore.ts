import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import serviceManager from '../services/ServiceManager'
import { log } from '@utils/logger'

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

  const getErrorMessage = (err: unknown): string => {
    return err instanceof Error ? err.message : String(err)
  }

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
        
        systemInfo.platform = sysInfo.platform || ''
        systemInfo.platform_version = sysInfo.platform_version || ''
        systemInfo.platform_release = sysInfo.platform_release || ''
        systemInfo.architecture = sysInfo.architecture || ''
        systemInfo.hostname = sysInfo.hostname || ''
        systemInfo.cpuCount = sysInfo.cpu_count || cpu.count_logical || cpu.count_physical || ''
        systemInfo.processor = sysInfo.processor || ''

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
    } catch (err: unknown) {
      log.error('Failed to fetch system info:', err)
      error.value = getErrorMessage(err)
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
        buildInfo.electronVersion = frontendInfo.electronVersion || ''
        buildInfo.nodeVersion = frontendInfo.nodeVersion || ''
        buildInfo.chromeVersion = frontendInfo.chromeVersion || ''
        buildInfo.appName = frontendInfo.appName || ''
        buildInfo.appVersion = frontendInfo.appVersion || ''
        buildInfo.appDescription = frontendInfo.appDescription || ''
      }
      
      if (backendInfo) {
        buildInfo.pythonVersion = backendInfo.python_version || ''
        buildInfo.javaVersion = backendInfo.java_version || ''
      }
    } catch (err: unknown) {
      log.error('Failed to fetch build info:', err)
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
