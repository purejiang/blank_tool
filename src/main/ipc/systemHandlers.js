import { ipcMain, dialog, shell } from 'electron'
import { promises as fs } from 'fs'

export function setupSystemHandlers(mainWindow) {
  ipcMain.handle('show-open-dialog', async (event, options) => {
    return await dialog.showOpenDialog(mainWindow, options)
  })

  ipcMain.handle('show-save-dialog', async (event, options) => {
    return await dialog.showSaveDialog(mainWindow, options)
  })

  ipcMain.handle('show-message-box', async (event, options) => {
    return await dialog.showMessageBox(mainWindow, options)
  })

  ipcMain.handle('get-file-stats', async (event, filePath) => {
    const stats = await fs.stat(filePath)
    return {
      size: stats.size,
      isFile: stats.isFile(),
      isDirectory: stats.isDirectory(),
      mtime: stats.mtime,
      ctime: stats.ctime
    }
  })

  ipcMain.handle('write-file', async (event, filePath, content) => {
    await fs.writeFile(filePath, typeof content === 'string' ? content : String(content), 'utf8')
    return true
  })

  ipcMain.handle('read-file', async (event, filePath) => {
    const data = await fs.readFile(filePath, 'utf8')
    return data
  })

  ipcMain.handle('open-directory', async (event, targetPath) => {
    if (!targetPath) return false
    const stat = await fs.stat(targetPath).catch(() => null)
    if (stat && stat.isDirectory()) {
      await shell.openPath(targetPath)
    } else {
      shell.showItemInFolder(targetPath)
    }
    return true
  })

  ipcMain.handle('open-dev-tools', async () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.openDevTools()
      return true
    }
    return false
  })

  ipcMain.handle('toggle-dev-tools', async () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      const isOpen = mainWindow.webContents.isDevToolsOpened()
      if (isOpen) {
        mainWindow.webContents.closeDevTools()
      } else {
        mainWindow.webContents.openDevTools()
      }
      return true
    }
    return false
  })
}