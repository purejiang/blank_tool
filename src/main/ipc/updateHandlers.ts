import { ipcMain } from 'electron'
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels'
import { checkForUpdatesManual, quitAndInstall } from '../updater/updater'

export function setupUpdateHandlers(): void {
  ipcMain.handle(IPC_CHANNEL_NAMES.checkForUpdates, async () => {
    return await checkForUpdatesManual()
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.quitAndInstall, () => {
    quitAndInstall()
  })
}
