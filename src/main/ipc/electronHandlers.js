import { ipcMain, dialog, shell, BrowserWindow } from 'electron'
import { promises as fs } from 'fs'

export function setupElectronHandlers() {
  ipcMain.handle('show-open-dialog', async (event, options) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    return await dialog.showOpenDialog(win, options)
  })

  ipcMain.handle('show-save-dialog', async (event, options) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    return await dialog.showSaveDialog(win, options)
  })

  ipcMain.handle('show-message-box', async (event, options) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    return await dialog.showMessageBox(win, options)
  })

  ipcMain.handle('get-file-stats', async (event, filePath) => {
    try {
      const stats = await fs.stat(filePath)
      return {
        size: stats.size,
        isFile: stats.isFile(),
        isDirectory: stats.isDirectory(),
        mtime: stats.mtime,
        ctime: stats.ctime,
        success: true
      }
    } catch (error) {
      return { success: false, error: error.message }
    }
  })

  ipcMain.handle('write-file', async (event, filePath, content) => {
    try {
      await fs.writeFile(filePath, typeof content === 'string' ? content : String(content), 'utf8')
      return { success: true }
    } catch (error) {
      return { success: false, error: error.message }
    }
  })

  ipcMain.handle('read-file', async (event, filePath) => {
    try {
      const data = await fs.readFile(filePath, 'utf8')
      return { success: true, data }
    } catch (error) {
      return { success: false, error: error.message }
    }
  })

  ipcMain.handle('open-directory', async (event, targetPath) => {
    if (!targetPath) return { success: false, error: 'Path is required' }
    try {
      const stat = await fs.stat(targetPath).catch(() => null)
      if (stat && stat.isDirectory()) {
        await shell.openPath(targetPath)
      } else {
        shell.showItemInFolder(targetPath)
      }
      return { success: true }
    } catch (error) {
      return { success: false, error: error.message }
    }
  })

  ipcMain.handle('open-dev-tools', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (win && !win.isDestroyed()) {
      win.webContents.openDevTools()
      return true
    }
    return false
  })

  ipcMain.handle('toggle-dev-tools', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (win && !win.isDestroyed()) {
      const isOpen = win.webContents.isDevToolsOpened()
      if (isOpen) {
        win.webContents.closeDevTools()
      } else {
        win.webContents.openDevTools()
      }
      return true
    }
    return false
  })
}