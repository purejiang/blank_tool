/**
 * 插件服务 - 封装后端 plugin.* handler 调用。
 * 所有方法经 unifiedApi.call 转发到主进程 -> Python 后端。
 */
import unifiedApi from '../api/unifiedApi'
import type { ApiMethodMap } from '../../shared/ipc/protocol'

type PluginList = ApiMethodMap['plugin.list']['result']
type PluginAddParams = ApiMethodMap['plugin.add']['params']

class PluginService {
  /** 获取插件列表 */
  list(): Promise<PluginList> {
    return unifiedApi.call<PluginList>('plugin.list', {})
  }

  /** 添加插件（path/config 可选，仅当传入时才携带） */
  add(module: string, path?: string, config?: Record<string, unknown>): Promise<PluginList> {
    const params: PluginAddParams = { module }
    if (path !== undefined) params.path = path
    if (config !== undefined) params.config = config
    return unifiedApi.call<PluginList>('plugin.add', params)
  }

  /** 删除插件 */
  delete(module: string): Promise<PluginList> {
    return unifiedApi.call<PluginList>('plugin.delete', { module })
  }

  /** 重载所有插件 */
  reload(): Promise<ApiMethodMap['plugin.reload']['result']> {
    return unifiedApi.call<ApiMethodMap['plugin.reload']['result']>('plugin.reload', {})
  }
}

export default PluginService
