/**
 * 设备管理服务
 * 提供设备连接、监控和管理功能
 */
import { useDeviceStore } from '../stores'

class DeviceService {
  constructor() {
    this.name = 'DeviceService'
    this.deviceStore = null
    this.listeners = new Set()
    this.isMonitoring = false
    this.monitoringInterval = null
    this.backendAPI = null
    
    console.log('DeviceService 已初始化')
  }

  /**
   * 初始化服务
   */
  async initialize() {
    try {
      // 初始化设备 store
      this.deviceStore = useDeviceStore()
      
      // 设置后端 API 引用
      if (typeof window !== 'undefined' && window.electronAPI) {
        this.backendAPI = window.electronAPI
      }
      
      console.log('DeviceService 初始化完成')
      return { success: true }
    } catch (error) {
      console.error('DeviceService 初始化失败:', error)
      throw error
    }
  }

  /**
   * 初始化设备连接
   */
  async initializeDevices(autoDetect = true, startMonitoring = false) {
    try {
      console.log('初始化设备连接...')
      
      if (autoDetect) {
        await this.getAdbDevices()
      }
      
      if (startMonitoring) {
        await this.startDeviceMonitoring()
      }
      
      return { success: true, message: '设备初始化完成' }
    } catch (error) {
      console.error('设备初始化失败:', error)
      return { success: false, error: error.message }
    }
  }

  /**
   * 获取 ADB 设备列表
   */
  async getAdbDevices() {
    try {
      const result = await this.callBackendAPI('device.list')
      
      if (result.success) {
        this.deviceStore.updateDevices(result.devices || [])
        this.notifyListeners('devices_updated', result.devices)
        return result
      } else {
        throw new Error(result.error || '获取设备列表失败')
      }
    } catch (error) {
      console.error('获取设备列表失败:', error)
      this.deviceStore.updateDevices([])
      throw error
    }
  }

  /**
   * 选择设备
   */
  async selectDevice(deviceId) {
    try {
      const devices = this.deviceStore.devices.value
      const device = devices.find(d => d.id === deviceId)
      
      if (!device) {
        throw new Error(`设备不存在: ${deviceId}`)
      }
      
      this.deviceStore.selectDevice(device)
      this.notifyListeners('device_selected', device)
      
      return { success: true, device }
    } catch (error) {
      console.error('选择设备失败:', error)
      throw error
    }
  }

  /**
   * 获取设备详细信息
   */
  async getDeviceInfo(deviceId) {
    try {
      const result = await this.callBackendAPI('device.info', { device_id: deviceId })
      
      if (result.success) {
        this.deviceStore.updateDeviceInfo(result.device)
        this.notifyListeners('device_info_updated', result.device)
        return result
      } else {
        throw new Error(result.error || '获取设备信息失败')
      }
    } catch (error) {
      console.error('获取设备信息失败:', error)
      throw error
    }
  }

  /**
   * 开始设备监控
   */
  async startDeviceMonitoring() {
    if (this.isMonitoring) {
      return { success: true, message: '设备监控已在运行' }
    }
    
    try {
      this.isMonitoring = true
      this.deviceStore.setMonitoring(true)
      
      // 启动定期检查设备状态
      this.monitoringInterval = setInterval(async () => {
        try {
          await this.getAdbDevices()
        } catch (error) {
          console.error('设备监控检查失败:', error)
        }
      }, 5000) // 每5秒检查一次
      
      this.notifyListeners('monitoring_started', { monitoring: true })
      console.log('设备监控已启动')
      
      return { success: true, message: '设备监控已启动' }
    } catch (error) {
      console.error('启动设备监控失败:', error)
      this.isMonitoring = false
      this.deviceStore.setMonitoring(false)
      throw error
    }
  }

  /**
   * 停止设备监控
   */
  async stopDeviceMonitoring() {
    try {
      this.isMonitoring = false
      this.deviceStore.setMonitoring(false)
      
      if (this.monitoringInterval) {
        clearInterval(this.monitoringInterval)
        this.monitoringInterval = null
      }
      
      this.notifyListeners('monitoring_stopped', { monitoring: false })
      console.log('设备监控已停止')
      
      return { success: true, message: '设备监控已停止' }
    } catch (error) {
      console.error('停止设备监控失败:', error)
      throw error
    }
  }

  /**
   * 安装应用
   */
  async installApp(filePath, deviceId = null) {
    try {
      const params = { apk_path: filePath }
      if (deviceId) {
        params.device_id = deviceId
      }
      
      const result = await this.callBackendAPI('device.install.apk', params)
      
      if (result.success) {
        this.notifyListeners('app_installed', { filePath, deviceId })
      }
      
      return result
    } catch (error) {
      console.error('安装应用失败:', error)
      throw error
    }
  }

  /**
   * 卸载应用
   */
  async uninstallApp(packageName, deviceId) {
    try {
      const result = await this.callBackendAPI('device.uninstall', {
        package_name: packageName,
        device_id: deviceId
      })
      
      if (result.success) {
        this.notifyListeners('app_uninstalled', { packageName, deviceId })
      }
      
      return result
    } catch (error) {
      console.error('卸载应用失败:', error)
      throw error
    }
  }

  /**
   * 获取已安装应用列表
   */
  async getInstalledApps(deviceId, appType = 'all') {
    try {
      const result = await this.callBackendAPI('device.packages', {
        device_id: deviceId,
        app_type: appType
      })
      
      return result
    } catch (error) {
      console.error('获取应用列表失败:', error)
      throw error
    }
  }

  /**
   * 导出 APK
   */
  async exportApk(packageName, deviceId, outputDir) {
    try {
      const result = await this.callBackendAPI('device.export', {
        package_name: packageName,
        device_id: deviceId,
        output_dir: outputDir
      })
      
      return result
    } catch (error) {
      console.error('导出APK失败:', error)
      throw error
    }
  }

  /**
   * 启动 Logcat
   */
  async startLogcat(options = {}) {
    try {
      const result = await this.callBackendAPI('logcat.start', options)
      return result
    } catch (error) {
      console.error('启动Logcat失败:', error)
      throw error
    }
  }

  /**
   * 停止 Logcat
   */
  async stopLogcat() {
    try {
      const result = await this.callBackendAPI('logcat.stop')
      return result
    } catch (error) {
      console.error('停止Logcat失败:', error)
      throw error
    }
  }

  /**
   * 调用后端 API
   */
  async callBackendAPI(action, params = {}) {
    try {
      if (this.backendAPI && this.backendAPI.callPythonAPI) {
        return await this.backendAPI.callPythonAPI(action, params)
      } else {
        // 在浏览器环境中返回模拟结果
        console.log(`Mock API 调用: ${action}`, params)
        return this.getMockResponse(action, params)
      }
    } catch (error) {
      console.error(`API 调用失败 [${action}]:`, error)
      throw error
    }
  }

  /**
   * 获取模拟响应（用于浏览器环境）
   */
  getMockResponse(action, params) {
    switch (action) {
      case 'device.list':
        return {
          success: true,
          devices: [
            {
              id: 'mock_device_001',
              status: 'device',
              model: 'Mock Phone',
              brand: 'MockBrand',
              android_version: '12.0',
              api_level: '31'
            }
          ],
          count: 1
        }
      
      case 'device.info':
        return {
          success: true,
          device: {
            id: params.device_id,
            model: 'Mock Phone',
            brand: 'MockBrand',
            android_version: '12.0',
            api_level: '31',
            manufacturer: 'Mock Inc.',
            build_id: 'MOCK123456'
          }
        }
      
      default:
        return {
          success: true,
          message: `模拟环境：${action} 操作完成`
        }
    }
  }

  /**
   * 添加事件监听器
   */
  addListener(callback) {
    this.listeners.add(callback)
  }

  /**
   * 移除事件监听器
   */
  removeListener(callback) {
    this.listeners.delete(callback)
  }

  /**
   * 设备变化监听器（兼容性方法）
   */
  onDeviceChange(callback) {
    this.addListener((event, data) => {
      if (event === 'devices_updated' || event === 'device_selected') {
        callback({ event, data })
      }
    })
  }

  /**
   * Logcat 输出监听器（兼容性方法）
   */
  onLogcatOutput(callback) {
    this.addListener((event, data) => {
      if (event === 'logcat_output') {
        callback(data)
      }
    })
  }

  /**
   * 通知所有监听器
   */
  notifyListeners(event, data) {
    this.listeners.forEach(callback => {
      try {
        callback(event, data)
      } catch (error) {
        console.error('设备服务监听器错误:', error)
      }
    })
  }

  /**
   * 销毁服务
   */
  destroy() {
    this.stopDeviceMonitoring()
    this.listeners.clear()
    console.log('DeviceService 已销毁')
  }
}

export default DeviceService