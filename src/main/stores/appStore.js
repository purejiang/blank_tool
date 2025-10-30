import Store from 'electron-store';

// 定义配置 schema
const schema = {
    // 应用配置
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
    // 工具配置
    tools: {
        type: 'object',
        properties: {
            adb: {
                type: 'string',
                default: './tools/adb'
            },
            aapt: {
                type: 'string',
                default: './tools/aapt'
            },
            apktool: {
                type: 'string',
                default: './tools/apktool'
            },
            bundletool: {
                type: 'string',
                default: './tools/bundletool'
            },
            java: {
                type: 'string',
                default: './tools/jre'
            },
            python: {
                type: 'string',
                default: './tools/python_runtime'
            },
            zipalign: {
                type: 'string',
                default: './tools/android'
            },
            apksigner: {
                type: 'string',
                default: './tools/android'
            }
        },
        default: {
            adb: './tools/adb',
            aapt: './tools/aapt',
            apktool: './tools/apktool',
            bundletool: './tools/bundletool',
            java: './tools/jre',
            python: './tools/python_runtime',
            zipalign: './tools/android',
            apksigner: './tools/android'
        }
    },
    // 命令配置
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
    // 日志配置
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
    }
};

// 创建 store 实例
const appStore = new Store({
    name: 'app-config',
    schema
});

// 添加自定义方法
appStore.resetToDefaults = () => {
    const defaults = {};
    Object.keys(schema).forEach(key => {
        defaults[key] = schema[key].default;
    });
    appStore.store = defaults;
};

export default appStore;