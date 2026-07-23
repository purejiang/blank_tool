import type { ApiMethodMap } from '../../shared/ipc/protocol'
import type { ElectronApi } from '../../shared/ipc/electronApi'
import { log } from '@utils/logger'

type MethodParams<M extends keyof ApiMethodMap> = ApiMethodMap[M]['params']
type MethodResult<M extends keyof ApiMethodMap> = ApiMethodMap[M]['result']

export async function callApi<M extends keyof ApiMethodMap>(
  method: M,
  params: MethodParams<M>
): Promise<MethodResult<M>> {
  return window.electronAPI.callBackendAPI(method as any, params) as Promise<MethodResult<M>>
}

type ApiFn = (...args: unknown[]) => unknown | Promise<unknown>
type FailedCallResult = { success: false; error: string }

function isFailedCallResult(value: unknown): value is FailedCallResult {
  if (!value || typeof value !== 'object') return false
  const result = value as Record<string, unknown>
  return result.success === false && typeof result.error === 'string'
}

class UnifiedApi {
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
      } else {
        log.warn('unifiedApiService: Electron API not detected, running in browser environment')
        this.isAvailable = false
        this.api = this.createMockAPI()
      }
    } catch (error) {
      log.error('unifiedApiService: Initialization failed', error)
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
        set: async () => undefined,
        setMany: async () => undefined,
        getAll: async () => ({}),
        reset: async () => undefined,
      },
      userConfig: {
        get: async () => ({}),
        set: async () => undefined,
        getAll: async () => ({}),
        reset: async () => undefined,
      },
      settings: {
        getViewModel: async () => ({ settings: {}, displayPaths: { runtime: '', server: '' } }),
        resolvePaths: async () => ({ runtime: '', server: '' }),
      },
      onDeviceChange: () => () => {},
      onLogUpdate: () => () => {},
      onLogcatOutput: () => () => {},
      onLogcatStarted: () => () => {},
      onLogcatFinished: () => () => {},
      onLogcatError: () => () => {},
      removeLogcatListener: () => {},
      rendererLog: async () => undefined,
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
        log.warn(`unifiedApiService: Method ${methodName} not available`)
        return { success: false, error: `Method ${methodName} not available` }
      }
    } catch (error) {
      log.error(`unifiedApiService: Call to ${methodName} failed`, error)
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

const api = new UnifiedApi()
export default api
export { UnifiedApi }
