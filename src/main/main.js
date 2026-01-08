import { app, BrowserWindow, Menu, Tray, nativeImage, dialog } from 'electron';
import path from 'path';
import { promises as fs } from 'fs';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import log from 'electron-log';
import { appStore } from './stores/index.js';
import { setupAllHandlers } from './ipc/index.js';

// 配置日志
log.transports.file.level = 'info';
log.transports.console.level = 'info';
// 可选：将 console 输出重定向到 electron-log
// Object.assign(console, log.functions);

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
    // In production, the file structure in app.asar is:
    // - src/main/main.js
    // - dist/renderer/index.html
    const indexPath = path.join(__dirname, '../../dist/renderer/index.html');
    mainWindow.loadFile(indexPath).catch(err => {
        log.error('Failed to load index.html:', err);
        log.error('Attempted path:', indexPath);
    });
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
  tray.setToolTip('Blank Tool');

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
  // 确定基准路径
  const baseDir = process.argv.includes('--dev')
    ? path.join(__dirname, '..', '..')
    : process.resourcesPath;

  // 获取 Server 配置
  const serverDir = appStore.get('server');

  // 解析 Server 路径
  let absServerDir;
  if (serverDir) {
    if (path.isAbsolute(serverDir)) {
      absServerDir = serverDir;
    } else {
      // 移除可能存在的开头的 .\ 或 ./
      const cleanServerDir = serverDir.replace(/^\.[\\/]/, '');
      absServerDir = path.join(baseDir, cleanServerDir);
    }
  } else {
    // 理论上 appStore 会返回默认值，如果真没有，为了防止崩溃给个基准路径
    // 但严格按照需求，我们不应该硬编码默认值来覆盖配置。
    // 如果配置为空，则认为是用户意图或配置错误。
    console.warn('Server path not configured in appStore!');
    absServerDir = baseDir; 
  }

  const scriptPath = path.join(absServerDir, 'main.py');
  log.info(`Python Script Path: ${scriptPath}`);

  let pythonExecutable = 'python';
  
  // 获取 Runtime 配置
  const runtimeDir = appStore.get('runtime');
  let absRuntimeDir; // 将变量提升到这里
  
  if (runtimeDir) {
      if (path.isAbsolute(runtimeDir)) {
          absRuntimeDir = runtimeDir;
      } else {
          const cleanRuntimeDir = runtimeDir.replace(/^\.[\\/]/, '');
          absRuntimeDir = path.join(baseDir, cleanRuntimeDir);
      }
      
      const candidate = path.join(absRuntimeDir, 'python', 'python.exe');
      try {
        await fs.access(candidate);
        pythonExecutable = candidate;
        log.info(`Using Python Runtime: ${pythonExecutable}`);
      } catch {
        log.warn(`Python runtime not found at ${candidate}, falling back to system python`);
      }
  }

  try {
    const env = { 
        ...process.env,
        BT_RUNTIME_DIR: absRuntimeDir || ''
    };
    pythonProcess = spawn(pythonExecutable, [scriptPath], { env });
  } catch (e) {
    log.error('启动 Python 进程失败:', e);
    pythonProcess = null;
    return;
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
