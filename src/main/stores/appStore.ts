import Store from 'electron-store';
import { PATH_CONFIG_DEFAULTS, type WritableAppConfigKey } from '../../shared/config/pathConfig';

export const APP_CONFIG_VERSION = 2;
export { PATH_CONFIG_DEFAULTS };

const LEGACY_SETTINGS_DEFAULTS = {
    language: 'zh-CN',
    theme: 'auto',
    autoSave: true,
    enableNotifications: true,
    adbPath: '',
    aaptPath: '',
    apktoolPath: '',
    bundletoolPath: '',
    javaPath: ''
};

const schema = {
    configVersion: {
        type: 'number',
        minimum: 1,
        default: APP_CONFIG_VERSION
    },
    app: {
        type: 'object',
        properties: {
            theme: {
                type: 'string',
                enum: ['light', 'dark'],
                default: 'light'
            },
            language: {
                type: 'string',
                default: 'zh-CN'
            },
            autoStart: {
                type: 'boolean',
                default: false
            },
            minimizeToTray: {
                type: 'boolean',
                default: false
            }
        },
        default: {
            theme: 'light',
            language: 'zh-CN',
            autoStart: false,
            minimizeToTray: false
        }
    },
    runtime: {
        type: 'string',
        default: PATH_CONFIG_DEFAULTS.runtime
    },
    server: {
        type: 'string',
        default: PATH_CONFIG_DEFAULTS.server
    },
    serverEntry: {
        type: 'string',
        default: PATH_CONFIG_DEFAULTS.serverEntry
    },
    runtimeExecutable: {
        type: 'string',
        default: PATH_CONFIG_DEFAULTS.runtimeExecutable
    },
    devServerUrl: {
        type: 'string',
        default: PATH_CONFIG_DEFAULTS.devServerUrl
    },
    rendererEntry: {
        type: 'string',
        default: PATH_CONFIG_DEFAULTS.rendererEntry
    },
    preloadCandidates: {
        type: 'array',
        items: {
            type: 'string'
        },
        default: PATH_CONFIG_DEFAULTS.preloadCandidates
    },
    commands: {
        type: 'object',
        properties: {
            timeout: {
                type: 'number',
                minimum: 1000,
                default: 30000
            },
            maxHistory: {
                type: 'number',
                minimum: 10,
                default: 100
            },
            autoSave: {
                type: 'boolean',
                default: true
            },
            outputFormat: {
                type: 'string',
                enum: ['json', 'text'],
                default: 'json'
            }
        },
        default: {
            timeout: 30000,
            maxHistory: 100,
            autoSave: true,
            outputFormat: 'json'
        }
    },
    logs: {
        type: 'object',
        properties: {
            level: {
                type: 'string',
                enum: ['debug', 'info', 'warn', 'error'],
                default: 'info'
            },
            maxSize: {
                type: 'number',
                minimum: 1,
                default: 10
            },
            maxFiles: {
                type: 'number',
                minimum: 1,
                default: 5
            },
            enableConsole: {
                type: 'boolean',
                default: true
            },
            enableFile: {
                type: 'boolean',
                default: true
            }
        },
        default: {
            level: 'info',
            maxSize: 10,
            maxFiles: 5,
            enableConsole: true,
            enableFile: true
        }
    },
    output: {
        type: 'object',
        properties: {
            output: {
                type: 'string',
                default: ''
            }
        },
        default: {
            output: ''
        }
    },
    language: {
        type: 'string',
        default: LEGACY_SETTINGS_DEFAULTS.language
    },
    theme: {
        type: 'string',
        enum: ['auto', 'light', 'dark'],
        default: LEGACY_SETTINGS_DEFAULTS.theme
    },
    autoSave: {
        type: 'boolean',
        default: LEGACY_SETTINGS_DEFAULTS.autoSave
    },
    enableNotifications: {
        type: 'boolean',
        default: LEGACY_SETTINGS_DEFAULTS.enableNotifications
    },
    adbPath: {
        type: 'string',
        default: LEGACY_SETTINGS_DEFAULTS.adbPath
    },
    aaptPath: {
        type: 'string',
        default: LEGACY_SETTINGS_DEFAULTS.aaptPath
    },
    apktoolPath: {
        type: 'string',
        default: LEGACY_SETTINGS_DEFAULTS.apktoolPath
    },
    bundletoolPath: {
        type: 'string',
        default: LEGACY_SETTINGS_DEFAULTS.bundletoolPath
    },
    javaPath: {
        type: 'string',
        default: LEGACY_SETTINGS_DEFAULTS.javaPath
    }
};

const appStore = new Store<Record<string, any>>({
    name: 'app-config',
    schema: schema as any
});

function cloneDefaultValue(defaultValue: any): any {
    if (Array.isArray(defaultValue)) {
        return [...defaultValue];
    }
    if (defaultValue && typeof defaultValue === 'object') {
        const output = {};
        Object.keys(defaultValue).forEach((key) => {
            output[key] = cloneDefaultValue(defaultValue[key]);
        });
        return output;
    }
    return defaultValue;
}

function mergeMissingDefaults(currentValue: any, defaultValue: any): any {
    if (Array.isArray(defaultValue)) {
        return Array.isArray(currentValue) ? currentValue : [...defaultValue];
    }
    if (defaultValue && typeof defaultValue === 'object') {
        const base: Record<string, any> = currentValue && typeof currentValue === 'object' && !Array.isArray(currentValue)
            ? { ...currentValue }
            : {};
        Object.keys(defaultValue).forEach(key => {
            if (typeof base[key] === 'undefined') {
                const nextDefault = defaultValue[key];
                base[key] = Array.isArray(nextDefault)
                    ? [...nextDefault]
                    : nextDefault && typeof nextDefault === 'object'
                        ? mergeMissingDefaults(undefined, nextDefault)
                        : nextDefault;
            } else if (defaultValue[key] && typeof defaultValue[key] === 'object' && !Array.isArray(defaultValue[key])) {
                base[key] = mergeMissingDefaults(base[key], defaultValue[key]);
            }
        });
        return base;
    }
    return typeof currentValue === 'undefined' ? defaultValue : currentValue;
}

const MIGRATIONS: Record<number, () => void> = {
    1: () => {
        const appConfig = appStore.get('app');
        const commandConfig = appStore.get('commands');

        if (!appStore.has('language') && appConfig && typeof appConfig.language === 'string') {
            appStore.set('language', appConfig.language);
        }
        if (!appStore.has('theme') && appConfig && typeof appConfig.theme === 'string') {
            if (['auto', 'light', 'dark'].includes(appConfig.theme)) {
                appStore.set('theme', appConfig.theme);
            }
        }
        if (!appStore.has('autoSave') && commandConfig && typeof commandConfig.autoSave === 'boolean') {
            appStore.set('autoSave', commandConfig.autoSave);
        }

        const preloadCandidates = appStore.get('preloadCandidates');
        if (!Array.isArray(preloadCandidates)) {
            appStore.set('preloadCandidates', cloneDefaultValue(PATH_CONFIG_DEFAULTS.preloadCandidates));
        }
    }
};

function runConfigMigrations() {
    let currentVersion = Number(appStore.get('configVersion') || 1);
    if (!Number.isFinite(currentVersion) || currentVersion < 1) {
        currentVersion = 1;
    }

    while (currentVersion < APP_CONFIG_VERSION) {
        const migrate = MIGRATIONS[currentVersion];
        if (typeof migrate === 'function') {
            migrate();
        }
        currentVersion += 1;
    }

    appStore.set('configVersion', APP_CONFIG_VERSION);
}

function syncStoreDefaults() {
    Object.keys(schema).forEach(key => {
        const defaultValue = (schema as any)[key].default;
        const hasKey = appStore.has(key);
        const currentValue = appStore.get(key);
        const mergedValue = mergeMissingDefaults(currentValue, defaultValue);
        if (!hasKey) {
            appStore.set(key, mergedValue);
            return;
        }
        if (defaultValue && typeof defaultValue === 'object') {
            appStore.set(key, mergedValue);
        }
    });
}

runConfigMigrations();
syncStoreDefaults();

const WRITABLE_TOP_LEVEL_KEYS = new Set<WritableAppConfigKey>(Object.keys(schema) as WritableAppConfigKey[]);

export function isWritableConfigKey(key: string) {
    if (typeof key !== 'string' || !key.trim()) {
        return false;
    }
    const topLevelKey = key.trim().split('.')[0];
    if (topLevelKey === 'configVersion') {
        return false;
    }
    return WRITABLE_TOP_LEVEL_KEYS.has(topLevelKey as WritableAppConfigKey);
}

export function getConfigValue(key?: string) {
    if (!key) {
        return appStore.store;
    }
    return appStore.get(key);
}

export function setConfigValue(key: string, value: unknown) {
    if (!isWritableConfigKey(key)) {
        throw new Error(`Invalid app config key: ${key}`);
    }
    if (typeof value === 'undefined') {
        appStore.delete(key);
        return;
    }
    appStore.set(key, value);
}

export function resetAppConfigToDefaults() {
    const defaults: Record<string, any> = {};
    Object.keys(schema).forEach(key => {
        defaults[key] = cloneDefaultValue((schema as any)[key].default);
    });
    appStore.store = defaults;
}

export default appStore;
