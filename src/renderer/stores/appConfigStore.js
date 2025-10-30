import { defineStore } from 'pinia'
import { ref, readonly } from 'vue'
import path from 'path'

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
      const appConfig = await window.electronAPI.appConfig.getAll()
      config.value = appConfig
      console.log('应用配置加载完成:', appConfig)
    } catch (err) {
      error.value = `加载应用配置失败: ${err.message}`
      console.error('应用配置加载失败:', err)
    } finally {
      loading.value = false
    }
  }

  // 获取应用配置值
  const get = (key) => {
    return config.value[key]
  }

  // 设置应用配置值
  const set = async (key, value) => {
    const oldValue = config.value[key]
    config.value[key] = value

    try {
      saving.value = true
      await window.electronAPI.appConfig.set(key, value)
      return true
    } catch (err) {
      // 回滚
      config.value[key] = oldValue
      error.value = `保存配置失败: ${err.message}`
      throw err
    } finally {
      saving.value = false
    }
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

    try {
      saving.value = true

      // 批量保存
      for (const [key, value] of Object.entries(updates)) {
        await window.electronAPI.appConfig.set(key, value)
      }

      return true
    } catch (err) {
      // 回滚所有更改
      Object.assign(config.value, oldValues)
      error.value = `批量更新配置失败: ${err.message}`
      throw err
    } finally {
      saving.value = false
    }
  }

  // 重置应用配置
  const reset = async () => {
    try {
      await window.electronAPI.appConfig.reset()
      await initialize() // 重新加载配置
      return true
    } catch (err) {
      error.value = `重置配置失败: ${err.message}`
      throw err
    }
  }

  // 添加最近项目
  const addRecentProject = async (projectPath) => {
    const recentProjects = config.value.recentProjects || []

    // 移除重复项
    const filtered = recentProjects.filter(p => p.path !== projectPath)

    // 添加到开头
    filtered.unshift({
      path: projectPath,
      name: path.basename(projectPath),
      lastOpened: new Date().toISOString()
    })

    // 限制数量
    const limited = filtered.slice(0, 10)

    await set('recentProjects', limited)
  }

  // 监听应用配置变化
  const onConfigChange = (callback) => {
    const handler = (data) => {
      const { key, newValue, oldValue } = data
      config.value[key] = newValue
      callback(key, newValue, oldValue)
    }

    window.electronAPI.onAppConfigChange(handler)

    // 返回清理函数
    return () => {
      window.electronAPI.onAppConfigChange(null)
    }
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
    addRecentProject,
    onConfigChange
  }
})