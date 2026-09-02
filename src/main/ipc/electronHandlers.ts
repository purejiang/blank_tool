import { ipcMain, dialog, shell, BrowserWindow, app, clipboard, Notification, IpcMainInvokeEvent } from 'electron'
import { promises as fs } from 'fs'
import path from 'path'
import log from 'electron-log'
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels'
import { getPythonProcess } from '../state'
import { getAppLocalDataPath } from '../utils/appPaths'

export function setupElectronHandlers(): void {
  ipcMain.handle(IPC_CHANNEL_NAMES.showSystemNotification, async (event: IpcMainInvokeEvent, payload: { title?: string; body?: string }) => {
    try {
      if (!Notification.isSupported()) return false
      const n = new Notification({ title: payload?.title ?? '', body: payload?.body ?? '' })
      n.on('click', () => {
        const win = BrowserWindow.fromWebContents(event.sender)
        if (win && !win.isDestroyed()) { win.show(); win.focus() }
      })
      n.show()
      return true
    } catch (e) {
      console.error('showSystemNotification failed:', e)
      return false
    }
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.showOpenDialog, async (event: IpcMainInvokeEvent, options: any) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return { canceled: true, filePaths: [] }
    return await dialog.showOpenDialog(win, options)
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.showSaveDialog, async (event: IpcMainInvokeEvent, options: any) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return { canceled: true }
    return await dialog.showSaveDialog(win, options)
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.showMessagebox, async (event: IpcMainInvokeEvent, options: any) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return { response: -1 }
    return await dialog.showMessageBox(win, options)
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.getFileStats, async (event: IpcMainInvokeEvent, filePath: string) => {
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

  ipcMain.handle(IPC_CHANNEL_NAMES.writeFile, async (event: IpcMainInvokeEvent, filePath: string, content: any) => {
    try {
      await fs.writeFile(filePath, typeof content === 'string' ? content : String(content), 'utf8')
      return { success: true }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.readFile, async (event: IpcMainInvokeEvent, filePath: string) => {
    try {
      const data = await fs.readFile(filePath, 'utf8')
      return { success: true, data }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  })

  // Read an image file off disk and return it as a base64 data URL. Used to
  // render APK launcher icons whose path is persisted in task.result instead
  // of the (large) inline base64 blob.
  ipcMain.handle(IPC_CHANNEL_NAMES.readImageAsDataURL, async (event: IpcMainInvokeEvent, filePath: string) => {
    try {
      const ext = (filePath.split('.').pop() || 'png').toLowerCase()
      const mimeMap: Record<string, string> = {
        png: 'image/png', webp: 'image/webp', jpg: 'image/jpeg',
        jpeg: 'image/jpeg', gif: 'image/gif', bmp: 'image/bmp', svg: 'image/svg+xml',
      }
      const mime = mimeMap[ext] || 'image/png'
      const buf = await fs.readFile(filePath)
      const b64 = buf.toString('base64')
      return { success: true, dataUrl: `data:${mime};base64,${b64}` }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  })
  
  // 文件/目录打开
  ipcMain.handle(IPC_CHANNEL_NAMES.openPath, async (event: IpcMainInvokeEvent, targetPath: string) => {
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

  ipcMain.handle(IPC_CHANNEL_NAMES.rendererLog, async (event: IpcMainInvokeEvent, level: 'error' | 'warn' | 'info', message: string) => {
    try {
      const prefixed = `[renderer] ${message}`
      if (level === 'error') log.error(prefixed)
      else if (level === 'warn') log.warn(prefixed)
      else if (level === 'info') log.info(prefixed)
      return true
    } catch {
      return false
    }
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.openDevTools, async (event: IpcMainInvokeEvent) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (win && !win.isDestroyed()) {
      win.webContents.openDevTools()
      return true
    }
    return false
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.toggleDevTools, async (event: IpcMainInvokeEvent) => {
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

  ipcMain.handle(IPC_CHANNEL_NAMES.getAppInfo, async (event: IpcMainInvokeEvent) => {
    return { version: app.getVersion() }
  })

  // 构建信息的获取
  ipcMain.handle(IPC_CHANNEL_NAMES.getFontendBuildInfo, async (event: IpcMainInvokeEvent) => {
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
  ipcMain.handle(IPC_CHANNEL_NAMES.readClipboardText, async () => {
    return clipboard.readText()
  })

  ipcMain.handle(IPC_CHANNEL_NAMES.writeClipboardText, async (event: IpcMainInvokeEvent, text: string) => {
    clipboard.writeText(text || '')
    return true
  })
  
  // 路径解析
  ipcMain.handle(IPC_CHANNEL_NAMES.pathResolve, async (event: IpcMainInvokeEvent, pathStr: string) => {
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

  // Backend health check — lightweight, < 5ms (no stdin roundtrip)
  ipcMain.handle(IPC_CHANNEL_NAMES.getBackendHealth, async () => {
    const proc = getPythonProcess()
    const healthy = Boolean(proc && !proc.killed && proc.exitCode === null)
    return { healthy, uptime_s: null, pending_requests: null }
  })

  // Electron log tail — reads last N lines of electron.log
  ipcMain.handle(IPC_CHANNEL_NAMES.readElectronLogTail, async (_event, params: { lines?: number } = {}) => {
    const requested = Math.max(1, Math.min(Number(params?.lines) || 200, 1000))
    const logPath = path.join(getAppLocalDataPath(), 'logs', 'electron.log')
    try {
      const content = await fs.readFile(logPath, 'utf-8')
      const allLines = content.split('\n')
      // Drop trailing empty line if file ends with \n
      if (allLines.length > 0 && allLines[allLines.length - 1] === '') allLines.pop()
      const truncated = allLines.length > requested
      const tail = allLines.slice(-requested)
      return { lines: tail, truncated, log_path: logPath, process: 'main' }
    } catch (e) {
      return { lines: [], truncated: false, log_path: logPath, error: String(e), process: 'main' }
    }
  })
}
