import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useBackendHealthStore = defineStore('backendHealth', () => {
  const isHealthy = ref<boolean | null>(null) // null = unknown (initial)
  const lastCheckedAt = ref<number | null>(null)
  let pollInterval: ReturnType<typeof setInterval> | null = null

  async function check() {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result = await window.electronAPI?.getBackendHealth?.()
      isHealthy.value = result?.healthy ?? false
      lastCheckedAt.value = Date.now()
    } catch {
      isHealthy.value = false
      lastCheckedAt.value = Date.now()
    }
  }

  function startPolling(intervalMs: number = 10000) {
    if (pollInterval) return
    check() // immediate first check
    pollInterval = setInterval(check, intervalMs)
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = null
    }
  }

  return { isHealthy, lastCheckedAt, check, startPolling, stopPolling }
})
