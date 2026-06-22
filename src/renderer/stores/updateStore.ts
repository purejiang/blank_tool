import { defineStore } from 'pinia'
import { ref } from 'vue'

export type UpdateStatus = 'idle' | 'checking' | 'available' | 'downloading' | 'downloaded' | 'error' | 'not-available'

export interface UpdateInfo {
  version: string
  releaseNotes?: string
  releaseDate?: string
}

export interface DownloadProgress {
  percent: number
  bytesPerSecond: number
  transferred: number
  total: number
}

export const useUpdateStore = defineStore('update', () => {
  const status = ref<UpdateStatus>('idle')
  const currentVersion = ref('')
  const latestVersion = ref<string | null>(null)
  const releaseNotes = ref<string | null>(null)
  const releaseDate = ref<string | null>(null)
  const downloadPercent = ref(0)
  const downloadSpeed = ref<number | null>(null)
  const error = ref<string | null>(null)

  function setStatus(s: UpdateStatus): void {
    status.value = s
  }

  function setUpdateInfo(info: UpdateInfo): void {
    latestVersion.value = info.version
    releaseNotes.value = info.releaseNotes || null
    releaseDate.value = info.releaseDate || null
  }

  function setDownloadProgress(progress: DownloadProgress): void {
    downloadPercent.value = progress.percent
    downloadSpeed.value = progress.bytesPerSecond
  }

  function setError(message: string): void {
    error.value = message
  }

  function setCurrentVersion(version: string): void {
    currentVersion.value = version
  }

  function reset(): void {
    status.value = 'idle'
    latestVersion.value = null
    releaseNotes.value = null
    releaseDate.value = null
    downloadPercent.value = 0
    downloadSpeed.value = null
    error.value = null
  }

  return {
    status,
    currentVersion,
    latestVersion,
    releaseNotes,
    releaseDate,
    downloadPercent,
    downloadSpeed,
    error,
    setStatus,
    setUpdateInfo,
    setDownloadProgress,
    setError,
    setCurrentVersion,
    reset,
  }
})
