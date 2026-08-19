import { defineStore } from 'pinia'
import { ref } from 'vue'
import serviceManager from '../services/ServiceManager'
import type { PluginEntry } from '../../shared/ipc/protocol'
import { log } from '@utils/logger'

/**
 * 插件状态 store。
 *
 * persist 决策：不持久化（未设置 persist: true）。
 * plugins 列表由后端 plugin.list 派生，每次 fetchPlugins/addPlugin/deletePlugin/
 * reloadPlugins 都以服务端返回的最新列表为准；持久化本地缓存反而会造成与后端
 * 实际状态不一致（本地缓存可能是旧列表，而服务端已增删插件）。故这里不 persist。
 */
export const usePluginStore = defineStore('plugin', () => {
  const plugins = ref<PluginEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const getErrorMessage = (err: unknown): string => {
    return err instanceof Error ? err.message : String(err)
  }

  const getPluginService = async () => {
    return serviceManager.getService('plugins')
  }

  async function fetchPlugins() {
    loading.value = true
    error.value = null
    try {
      const svc = await getPluginService()
      const result = await svc.list()
      plugins.value = result.plugins ?? []
    } catch (err: unknown) {
      log.error('Failed to fetch plugins:', err)
      error.value = getErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function addPlugin(module: string, path?: string, config?: Record<string, unknown>) {
    loading.value = true
    error.value = null
    try {
      const svc = await getPluginService()
      const result = await svc.add(module, path, config)
      plugins.value = result.plugins ?? []
    } catch (err: unknown) {
      log.error('Failed to add plugin:', err)
      error.value = getErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function deletePlugin(module: string) {
    loading.value = true
    error.value = null
    try {
      const svc = await getPluginService()
      const result = await svc.delete(module)
      plugins.value = result.plugins ?? []
    } catch (err: unknown) {
      log.error('Failed to delete plugin:', err)
      error.value = getErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  async function reloadPlugins() {
    loading.value = true
    error.value = null
    try {
      const svc = await getPluginService()
      await svc.reload()
      // reload 返回 {ok}，不含列表；重载后重新拉取一次以刷新 plugins 状态。
      const result = await svc.list()
      plugins.value = result.plugins ?? []
    } catch (err: unknown) {
      log.error('Failed to reload plugins:', err)
      error.value = getErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  return {
    plugins,
    loading,
    error,
    fetchPlugins,
    addPlugin,
    deletePlugin,
    reloadPlugins,
  }
})
