import { contextBridge, ipcRenderer } from 'electron';
// preload.js 运行在渲染进程中

// 统一的后端API调用函数
const callBackendAPI = (action, params = {}) => {
  const requestId = `${Date.now()}-${Math.random()}`;
  const request = {
    id: requestId,
    method: action,
    params: params,
  };
  return ipcInvoke('call-backend-api', request);
};

// 统一的IPC调用函数 - 用于非后端API的调用
const ipcInvoke = (channel, ...args) => {
  return ipcRenderer.invoke(channel, ...args);
};

// 预加载，暴露安全的API给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 统一的Ipc调用接口
  ipcInvoke,
  callBackendAPI,
  // 后端相关API
  analyzeApk: (filePath) => callBackendAPI('apk.analyze', { filePath }),
  extractApkResources: (filePath, outputDir) => callBackendAPI('apk.extractResources', { filePath, outputDir }),
  getApkInfo: (filePath) => callBackendAPI('apk.getInfo', { filePath }),
  decompileApk: (filePath, options) => callBackendAPI('apk.decompile', { filePath, options }),
  recompileApk: (projectPath, options) => callBackendAPI('apk.recompile', { projectPath, options }),
  signApk: (apkPath, keystore, options) => callBackendAPI('apk.sign', { apkPath, keystore, options }),
  getApkProgress: (taskId) => callBackendAPI('apk.getProgress', { taskId }),
  cancelApkTask: (taskId) => callBackendAPI('apk.cancelTask', { taskId }),
  // 系统相关API


  // 设备相关API
  getAdbDevices: () => callBackendAPI('device.get_devices'),
  startDeviceMonitoring: () => callBackendAPI('device.monitor.start'),
  startRealtimeDeviceMonitoring: () => callBackendAPI('device.monitor.realtime'),
  stopRealtimeDeviceMonitoring: () => callBackendAPI('device.monitor.stop'),
  getDeviceInfo: (deviceId) => callBackendAPI('device.get_device_info', { device_id: deviceId }),
  installApk: (apkPath, deviceId) => callBackendAPI('device.install_apk', { apk_path: apkPath, device_id: deviceId }),
  installAab: (aabPath, deviceId) => callBackendAPI('device.install_aab', { aab_path: aabPath, device_id: deviceId }),
  convertAabToApks: (aabPath, deviceId) => callBackendAPI('device.convert_aab_to_apks', { aab_path: aabPath, device_id: deviceId }),
  installApks: (apksPath, deviceId) => callBackendAPI('device.install_apks', { apks_path: apksPath, device_id: deviceId }),
  uninstallApp: (packageName, deviceId) => callBackendAPI('device.uninstall_app', { package_name: packageName, device_id: deviceId }),
  getInstalledApps: (deviceId, appType) => callBackendAPI('device.get_installed_packages', { device_id: deviceId, app_type: appType }),
  exportApk: (packageName, deviceId, outputDir) => callBackendAPI('device.export_apk', {
    package_name: packageName,
    device_id: deviceId,
    output_dir: outputDir
  }),

  // 日志相关 - 混合调用
  logMessage: (level, message, category) => ipcInvoke('log-message', level, message, category),
  getLogPreview: (lines) => callBackendAPI('log.preview', { lines: lines }),

  // 存储相关API - 为electron-store提供支持
  // App 配置相关 API
  appConfig: {
    get: (key) => ipcRenderer.invoke('get-app-config', key),
    set: (key, value) => ipcRenderer.invoke('set-app-config', key, value),
    getAll: () => ipcRenderer.invoke('app-config-getAll'),
    reset: () => ipcRenderer.invoke('reset-app-config')
  },
  userConfig: {
    get: (key) => ipcRenderer.invoke('get-user-config', key),
    set: (key, value) => ipcRenderer.invoke('set-user-config', key, value),
    getAll: () => ipcRenderer.invoke('user-config-getAll'),
    reset: () => ipcRenderer.invoke('reset-user-config')
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
  getSystemInfo: () => callBackendAPI('app.system'),
  getBackendVersion: () => callBackendAPI('app.version'),
  getBuildInfo: () => callBackendAPI('app.build'),
  getAppVersion: () => process.env.npm_package_version || 'Unknown',
  getElectronVersion: () => process.versions.electron,
  getStatus: () => callBackendAPI('system.status'),
  getDiskUsage: () => ipcInvoke('get-disk-usage'),

  // 对话框相关 - 系统调用
  showOpenDialog: (options) => ipcInvoke('show-open-dialog', options),
  showSaveDialog: (options) => ipcInvoke('show-save-dialog', options),
  showMessageBox: (options) => ipcInvoke('show-message-box', options),

  // 便捷封装 - 文件/目录选择
  selectFile: (options = {}) => {
    const props = Array.isArray(options.properties) ? [...options.properties] : []
    if (!props.includes('openFile')) props.push('openFile')
    const opts = { ...options, properties: props }
    return ipcInvoke('show-open-dialog', opts)
  },
  selectDirectory: (options = {}) => {
    const props = Array.isArray(options.properties) ? [...options.properties] : []
    if (!props.includes('openDirectory')) props.push('openDirectory')
    const opts = { ...options, properties: props }
    return ipcInvoke('show-open-dialog', opts)
  },

  // 文件系统相关 - 系统调用
  getFileStats: (filePath) => ipcInvoke('get-file-stats', filePath),
  writeFile: (filePath, content) => ipcInvoke('write-file', filePath, content),
  readFile: (filePath) => ipcInvoke('read-file', filePath),
  openDirectory: (filePath) => ipcInvoke('open-directory', filePath),
  openPath: (filePath) => ipcInvoke('open-directory', filePath),

  // 开发者工具 - 系统调用
  toggleDevTools: () => ipcInvoke('toggle-dev-tools'),
  openDevTools: () => ipcInvoke('open-dev-tools'),
  
  // 更新相关 - 系统调用
  checkForUpdates: () => ipcInvoke('check-for-updates'),

  // 系统相关 - 系统调用
  restart: () => ipcInvoke('restart'),
  openExternal: (url) => ipcInvoke('open-external', url),

  
  exportDeviceLog: (params) => callBackendAPI('log.export', params),

  // 事件监听 - 保持原有实现
  onDeviceChange: (callback) => {
    ipcRenderer.on('device-change', callback);
    return () => ipcRenderer.removeListener('device-change', callback);
  },

  onLogUpdate: (callback) => {
    ipcRenderer.on('log-update', callback);
    return () => ipcRenderer.removeListener('log-update', callback);
  },

  onLogcatOutput: (callback) => {
    ipcRenderer.on('logcat-output', callback);
    return () => ipcRenderer.removeListener('logcat-output', callback);
  },
  onLogcatStarted: (callback) => {
    ipcRenderer.on('logcat-started', callback);
    return () => ipcRenderer.removeListener('logcat-started', callback);
  },
  onLogcatFinished: (callback) => {
    ipcRenderer.on('logcat-finished', callback);
    return () => ipcRenderer.removeListener('logcat-finished', callback);
  },
  onLogcatError: (callback) => {
    ipcRenderer.on('logcat-error', callback);
    return () => ipcRenderer.removeListener('logcat-error', callback);
  },

  removeLogcatListener: () => {
    ipcRenderer.removeAllListeners('logcat-output');
  }
});
