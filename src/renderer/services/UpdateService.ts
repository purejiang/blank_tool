import { useUpdateStore } from '@stores/updateStore'
import type { UpdateStatus } from '@stores/updateStore'
import unifiedApi from '../api/unifiedApi'
import NotificationService from './NotificationService'
import type { NotificationAction } from './NotificationService'

class UpdateService {
  private store: ReturnType<typeof useUpdateStore> | null = null
  private unsubscribers: Array<() => void> = []
  private manualCheckInProgress = false
  private notifyId: number | null = null
  private notificationService: NotificationService | null = null

  private getStore(): ReturnType<typeof useUpdateStore> {
    if (!this.store) {
      this.store = useUpdateStore()
    }
    return this.store
  }

  private async getNotificationService(): Promise<NotificationService> {
    if (!this.notificationService) {
      const { default: serviceManager } = await import('./ServiceManager')
      this.notificationService = await serviceManager.getService('notification') as NotificationService
    }
    return this.notificationService
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
        const version = data.version || ''
        store.setUpdateInfo({
          version,
          releaseNotes: data.releaseNotes,
          releaseDate: data.releaseDate,
        })
        store.setStatus('available')
        this.showAvailableNotification(version)
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
        this.updateDownloadProgress(data.percent)
      }))
    }

    if (api && typeof api.onUpdateDownloaded === 'function') {
      this.unsubscribers.push(api.onUpdateDownloaded((data: any) => {
        store.setStatus('downloaded')
        if (data.version) {
          store.setUpdateInfo({ version: data.version })
        }
        this.showDownloadedNotification()
      }))
    }

    if (api && typeof api.onUpdateError === 'function') {
      this.unsubscribers.push(api.onUpdateError((data: any) => {
        // Only show error UI for manual checks; auto-check failures are silent
        if (this.manualCheckInProgress) {
          store.setError(data.message || 'Update failed')
          store.setStatus('error')
          this.manualCheckInProgress = false
          this.showErrorNotification(data.message || 'Update failed')
        }
      }))
    }
  }

  private async showAvailableNotification(version: string): Promise<void> {
    // Dismiss any previous update notification
    this.dismissNotify()

    const ns = await this.getNotificationService()
    const actions: NotificationAction[] = [
      {
        label: '稍后再说',
        type: 'default',
        onClick: () => this.dismissNotify(),
      },
      {
        label: '立即下载',
        type: 'primary',
        onClick: () => this.downloadUpdate(),
      },
    ]
    this.notifyId = ns.show('info', '发现新版本', `版本 ${version} 可用，是否立即下载更新？`, 0, undefined, actions)
  }

  private updateDownloadProgress(percent: number): void {
    if (this.notifyId === null) return
    // Fire-and-forget: the notification service is already resolved
    this.getNotificationService().then(ns => {
      ns.updateLoading(this.notifyId!, '', `正在下载... ${percent.toFixed(2)}%`, percent)
    })
  }

  private async showDownloadedNotification(): Promise<void> {
    if (this.notifyId === null) return
    const ns = await this.getNotificationService()
    const actions: NotificationAction[] = [
      {
        label: '立即重启',
        type: 'primary',
        onClick: () => this.quitAndInstall(),
      },
    ]
    ns.completeLoading(this.notifyId, '下载完成', '更新已就绪，点击重启安装新版本', actions, 0)
  }

  private async showErrorNotification(message: string): Promise<void> {
    this.dismissNotify()
    const ns = await this.getNotificationService()
    const actions: NotificationAction[] = [
      {
        label: '重试',
        type: 'primary',
        onClick: () => this.checkForUpdates(),
      },
    ]
    this.notifyId = ns.show('error', '更新失败', message, 0, undefined, actions)
  }

  private dismissNotify(): void {
    if (this.notifyId !== null) {
      // Fire-and-forget hide
      this.getNotificationService().then(ns => ns.hide(this.notifyId!))
      this.notifyId = null
    }
  }

  async checkForUpdates(): Promise<{ updateAvailable: boolean; version?: string; releaseNotes?: string }> {
    const store = this.getStore()
    this.manualCheckInProgress = true
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
        this.manualCheckInProgress = false
        return typed
      }
      throw new Error('checkForUpdates not available')
    } catch (err: any) {
      store.setError(err.message || 'Check failed')
      store.setStatus('error')
      this.manualCheckInProgress = false
      throw err
    }
  }

  async downloadUpdate(): Promise<void> {
    const store = this.getStore()
    store.setStatus('downloading')
    store.setError(null)

    // Switch notification to loading state
    if (this.notifyId !== null) {
      const ns = await this.getNotificationService()
      ns.update(this.notifyId, {
        type: 'loading',
        title: '正在下载',
        message: '准备下载...',
        duration: 0,
        progress: 0,
        actions: [],
      } as any)
    }

    const api = unifiedApi.getAPI()
    try {
      if (api && typeof api.downloadUpdate === 'function') {
        await api.downloadUpdate()
      } else {
        throw new Error('downloadUpdate not available')
      }
    } catch (err: any) {
      store.setError(err.message || 'Download failed')
      store.setStatus('error')
      this.showErrorNotification(err.message || 'Download failed')
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
    this.dismissNotify()
    for (const unsub of this.unsubscribers) {
      try { unsub() } catch {}
    }
    this.unsubscribers = []
  }
}

export default UpdateService
