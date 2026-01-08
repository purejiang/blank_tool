import { ipcMain, BrowserWindow } from 'electron';
import { appStore } from '../stores/index.js';


export function setupAppConfigHandlers() {
    ipcMain.handle('get-app-config', (event, key) => {
        console.log(`[IPC] 接收到get-app-config: key=${key}`);
        return key ? appStore.get(key) : appStore.store;
    });

    ipcMain.handle('app-config-getAll', () => {
        console.log(`[IPC] 接收到app-config-getAll`);
        return appStore.store;
    });

    ipcMain.handle('set-app-config', (event, key, value) => {
        console.log(`[IPC] 接收到set-app-config: key=${key}, value=${value}`);
        if (typeof value === 'undefined') {
            appStore.delete(key);
        } else {
            appStore.set(key, value);
        }
         // 通知所有窗口配置已变更
        BrowserWindow.getAllWindows().forEach(win => {
            win.webContents.send('app-config-changed', key, value);
        });
        return true;
    });

    ipcMain.handle('reset-app-config', () => {
        console.log(`[IPC] 接收到reset-app-config`);
        appStore.resetToDefaults();
        return true;
    });
}

