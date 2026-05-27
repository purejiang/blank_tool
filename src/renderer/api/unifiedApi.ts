/**
 *   统一的 API 服务
 * - 初始化并暴露 window.electronAPI
 * - 提供 safeCall 与后端 call(action, params)
 * - 在非 Electron 环境提供 Mock
 */
import type { ElectronApi } from '../../shared/ipc/electronApi'

type ApiFn = (...args: unknown[]) => unknown | Promise<unknown>
type FailedCallResult = { success: false; error: string }

function isFailedCallResult(value: unknown): value is FailedCallResult {
  if (!value || typeof value !== 'object') return false
  const result = value as Record<string, unknown>
  return result.success === false && typeof result.error === 'string'
}

// declare global moved to src/shared/ipc/electronApi.ts

class unifiedApi {
  private api: ElectronApi | null
  private isAvailable: boolean

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
        console.log('unifiedApiService: Electron API 已初始化')
      } else {
        console.warn('unifiedApiService: 未检测到 Electron API，可能运行在浏览器环境中')
        this.isAvailable = false
        this.api = this.createMockAPI()
      }
    } catch (error) {
      console.error('unifiedApiService: 初始化失败', error)
      this.isAvailable = false
      this.api = this.createMockAPI()
    }
  }

  createMockAPI(): ElectronApi {
    return {
      callBackendAPI: async () => ({}),
      callBackendByRequest: async () => ({}),
      appConfig: {
        get: async () => ({}),
        set: async () => ({ success: true }),
        setMany: async () => ({ success: true }),
        getAll: async () => ({}),
        reset: async () => true
      },
      userConfig: {
        get: async () => ({}),
        set: async () => ({ success: true }),
        getAll: async () => ({}),
        reset: async () => true
      },
      settings: {
        getViewModel: async () => ({ settings: {}, displayPaths: { runtime: '', server: '' } }),
        resolvePaths: async () => ({ runtime: '', server: '' })
      },
      onDeviceChange: () => () => {},
      onLogUpdate: () => () => {},
      onLogcatOutput: () => () => {},
      onLogcatStarted: () => () => {},
      onLogcatFinished: () => () => {},
      onLogcatError: () => () => {},
      removeLogcatListener: () => {}
    }
  }

  checkAvailability() { return this.isAvailable }
  getAPI() { return this.api }

  async safeCall<T = unknown>(methodName: string, ...args: unknown[]): Promise<T | FailedCallResult> {
    try {
      const method = this.api?.[methodName] as ApiFn | undefined
      if (typeof method === 'function') {
        return await method(...args) as T
      } else {
        console.warn(`unifiedApiService: 方法 ${methodName} 不可用`)
        return { success: false, error: `方法 ${methodName} 不可用` }
      }
    } catch (error) {
      console.error(`unifiedApiService: 调用 ${methodName} 失败`, error)
      const errorMessage = error instanceof Error ? error.message : String(error)
      return { success: false, error: errorMessage }
    }
  }

  async call<T = unknown>(action: string, params: Record<string, unknown> = {}): Promise<T> {
    const resp = await this.safeCall('callBackendAPI', action, params)
    if (isFailedCallResult(resp)) {
      throw new Error(resp.error)
    }

    return resp as T
  }
}

const api = new unifiedApi()
export default api
export { unifiedApi }
