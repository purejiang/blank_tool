import { useUpdateStore } from '@stores/updateStore'
import type { UpdateStatus } from '@stores/updateStore'
import unifiedApi from '../api/unifiedApi'
import NotificationService from './NotificationService'
import type { NotificationAction } from './NotificationService'
import i18n from '../i18n'

class UpdateService {
  private store: ReturnType<typeof useUpdateStore> | null = null
  private unsubscribers: Array<() => void> = []
  private manualCheckInProgress = false
  private notifyId: number | null = null
  private notificationService: NotificationService | null = null
  private simulatedDownloadTimer: ReturnType<typeof setInterval> | null = null
  private initialized = false

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
    if (this.initialized) return
    this.initialized = true

    const store = this.getStore()
    const api = unifiedApi.getAPI()

    // DEV: expose test helper to window for manual testing
    if (import.meta.env.DEV && typeof window !== 'undefined' && !(window as any).__testUpdate) {
      ;(window as any).__testUpdate = () => this.testUpdateFlow()
      console.log('[UpdateService] Dev test helper ready: run __testUpdate() in console')
    }

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
    let lastNotifiedVersion = ''
    if (api && typeof api.onUpdateAvailable === 'function') {
      this.unsubscribers.push(api.onUpdateAvailable((data: any) => {
        const version = data.version || ''
        // Deduplicate — don't show the same notification twice
        if (version && version === lastNotifiedVersion) return
        lastNotifiedVersion = version
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

  /**
   * Show "update available" notification.
   * Returns the notification id so callers can track it.
   */
  private async showAvailableNotification(version: string): Promise<void> {
    // Await dismiss of any previous notification so we don't end up with two
    await this.dismissNotifyAsync()

    const ns = await this.getNotificationService()
    const { t } = i18n.global

    // Capture the id in a local const so button onClick closures always
    // reference the correct notification even if this.notifyId changes later.
    const capturedId = ns.show(
      'info',
      t('update.newVersion'),
      `v${version}`,
      0,
      undefined,
      [], // actions set below so we can close over capturedId
    )
    this.notifyId = capturedId

    // Now set the actions with properly captured notifyId
    const actions: NotificationAction[] = [
      {
        label: t('update.later'),
        type: 'default',
        onClick: () => {
          ns.hide(capturedId)
          if (this.notifyId === capturedId) this.notifyId = null
        },
      },
      {
        label: t('update.download'),
        type: 'primary',
        onClick: () => this.downloadUpdate(capturedId),
      },
    ]
    ns.update(capturedId, { actions } as any)
  }

  private updateDownloadProgress(percent: number): void {
    const notifyId = this.notifyId
    if (notifyId === null) return
    const { t } = i18n.global
    this.getNotificationService().then(ns => {
      ns.updateLoading(
        notifyId,
        t('update.downloading', { version: this.getStore().latestVersion || '' }),
        `${percent.toFixed(2)}%`,
        percent,
      )
    })
  }

  private async showDownloadedNotification(notifyId?: number): Promise<void> {
    const nid = notifyId ?? this.notifyId
    if (nid === null) return
    const { t } = i18n.global
    const ns = await this.getNotificationService()
    const actions: NotificationAction[] = [
      {
        label: t('update.restartNow'),
        type: 'primary',
        onClick: () => this.quitAndInstall(),
      },
    ]
    ns.completeLoading(nid, t('update.downloaded'), t('update.restartToInstall'), actions, 0)
  }

  private async showErrorNotification(message: string): Promise<void> {
    await this.dismissNotifyAsync()
    const ns = await this.getNotificationService()
    const { t } = i18n.global
    const capturedId = ns.show(
      'error',
      t('update.error'),
      message,
      0,
      undefined,
      [],
    )
    this.notifyId = capturedId

    const actions: NotificationAction[] = [
      {
        label: t('app.retry'),
        type: 'primary',
        onClick: () => this.checkForUpdates(),
      },
    ]
    ns.update(capturedId, { actions } as any)
  }

  /** Synchronously clear notifyId — for non-critical cleanup paths */
  private dismissNotify(): void {
    if (this.notifyId !== null) {
      this.getNotificationService().then(ns => ns.hide(this.notifyId!))
      this.notifyId = null
    }
  }

  /** Await the dismiss so the caller can be sure the old notification is gone */
  private async dismissNotifyAsync(): Promise<void> {
    if (this.notifyId !== null) {
      const oldId = this.notifyId
      this.notifyId = null
      const ns = await this.getNotificationService()
      ns.hide(oldId)
    }
  }

  async checkForUpdates(): Promise<{ updateAvailable: boolean; version?: string; releaseNotes?: string; error?: string }> {
    const store = this.getStore()
    this.manualCheckInProgress = true
    store.setStatus('checking')
    store.setError(null)

    const api = unifiedApi.getAPI()
    try {
      if (api && typeof api.checkForUpdates === 'function') {
        const result = await api.checkForUpdates()
        const typed = result as { updateAvailable: boolean; version?: string; releaseNotes?: string; error?: string }
        if (typed.updateAvailable) {
          store.setUpdateInfo({
            version: typed.version || '',
            releaseNotes: typed.releaseNotes,
          })
          store.setStatus('available')
          this.manualCheckInProgress = false
          return typed
        } else if (typed.error) {
          store.setError(typed.error)
          store.setStatus('error')
          this.manualCheckInProgress = false
          this.showErrorNotification(typed.error)
          return { updateAvailable: false }
        } else {
          store.setStatus('not-available')
          this.manualCheckInProgress = false
          return typed
        }
      }
      throw new Error('checkForUpdates not available')
    } catch (err: any) {
      store.setError(err.message || 'Check failed')
      store.setStatus('error')
      this.manualCheckInProgress = false
      throw err
    }
  }

  /**
   * DEV TEST: simulate download progress purely in the renderer.
   * Used when no real update is available on the server but we want
   * to test the download → complete UI flow.
   */
  private async simulateDownload(notifyId?: number): Promise<void> {
    const nid = notifyId ?? this.notifyId
    const store = this.getStore()
    const { t } = i18n.global

    // Switch notification to loading state
    if (nid !== null) {
      const ns = await this.getNotificationService()
      ns.update(nid, {
        type: 'loading',
        title: t('update.downloading', { version: store.latestVersion || '' }),
        message: '0.00%',
        duration: 0,
        progress: 0,
        actions: [],
      } as any)
    }

    store.setStatus('downloading')
    store.setError(null)

    // Simulate progress over ~3 seconds
    let progress = 0
    this.simulatedDownloadTimer = setInterval(() => {
      progress += Math.random() * 15 + 3
      if (progress >= 100) {
        progress = 100
        if (this.simulatedDownloadTimer) {
          clearInterval(this.simulatedDownloadTimer)
          this.simulatedDownloadTimer = null
        }
        // Simulate download complete
        store.setDownloadProgress({ percent: 100, bytesPerSecond: 0, transferred: 0, total: 0 })
        store.setStatus('downloaded')
        this.showDownloadedNotification(nid)
      } else {
        store.setDownloadProgress({
          percent: Math.round(progress * 100) / 100,
          bytesPerSecond: Math.round(Math.random() * 5_000_000 + 1_000_000),
          transferred: 0,
          total: 0,
        })
        this.updateDownloadProgress(Math.round(progress * 100) / 100)
      }
    }, 150)
  }

  async downloadUpdate(notifyId?: number): Promise<void> {
    const nid = notifyId ?? this.notifyId
    const store = this.getStore()
    store.setStatus('downloading')
    store.setError(null)

    // Switch notification to loading state
    if (nid !== null) {
      const { t } = i18n.global
      const ns = await this.getNotificationService()
      ns.update(nid, {
        type: 'loading',
        title: t('update.downloading', { version: store.latestVersion || '' }),
        message: '0.00%',
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

  /**
   * DEV TEST: simulate the full update flow for UI testing.
   * Run: __testUpdate() in browser devtools console
   *
   * Tries a real check first.  If a real update is available the normal
   * flow handles everything end-to-end.  Otherwise falls back to a
   * renderer-side simulation so you can still test the notification,
   * progress bar, and "downloaded" state without a real update server.
   */
  private async testUpdateFlow(): Promise<void> {
    console.log('[UpdateService] Starting test update flow...')
    const store = this.getStore()
    store.setCurrentVersion('2.0.4')

    // Try a real check first
    let realUpdate = false
    try {
      const result = await this.checkForUpdates()
      realUpdate = result.updateAvailable
      if (realUpdate) {
        console.log('[UpdateService] ✅ Real update found, normal flow active')
        return // normal flow already shows notification
      }
    } catch {
      console.log('[UpdateService] Check failed, using simulated flow')
    }

    // No real update — show a notification with simulated download
    store.setUpdateInfo({ version: '2.0.5' })
    await this.dismissNotifyAsync()

    const { t } = i18n.global
    const ns = await this.getNotificationService()
    const capturedId = ns.show(
      'info',
      t('update.newVersion'),
      'v2.0.5',
      0,
      undefined,
      [],
    )
    this.notifyId = capturedId

    const actions: NotificationAction[] = [
      {
        label: t('update.later'),
        type: 'default',
        onClick: () => {
          ns.hide(capturedId)
          if (this.notifyId === capturedId) this.notifyId = null
        },
      },
      {
        label: t('update.download'),
        type: 'primary',
        onClick: () => this.simulateDownload(capturedId),
      },
    ]
    ns.update(capturedId, { actions } as any)
    console.log('[UpdateService] ✅ Simulated notification shown')
  }

  destroy(): void {
    if (this.simulatedDownloadTimer) {
      clearInterval(this.simulatedDownloadTimer)
      this.simulatedDownloadTimer = null
    }
    this.dismissNotify()
    for (const unsub of this.unsubscribers) {
      try { unsub() } catch {}
    }
    this.unsubscribers = []
  }
}

export default UpdateService
