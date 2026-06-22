import { autoUpdater } from 'electron-updater'
import { BrowserWindow, app } from 'electron'
import log from 'electron-log'
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels'

let initialized = false

function sendToAllWindows(channel: string, data: unknown): void {
  const wins = BrowserWindow.getAllWindows()
  for (const w of wins) {
    if (!w.isDestroyed()) {
      w.webContents.send(channel, data)
    }
  }
}

export function initAutoUpdater(): void {
  if (initialized) return
  initialized = true

  if (!app.isPackaged) {
    log.info('AutoUpdater: disabled in dev mode')
    return
  }

  autoUpdater.logger = log
  autoUpdater.autoDownload = true
  autoUpdater.allowDowngrade = false
  autoUpdater.allowPrerelease = false

  autoUpdater.on('checking-for-update', () => {
    log.info('AutoUpdater: checking for update...')
  })

  autoUpdater.on('update-available', (info) => {
    log.info('AutoUpdater: update available', info.version)
    sendToAllWindows(IPC_CHANNEL_NAMES.updateAvailable, {
      version: info.version,
      releaseNotes: (info.releaseNotes as string) || '',
      releaseDate: info.releaseDate || '',
    })
  })

  autoUpdater.on('update-not-available', (info) => {
    log.info('AutoUpdater: already up to date', info.version)
    sendToAllWindows(IPC_CHANNEL_NAMES.updateNotAvailable, { version: info.version })
  })

  autoUpdater.on('download-progress', (p) => {
    sendToAllWindows(IPC_CHANNEL_NAMES.downloadProgress, {
      percent: p.percent,
      bytesPerSecond: p.bytesPerSecond,
      transferred: p.transferred,
      total: p.total,
    })
  })

  autoUpdater.on('update-downloaded', (info) => {
    log.info('AutoUpdater: update downloaded', info.version)
    sendToAllWindows(IPC_CHANNEL_NAMES.updateDownloaded, { version: info.version })
  })

  autoUpdater.on('error', (err) => {
    log.error('AutoUpdater: error', err)
    sendToAllWindows(IPC_CHANNEL_NAMES.updateError, { message: err.message })
  })
}

export async function checkForUpdatesManual(): Promise<{
  updateAvailable: boolean
  version?: string
  releaseNotes?: string
}> {
  if (!app.isPackaged) {
    return { updateAvailable: false }
  }
  try {
    const result = await autoUpdater.checkForUpdates()
    if (result?.updateInfo) {
      return {
        updateAvailable: true,
        version: result.updateInfo.version,
        releaseNotes: (result.updateInfo.releaseNotes as string) || '',
      }
    }
    return { updateAvailable: false }
  } catch {
    return { updateAvailable: false }
  }
}

export async function autoCheckForUpdates(): Promise<void> {
  if (!app.isPackaged) return
  try {
    await autoUpdater.checkForUpdates()
  } catch {
    // "no update available" throws in electron-updater; silently ignore for auto-check
  }
}

export function quitAndInstall(): void {
  autoUpdater.quitAndInstall(false, true)
}
