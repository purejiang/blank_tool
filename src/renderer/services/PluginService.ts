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
  /** plugin id — the identity every plugin.* call keys on */
  name: string
  /** manifest `name` for packages, else the id; display only */
  display_name?: string
  description: string
  version: string
  author: string
  params?: PluginParam[]
  /** package plugin with custom UI: absolute path of the ui html */
  ui_path?: string
  /** ships with the app (builtin dir) rather than the user plugin dir */
  builtin?: boolean
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

  /**
   * plugin.delete — remove a plugin from its scan dir and rescan.
   * Returns the refreshed PluginInfo[].
   */
  async deletePlugin(name: string): Promise<PluginInfo[]> {
    const res = await this.api('plugin.delete', { name })
    return Array.isArray(res) ? res : []
  }

  /**
   * plugin.import — install a zip plugin package.
   * Returns PluginInfo[] on success; { needs_overwrite: true, id } when
   * the target exists and overwrite was not confirmed.
   */
  async importPackage(zipPath: string, overwrite = false): Promise<PluginInfo[] | { needs_overwrite: boolean; id: string }> {
    const res = await this.api('plugin.import', { zip_path: zipPath, overwrite })
    if (res && typeof res === 'object' && !Array.isArray(res) && (res as any).needs_overwrite) {
      return res as { needs_overwrite: boolean; id: string }
    }
    return Array.isArray(res) ? res : []
  }

  /** plugin.export — zip an installed plugin to targetPath. */
  async exportPackage(name: string, targetPath: string): Promise<{ path: string }> {
    return await this.api('plugin.export', { name, target_path: targetPath })
  }
}

export default new PluginService()
