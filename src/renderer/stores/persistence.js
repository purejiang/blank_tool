import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

/**
 * 运行时缓存管理器
 * 负责管理Pinia store的运行时缓存
 */
export const runtimeStore = defineStore('runtime-store', () => {
  // 状态
  const isInitialized = ref(false)
  const syncStatus = ref('idle') // idle, syncing, error
  const lastSyncTime = ref(null)
  const syncError = ref(null)
  
  // 运行时缓存配置
  const runtimeConfig = ref({
    // 当前设备
    currentDevice: null
  })

  // 本地缓存存储
  const localCache = ref(new Map())
  
  // 自动同步定时器
  let autoSyncTimer = null

  /**
   * 初始化持久化系统
   */
  const initialize = async () => {
    try {
      syncStatus.value = 'syncing'
      
      // 从electron-store加载配置
      if (window.electronAPI) {
        const savedConfig = await window.electronAPI.getAllConfig()
        if (savedConfig) {
          // 恢复持久化配置
          if (savedConfig.persistence) {
            persistenceConfig.value = { ...persistenceConfig.value, ...savedConfig.persistence }
          }
        }
      }
      
      // 启动自动同步
      if (persistenceConfig.value.enableAutoSync) {
        startAutoSync()
      }
      
      isInitialized.value = true
      syncStatus.value = 'idle'
      lastSyncTime.value = new Date()
      
      console.log('Persistence system initialized')
    } catch (error) {
      console.error('Failed to initialize persistence system:', error)
      syncStatus.value = 'error'
      syncError.value = error.message
    }
  }

  /**
   * 持久化store数据
   * @param {string} storeName - store名称
   * @param {Object} storeData - store数据
   */
  const persistStore = async (storeName, storeData) => {
    try {
      if (!persistenceConfig.value.persistedStores.includes(storeName)) {
        return
      }

      // 过滤排除的字段
      const excludeFields = persistenceConfig.value.excludeFields[storeName] || []
      const filteredData = filterData(storeData, excludeFields)
      
      // 保存到electron-store
      if (window.electronAPI) {
        await window.electronAPI.setConfig(`stores.${storeName}`, filteredData)
      }
      
      // 更新本地缓存
      if (persistenceConfig.value.enableLocalCache) {
        localCache.value.set(storeName, {
          data: filteredData,
          timestamp: Date.now()
        })
      }
      
      lastSyncTime.value = new Date()
    } catch (error) {
      console.error(`Failed to persist store ${storeName}:`, error)
      syncError.value = error.message
      throw error
    }
  }

  /**
   * 恢复store数据
   * @param {string} storeName - store名称
   * @returns {Object|null} 恢复的数据
   */
  const restoreStore = async (storeName) => {
    try {
      if (!persistenceConfig.value.persistedStores.includes(storeName)) {
        return null
      }

      // 首先尝试从本地缓存获取
      if (persistenceConfig.value.enableLocalCache) {
        const cached = localCache.value.get(storeName)
        if (cached && !isCacheExpired(cached.timestamp)) {
          return cached.data
        }
      }
      
      // 从electron-store获取
      if (window.electronAPI) {
        const data = await window.electronAPI.getConfig(`stores.${storeName}`)
        
        // 更新本地缓存
        if (data && persistenceConfig.value.enableLocalCache) {
          localCache.value.set(storeName, {
            data,
            timestamp: Date.now()
          })
        }
        
        return data
      }
      
      return null
    } catch (error) {
      console.error(`Failed to restore store ${storeName}:`, error)
      return null
    }
  }

  /**
   * 批量持久化多个store
   * @param {Object} storesData - 多个store的数据
   */
  const persistMultipleStores = async (storesData) => {
    try {
      syncStatus.value = 'syncing'
      
      const promises = Object.entries(storesData).map(([storeName, storeData]) => 
        persistStore(storeName, storeData)
      )
      
      await Promise.all(promises)
      syncStatus.value = 'idle'
    } catch (error) {
      syncStatus.value = 'error'
      throw error
    }
  }

  /**
   * 清除store的持久化数据
   * @param {string} storeName - store名称
   */
  const clearPersistedStore = async (storeName) => {
    try {
      if (window.electronAPI) {
        await window.electronAPI.setConfig(`stores.${storeName}`, null)
      }
      
      localCache.value.delete(storeName)
    } catch (error) {
      console.error(`Failed to clear persisted store ${storeName}:`, error)
      throw error
    }
  }

  /**
   * 清除所有持久化数据
   */
  const clearAllPersistedData = async () => {
    try {
      const promises = persistenceConfig.value.persistedStores.map(storeName => 
        clearPersistedStore(storeName)
      )
      
      await Promise.all(promises)
      localCache.value.clear()
    } catch (error) {
      console.error('Failed to clear all persisted data:', error)
      throw error
    }
  }

  /**
   * 启动自动同步
   */
  const startAutoSync = () => {
    if (autoSyncTimer) {
      clearInterval(autoSyncTimer)
    }
    
    autoSyncTimer = setInterval(() => {
      // 这里可以触发所有注册的store进行同步
      // 具体实现需要在各个store中监听这个事件
      window.dispatchEvent(new CustomEvent('auto-sync-stores'))
    }, persistenceConfig.value.autoSyncInterval)
  }

  /**
   * 停止自动同步
   */
  const stopAutoSync = () => {
    if (autoSyncTimer) {
      clearInterval(autoSyncTimer)
      autoSyncTimer = null
    }
  }

  /**
   * 更新持久化配置
   * @param {Object} newConfig - 新的配置
   */
  const updateConfig = async (newConfig) => {
    try {
      persistenceConfig.value = { ...persistenceConfig.value, ...newConfig }
      
      // 保存配置到electron-store
      if (window.electronAPI) {
        await window.electronAPI.setConfig('persistence', persistenceConfig.value)
      }
      
      // 重新启动自动同步
      if (persistenceConfig.value.enableAutoSync) {
        startAutoSync()
      } else {
        stopAutoSync()
      }
    } catch (error) {
      console.error('Failed to update persistence config:', error)
      throw error
    }
  }

  /**
   * 过滤数据，移除不可序列化的字段
   * @param {Object} data - 原始数据
   * @param {Array} excludeFields - 要排除的字段
   * @returns {Object} 过滤后的数据
   */
  const filterData = (data, excludeFields) => {
    if (!data || typeof data !== 'object') return data
    
    // 深度克隆并过滤不可序列化的数据
    const filtered = JSON.parse(JSON.stringify(data, (key, value) => {
      // 排除函数、Symbol、undefined等不可序列化的值
      if (typeof value === 'function' || typeof value === 'symbol' || value === undefined) {
        return null
      }
      // 排除循环引用
      if (typeof value === 'object' && value !== null) {
        if (value.constructor && value.constructor.name === 'Object') {
          return value
        }
        // 对于其他对象类型，转换为普通对象
        return Object.assign({}, value)
      }
      return value
    }))
    
    // 移除指定的排除字段
    excludeFields.forEach(field => {
      delete filtered[field]
    })
    
    return filtered
  }

  /**
   * 检查缓存是否过期
   * @param {number} timestamp - 缓存时间戳
   * @returns {boolean} 是否过期
   */
  const isCacheExpired = (timestamp) => {
    return Date.now() - timestamp > persistenceConfig.value.cacheExpiration
  }

  /**
   * 获取同步状态信息
   * @returns {Object} 状态信息
   */
  const getSyncStatus = () => {
    return {
      isInitialized: isInitialized.value,
      syncStatus: syncStatus.value,
      lastSyncTime: lastSyncTime.value,
      syncError: syncError.value,
      cacheSize: localCache.value.size
    }
  }

  // 监听配置变化
  watch(persistenceConfig, (newConfig) => {
    if (isInitialized.value) {
      updateConfig(newConfig)
    }
  }, { deep: true })

  // 清理函数
  const cleanup = () => {
    stopAutoSync()
    localCache.value.clear()
  }

  return {
    // 状态
    isInitialized,
    syncStatus,
    lastSyncTime,
    syncError,
    persistenceConfig,
    
    // 方法
    initialize,
    persistStore,
    restoreStore,
    persistMultipleStores,
    clearPersistedStore,
    clearAllPersistedData,
    updateConfig,
    getSyncStatus,
    cleanup
  }
})

/**
 * 创建持久化插件
 * @param {Object} options - 插件选项
 * @returns {Function} Pinia插件函数
 */
export function createPersistencePlugin(options = {}) {
  return ({ store, options: storeOptions }) => {
    const persistenceStore = usePersistenceStore()
    
    // 如果store配置了持久化
    if (storeOptions.persist !== false && persistenceStore.persistenceConfig.persistedStores.includes(store.$id)) {
      // 恢复数据
      persistenceStore.restoreStore(store.$id).then(data => {
        if (data) {
          store.$patch(data)
        }
      })
      
      // 监听状态变化并持久化
      store.$subscribe((mutation, state) => {
        persistenceStore.persistStore(store.$id, state)
      }, { detached: true })
      
      // 监听自动同步事件
      window.addEventListener('auto-sync-stores', () => {
        persistenceStore.persistStore(store.$id, store.$state)
      })
    }
  }
}