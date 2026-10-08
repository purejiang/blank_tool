// ⚠️ 必须保持为第一个 import：模块内的 app.setName('blanks') 决定 userData 目录
// （%APPDATA%\blanks），必须在 electron-store（./stores/index）构造之前生效。
import './appIdentity';
import { APP_ID } from './appIdentity';
import { releaseDevStartupGuard } from './dataRoot';
import { app, BrowserWindow } from 'electron';
import { setupAllHandlers } from './ipc/index';
import { initAutoUpdater, autoCheckForUpdates, isUpdateInstallInProgress } from './updater/updater';
import { configureLogging, LogLevel } from './logging';
import { createMainWindow } from './window/mainWindow';
import {
  getPythonProcess,
  setIsAppQuitting,
  getTray, setTray,
  getMainWindow
} from './state';
import { ensurePythonService } from './python/service';
import { appStore } from './stores/index';

app.whenReady().then(async () => {
  // 启动期已过：把 dev 的未捕获异常处理交还给 Electron 默认行为（弹窗 + 保活），
  // 免得运行期一个偶发同步异常变成"悄悄退出"。见 src/main/dataRoot.ts。
  releaseDevStartupGuard();

  const logsConfig = appStore.get('logs') as { level?: string } | undefined;
  const logLevel: LogLevel = (logsConfig?.level as LogLevel) || 'info';
  configureLogging(logLevel);

  if (process.platform === 'win32') {
    // 必须是 APP_ID（= package.json 的 build.appId）：写死旧 id 会让 Windows 把本应用
    // 归到旧的 "Blank Tool" 那一组（任务栏分组/固定、通知归属全跟着错），见 appIdentity.ts。
    app.setAppUserModelId(APP_ID);
  }

  await ensurePythonService();
  setupAllHandlers(() => getPythonProcess(), ensurePythonService);

  createMainWindow();

  // Auto-update check (3s delay to avoid impacting startup)
  setTimeout(() => {
    initAutoUpdater()
    if (app.isPackaged) {
      autoCheckForUpdates()
    }
  }, 3000)
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  setIsAppQuitting(true);
  const currentTray = getTray();
  if (currentTray) {
    currentTray.destroy();
    setTray(null);
  }

  const currentProc = getPythonProcess();
  if (currentProc) {
    currentProc.kill();
  }

  if (!isUpdateInstallInProgress()) {
    setTimeout(() => {
      app.exit(0);
    }, 100);
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createMainWindow();
  } else {
    const mw = getMainWindow();
    if (mw) {
      mw.show();
      mw.focus();
    }
  }
});
