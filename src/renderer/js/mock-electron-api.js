/**
 * 模拟Electron API - 用于Web环境
 * 当应用在浏览器中运行时，提供与Electron API兼容的接口
 */

class MockElectronAPI {
    constructor() {
        this.isElectron = false;
        this.mockSettings = {
            // 通用设置
            language: 'zh-CN',
            theme: 'light',
            autoSave: true,
            enableNotifications: true,
            
            // 工具路径设置
            adbPath: '',
            aaptPath: '',
            apktoolPath: '',
            bundletoolPath: '',
            javaPath: '',
            
            // 输出设置
            outputDirectory: '',
            keepOriginalStructure: true,
            compressOutput: false,
            
            // 高级设置
            enableDevTools: true, // Web环境默认启用
            enableLogging: true,
            logLevel: 'info',
            maxLogSize: 10,
            
            // 性能设置
            maxConcurrentTasks: 3,
            enableCache: true,
            cacheExpiry: 24
        };
    }

    // 设置相关
    async getSettings() {
        return { success: true, settings: this.mockSettings };
    }

    async saveSettings(settings) {
        this.mockSettings = { ...this.mockSettings, ...settings };
        console.log('Mock: 设置已保存', settings);
        return { success: true };
    }

    // 配置相关 - 新增的配置管理方法
    async getAllConfig() {
        console.log('Mock: 获取所有配置');
        // 直接返回配置对象，不包装在 success 结构中
        return {
            app: {
                theme: 'light',
                language: 'zh-CN',
                autoStart: false,
                minimizeToTray: true,
                closeToTray: false
            },
            commands: {
                timeout: 30000,
                maxHistory: 100,
                autoSave: true,
                outputFormat: 'json'
            },
            logs: {
                level: 'info',
                maxSize: 10,
                maxFiles: 5,
                enableConsole: true,
                enableFile: true
            }
        };
    }

    async saveAllConfig(config) {
        console.log('Mock: 保存所有配置', config);
        return { success: true };
    }

    async resetAllConfig() {
        console.log('Mock: 重置所有配置');
        return { success: true };
    }

    async getConfigItem(key) {
        console.log('Mock: 获取配置项', key);
        return { success: true, value: null };
    }

    async setConfigItem(key, value) {
        console.log('Mock: 设置配置项', key, value);
        return { success: true };
    }

    // APK相关
    async analyzeApk(apkPath) {
        console.log('Mock: 分析APK', apkPath);
        return { success: false, error: 'Web环境不支持APK分析' };
    }

    async extractApkResources(apkPath, outputDir) {
        console.log('Mock: 提取APK资源', apkPath, outputDir);
        return { success: false, error: 'Web环境不支持APK资源提取' };
    }

    // 设备相关
    async getAdbDevices() {
        console.log('Mock: 获取ADB设备');
        return { success: true, devices: [] };
    }

    async getDeviceInfo(deviceId) {
        console.log('Mock: 获取设备信息', deviceId);
        return { success: false, error: 'Web环境不支持设备操作' };
    }

    async installApk(apkPath, deviceId) {
        console.log('Mock: 安装APK', apkPath, deviceId);
        return { success: false, error: 'Web环境不支持APK安装' };
    }

    async installAab(aabPath, deviceId) {
        console.log('Mock: 安装AAB', aabPath, deviceId);
        return { success: false, error: 'Web环境不支持AAB安装' };
    }

    async convertAabToApks(aabPath, deviceId) {
        console.log('Mock: 转换AAB为APKS', aabPath, deviceId);
        return { success: false, error: 'Web环境不支持AAB转换' };
    }

    async installApks(apksPath, deviceId) {
        console.log('Mock: 安装APKS', apksPath, deviceId);
        return { success: false, error: 'Web环境不支持APKS安装' };
    }

    async uninstallApp(packageName, deviceId) {
        console.log('Mock: 卸载应用', packageName, deviceId);
        return { success: false, error: 'Web环境不支持应用卸载' };
    }

    async exportApk(packageName, deviceId, outputDir) {
        console.log('Mock: 导出APK', packageName, deviceId, outputDir);
        return { success: false, error: 'Web环境不支持APK导出' };
    }

    // 日志相关
    async logMessage(level, message, category) {
        console.log(`Mock Log [${level}] [${category}]:`, message);
        return { success: true };
    }

    async getLogPreview(lines) {
        return { success: true, logs: [] };
    }

    // 缓存相关
    async getCacheInfo() {
        return { 
            success: true, 
            cache: { 
                size: 0, 
                files: 0, 
                lastCleared: new Date().toISOString() 
            } 
        };
    }

    async clearCache(cacheTypes, confirm) {
        console.log('Mock: 清除缓存', cacheTypes, confirm);
        return { success: true };
    }

    // 系统信息相关
    async getSystemInfo() {
        return { 
            success: true, 
            info: { 
                platform: 'web',
                arch: 'unknown',
                version: '1.0.0'
            } 
        };
    }

    async getVersionInfo() {
        return { 
            success: true, 
            versions: { 
                app: '1.0.0',
                electron: '27.0.0',
                node: '18.17.1',
                chrome: '118.0.5993.54',
                buildTime: new Date().toISOString()
            } 
        };
    }

    async getStatus() {
        return { 
            success: true, 
            status: { 
                ready: true,
                devices: 0,
                operations: 0
            } 
        };
    }

    async getDiskUsage() {
        return { 
            success: true, 
            usage: { 
                total: 0,
                used: 0,
                free: 0
            } 
        };
    }

    // 文件系统相关
    async writeFile(filePath, content) {
        console.log('Mock: 写入文件', filePath);
        return { success: false, error: 'Web环境不支持文件写入' };
    }

    async readFile(filePath) {
        console.log('Mock: 读取文件', filePath);
        return { success: false, error: 'Web环境不支持文件读取' };
    }

    async openDirectory(filePath) {
        console.log('Mock: 打开目录', filePath);
        return { success: false, error: 'Web环境不支持打开目录' };
    }

    // 外部链接
    async openExternal(url) {
        console.log('Mock: 打开外部链接', url);
        window.open(url, '_blank');
        return { success: true };
    }

    // 应用控制
    async restart() {
        console.log('Mock: 重启应用');
        window.location.reload();
        return { success: true };
    }

    // 开发工具
    async openDevTools() {
        console.log('Mock: 打开开发者工具');
        return { success: true };
    }

    // 设备相关
    async rebootDevice(deviceId, mode) {
        console.log('Mock: 重启设备', deviceId, mode);
        return { success: true, message: '设备重启命令已发送' };
    }

    async executeShellCommand(deviceId, command) {
        console.log('Mock: 执行Shell命令', deviceId, command);
        return { success: true, output: 'Mock shell output' };
    }

    async getInstalledApps(deviceId, appType) {
        console.log('Mock: 获取已安装应用', deviceId, appType);
        return { 
            success: true, 
            apps: [
                { packageName: 'com.example.app1', name: '示例应用1' },
                { packageName: 'com.example.app2', name: '示例应用2' }
            ]
        };
    }

    // 实时监控
    async startRealtimeDeviceMonitoring() {
        console.log('Mock: 开始实时设备监控');
        return { success: true };
    }

    async stopRealtimeDeviceMonitoring() {
        console.log('Mock: 停止实时设备监控');
        return { success: true };
    }

    async startDeviceLogging(deviceId, logLevel) {
        console.log('Mock: 开始设备日志记录', deviceId, logLevel);
        return { success: true };
    }

    async stopDeviceLogging() {
        console.log('Mock: 停止设备日志记录');
        return { success: true };
    }

    // 工具检测
    async detectTool(toolName) {
        console.log('Mock: 检测工具', toolName);
        return { success: true, found: false, path: '' };
    }

    // 工具检查
    async checkTool(pythonPath, toolName) {
        console.log('Mock: 检查工具', toolName, '使用Python路径:', pythonPath);
        return { 
            success: true, 
            status: 'available',
            message: `工具 ${toolName} 在模拟环境中可用`,
            path: pythonPath 
        };
    }

    // 更新检查
    async checkForUpdates() {
        console.log('Mock: 检查更新');
        return { success: true, hasUpdate: false, version: '1.0.0' };
    }

    // 设置重置
    async resetSettings() {
        console.log('Mock: 重置设置');
        this.mockSettings = {
            language: 'zh-CN',
            theme: 'light',
            autoSave: true,
            enableNotifications: true,
            adbPath: '',
            aaptPath: '',
            apktoolPath: '',
            bundletoolPath: '',
            javaPath: '',
            outputDirectory: '',
            keepOriginalStructure: true,
            compressOutput: false,
            enableDevTools: true,
            enableLogging: true,
            logLevel: 'info',
            maxLogSize: 10,
            maxConcurrentTasks: 3,
            enableCache: true,
            cacheExpiry: 24
        };
        return { success: true };
    }

    // 对话框
    async showOpenDialog(options) {
        console.log('Mock: 显示打开对话框', options);
        return { canceled: true, filePaths: [] };
    }

    async showSaveDialog(options) {
        console.log('Mock: 显示保存对话框', options);
        return { canceled: true, filePath: '' };
    }

    async showMessageBox(options) {
        console.log('Mock: 显示消息框', options);
        const result = confirm(options.message || '确认操作？');
        return { response: result ? 0 : 1 };
    }

    // 开发工具
    async toggleDevTools() {
        console.log('Mock: 切换开发者工具');
        // 在Web环境中，我们可以尝试打开浏览器的开发者工具
        if (typeof window !== 'undefined' && window.console) {
            console.log('请按F12打开浏览器开发者工具');
        }
        return { success: true };
    }

    // 后端API调用
    async callBackendAPI(endpoint, data = {}) {
        console.log('Mock: 调用后端API', endpoint, data);
        
        // 根据不同的endpoint返回模拟数据
        switch (endpoint) {
            case 'tool.status':
                return {
                    success: true,
                    data: {
                        adb: { status: 'available', version: '1.0.41', path: '/mock/adb' },
                        aapt: { status: 'available', version: '0.2', path: '/mock/aapt' },
                        aapt2: { status: 'available', version: '4.2.2', path: '/mock/aapt2' },
                        apktool: { status: 'available', version: '2.7.0', path: '/mock/apktool' },
                        bundletool: { status: 'available', version: '1.15.4', path: '/mock/bundletool' },
                        java: { status: 'available', version: '11.0.19', path: '/mock/java' }
                    }
                };
            case 'device.reboot':
                return { success: true, message: '设备重启命令已发送' };
            case 'device.shell':
                return { success: true, output: 'Mock shell command output' };
            case 'apk.decompile':
            case 'apk.recompile':
            case 'apk.sign':
                return { success: false, error: 'Web环境不支持APK操作' };
            case 'apk.getProgress':
                return { success: true, progress: 0 };
            case 'apk.cancelTask':
                return { success: true };
            case '/api/logs/error':
                return { success: true };
            default:
                return { success: false, error: `未知的API端点: ${endpoint}` };
        }
    }

    // 事件监听器
    onDeviceChange(callback) {
        console.log('Mock: 注册设备变化监听器');
        // 模拟设备变化事件
        setTimeout(() => {
            callback({ type: 'device-added', device: { id: 'mock-device', name: '模拟设备' } });
        }, 1000);
    }

    onLogUpdate(callback) {
        console.log('Mock: 注册日志更新监听器');
        // 模拟日志更新事件
        setInterval(() => {
            callback({ level: 'info', message: '模拟日志消息', timestamp: Date.now() });
        }, 5000);
    }
}

// 检查是否在Electron环境中
function isElectronEnvironment() {
    return typeof window !== 'undefined' && 
           window.electronAPI && 
           typeof window.electronAPI === 'object';
}

// 初始化API
function initializeElectronAPI() {
    if (!isElectronEnvironment()) {
        console.log('检测到Web环境，初始化模拟Electron API');
        const mockAPI = new MockElectronAPI();
        
        // 创建与真实 Electron API 兼容的结构
        window.electronAPI = {
            // 应用配置 API
            appConfig: {
                getAll: mockAPI.getAllConfig.bind(mockAPI),
                set: mockAPI.setConfigItem.bind(mockAPI),
                get: mockAPI.getConfigItem.bind(mockAPI),
                save: mockAPI.saveAllConfig.bind(mockAPI),
                reset: mockAPI.resetAllConfig.bind(mockAPI)
            },
            
            // 用户配置 API (与应用配置相同的实现)
            userConfig: {
                getAll: mockAPI.getAllConfig.bind(mockAPI),
                set: mockAPI.setConfigItem.bind(mockAPI),
                get: mockAPI.getConfigItem.bind(mockAPI),
                save: mockAPI.saveAllConfig.bind(mockAPI),
                reset: mockAPI.resetAllConfig.bind(mockAPI)
            },
            
            // 工具相关 API
            checkTool: mockAPI.checkTool.bind(mockAPI),
            detectTool: mockAPI.detectTool.bind(mockAPI),
            
            // 缓存相关 API
            getCacheInfo: mockAPI.getCacheInfo.bind(mockAPI),
            clearCache: mockAPI.clearCache.bind(mockAPI),
            
            // 设置相关 API
            getSettings: mockAPI.getSettings.bind(mockAPI),
            saveSettings: mockAPI.saveSettings.bind(mockAPI),
            resetSettings: mockAPI.resetSettings.bind(mockAPI),
            
            // 其他常用 API
            callBackendAPI: mockAPI.callBackendAPI.bind(mockAPI),
            getAdbDevices: mockAPI.getAdbDevices.bind(mockAPI),
            getDeviceInfo: mockAPI.getDeviceInfo.bind(mockAPI),
            getSystemInfo: mockAPI.getSystemInfo.bind(mockAPI),
            getVersionInfo: mockAPI.getVersionInfo.bind(mockAPI),
            getStatus: mockAPI.getStatus.bind(mockAPI),
            getDiskUsage: mockAPI.getDiskUsage.bind(mockAPI),
            
            // 文件操作 API
            writeFile: mockAPI.writeFile.bind(mockAPI),
            readFile: mockAPI.readFile.bind(mockAPI),
            openDirectory: mockAPI.openDirectory.bind(mockAPI),
            
            // 对话框 API
            showOpenDialog: mockAPI.showOpenDialog.bind(mockAPI),
            showSaveDialog: mockAPI.showSaveDialog.bind(mockAPI),
            showMessageBox: mockAPI.showMessageBox.bind(mockAPI),
            
            // 应用控制 API
            restart: mockAPI.restart.bind(mockAPI),
            openDevTools: mockAPI.openDevTools.bind(mockAPI),
            toggleDevTools: mockAPI.toggleDevTools.bind(mockAPI),
            openExternal: mockAPI.openExternal.bind(mockAPI),
            
            // 事件监听 API
            onDeviceChange: mockAPI.onDeviceChange.bind(mockAPI),
            onLogUpdate: mockAPI.onLogUpdate.bind(mockAPI)
        };
    } else {
        console.log('检测到Electron环境，使用原生API');
    }
}

// 立即初始化
initializeElectronAPI();

export { MockElectronAPI, isElectronEnvironment, initializeElectronAPI };