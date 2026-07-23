import { defineStore } from 'pinia'
import { ref } from 'vue'
import unifiedApi from '../api/unifiedApi'
import { log } from '@utils/logger'

type SignatureConfig = {
  id: string
  [key: string]: unknown
}

export const useSignatureStore = defineStore('signature', () => {
  const configs = ref<SignatureConfig[]>([])
  const loading = ref(false)

  // Load configs from app settings
  const loadConfigs = async () => {
    loading.value = true
    try {
      const api = unifiedApi.getAPI()
      if (api && api.appConfig) {
        const storedConfigs = await api.appConfig.get('signatureConfigs')
        if (Array.isArray(storedConfigs)) {
          configs.value = storedConfigs
        } else {
          configs.value = []
        }
      }
    } catch (error) {
      log.error('Failed to load signature configs:', error)
    } finally {
      loading.value = false
    }
  }

  // Save configs to app settings
  const saveConfigs = async () => {
    try {
      const api = unifiedApi.getAPI()
      if (api && api.appConfig) {
        // Ensure we are saving a plain array
        await api.appConfig.set('signatureConfigs', JSON.parse(JSON.stringify(configs.value)))
      }
    } catch (error) {
      log.error('Failed to save signature configs:', error)
      throw error
    }
  }

  const addConfig = async (config: SignatureConfig) => {
    const nextConfig = {
      ...config,
      id: config.id || Date.now().toString()
    }
    configs.value.push(nextConfig)
    await saveConfigs()
  }

  const updateConfig = async (updatedConfig: SignatureConfig) => {
    const index = configs.value.findIndex(c => c.id === updatedConfig.id)
    if (index !== -1) {
      configs.value[index] = updatedConfig
      await saveConfigs()
    }
  }

  const removeConfig = async (id: string) => {
    const index = configs.value.findIndex(c => c.id === id)
    if (index !== -1) {
      configs.value.splice(index, 1)
      await saveConfigs()
    }
  }

  const getConfigById = (id: string) => {
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
