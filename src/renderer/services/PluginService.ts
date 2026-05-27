import unifiedApi from '../api/unifiedApi'

interface PluginApiLike {
  callBackend?: (method: string, payload: Record<string, unknown>) => Promise<unknown>
}

class PluginService {
  private api: PluginApiLike | null

  constructor() {
    this.api = unifiedApi.getAPI() as PluginApiLike | null
  }

  /**
   * 获取插件列表
   */
  async getPlugins() {
    if (this.api && typeof this.api.callBackend === 'function') {
      return await this.api.callBackend('plugin.list', {})
    }
    // Mock data for browser environment
    return [
      { name: 'hello_world', description: 'Mock Plugin', version: '1.0.0', author: 'Dev' }
    ]
  }

  /**
   * 运行插件
   * @param {string} pluginName 插件名称
   * @param {Object} params 参数
   */
  async runPlugin(pluginName: string, params: Record<string, unknown> = {}) {
    if (this.api && typeof this.api.callBackend === 'function') {
      return await this.api.callBackend('plugin.run', {
        name: pluginName,
        params: params
      })
    }
    console.log(`Running plugin ${pluginName} with params:`, params)
    return { success: true, message: 'Mock execution result' }
  }

  /**
   * 重新加载插件
   */
  async reloadPlugins() {
    if (this.api && typeof this.api.callBackend === 'function') {
      return await this.api.callBackend('plugin.reload', {})
    }
    return await this.getPlugins()
  }
}

export default new PluginService()
