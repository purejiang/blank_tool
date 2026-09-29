import Store from 'electron-store';
import { PATH_CONFIG_DEFAULTS, type WritableAppConfigKey } from '../../shared/config/pathConfig';

export const APP_CONFIG_VERSION = 9;
export { PATH_CONFIG_DEFAULTS };

const schema = {
    configVersion: {
        type: 'number',
        minimum: 1,
        default: APP_CONFIG_VERSION
    },
    app: {
        type: 'object',
        properties: {
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
            // 300000ms = 5min, matches commandHandlers.ts default IPC timeout
            timeout: {
                type: 'number',
                minimum: 1000,
                default: 300000
            },
            maxHistory: {
                type: 'number',
                minimum: 10,
                default: 100
            },
            outputFormat: {
                type: 'string',
                enum: ['json', 'text'],
                default: 'json'
            }
        },
        default: {
            timeout: 300000,
            maxHistory: 100,
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
    language: {
        type: 'string',
        default: 'zh-CN'
    },
    theme: {
        type: 'string',
        enum: ['auto', 'light', 'dark'],
        default: 'auto'
    },
    enableNotifications: {
        type: 'boolean',
        default: false
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

        if (!appStore.has('language') && appConfig && typeof appConfig.language === 'string') {
            appStore.set('language', appConfig.language);
        }
        if (!appStore.has('theme') && appConfig && typeof appConfig.theme === 'string') {
            if (['auto', 'light', 'dark'].includes(appConfig.theme)) {
                appStore.set('theme', appConfig.theme);
            }
        }
        const preloadCandidates = appStore.get('preloadCandidates');
        if (!Array.isArray(preloadCandidates)) {
            appStore.set('preloadCandidates', cloneDefaultValue(PATH_CONFIG_DEFAULTS.preloadCandidates));
        }
    },
    2: () => {
        appStore.set('preloadCandidates', cloneDefaultValue(PATH_CONFIG_DEFAULTS.preloadCandidates));
        appStore.set('rendererEntry', PATH_CONFIG_DEFAULTS.rendererEntry);
    },
    // Migrations 3 and 4 were byte-identical to 2 (re-set the same two defaults)
    // and have been folded into 2; the version loop still advances through 3/4.
    5: () => {
        const app = appStore.get('app');
        if (app && typeof app === 'object') {
            delete (app as Record<string, unknown>).theme;
            delete (app as Record<string, unknown>).language;
            appStore.set('app', app);
        }
    },
    // 6: system notifications now default to OFF (WP4, #15). A migration is
    // required rather than relying on syncStoreDefaults(): that only fills in
    // *missing* keys, so an existing `true` written under the old default would
    // survive the schema flip. An explicit `false` is left untouched.
    6: () => {
        if (appStore.get('enableNotifications') === true) {
            appStore.set('enableNotifications', false);
        }
    },
    // 7: drop the two dead keys (WP10, #19). `output.output` and `javaPath` were
    // declared writable but read nowhere: the data directories (cache/output/
    // tasks/logs) are fixed subdirectories of getAppLocalDataPath(), injected as
    // BT_*_DIR by src/main/python/service.ts. A stale value left behind would
    // look like it does something, so remove it from existing config files.
    7: () => {
        appStore.delete('output');
        appStore.delete('javaPath');
    },
    // 8: drop `autoDeleteOutputOnTaskRemove` (never read anywhere; the setting UI
    // was removed). Deleting a task now always cleans up that task's run
    // artifacts (cli/app/handlers/task_def_handler.py), so there is nothing left
    // to toggle — a stale key would only look like it still does something.
    8: () => {
        appStore.delete('autoDeleteOutputOnTaskRemove');
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
