import unifiedAPI from '../api/unifiedAPI.js'

class SettingsService {
  constructor(storeService) {
    this.storeService = storeService
  }

  async loadSettings() {
    const appStore = await this.storeService.ensureAppConfigStore()
    const api = unifiedAPI.getAPI()
    if (api && api.appConfig && typeof api.appConfig.getAll === 'function') {
      try {
        const cfg = await api.appConfig.getAll()
        if (typeof appStore.replaceAll === 'function') appStore.replaceAll(cfg || {})
        return cfg || {}
      } catch {
        return appStore && appStore.config ? appStore.config : {}
      }
    }
    return appStore && appStore.config ? appStore.config : {}
  }

  async saveSettings(updates) {
    const appStore = await this.storeService.ensureAppConfigStore()
    const api = unifiedAPI.getAPI()
    if (api && api.appConfig && typeof api.appConfig.set === 'function') {
      for (const [key, value] of Object.entries(updates || {})) {
        try { await api.appConfig.set(key, value) } catch {}
      }
    }
    return await appStore.update(updates)
  }

  async resetSettings() {
    const appStore = await this.storeService.ensureAppConfigStore()
    const api = unifiedAPI.getAPI()
    if (api && api.appConfig && typeof api.appConfig.reset === 'function') {
      try { await api.appConfig.reset() } catch {}
    }
    return await appStore.reset()
  }
}

export default SettingsService
