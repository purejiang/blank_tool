import { defineStore } from 'pinia'
import { ref, readonly } from 'vue'
import serviceManager from '../services/ServiceManager'
import { log } from '@utils/logger'

export const useAppConfigStore = defineStore('appConfig', () => {
  const config = ref<Record<string, unknown>>({})
  const loading = ref(true)
  const error = ref<string | null>(null)
  const saving = ref(false)

  // 初始化用户配置
  const initialize = async () => {
    loading.value = true
    error.value = null
    try {
      const configService = await serviceManager.getService('config')
      if (configService) {
          const result = await configService.getAllAppConfig()
          if (result) {
            config.value = result
          } else {
            config.value = {}
          }
      } else {
        config.value = {}
      }
    } catch (err: unknown) {
      log.error('Failed to initialize app config:', err)
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  // 获取应用配置值
  const get = (key: string) => config.value[key]

  // 设置应用配置值
  const set = async (key: string, value: unknown) => {
    saving.value = true
    try {
      const configService = await serviceManager.getService('config')
      if (configService) {
        await configService.setAppConfig(key, value)
      }
      config.value[key] = value
      return true
    } catch (err: unknown) {
      log.error('Failed to save app config:', err)
      error.value = err instanceof Error ? err.message : String(err)
      return false
    } finally {
      saving.value = false
    }
  }

  // 批量更新应用配置
  const update = async (updates: Record<string, unknown>) => {
    saving.value = true
    try {
      const configService = await serviceManager.getService('config')
      if (configService) {
        for (const [key, value] of Object.entries(updates)) {
          await configService.setAppConfig(key, value)
        }
      }
      Object.assign(config.value, updates)
      return true
    } catch (err: unknown) {
      log.error('Failed to update app config:', err)
      error.value = err instanceof Error ? err.message : String(err)
      return false
    } finally {
      saving.value = false
    }
  }

  // 重置应用配置
  const reset = async () => {
    config.value = {}
    return true
  }

  // 监听应用配置变化
  const onConfigChange = () => () => {}

  const replaceAll = (newConfig: Record<string, unknown>) => {
    config.value = { ...(newConfig || {}) }
  }

  return {
    // 状态
    config: readonly(config),
    loading: readonly(loading),
    error: readonly(error),
    saving: readonly(saving),

    // 方法
    initialize,
    get,
    set,
    update,
    reset,
    onConfigChange,
    replaceAll
  }
})
