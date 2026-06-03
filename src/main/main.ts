import { app, BrowserWindow, Menu, Tray, nativeImage, ipcMain } from 'electron';
import path from 'path';
import { existsSync, promises as fs } from 'fs';
import { fileURLToPath } from 'url';
import { spawn, ChildProcessWithoutNullStreams } from 'child_process';
import log from 'electron-log';
import { appStore } from './stores/index';
import { setupAllHandlers } from './ipc/index';
import { APP_CONFIG_KEYS, PATH_CONFIG_DEFAULTS } from '../shared/config/pathConfig';
import { IPC_CHANNEL_NAMES } from '../shared/ipc/channels';

// 配置日志
log.transports.file.level = 'info';
log.transports.console.level = 'info';
// 可选：将 console 输出重定向到 electron-log
// Object.assign(console, log.functions);

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let pythonProcess: ChildProcessWithoutNullStreams | null = null;
let startPythonPromise: Promise<ChildProcessWithoutNullStreams | null> | null = null;
let isAppQuitting = false;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const __iconPath = !app.isPackaged
  ? path.join(__dirname, '..', '..', 'src', 'main', 'assets', 'images', 'icon.png')
  : path.join(__dirname, 'assets', 'images', 'icon.png');

function getBaseDir(): string {
  return !app.isPackaged
    ? path.join(__dirname, '..', '..')
    : process.resourcesPath;
}

function toNonEmptyString(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }
  return fallback;
}

function resolvePathFromBase(baseDir: string, targetPath: string): string {
  if (path.isAbsolute(targetPath)) return targetPath;
  const cleanPath = targetPath.replace(/^\.[\\/]/, '');
  return path.join(baseDir, cleanPath);
}

function resolvePathFromMainDir(targetPath: string): string {
  if (path.isAbsolute(targetPath)) return targetPath;
  return path.join(__dirname, targetPath);
}

function resolvePreloadPath(): string {
  const configured = appStore.get(APP_CONFIG_KEYS.preloadCandidates);
  const rawCandidates = Array.isArray(configured) && configured.length > 0
    ? configured.map((item) => toNonEmptyString(item, ''))
    : PATH_CONFIG_DEFAULTS.preloadCandidates;
  const candidates = rawCandidates
    .filter(Boolean)
    .map((candidate) => resolvePathFromMainDir(candidate));
  const found = candidates.find((candidate) => existsSync(candidate));
  if (found) return found;
  return candidates[0];
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      sandbox: false,
      preload: resolvePreloadPath()
    },
    icon: __iconPath
  });

  Menu.setApplicationMenu(null);

  if (!app.isPackaged && process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
    mainWindow.webContents.openDevTools();
  } else if (!app.isPackaged) {
    const devServerUrl = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.devServerUrl), PATH_CONFIG_DEFAULTS.devServerUrl);
    mainWindow.loadURL(devServerUrl);
    mainWindow.webContents.openDevTools();
  } else {
    const rendererEntry = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.rendererEntry), PATH_CONFIG_DEFAULTS.rendererEntry);
    const indexPath = resolvePathFromMainDir(rendererEntry);
    mainWindow.loadFile(indexPath).catch(err => {
        log.error('Failed to load index.html:', err);
        log.error('Attempted path:', indexPath);
    });
  }

  createTray();

  // Custom quit dialog via renderer IPC (supports frontend i18n)
  let quitDialogResolver: ((action: string) => void) | null = null

  ipcMain.handle(IPC_CHANNEL_NAMES.respondQuitDialog, (_event, action: string) => {
    if (quitDialogResolver) {
      quitDialogResolver(action)
      quitDialogResolver = null
    }
  })

  mainWindow.on('close', async (e) => {
    if (quitDialogResolver) return
    e.preventDefault()
    mainWindow?.webContents.send(IPC_CHANNEL_NAMES.showQuitDialog)
    const action = await new Promise<string>(resolve => { quitDialogResolver = resolve })
    if (action === 'quit') {
      mainWindow?.destroy()
      app.quit()
    } else if (action === 'minimize') {
      mainWindow?.hide()
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray(): void {
  const iconImage = nativeImage.createFromPath(__iconPath);
  const isZh = app.getLocale().startsWith('zh')

  tray = new Tray(iconImage.isEmpty() ? nativeImage.createEmpty() : iconImage);
  tray.setToolTip('Blank Tool');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: isZh ? '显示主窗口' : 'Show Window',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      }
    },
    {
      label: isZh ? '隐藏窗口' : 'Hide Window',
      click: () => {
        if (mainWindow) {
          mainWindow.hide();
        }
      }
    },
    { type: 'separator' },
    {
      label: isZh ? '退出' : 'Quit',
      click: () => {
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(contextMenu);

  tray.on('double-click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    }
  });
}

async function startPythonService(): Promise<ChildProcessWithoutNullStreams | null> {
  if (isAppQuitting) {
    return null;
  }
  const baseDir = getBaseDir();
  const serverDir = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.server), PATH_CONFIG_DEFAULTS.server);
  const serverEntry = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.serverEntry), PATH_CONFIG_DEFAULTS.serverEntry);
  const runtimeDir = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.runtime), PATH_CONFIG_DEFAULTS.runtime);
  const runtimeExecutable = toNonEmptyString(appStore.get(APP_CONFIG_KEYS.runtimeExecutable), PATH_CONFIG_DEFAULTS.runtimeExecutable);

  let absServerDir = resolvePathFromBase(baseDir, serverDir);
  let scriptPath = path.join(absServerDir, serverEntry);
  try {
    await fs.access(scriptPath);
  } catch {
    const fallbackServerDir = resolvePathFromBase(baseDir, PATH_CONFIG_DEFAULTS.server);
    const fallbackScriptPath = path.join(fallbackServerDir, PATH_CONFIG_DEFAULTS.serverEntry);
    log.warn(`Configured server path invalid, fallback to: ${fallbackScriptPath}`);
    absServerDir = fallbackServerDir;
    scriptPath = fallbackScriptPath;
  }
  log.info(`Python Script Path: ${scriptPath}`);

  let pythonExecutable = 'python';
  let absRuntimeDir = resolvePathFromBase(baseDir, runtimeDir);
  const candidate = path.join(absRuntimeDir, runtimeExecutable);
  try {
    await fs.access(candidate);
    pythonExecutable = candidate;
    log.info(`Using Python Runtime: ${pythonExecutable}`);
  } catch {
    const defaultRuntimeDir = resolvePathFromBase(baseDir, PATH_CONFIG_DEFAULTS.runtime);
    const defaultCandidate = path.join(defaultRuntimeDir, PATH_CONFIG_DEFAULTS.runtimeExecutable);
    try {
      await fs.access(defaultCandidate);
      absRuntimeDir = defaultRuntimeDir;
      pythonExecutable = defaultCandidate;
      log.warn(`Configured runtime path invalid, fallback to: ${pythonExecutable}`);
    } catch {
      log.warn(`Python runtime not found at ${candidate}, falling back to system python`);
    }
  }

  try {
    const userDataPath = app.getPath('userData');
    const env = {
        ...process.env,
        BT_RUNTIME_DIR: absRuntimeDir || '',
        BT_CACHE_DIR: path.join(userDataPath, 'cache'),
        BT_OUTPUT_DIR: path.join(userDataPath, 'output')
    };
    log.info(`Spawning Python process with: ${pythonExecutable} ${scriptPath}`);
    pythonProcess = spawn(pythonExecutable, [scriptPath], { env });
  } catch (e) {
    log.error('启动 Python 进程失败:', e);
    pythonProcess = null;
    return null;
  }

  pythonProcess.on('error', (err) => {
    log.error('Python 进程错误:', err);
  });

  pythonProcess.stderr.on('data', (data) => {
    const errorMsg = data.toString();
    // 只有当包含真正的错误关键词时才作为错误处理，否则视为普通日志
    const isError = /error|exception|traceback|fail/i.test(errorMsg);
    
    if (isError) {
        log.error(`Python Stderr: ${errorMsg}`);
        // 尝试将错误广播给所有窗口
        if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('python-error', errorMsg);
        }
    } else {
        log.info(`Python Out: ${errorMsg}`);
    }
  });

  pythonProcess.on('close', (code) => {
    log.info(`Python process exited with code ${code}`);
    pythonProcess = null;
  });
  return pythonProcess;
}

function isProcessWritable(proc: ChildProcessWithoutNullStreams | null): boolean {
  return Boolean(
    proc &&
    !proc.killed &&
    proc.exitCode === null &&
    proc.stdin &&
    !proc.stdin.destroyed &&
    !proc.stdin.writableEnded &&
    proc.stdin.writable
  );
}

async function ensurePythonService(): Promise<ChildProcessWithoutNullStreams | null> {
  if (isAppQuitting) {
    return null;
  }
  if (isProcessWritable(pythonProcess)) {
    return pythonProcess;
  }
  if (!startPythonPromise) {
    startPythonPromise = startPythonService().finally(() => {
      startPythonPromise = null;
    });
  }
  return await startPythonPromise;
}


app.whenReady().then(async () => {
  await ensurePythonService();
  setupAllHandlers(() => pythonProcess, ensurePythonService);

  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  isAppQuitting = true;
  if (tray) {
    tray.destroy();
    tray = null;
  }

  if (pythonProcess) {
    pythonProcess.kill();
  }

  setTimeout(() => {
    app.exit(0);
  }, 100);
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  } else if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
  }
});
