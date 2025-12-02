import { app, BrowserWindow, Menu, Tray, nativeImage } from 'electron';
import path from 'path';
import { promises as fs } from 'fs';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import { appStore } from './stores/index.js';
import { setupAppConfigHandlers, setupUserConfigHandlers } from './ipc/configHandlers.js';
import { setupCommandHandlers } from './ipc/commandHandlers.js';
import { setupSystemHandlers } from './ipc/systemHandlers.js';


let mainWindow;
let tray = null;
let pythonProcess = null;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      webSecurity: true,
      allowRunningInsecureContent: false,
      sandbox: false,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, '../assets/images', 'icon.png')
  });

  Menu.setApplicationMenu(null);

  if (process.argv.includes('--dev')) {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../index.html'));
  }

  createTray();

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  const iconPath = path.join(__dirname, '../renderer/assets/images', 'icon.png');
  const iconImage = nativeImage.createFromPath(iconPath);
  tray = new Tray(iconImage.isEmpty() ? nativeImage.createEmpty() : iconImage);
  tray.setToolTip('Blank Tool - Android开发工具');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示主窗口',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      }
    },
    {
      label: '隐藏窗口',
      click: () => {
        if (mainWindow) {
          mainWindow.hide();
        }
      }
    },
    { type: 'separator' },
    {
      label: '退出',
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

async function startPythonService() {
  const scriptPath = process.argv.includes('--dev')
    ? path.join(__dirname, '..', '..', 'backend', 'main.py')
    : path.join(process.resourcesPath, 'backend', 'main.py');

  let pythonExecutable = 'python';
  try {
    const pythonRuntime = appStore.get('tools.python');
    if (pythonRuntime && typeof pythonRuntime === 'string' && pythonRuntime.trim() !== '') {
      const candidate = path.isAbsolute(pythonRuntime)
        ? path.join(pythonRuntime, 'python.exe')
        : path.join(__dirname, '..', '..', pythonRuntime, 'python.exe');
      try {
        await fs.access(candidate);
        pythonExecutable = candidate;
      } catch {
        // 无法访问候选路径则回退到系统 python
      }
    }
  } catch { }

  try {
    pythonProcess = spawn(pythonExecutable, [scriptPath]);
  } catch (e) {
    console.error('启动 Python 进程失败:', e);
    pythonProcess = null;
    return;
  }

  pythonProcess.on('error', (err) => {
    console.error('Python 进程错误:', err);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`Python Error: ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
    pythonProcess = null;
  });
  return pythonProcess;
}


app.whenReady().then(async () => {
  setupAppConfigHandlers();
  setupUserConfigHandlers();

  const proc = await startPythonService();
  if (proc) {
    setupCommandHandlers(proc);
  }

  createWindow();
  setupSystemHandlers(mainWindow);
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
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
