import { ipcMain, app, BrowserWindow } from 'electron';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';
import { isUpdateInstallInProgress } from '../updater/updater';

let quitDialogResolver: ((action: string) => void) | null = null;

export function setupQuitDialog(window: BrowserWindow): void {
  ipcMain.handle(IPC_CHANNEL_NAMES.respondQuitDialog, (_event, action: string) => {
    if (quitDialogResolver) {
      quitDialogResolver(action);
      quitDialogResolver = null;
    }
  });

  window.on('close', async (e) => {
    if (isUpdateInstallInProgress()) return;
    if (quitDialogResolver) return;
    e.preventDefault();
    window.webContents.send(IPC_CHANNEL_NAMES.showQuitDialog);
    const action = await new Promise<string>(resolve => { quitDialogResolver = resolve; });
    if (action === 'quit') {
      window.destroy();
      app.quit();
    } else if (action === 'minimize') {
      window.hide();
    }
  });
}
