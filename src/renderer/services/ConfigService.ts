import type { AppConfigApi, UserConfigApi } from '../../shared/ipc/electronApi'

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
  async setAppConfig(key: string, value: unknown) { return this.appConfig.set(key, value) }
  async getAllAppConfig() { return this.appConfig.getAll() }
  async resetAppConfig() { return this.appConfig.reset() }

  // User config
  async getUserConfig(key?: string) { return this.userConfig.get(key) }
  async setUserConfig(key: string, value: unknown) { return this.userConfig.set(key, value) }
  async getAllUserConfig() { return this.userConfig.getAll() }
  async resetUserConfig() { return this.userConfig.reset() }
}
