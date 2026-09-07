import type { AppConfigApi, UserConfigApi } from '../../shared/ipc/electronApi'

/**
 * Vue reactive proxies are NOT structured-cloneable: handing one to
 * `ipcRenderer.invoke` makes Electron reject with "could not be cloned",
 * which surfaces as a red toast on every config write that passes a
 * reactive value (e.g. automation page's `persist()` sending
 * `{ projects: projects.value }`). Deep-copy through JSON here so every
 * write at this boundary is plain data.
 */
function toPlainValue<T>(value: T): T {
  if (value === undefined || value === null) return value
  try {
    return JSON.parse(JSON.stringify(value)) as T
  } catch {
    return value
  }
}

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
  async setAppConfig(key: string, value: unknown) { return this.appConfig.set(key, toPlainValue(value)) }
  async getAllAppConfig() { return this.appConfig.getAll() }
  async resetAppConfig() { return this.appConfig.reset() }

  // User config
  async getUserConfig(key?: string) { return this.userConfig.get(key) }
  async setUserConfig(key: string, value: unknown) { return this.userConfig.set(key, toPlainValue(value)) }
  async getAllUserConfig() { return this.userConfig.getAll() }
  async resetUserConfig() { return this.userConfig.reset() }
}
