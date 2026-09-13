import unifiedApi from '../api/unifiedApi'
import type { AppConfigApi, SettingsApi, SettingsViewModel } from '../../shared/ipc/electronApi'
import type { AppConfigStoreLike } from '../../shared/stores/appConfigStore'

interface StoreServiceLike {
  ensureAppConfigStore: () => Promise<AppConfigStoreLike>
}

const EMPTY_SETTINGS_MODEL: SettingsViewModel = {
  settings: {},
  displayPaths: {
    runtime: '',
    server: ''
  }
}

class SettingsService {
  private storeService: StoreServiceLike

  constructor(storeService: StoreServiceLike) {
    this.storeService = storeService
  }

  async loadSettings() {
    const model = await this.loadSettingsModel()
    return model.settings || {}
  }

  async loadSettingsModel(): Promise<SettingsViewModel> {
    const appStore = await this.storeService.ensureAppConfigStore()
    const settingsApi = this.getSettingsApi()
    if (settingsApi) {
      try {
        const model = await settingsApi.getViewModel()
        const settings = (model && model.settings) ? model.settings : {}
        if (typeof appStore.replaceAll === 'function') appStore.replaceAll(settings)
        return {
          settings,
          displayPaths: model?.displayPaths || EMPTY_SETTINGS_MODEL.displayPaths
        }
      } catch {}
    }

    const appConfigApi = this.getAppConfigApi()
    if (appConfigApi) {
      try {
        const cfg = await appConfigApi.getAll()
        if (typeof appStore.replaceAll === 'function') appStore.replaceAll(cfg || {})
        return {
          settings: cfg || {},
          displayPaths: await this.resolveDisplayPaths(cfg || {})
        }
      } catch {
        const fallback = appStore && appStore.config ? appStore.config : {}
        return {
          settings: fallback,
          displayPaths: await this.resolveDisplayPaths(fallback)
        }
      }
    }
    const fallback = appStore && appStore.config ? appStore.config : {}
    return {
      settings: fallback,
      displayPaths: await this.resolveDisplayPaths(fallback)
    }
  }

  async saveSettings(updates: Record<string, unknown>) {
    const appStore = await this.storeService.ensureAppConfigStore()
    // Single write path. This used to call `appConfigApi.setMany(updates)` and
    // then `appStore.update(updates)` — the latter looped one IPC per key, so the
    // same batch was persisted twice (1 + N invokes). `update()` now issues one
    // `set-app-config-batch`, and still surfaces rejected keys as `false`.
    const saved = await appStore.update(updates || {})
    if (saved === false) {
      // Keep the old behaviour: a rejected key must not look like a save.
      throw new Error(appStore.error || 'Failed to save settings')
    }
    return await this.loadSettingsModel()
  }

  async resetSettings() {
    const appStore = await this.storeService.ensureAppConfigStore()
    const appConfigApi = this.getAppConfigApi()
    if (appConfigApi) {
      try { await appConfigApi.reset() } catch {}
    }
    await appStore.reset()
    return await this.loadSettingsModel()
  }

  async resolveDisplayPaths(source: Record<string, unknown>): Promise<SettingsViewModel['displayPaths']> {
    const settingsApi = this.getSettingsApi()
    if (settingsApi) {
      try {
        return await settingsApi.resolvePaths({
          runtime: source.runtime,
          server: source.server
        })
      } catch {}
    }
    const api = unifiedApi.getAPI()
    if (api && typeof api.resolvePath === 'function') {
      const runtimeInput = typeof source.runtime === 'string' ? source.runtime : ''
      const serverInput = typeof source.server === 'string' ? source.server : ''
      const [runtime, server] = await Promise.all([
        runtimeInput ? api.resolvePath(runtimeInput) : Promise.resolve(''),
        serverInput ? api.resolvePath(serverInput) : Promise.resolve('')
      ])
      return { runtime, server }
    }
    return { ...EMPTY_SETTINGS_MODEL.displayPaths }
  }

  private getAppConfigApi(): AppConfigApi | null {
    const api = unifiedApi.getAPI()
    if (!api || !api.appConfig) return null
    return api.appConfig
  }

  private getSettingsApi(): SettingsApi | null {
    const api = unifiedApi.getAPI()
    if (!api || !api.settings) return null
    return api.settings
  }
}

export default SettingsService
