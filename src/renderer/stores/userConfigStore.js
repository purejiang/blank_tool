import { defineStore } from 'pinia'
import { ref, readonly } from 'vue'

export const useUserConfigStore = defineStore('userConfig', () => {
  const config = ref({})
  const loading = ref(true)
  const error = ref(null)
  const saving = ref(false)

  // 初始化用户配置
  const initialize = async () => {
    loading.value = true
    error.value = null
    try { config.value = {} } finally { loading.value = false }
  }

  // 获取用户配置值
  const get = (key) => config.value[key]

  // 设置用户配置值
  const set = async (key, value) => {
    const oldValue = config.value[key]
    config.value[key] = value
    saving.value = false
    return true
  }

  // 批量更新用户配置
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

  // 重置用户配置
  const reset = async () => { config.value = {}; return true }

  // 监听用户配置变化
  const onConfigChange = () => () => {}

  const replaceAll = (newConfig) => { config.value = { ...(newConfig || {}) } }

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
