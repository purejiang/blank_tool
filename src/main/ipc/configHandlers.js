import { ipcMain, BrowserWindow } from 'electron';
import { appStore, userStore} from '../stores/index.js';


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
        appStore.set(key, value);
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

export function setupUserConfigHandlers() {
    ipcMain.handle('get-user-config', (event, key) => {
        console.log(`[IPC] 接收到get-user-config: key=${key}`);
        return key ? userStore.get(key) : userStore.store;
    });

    ipcMain.handle('user-config-getAll', () => {
        console.log(`[IPC] 接收到user-config-getAll`);
        return userStore.store;
    });

    ipcMain.handle('set-user-config', (event, key, value) => {
        console.log(`[IPC] 接收到set-user-config: key=${key}, value=${value}`);
        userStore.set(key, value);
        // 通知所有窗口配置已变更
        BrowserWindow.getAllWindows().forEach(win => {
            win.webContents.send('user-config-changed', key, value);
        });
        return true;
    });

    ipcMain.handle('reset-user-config', () => {
        console.log(`[IPC] 接收到reset-user-config`);
        userStore.resetToDefaults();
        // 获取重置后的配置
        const newConfig = userStore.store;
        
        // 通知所有窗口用户配置已重置
        BrowserWindow.getAllWindows().forEach(win => {
            if (!win.isDestroyed()) {
                // 发送整个新的配置，或者发送一个重置事件
                win.webContents.send('user-config-reset', newConfig);
            }
        });
        return true;
    });
}

