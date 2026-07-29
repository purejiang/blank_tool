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
import { startPythonService, ensurePythonService } from './python/service';
import { appStore } from './stores/index';

app.whenReady().then(async () => {
  const logsConfig = appStore.get('logs') as { level?: string } | undefined;
  const logLevel: LogLevel = (logsConfig?.level as LogLevel) || 'info';
  configureLogging(logLevel);

  if (process.platform === 'win32') {
    app.setAppUserModelId('com.cyanrain.blank-tool');
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
