import { contextBridge, ipcRenderer } from 'electron';

// 统一的后端API调用函数
const callBackendAPI = (action, params = {}, options = {}) => {
  return ipcRenderer.invoke('call-backend-api', action, params, options);
};

// 统一的IPC调用函数 - 用于非后端API的系统调用
const callSystemAPI = (channel, ...args) => {
  return ipcRenderer.invoke(channel, ...args);
};

// 预加载，暴露安全的API给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 统一的后端API调用接口
  callBackendAPI,

  // APK相关API
  analyzeApk: (filePath) => callBackendAPI('apk.analyze', { filePath }),
  extractApkResources: (filePath, outputDir) => callBackendAPI('apk.extractResources', { filePath, outputDir }),
  getApkInfo: (filePath) => callBackendAPI('apk.getInfo', { filePath }),
  decompileApk: (filePath, options) => callBackendAPI('apk.decompile', { filePath, options }),
  recompileApk: (projectPath, options) => callBackendAPI('apk.recompile', { projectPath, options }),
  signApk: (apkPath, keystore, options) => callBackendAPI('apk.sign', { apkPath, keystore, options }),
  getApkProgress: (taskId) => callBackendAPI('apk.getProgress', { taskId }),
  cancelApkTask: (taskId) => callBackendAPI('apk.cancelTask', { taskId }),

  // 设备相关API
  getAdbDevices: () => callBackendAPI('device.list'),
  startDeviceMonitoring: () => callBackendAPI('device.monitor.start'),
  startRealtimeDeviceMonitoring: () => callBackendAPI('device.monitor.realtime'),
  stopRealtimeDeviceMonitoring: () => callBackendAPI('device.monitor.stop'),
  getDeviceInfo: (deviceId) => callBackendAPI('device.info', { device_id: deviceId }),
  installApk: (apkPath, deviceId) => callBackendAPI('device.install.apk', { apk_path: apkPath, device_id: deviceId }),
  installAab: (aabPath, deviceId) => callBackendAPI('device.install.aab', { aab_path: aabPath, device_id: deviceId }),
  convertAabToApks: (aabPath, deviceId) => callBackendAPI('aab.convert', { aab_path: aabPath, device_id: deviceId }),
  installApks: (apksPath, deviceId) => callBackendAPI('device.install.apks', { apks_path: apksPath, device_id: deviceId }),
  uninstallApp: (packageName, deviceId) => callBackendAPI('device.uninstall', { package_name: packageName, device_id: deviceId }),
  getInstalledApps: (deviceId, appType) => callBackendAPI('device.packages', { device_id: deviceId, app_type: appType }),
  exportApk: (packageName, deviceId, outputDir) => callBackendAPI('device.export', {
    package_name: packageName,
    device_id: deviceId,
    output_dir: outputDir
  }),

  // 日志相关 - 混合调用
  logMessage: (level, message, category) => callSystemAPI('log-message', level, message, category),
  getLogPreview: (lines) => callBackendAPI('log.preview', { lines: lines }),

  // 存储相关API - 为electron-store提供支持
  // App 配置相关 API
  appConfig: {
    get: (key) => ipcRenderer.invoke('get-app-config', key),
    set: (key, value) => ipcRenderer.invoke('set-app-config', key, value),
    getAll: () => ipcRenderer.invoke('app-config-getAll'),
    reset: () => ipcRenderer.invoke('app-config-reset')
  },
  userConfig: {
    get: (key) => ipcRenderer.invoke('user-config-get', key),
    set: (key, value) => ipcRenderer.invoke('user-config-set', key, value),
    getAll: () => ipcRenderer.invoke('user-config-getAll'),
    reset: () => ipcRenderer.invoke('user-config-reset')
  },
  // 监听配置变化
  onAppConfigChange: (callback) => {
    ipcRenderer.on('app-config-changed', (event, key, value) => callback(key, value));
  },
  // 监听配置变化
  onUserConfigChange: (callback) => {
    ipcRenderer.on('user-config-changed', (event, key, value) => callback(key, value));
  },


  // 缓存相关 - 使用统一后端API
  getCacheInfo: () => callBackendAPI('cache.info'),
  clearCache: (cacheTypes, confirm) => callBackendAPI('cache.clear', { cache_types: cacheTypes, confirm: confirm }),

  // 系统相关 - 使用统一后端API
  getSystemInfo: () => callBackendAPI('system.info'),
  getVersionInfo: () => callSystemAPI('get-version-info'),
  getStatus: () => callBackendAPI('system.status'),
  getDiskUsage: () => callSystemAPI('get-disk-usage'),

  // 对话框相关 - 系统调用
  showOpenDialog: (options) => callSystemAPI('show-open-dialog', options),
  showSaveDialog: (options) => callSystemAPI('show-save-dialog', options),
  showMessageBox: (options) => callSystemAPI('show-message-box', options),

  // 文件系统相关 - 系统调用
  getFileStats: (filePath) => callSystemAPI('get-file-stats', filePath),
  writeFile: (filePath, content) => callSystemAPI('write-file', filePath, content),
  readFile: (filePath) => callSystemAPI('read-file', filePath),
  openDirectory: (filePath) => callSystemAPI('open-directory', filePath),

  // 开发者工具 - 系统调用
  toggleDevTools: () => callSystemAPI('toggle-dev-tools'),
  openDevTools: () => callSystemAPI('open-dev-tools'),

  // 设备操作相关 - 使用统一后端API
  rebootDevice: (deviceId, mode) => callBackendAPI('device.reboot', { device_id: deviceId, mode: mode }),
  executeShellCommand: (deviceId, command) => callBackendAPI('device.shell', { device_id: deviceId, command: command }),
  stopDeviceMonitoring: () => callBackendAPI('device.monitor.stop'),
  exportAppList: (deviceId, outputPath) => callBackendAPI('device.export.applist', { device_id: deviceId, output_path: outputPath }),

  // 日志相关 - 系统调用
  startDeviceLogging: (deviceId, logLevel) => callSystemAPI('start-device-logging', deviceId, logLevel),
  stopDeviceLogging: () => callSystemAPI('stop-device-logging'),

  // 工具检测相关 - 使用统一后端API
  checkTool: (python_path, toolName) => callBackendAPI('tool.check', { tool_name: toolName }, { python_path: python_path }),

  // 更新相关 - 系统调用
  checkForUpdates: () => callSystemAPI('check-for-updates'),

  // 系统相关 - 系统调用
  restart: () => callSystemAPI('restart'),
  openExternal: (url) => callSystemAPI('open-external', url),

  // 设备日志相关 (adb logcat) - 特殊处理，保持原有调用方式
  // startLogcat: (params) => callSystemAPI('start-logcat', params),
  // stopLogcat: (processId) => callSystemAPI('stop-logcat', processId),
  // exportDeviceLog: (params) => callBackendAPI('log.export', params),

  // 事件监听 - 保持原有实现
  onDeviceChange: (callback) => {
    ipcRenderer.on('device-change', callback);
    return () => ipcRenderer.removeListener('device-change', callback);
  },

  // onLogUpdate: (callback) => {
  //   ipcRenderer.on('log-update', callback);
  //   return () => ipcRenderer.removeListener('log-update', callback);
  // },

  // onLogcatOutput: (callback) => {
  //   ipcRenderer.on('logcat-output', callback);
  //   return () => ipcRenderer.removeListener('logcat-output', callback);
  // },

  // removeLogcatListener: () => {
  //   ipcRenderer.removeAllListeners('logcat-output');
  // }
});