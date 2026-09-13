import { BrowserWindow } from 'electron';

/**
 * Send an IPC message to every live renderer window.
 *
 * Always guards with `isDestroyed()`: a window can close between
 * `getAllWindows()` and the `send()` call, which throws
 * "Object has been destroyed" and would turn a successful operation into a
 * rejected one (previously the case for app-config writes).
 *
 * This is the single broadcast entry point for the main process — do not
 * re-implement the loop locally.
 */
export function broadcastToAllWindows(channel: string, ...args: unknown[]): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed() && !win.webContents.isDestroyed()) {
      win.webContents.send(channel, ...args);
    }
  }
}
