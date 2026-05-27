import { defineStore } from 'pinia'
import { ref, reactive, computed, watch } from 'vue'

interface Device {
  id: string;
  name?: string;
  status?: string;
  [key: string]: unknown;
}

interface InstalledApp {
  packageName: string;
  [key: string]: unknown;
}

export const useDeviceStore = defineStore('deviceConfig', () => {
  // 设备列表
  const devices = ref<Device[]>([])
  const selectedDeviceId = ref('')
  const apps = ref<InstalledApp[]>([])
  const appType = ref('all')
  const isLogcatRunning = ref(false)
  const logcatOutput = ref<string[]>([])
  const logcatProcessId = ref<string>('')

  // 设备详细信息
  const deviceInfo = reactive<Record<string, string>>({
    model: '',
    brand: '',
    androidVersion: '',
    apiLevel: '',
    manufacturer: '',
    buildId: '',
    buildNumber: '',
    totalStorage: '',
    availableStorage: '',
    batteryLevel: '',
    screenResolution: '',
    density: '',
    architecture: '',
    systemActivationDate: '',
    pageSize: '',
    product: '',
    serial: '',
    state: ''
  })

  // 监控状态
  const isMonitoring = ref(false)
  const monitoringInterval = ref<ReturnType<typeof setInterval> | null>(null)

  const shellOutput = ref('')

  // 计算属性
  const deviceCount = computed(() => devices.value.length)
  const selectedDevice = computed(() => devices.value.find(d => d.id === selectedDeviceId.value) || null)
  const connectionStatus = computed(() => ({
    connected: deviceCount.value > 0,
    text: deviceCount.value > 0 ? `已连接 ${deviceCount.value} 个设备` : '未发现设备'
  }))

  // 更新设备列表
  const updateDevices = (deviceList: unknown[]) => {
    const list = Array.isArray(deviceList) ? deviceList : []
    devices.value = list
      .map(d => {
        if (typeof d === 'string') {
          return { id: d, name: d, status: 'online' } as Device
        }
        if (d && typeof d === 'object') {
          const maybeDevice = d as Device
          if (typeof maybeDevice.id === 'string' && maybeDevice.id) {
            return maybeDevice
          }
        }
        return null
      })
      .filter((item): item is Device => item !== null)

    // 如果当前选中的设备不在新列表中，清除选择
    if (selectedDeviceId.value && !devices.value.find(d => d.id === selectedDeviceId.value)) {
      selectedDeviceId.value = ''
      Object.keys(deviceInfo).forEach(key => deviceInfo[key] = '')
    }
  }

  // 选择设备
  const selectDevice = (deviceId: string) => {
    selectedDeviceId.value = deviceId || ''
  }

  // 更新设备详细信息
  const updateDeviceInfo = (info: unknown) => {
    const newInfo = (info && typeof info === 'object') ? (info as Record<string, unknown>) : {}
    Object.keys(deviceInfo).forEach(key => {
      const snakeKey = key.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`)
      const directValue = newInfo[key]
      const snakeValue = newInfo[snakeKey]
      const nextValue = typeof directValue === 'string'
        ? directValue
        : (typeof snakeValue === 'string' ? snakeValue : '')
      deviceInfo[key] = nextValue
    })
  }

  const clearLogcat = () => { logcatOutput.value = [] }

  const stopDeviceMonitoring = async () => {
    try {
      isMonitoring.value = false

      if (monitoringInterval.value) {
        clearInterval(monitoringInterval.value)
        monitoringInterval.value = null
      }

      console.log('设备监控已停止')

      return { success: true, message: '设备监控已停止' }
    } catch (error) {
      console.error('停止设备监控失败:', error)
      throw error
    }
  }

  // 监听设备选择变化，自动刷新详情
  watch(selectedDeviceId, async (id) => {
    if (!id) {
      Object.keys(deviceInfo).forEach(key => deviceInfo[key] = '')
      apps.value = []
      return
    }

  })

  return {
    // 状态
    devices,
    selectedDeviceId,
    selectedDevice,
    deviceInfo,
    isMonitoring,
    connectionStatus,
    deviceCount,
    shellOutput,
    apps,
    appType,
    isLogcatRunning,
    logcatOutput,
    logcatProcessId,
    // 方法
    selectDevice,
    updateDevices,
    updateDeviceInfo,
    stopDeviceMonitoring,
    clearLogcat
  }
}, { persist: true })

// 导出 store 定义，实例化应该在组件中或 Pinia 初始化后进行
