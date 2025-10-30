/**
 * Electron API 服务
 * 提供对 Electron API 的统一访问接口
 */
class ElectronAPIService {
  constructor() {
    this.api = null
    this.isAvailable = false
    this.initialize()
  }

  /**
   * 初始化 Electron API
   */
  initialize() {
    try {
      // 检查是否在 Electron 环境中
      if (typeof window !== 'undefined' && window.electronAPI) {
        this.api = window.electronAPI
        this.isAvailable = true
        console.log('ElectronAPIService: Electron API 已初始化')
      } else {
        console.warn('ElectronAPIService: 未检测到 Electron API，可能运行在浏览器环境中')
        this.isAvailable = false
        // 在浏览器环境中提供模拟 API
        this.api = this.createMockAPI()
      }
    } catch (error) {
      console.error('ElectronAPIService: 初始化失败', error)
      this.isAvailable = false
      this.api = this.createMockAPI()
    }
  }

  /**
   * 创建模拟 API（用于浏览器环境）
   */
  createMockAPI() {
    return {
      // 文件系统操作
      openPath: async (path) => {
        console.log('Mock: 打开路径', path)
        return { success: true, message: '模拟环境：无法打开路径' }
      },
      
      selectDirectory: async () => {
        console.log('Mock: 选择目录')
        return { 
          success: true, 
          path: '/mock/selected/directory',
          message: '模拟环境：已选择模拟目录'
        }
      },
      
      selectFile: async (options = {}) => {
        console.log('Mock: 选择文件', options)
        return { 
          success: true, 
          path: '/mock/selected/file.txt',
          message: '模拟环境：已选择模拟文件'
        }
      },
      
      // 开发者工具
      openDevTools: () => {
        console.log('Mock: 打开开发者工具')
        if (typeof window !== 'undefined' && window.open) {
          // 在浏览器中打开新窗口作为模拟
          window.open('about:blank', '_blank', 'width=800,height=600')
        }
      },
      
      // 应用信息
      getAppVersion: async () => {
        return '1.0.0-mock'
      },
      
      // 系统信息
      getSystemInfo: async () => {
        return {
          platform: 'mock',
          arch: 'x64',
          version: '1.0.0'
        }
      }
    }
  }

  /**
   * 检查 API 是否可用
   */
  checkAvailability() {
    return this.isAvailable
  }

  /**
   * 获取 API 实例
   */
  getAPI() {
    return this.api
  }

  /**
   * 安全调用 API 方法
   */
  async safeCall(methodName, ...args) {
    try {
      if (this.api && typeof this.api[methodName] === 'function') {
        return await this.api[methodName](...args)
      } else {
        console.warn(`ElectronAPIService: 方法 ${methodName} 不可用`)
        return { success: false, error: `方法 ${methodName} 不可用` }
      }
    } catch (error) {
      console.error(`ElectronAPIService: 调用 ${methodName} 失败`, error)
      return { success: false, error: error.message }
    }
  }
}

// 创建单例实例
const electronAPIService = new ElectronAPIService()

export default electronAPIService