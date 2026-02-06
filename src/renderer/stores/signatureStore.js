import { defineStore } from 'pinia'
import { ref } from 'vue'
import unifiedAPI from '../api/unifiedAPI.js'

export const useSignatureStore = defineStore('signature', () => {
  const configs = ref([])
  const loading = ref(false)

  // Load configs from app settings
  const loadConfigs = async () => {
    loading.value = true
    try {
      const api = unifiedAPI.getAPI()
      if (api && api.appConfig) {
        const storedConfigs = await api.appConfig.get('signature_configs')
        if (Array.isArray(storedConfigs)) {
          configs.value = storedConfigs
        } else {
          configs.value = []
        }
      }
    } catch (error) {
      console.error('Failed to load signature configs:', error)
    } finally {
      loading.value = false
    }
  }

  // Save configs to app settings
  const saveConfigs = async () => {
    try {
      const api = unifiedAPI.getAPI()
      if (api && api.appConfig) {
        // Ensure we are saving a plain array
        await api.appConfig.set('signature_configs', JSON.parse(JSON.stringify(configs.value)))
      }
    } catch (error) {
      console.error('Failed to save signature configs:', error)
      throw error
    }
  }

  const addConfig = async (config) => {
    // Generate a simple ID if not present
    if (!config.id) {
      config.id = Date.now().toString()
    }
    configs.value.push(config)
    await saveConfigs()
  }

  const updateConfig = async (updatedConfig) => {
    const index = configs.value.findIndex(c => c.id === updatedConfig.id)
    if (index !== -1) {
      configs.value[index] = updatedConfig
      await saveConfigs()
    }
  }

  const removeConfig = async (id) => {
    const index = configs.value.findIndex(c => c.id === id)
    if (index !== -1) {
      configs.value.splice(index, 1)
      await saveConfigs()
    }
  }

  const getConfigById = (id) => {
    return configs.value.find(c => c.id === id)
  }

  return {
    configs,
    loading,
    loadConfigs,
    addConfig,
    updateConfig,
    removeConfig,
    getConfigById
  }
})
