/**
 * PluginService — thin wrapper over the plugin.* backend API.
 *
 * Plugins are external .py files (builtin/ + user dir); running one is a
 * STREAMING operation, so `run` is NOT here — pages drive it through
 * TaskStreamService with `plugin.run` (see PluginsPage.vue), same pattern
 * as useScriptRunner does for automation.run.
 */

export interface PluginParam {
  key: string
  label?: string
  type?: 'string' | 'number' | 'bool'
  required?: boolean
  default?: unknown
}

export interface PluginInfo {
  name: string
  description: string
  version: string
  author: string
  params?: PluginParam[]
}

class PluginService {
  private api(method: string, params: Record<string, unknown> = {}): Promise<any> {
    const api = (window as any).electronAPI
    if (!api || typeof api.callBackendAPI !== 'function') {
      return Promise.reject(new Error('backend API unavailable'))
    }
    return api.callBackendAPI(method, params)
  }

  /** plugin.list → PluginInfo[] */
  async list(): Promise<PluginInfo[]> {
    const res = await this.api('plugin.list')
    return Array.isArray(res) ? res : []
  }

  /** plugin.reload → PluginInfo[] (rescans builtin + user dirs) */
  async reload(): Promise<PluginInfo[]> {
    const res = await this.api('plugin.reload')
    return Array.isArray(res) ? res : []
  }
}

export default new PluginService()
