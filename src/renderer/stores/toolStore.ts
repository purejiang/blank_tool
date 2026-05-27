import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import serviceManager from '../services/ServiceManager'

export const useToolStore = defineStore('tool', () => {
  const tools = ref([])
  const loading = ref(false)
  const error = ref(null)
  const lastFetched = ref(null)

  // Getters
  const getTool = (name) => tools.value.find(t => t.name === name || t.key === name)
  const availableTools = computed(() => tools.value.filter(t => t.status === 'available'))

  // Actions
  const fetchTools = async (force = false) => {
    // If we have fetched recently (e.g. within 5 minutes) and not forced, return existing
    // But for now, let's just say if we have tools, don't fetch unless forced
    if (!force && tools.value.length > 0) {
      return tools.value
    }

    loading.value = true
    error.value = null
    try {
      const toolService = await serviceManager.getService('tools')
      // Note: ToolService.checkTools returns an array of tool info objects
      const result = await toolService.checkTools({ refresh: force })
      
      // Map result to ensure consistent structure if needed, 
      // but ToolService seems to return a good structure already.
      tools.value = result
      lastFetched.value = Date.now()
    } catch (err) {
      console.error('Failed to fetch tools:', err)
      error.value = err.message || '获取工具信息失败'
    } finally {
      loading.value = false
    }
  }

  const updateTool = (toolData) => {
    const index = tools.value.findIndex(t => t.name === toolData.name || t.key === toolData.name)
    if (index !== -1) {
      tools.value[index] = { ...tools.value[index], ...toolData }
    } else {
      tools.value.push(toolData)
    }
  }

  return {
    tools,
    loading,
    error,
    lastFetched,
    getTool,
    availableTools,
    fetchTools,
    updateTool
  }
})
