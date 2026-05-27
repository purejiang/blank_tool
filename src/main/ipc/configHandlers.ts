import { ipcMain, BrowserWindow, IpcMainInvokeEvent } from 'electron';
import { app } from 'electron';
import path from 'path';
import { appStore, getConfigValue, isWritableConfigKey, setConfigValue, resetAppConfigToDefaults } from '../stores/index';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';
import { APP_CONFIG_KEYS, PATH_CONFIG_DEFAULTS } from '../../shared/config/pathConfig';

function getUserConfigStore(): Record<string, unknown> {
    const raw = appStore.get('user');
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
        return {};
    }
    return { ...(raw as Record<string, unknown>) };
}

function setUserConfigStore(nextConfig: Record<string, unknown>): void {
    appStore.set('user', nextConfig);
}

function broadcastConfigChange(channel: string, key: string, value: unknown): void {
    BrowserWindow.getAllWindows().forEach(win => {
        win.webContents.send(channel, key, value);
    });
}

function toNonEmptyString(value: unknown, fallback: string): string {
    if (typeof value === 'string' && value.trim()) {
        return value.trim();
    }
    return fallback;
}

function resolvePathFromAppBase(targetPath: string): string {
    if (!targetPath) {
        return targetPath;
    }
    if (path.isAbsolute(targetPath)) {
        return targetPath;
    }
    const baseDir = app.isPackaged ? process.resourcesPath : app.getAppPath();
    const cleanPath = targetPath.replace(/^\.[\\/]/, '');
    return path.join(baseDir, cleanPath);
}

function getSettingsViewModel() {
    const settings = getConfigValue() as Record<string, unknown>;
    const runtime = toNonEmptyString(settings[APP_CONFIG_KEYS.runtime], PATH_CONFIG_DEFAULTS.runtime);
    const server = toNonEmptyString(settings[APP_CONFIG_KEYS.server], PATH_CONFIG_DEFAULTS.server);
    return {
        settings,
        displayPaths: {
            runtime: resolvePathFromAppBase(runtime),
            server: resolvePathFromAppBase(server)
        }
    };
}

export function setupAppConfigHandlers(): void {
    ipcMain.handle(IPC_CHANNEL_NAMES.getAppConfig, (event: IpcMainInvokeEvent, key?: string) => {
        console.log(`[IPC] 接收到get-app-config: key=${key}`);
        return getConfigValue(key);
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.getAllAppConfig, () => {
        console.log(`[IPC] 接收到app-config-getAll`);
        return getConfigValue();
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.setAppConfig, (event: IpcMainInvokeEvent, key: string, value: unknown) => {
        console.log(`[IPC] 接收到set-app-config: key=${key}`);
        if (!isWritableConfigKey(key)) {
            return { success: false, error: `Invalid app config key: ${key}` };
        }
        try {
            setConfigValue(key, value);
        } catch (error) {
            return { success: false, error: error instanceof Error ? error.message : String(error) };
        }
        broadcastConfigChange(IPC_CHANNEL_NAMES.appConfigChanged, key, value);
        return { success: true };
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.setManyAppConfig, (event: IpcMainInvokeEvent, updates: Record<string, unknown>) => {
        if (!updates || typeof updates !== 'object') {
            return { success: false, error: 'Invalid updates payload' };
        }
        for (const [key, value] of Object.entries(updates)) {
            if (!isWritableConfigKey(key)) {
                return { success: false, error: `Invalid app config key: ${key}` };
            }
            try {
                setConfigValue(key, value);
            } catch (error) {
                return { success: false, error: error instanceof Error ? error.message : String(error) };
            }
            broadcastConfigChange(IPC_CHANNEL_NAMES.appConfigChanged, key, value);
        }
        return { success: true };
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.resetAppConfig, () => {
        console.log(`[IPC] 接收到reset-app-config`);
        resetAppConfigToDefaults();
        return true;
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.getUserConfig, (event: IpcMainInvokeEvent, key?: string) => {
        const userConfig = getUserConfigStore();
        if (!key) {
            return userConfig;
        }
        return userConfig[key];
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.getAllUserConfig, () => {
        return getUserConfigStore();
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.setUserConfig, (event: IpcMainInvokeEvent, key: string, value: unknown) => {
        if (typeof key !== 'string' || !key.trim()) {
            return { success: false, error: 'Invalid user config key' };
        }
        const nextConfig = getUserConfigStore();
        if (typeof value === 'undefined') {
            delete nextConfig[key];
        } else {
            nextConfig[key] = value;
        }
        setUserConfigStore(nextConfig);
        broadcastConfigChange(IPC_CHANNEL_NAMES.userConfigChanged, key, value);
        return { success: true };
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.resetUserConfig, () => {
        setUserConfigStore({});
        return true;
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.getSettingsViewModel, () => {
        return getSettingsViewModel();
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.resolveSettingsPaths, (event: IpcMainInvokeEvent, paths: { runtime?: unknown; server?: unknown } = {}) => {
        const runtime = toNonEmptyString(paths.runtime, PATH_CONFIG_DEFAULTS.runtime);
        const server = toNonEmptyString(paths.server, PATH_CONFIG_DEFAULTS.server);
        return {
            runtime: resolvePathFromAppBase(runtime),
            server: resolvePathFromAppBase(server)
        };
    });
}
