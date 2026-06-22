import { useUpdateStore } from '@stores/updateStore'
import type { UpdateStatus } from '@stores/updateStore'
import unifiedApi from '../api/unifiedApi'

class UpdateService {
  private store: ReturnType<typeof useUpdateStore> | null = null
  private unsubscribers: Array<() => void> = []

  private getStore(): ReturnType<typeof useUpdateStore> {
    if (!this.store) {
      this.store = useUpdateStore()
    }
    return this.store
  }

  async initialize(): Promise<void> {
    const store = this.getStore()
    const api = unifiedApi.getAPI()

    // Fetch current version from electron
    if (api && typeof api.getAppInfo === 'function') {
      try {
        const info = await api.getAppInfo()
        if (info && typeof info === 'object' && 'version' in info) {
          store.setCurrentVersion(String((info as Record<string, unknown>).version))
        }
      } catch {}
    }

    // Listen for main process events via specific preload methods
    if (api && typeof api.onUpdateAvailable === 'function') {
      this.unsubscribers.push(api.onUpdateAvailable((data: any) => {
        store.setUpdateInfo({
          version: data.version || '',
          releaseNotes: data.releaseNotes,
          releaseDate: data.releaseDate,
        })
        store.setStatus('available')
      }))
    }

    if (api && typeof api.onUpdateNotAvailable === 'function') {
      this.unsubscribers.push(api.onUpdateNotAvailable((_data: any) => {
        store.setStatus('not-available')
      }))
    }

    if (api && typeof api.onDownloadProgress === 'function') {
      this.unsubscribers.push(api.onDownloadProgress((data: any) => {
        if (store.status !== 'downloading') {
          store.setStatus('downloading')
        }
        store.setDownloadProgress(data)
      }))
    }

    if (api && typeof api.onUpdateDownloaded === 'function') {
      this.unsubscribers.push(api.onUpdateDownloaded((data: any) => {
        store.setStatus('downloaded')
        if (data.version) {
          store.setUpdateInfo({ version: data.version })
        }
      }))
    }

    if (api && typeof api.onUpdateError === 'function') {
      this.unsubscribers.push(api.onUpdateError((data: any) => {
        store.setError(data.message || 'Update failed')
        store.setStatus('error')
      }))
    }
  }

  async checkForUpdates(): Promise<{ updateAvailable: boolean; version?: string; releaseNotes?: string }> {
    const store = this.getStore()
    store.setStatus('checking')
    store.setError(null)

    const api = unifiedApi.getAPI()
    try {
      if (api && typeof api.checkForUpdates === 'function') {
        const result = await api.checkForUpdates()
        const typed = result as { updateAvailable: boolean; version?: string; releaseNotes?: string }
        if (typed.updateAvailable) {
          store.setUpdateInfo({
            version: typed.version || '',
            releaseNotes: typed.releaseNotes,
          })
          store.setStatus('available')
        } else {
          store.setStatus('not-available')
        }
        return typed
      }
      throw new Error('checkForUpdates not available')
    } catch (err: any) {
      store.setError(err.message || 'Check failed')
      store.setStatus('error')
      throw err
    }
  }

  async quitAndInstall(): Promise<void> {
    const api = unifiedApi.getAPI()
    try {
      if (api && typeof api.quitAndInstall === 'function') {
        await api.quitAndInstall()
      }
    } catch (err: any) {
      console.error('quitAndInstall failed:', err)
    }
  }

  getStatus(): UpdateStatus {
    return this.getStore().status
  }

  destroy(): void {
    for (const unsub of this.unsubscribers) {
      try { unsub() } catch {}
    }
    this.unsubscribers = []
  }
}

export default UpdateService
