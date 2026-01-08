import { defineStore } from 'pinia'
import { ref, readonly } from 'vue'
import serviceManager from '../services/ServiceManager'

export const useAppConfigStore = defineStore('appConfig', () => {
  const config = ref({})
  const loading = ref(true)
  const error = ref(null)
  const saving = ref(false)

  // 初始化用户配置
  const initialize = async () => {
    loading.value = true
    error.value = null
    try {
      const settingsService = await serviceManager.getService('settings')
      if (settingsService) {
          const result = await settingsService.loadSettings()
          if (result) {
            config.value = result
          } else {
            config.value = {}
          }
      } else {
        config.value = {}
      }
    } catch (err) {
      console.error('Failed to initialize app config:', err)
      error.value = err.message
    } finally {
      loading.value = false
    }
  }

  // 获取应用配置值
  const get = (key) => config.value[key]

  // 设置应用配置值
  const set = async (key, value) => {
    const oldValue = config.value[key]
    config.value[key] = value
    saving.value = false
    return true
  }

  // 批量更新应用配置
  const update = async (updates) => {
    const oldValues = {}

    // 保存旧值
    Object.keys(updates).forEach(key => {
      oldValues[key] = config.value[key]
    })

    // 应用更新
    Object.assign(config.value, updates)

    saving.value = false
    return true
  }

  // 重置应用配置
  const reset = async () => {
    config.value = {}
    return true
  }

  // 监听应用配置变化
  const onConfigChange = () => () => {}

  const replaceAll = (newConfig) => {
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
