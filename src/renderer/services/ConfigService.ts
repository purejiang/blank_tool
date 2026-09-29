import type { AppConfigApi, UserConfigApi } from '../../shared/ipc/electronApi'
import { toJsonPayload } from '@utils/jsonPayload'

/**
 * 配置读写。写值前一律 `toJsonPayload`：这些值来自 Pinia/`reactive` 表单，可能是
 * 响应式代理，而 contextBridge **无法克隆代理**（`DataCloneError: An object could
 * not be cloned.`）。配置写入的 catch 又是静默的，一旦克隆失败设置就会**无声丢失**。
 */
export class ConfigService {
  private appConfig: AppConfigApi
  private userConfig: UserConfigApi

  constructor() {
    this.appConfig = window.electronAPI?.appConfig ?? this.createMockAppConfig()
    this.userConfig = window.electronAPI?.userConfig ?? this.createMockUserConfig()
  }

  private createMockAppConfig(): AppConfigApi {
    return {
      get: async () => ({}),
      set: async () => undefined,
      setMany: async () => undefined,
      getAll: async () => ({}),
      reset: async () => undefined,
    }
  }

  private createMockUserConfig(): UserConfigApi {
    return {
      get: async () => ({}),
      set: async () => undefined,
      getAll: async () => ({}),
      reset: async () => undefined,
    }
  }

  // App config
  async getAppConfig(key?: string) { return this.appConfig.get(key) }
  async setAppConfig(key: string, value: unknown) { return this.appConfig.set(key, toJsonPayload(value)) }
  async getAllAppConfig() { return this.appConfig.getAll() }
  async resetAppConfig() { return this.appConfig.reset() }

  // User config
  async getUserConfig(key?: string) { return this.userConfig.get(key) }
  async setUserConfig(key: string, value: unknown) { return this.userConfig.set(key, toJsonPayload(value)) }
  async getAllUserConfig() { return this.userConfig.getAll() }
  async resetUserConfig() { return this.userConfig.reset() }
}
