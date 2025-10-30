import { app, BrowserWindow, ipcMain, dialog, Menu, Tray } from 'electron';
import path from 'path';
import { promises as fs } from 'fs';
import { fileURLToPath } from 'url';
import { setupAppConfigHandlers, setupUserConfigHandlers } from './ipc/configHandlers.js';
import { setupCommandHandlers } from './ipc/commandHandlers.js';



// 保持对window对象的全局引用，如果不这么做的话，当JavaScript对象被
// 垃圾回收的时候，window对象将会自动的关闭
let mainWindow;
let tray = null;

// ES6模块中获取__dirname的替代方案
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);


function createWindow() {
  // 创建浏览器窗口
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      webSecurity: true, // 启用Web安全，防止跨域问题
      allowRunningInsecureContent: false, // 允许运行不安全的内容
      sandbox: false, // 禁用沙盒模式以支持 ES6 模块
      preload: path.join(__dirname, 'preload.js')  // 加载预加载脚本
    },
    icon: path.join(__dirname, '../../assets', 'icon.png')
  });

  // 移除默认菜单栏
  Menu.setApplicationMenu(null);

  // 加载应用的 index.html
  // 在开发模式下加载开发服务器，生产模式下加载本地文件
  if (process.env.NODE_ENV === 'development' || process.argv.includes('--dev')) {
    mainWindow.loadURL('http://localhost:3000');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../index.html'));
  }

  // 在开发模式下打开开发者工具
  if (process.env.NODE_ENV === 'development' || process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }

  // 创建系统托盘
  createTray();

  // 处理窗口关闭事件 - 使用默认行为
  // mainWindow.on('close', (event) => {
  //   // 移除了closeToTray配置依赖，使用默认关闭行为
  // });

  // 当 window 被关闭，这个事件会被触发
  mainWindow.on('closed', () => {
    // 取消引用 window 对象，如果你的应用支持多窗口的话，
    // 通常会把多个 window 对象存放在一个数组里面，
    // 与此同时，你应该删除相应的元素。
    mainWindow = null;
  });
}

// 创建系统托盘
function createTray() {
  // 使用应用图标作为托盘图标
  const iconPath = path.join(__dirname, '../../assets', 'icon.png');
  tray = new Tray(iconPath);

  // 设置托盘提示文本
  tray.setToolTip('Blank Tool - Android开发工具');

  // 创建托盘菜单
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

  // 设置托盘菜单
  tray.setContextMenu(contextMenu);

  // 双击托盘图标显示/隐藏窗口
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

// 添加文件对话框处理
ipcMain.handle('show-open-dialog', async (event, options) => {
  const result = await dialog.showOpenDialog(mainWindow, options);
  return result;
});

ipcMain.handle('show-save-dialog', async (event, options) => {
  const result = await dialog.showSaveDialog(mainWindow, options);
  return result;
});

ipcMain.handle('show-message-box', async (event, options) => {
  const result = await dialog.showMessageBox(mainWindow, options);
  return result;
});

// 添加文件系统相关处理
ipcMain.handle('get-file-stats', async (event, filePath) => {
  try {
    const stats = await fs.stat(filePath);
    return {
      size: stats.size,
      isFile: stats.isFile(),
      isDirectory: stats.isDirectory(),
      mtime: stats.mtime,
      ctime: stats.ctime
    };
  } catch (error) {
    console.error('获取文件统计信息失败:', error);
    throw error;
  }
});

// Electron 会在初始化后并准备
// 创建浏览器窗口时，调用这个函数。
// 部分 API 在 ready 事件触发后才能使用。
app.whenReady().then(() => {

  // 初始化应用配置和用户配置
  setupAppConfigHandlers();
  setupUserConfigHandlers();

  // 初始化命令行处理
  setupCommandHandlers();

  // 创建主窗口
  createWindow();
});

// 当全部窗口关闭时退出。
app.on('window-all-closed', () => {
  // 在 macOS 上，除非用户用 Cmd + Q 确定地退出，
  // 否则绝大部分应用及其菜单栏会保持激活。
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  // 销毁托盘图标
  if (tray) {
    tray.destroy();
    tray = null;
  }
});
app.on('activate', () => {
  // 在macOS上，当单击dock图标并且没有其他窗口打开时，
  // 通常在应用程序中重新创建一个窗口。
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  } else if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
  }
});