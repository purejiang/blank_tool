/**
 *   统一的 API 服务
 * - 初始化并暴露 window.electronAPI
 * - 提供 safeCall 与后端 call(action, params)
 * - 在非 Electron 环境提供 Mock
 */
class UnifiedAPI {
  constructor() {
    this.api = null
    this.isAvailable = false
    this.initialize()
  }

  initialize() {
    try {
      if (typeof window !== 'undefined' && window.electronAPI) {
        this.api = window.electronAPI
        this.isAvailable = true
        console.log('UnifiedAPIService: Electron API 已初始化')
      } else {
        console.warn('UnifiedAPIService: 未检测到 Electron API，可能运行在浏览器环境中')
        this.isAvailable = false
        this.api = this.createMockAPI()
      }
    } catch (error) {
      console.error('UnifiedAPIService: 初始化失败', error)
      this.isAvailable = false
      this.api = this.createMockAPI()
    }
  }

  createMockAPI() {
    return {
      openPath: async (path) => {
        console.log('Mock: 打开路径', path)
        return { success: true, message: '模拟环境：无法打开路径' }
      },
      selectDirectory: async () => {
        console.log('Mock: 选择目录')
        return { success: true, path: '/mock/selected/directory', message: '模拟环境：已选择模拟目录' }
      },
      selectFile: async (options = {}) => {
        console.log('Mock: 选择文件', options)
        return { success: true, path: '/mock/selected/file.txt', message: '模拟环境：已选择模拟文件' }
      },
      openDevTools: () => {
        console.log('Mock: 打开开发者工具')
        if (typeof window !== 'undefined' && window.open) {
          window.open('about:blank', '_blank', 'width=800,height=600')
        }
      },
      writeClipboardText: async (text) => {
        console.log('Mock: 写入剪贴板', text)
        return { success: true, message: '模拟环境：已写入剪贴板' }
      },
      getFileStats: async (path) => {
        console.log('Mock: 获取文件统计信息', path)
        return { success: true, size: 1024 * 1024, message: '模拟环境：文件大小为 1MB' }
      },
      getAppVersion: async () => '1.0.0-mock',
      getSystemInfo: async () => ({ platform: 'mock', arch: 'x64', version: '1.0.0' })
    }
  }

  checkAvailability() { return this.isAvailable }
  getAPI() { return this.api }

  async safeCall(methodName, ...args) {
    try {
      if (this.api && typeof this.api[methodName] === 'function') {
        return await this.api[methodName](...args)
      } else {
        console.warn(`UnifiedAPIService: 方法 ${methodName} 不可用`)
        return { success: false, error: `方法 ${methodName} 不可用` }
      }
    } catch (error) {
      console.error(`UnifiedAPIService: 调用 ${methodName} 失败`, error)
      return { success: false, error: error.message }
    }
  }

  async call(action, params = {}) {
    const resp = await this.safeCall('callBackendAPI', action, params)
    
    // 1. 处理 IPC 调用失败或 safeCall 捕获的异常（包括后端抛出的错误）
    if (resp && resp.success === false && resp.error) {
      throw new Error(resp.error)
    }

    // 2. preload.js 已经处理了解包，这里直接返回数据
    return resp
  }
}

const api = new UnifiedAPI()
export default api
export { UnifiedAPI }
