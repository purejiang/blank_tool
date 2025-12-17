import { app, BrowserWindow, Menu, Tray, nativeImage, dialog } from 'electron';
import path from 'path';
import { promises as fs } from 'fs';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import { appStore } from './stores/index.js';
import { setupAllHandlers } from './ipc/index.js';


let mainWindow;
let tray = null;
let pythonProcess = null;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const __iconPath = path.join(__dirname, 'assets', 'images', 'icon.png');

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
    icon: __iconPath
  });

  Menu.setApplicationMenu(null);

  if (process.argv.includes('--dev')) {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../index.html'));
  }

  createTray();

  // 处理关闭事件
  mainWindow.on('close', (e) => {
    // 阻止默认关闭行为
    e.preventDefault();

    dialog.showMessageBox(mainWindow, {
      type: 'question',
      buttons: ['最小化到托盘', '退出程序', '取消'],
      defaultId: 0,
      cancelId: 2,
      title: '确认退出',
      message: '确定要退出程序吗？',
      detail: '您可以选择最小化到系统托盘，以便在后台继续运行服务。'
    }).then(({ response }) => {
      if (response === 0) {
        // 最小化到托盘
        mainWindow.hide();
      } else if (response === 1) {
        // 退出程序 - 销毁窗口会触发 closed 事件，不会再次触发 close
        mainWindow.destroy();
        app.quit();
      }
      // response === 2 (取消) - 什么都不做，因为已经 preventDefault 了
    });
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  const iconImage = nativeImage.createFromPath(__iconPath);

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
    const errorMsg = data.toString();
    // 只有当包含真正的错误关键词时才作为错误处理，否则视为普通日志
    const isError = /error|exception|traceback|fail/i.test(errorMsg);
    
    if (isError) {
        console.error(`Python Stderr: ${errorMsg}`);
        // 尝试将错误广播给所有窗口
        if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('python-error', errorMsg);
        }
    } else {
        console.log(`Python Out: ${errorMsg}`);
    }
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
    pythonProcess = null;
  });
  return pythonProcess;
}


app.whenReady().then(async () => {
  const proc = await startPythonService();
  setupAllHandlers(proc);

  createWindow();
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
