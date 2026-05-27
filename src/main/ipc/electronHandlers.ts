import { ipcMain, dialog, shell, BrowserWindow, app, clipboard, IpcMainInvokeEvent } from 'electron'
import { promises as fs } from 'fs'
import path from 'path'

export function setupElectronHandlers(): void {
  ipcMain.handle('show-open-dialog', async (event: IpcMainInvokeEvent, options: any) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return { canceled: true, filePaths: [] }
    return await dialog.showOpenDialog(win, options)
  })

  ipcMain.handle('show-save-dialog', async (event: IpcMainInvokeEvent, options: any) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return { canceled: true }
    return await dialog.showSaveDialog(win, options)
  })

  ipcMain.handle('show-message-box', async (event: IpcMainInvokeEvent, options: any) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return { response: -1 }
    return await dialog.showMessageBox(win, options)
  })

  ipcMain.handle('get-file-stats', async (event: IpcMainInvokeEvent, filePath: string) => {
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

  ipcMain.handle('write-file', async (event: IpcMainInvokeEvent, filePath: string, content: any) => {
    try {
      await fs.writeFile(filePath, typeof content === 'string' ? content : String(content), 'utf8')
      return { success: true }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  })

  ipcMain.handle('read-file', async (event: IpcMainInvokeEvent, filePath: string) => {
    try {
      const data = await fs.readFile(filePath, 'utf8')
      return { success: true, data }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  })
  
  // 文件/目录打开
  ipcMain.handle('open-path', async (event: IpcMainInvokeEvent, targetPath: string) => {
    if (!targetPath) return { success: false, error: 'Path is required' }
    try {
      const stat = await fs.stat(targetPath).catch(() => null)
      if (stat && stat.isDirectory()) {
        await shell.openPath(targetPath)
      } else {
        shell.showItemInFolder(targetPath)
      }
      return { success: true }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  })

  ipcMain.handle('open-dev-tools', async (event: IpcMainInvokeEvent) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (win && !win.isDestroyed()) {
      win.webContents.openDevTools()
      return true
    }
    return false
  })

  ipcMain.handle('toggle-dev-tools', async (event: IpcMainInvokeEvent) => {
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

  ipcMain.handle('get-app-info', async (event: IpcMainInvokeEvent) => {
    return { version: app.getVersion() }
  })

  // 构建信息的获取
  ipcMain.handle('get-fontend-build-info', async (event: IpcMainInvokeEvent) => {
    let appDescription = ''
    try {
      const pkgPath = path.join(app.getAppPath(), 'package.json')
      const raw = await fs.readFile(pkgPath, 'utf8')
      const pkg = JSON.parse(raw)
      appDescription = pkg?.description || ''
    } catch {}

    return {
      appName: app.getName(),
      appVersion: app.getVersion(),
      appDescription,
      nodeVersion: process.versions.node,
      chromeVersion: process.versions.chrome,
      electronVersion: process.versions.electron
    }
  })

  // 剪贴板处理
  ipcMain.handle('read-clipboard-text', async () => {
    return clipboard.readText()
  })

  ipcMain.handle('write-clipboard-text', async (event: IpcMainInvokeEvent, text: string) => {
    clipboard.writeText(text || '')
    return true
  })
  
  // 路径解析
  ipcMain.handle('path-resolve', async (event: IpcMainInvokeEvent, pathStr: string) => {
    if (!pathStr) return pathStr;
  
    if (path.isAbsolute(pathStr)) return pathStr;
    
    // 如果是相对路径，则相对于应用根目录解析
    const baseDir = !app.isPackaged
      ? path.join(__dirname, '..', '..')
      : process.resourcesPath;
      
    // 移除可能存在的开头的 .\ 或 ./
    const cleanPath = pathStr.replace(/^\.[\\/]/, '');
    return path.join(baseDir, cleanPath);
  })
}
