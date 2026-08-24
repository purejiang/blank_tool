import { ipcMain, BrowserWindow, IpcMainInvokeEvent } from 'electron';
import { appStore, getConfigValue, isWritableConfigKey, setConfigValue, resetAppConfigToDefaults } from '../stores/index';
import { IPC_CHANNEL_NAMES } from '../../shared/ipc/channels';
import { APP_CONFIG_KEYS, PATH_CONFIG_DEFAULTS } from '../../shared/config/pathConfig';
import { resolveFromAppBase } from '../utils/appPaths';
import { toNonEmptyString } from '../python/paths';

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

function resolvePathFromAppBase(targetPath: string): string {
    return resolveFromAppBase(targetPath);
}

function applyConfigUpdate(key: string, value: unknown): { success: boolean; error?: string } {
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
        return getConfigValue(key);
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.getAllAppConfig, () => {
        // Delegates to getConfigValue() — intentionally equivalent to getAppConfig with no key; both exist for API clarity.
        return getConfigValue();
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.setAppConfig, (event: IpcMainInvokeEvent, key: string, value: unknown) => {
        return applyConfigUpdate(key, value);
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.setManyAppConfig, (event: IpcMainInvokeEvent, updates: Record<string, unknown>) => {
        if (!updates || typeof updates !== 'object') {
            return { success: false, error: 'Invalid updates payload' };
        }
        for (const [key, value] of Object.entries(updates)) {
            const result = applyConfigUpdate(key, value);
            if (!result.success) {
                return result;
            }
        }
        return { success: true };
    });

    ipcMain.handle(IPC_CHANNEL_NAMES.resetAppConfig, () => {
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
