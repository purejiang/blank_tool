import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

export const useDeviceStore = defineStore('device', () => {
  // 设备列表
  const devices = ref([])
  
  // 当前选中的设备
  const currentDevice = ref(null)
  
  // 设备详细信息
  const deviceInfo = reactive({
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
    density: ''
  })
  
  // 监控状态
  const isMonitoring = ref(false)
  
  // 连接状态
  const connectionStatus = reactive({
    connected: false,
    text: '未连接'
  })

  // 更新设备列表
  const updateDevices = (deviceList) => {
    devices.value = deviceList || []
    
    // 如果当前选中的设备不在新列表中，清除选择
    if (currentDevice.value && !deviceList.find(d => d.id === currentDevice.value.id)) {
      currentDevice.value = null
      clearDeviceInfo()
    }
    
    // 更新连接状态
    updateConnectionStatus()
  }

  // 选择设备
  const selectDevice = (device) => {
    currentDevice.value = device
  }

  // 更新设备详细信息
  const updateDeviceInfo = (info) => {
    Object.assign(deviceInfo, {
      model: info.model || '',
      brand: info.brand || '',
      androidVersion: info.android_version || info.androidVersion || '',
      apiLevel: info.api_level || info.apiLevel || '',
      manufacturer: info.manufacturer || '',
      buildId: info.build_id || info.buildId || '',
      buildNumber: info.build_number || info.buildNumber || '',
      totalStorage: info.total_storage || info.totalStorage || '',
      availableStorage: info.available_storage || info.availableStorage || '',
      batteryLevel: info.battery_level || info.batteryLevel || '',
      screenResolution: info.screen_resolution || info.screenResolution || '',
      density: info.density || ''
    })
  }

  // 清除设备信息
  const clearDeviceInfo = () => {
    Object.assign(deviceInfo, {
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
      density: ''
    })
  }

  // 更新连接状态
  const updateConnectionStatus = () => {
    const deviceCount = devices.value.length
    connectionStatus.connected = deviceCount > 0
    connectionStatus.text = deviceCount > 0 
      ? `已连接 ${deviceCount} 个设备` 
      : '未发现设备'
  }

  // 设置监控状态
  const setMonitoring = (status) => {
    isMonitoring.value = status
  }

  // 获取设备数量
  const getDeviceCount = () => {
    return devices.value.length
  }

  // 根据ID查找设备
  const findDeviceById = (deviceId) => {
    return devices.value.find(device => device.id === deviceId)
  }

  return {
    // 状态
    devices,
    currentDevice,
    deviceInfo,
    isMonitoring,
    connectionStatus,
    
    // 方法
    updateDevices,
    selectDevice,
    updateDeviceInfo,
    clearDeviceInfo,
    updateConnectionStatus,
    setMonitoring,
    getDeviceCount,
    findDeviceById
  }
})

// 导出 store 定义，实例化应该在组件中或 Pinia 初始化后进行