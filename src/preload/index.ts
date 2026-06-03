import { contextBridge, ipcRenderer } from 'electron';
import { IPC_CHANNEL_NAMES } from '../shared/ipc/channels';
import type { BackendApiRequest, JsonObject } from '../shared/ipc/protocol';
// preload.js 运行在渲染进程中

type DialogOptions = {
  properties?: string[]
  [key: string]: unknown
}

const isObjectRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null
}

const extractErrorMessage = (value: unknown): string | null => {
  if (!isObjectRecord(value)) {
    return null
  }
  const message = value.message
  if (typeof message === 'string' && message.trim()) {
    return message
  }
  return null
}

const unwrapBackendResponse = (raw: unknown): unknown => {
  const candidate = isObjectRecord(raw) && 'result' in raw ? raw.result : raw
  if (!isObjectRecord(candidate)) {
    return candidate
  }

  if (candidate.type === 'success') {
    return candidate.payload
  }

  if (candidate.type === 'error') {
    const payloadMessage = extractErrorMessage(candidate.payload)
    const errorMessage = extractErrorMessage(candidate.error)
    const message = payloadMessage || errorMessage || 'Unknown backend error'
    throw new Error(message)
  }

  const directErrorMessage = extractErrorMessage(candidate.error)
  if (directErrorMessage) {
    throw new Error(directErrorMessage)
  }

  return candidate
}

// 统一的后端API调用函数
const callBackendByRequest = async (request: BackendApiRequest) => {
  return await ipcInvoke(IPC_CHANNEL_NAMES.callBackendApi, request);
};

const callBackendAPI = async (action: string, params: JsonObject = {}) => {
  const requestId = `${Date.now()}-${Math.random()}`;
  const request: BackendApiRequest = {
    id: requestId,
    method: action,
    params,
  };
  try {
    const resp = await callBackendByRequest(request);
    console.log('callBackendAPI', requestId, action, params, resp);
    return unwrapBackendResponse(resp);
  } catch (error) {
    throw error;
  }
};

// 统一的IPC调用函数 - 用于非后端API的调用
const ipcInvoke = (channel, ...args) => {
  return ipcRenderer.invoke(channel, ...args);
};

// 预加载，暴露安全的API给渲染进程
const electronApi = {
  // 统一的Ipc调用接口
  ipcInvoke,
  callBackendAPI,
  callBackendByRequest,
  // ==================== 后端API ====================
  // ========== APK相关 ==========
  // APK分析
  analyzeApk: (apkPath) => callBackendAPI('apk.analyze', { apk_path: apkPath }),
  // APK信息获取
  getApkInfo: (filePath) => callBackendAPI('apk.getInfo', { file_path: filePath }),
  // APK反编译
  decompileApk: (filePath, options) => callBackendAPI('apk.decompile', { file_path: filePath, options }),
  // APK重新编译
  recompileApk: (projectPath, options) => callBackendAPI('apk.recompile', { project_path: projectPath, options }),
  // APK签名
  signApk: (apkPath, keystore, options) => callBackendAPI('apk.sign', { apk_path: apkPath, keystore, options }),
  // APK任务进度获取
  getApkProgress: (taskId) => callBackendAPI('apk.getProgress', { task_id: taskId }),
  // APK任务取消
  cancelApkTask: (taskId) => callBackendAPI('apk.cancelTask', { task_id: taskId }),
  // 文件下载
  downloadFile: (url, filename, taskId) => callBackendAPI('download.file', { url, filename, task_id: taskId }),

  // ========== 工具相关 ==========
  // 获取工具列表/检查工具
  getTools: (params) => callBackendAPI('tool.get_tools', params),
  checkTool: (toolName, refresh) => callBackendAPI('tool.get_tools', { tool_name: toolName, refresh }),
  // 设置系统查找模式
  setToolSearchMode: (systemSearch) => callBackendAPI('tool.set_search_mode', { system_search: systemSearch }),

  // ========== 设备相关API ==========
  // 设备列表获取
  getAdbDevices: () => callBackendAPI('adb.devices'),
  // ADB 远程连接
  adbConnect: (address: string) => callBackendAPI('adb.connect', { address }),
  adbDisconnect: (address?: string) => callBackendAPI('adb.disconnect', { address: address || '' }),
  // 设备重启
  rebootDevice: (deviceId, mode) => callBackendAPI('device.reboot', { device_id: deviceId, mode }),
  // 设备Shell命令执行
  executeShell: (deviceId, command) => callBackendAPI('device.shell', { device_id: deviceId, command }),
  // Logcat
  startLogcat: (deviceId) => callBackendAPI('adb.logcat', { device_id: deviceId }),
  stopLogcat: (processId) => callBackendAPI('adb.stop_logcat', { process_id: processId }),
  // 设备监控启动
  startDeviceMonitoring: () => callBackendAPI('device.monitor.start'),
  // 设备实时监控启动
  startRealtimeDeviceMonitoring: () => callBackendAPI('device.monitor.realtime'),
  // 设备实时监控停止
  stopRealtimeDeviceMonitoring: () => callBackendAPI('device.monitor.stop'),
  // 设备信息获取
  getDeviceInfo: (deviceId) => callBackendAPI('device.get_device_info', { device_id: deviceId }),
  // 设备安装apk、aab、apks
  installApk: (apkPath, deviceId) => callBackendAPI('device.install_apk', { apk_path: apkPath, device_id: deviceId }),
  installAab: (aabPath, deviceId) => callBackendAPI('device.install_aab', { aab_path: aabPath, device_id: deviceId }),
  installApks: (apksPath, deviceId) => callBackendAPI('device.install_apks', { apks_path: apksPath, device_id: deviceId }),
  // 设备转换aab为apks
  convertAabToApks: (aabPath, deviceId) => callBackendAPI('device.convert_aab_to_apks', { aab_path: aabPath, device_id: deviceId }),
  // 设备卸载应用
  uninstallApp: (packageName, deviceId) => callBackendAPI('device.uninstall_app', { package_name: packageName, device_id: deviceId }),
  // 设备获取已安装应用
  getInstalledApps: (deviceId, appType) => callBackendAPI('device.get_installed_packages', { device_id: deviceId, app_type: appType }),
  // 设备导出应用APK 到指定目录
  exportApk: (packageName, deviceId, outputDir) => callBackendAPI('device.export_apk', {
    package_name: packageName,
    device_id: deviceId,
    output_dir: outputDir
  }),
  // ========== 应用相关API ==========
  // 后端信息获取
  getBackendInfo: () => callBackendAPI('app.info'),

  // ==================== electron API ====================
  // ========== 路径处理 ==========
  resolvePath: (pathStr) => ipcInvoke('path-resolve', pathStr),
  // ========== 应用相关 ==========
  // 应用（前端）信息获取
  getAppInfo: () => ipcInvoke('get-app-info'),
  // 前端构建信息获取
  getFontendBuildInfo: () => ipcInvoke('get-fontend-build-info'),
  // ========== 剪贴板相关 ==========
  readClipboardText: () => ipcInvoke('read-clipboard-text'),
  writeClipboardText: (text) => ipcInvoke('write-clipboard-text', text),
  // ========== 对话框相关 ==========
  showOpenDialog: (options) => ipcInvoke('show-open-dialog', options),
  showSaveDialog: (options) => ipcInvoke('show-save-dialog', options),
  showMessageBox: (options) => ipcInvoke('show-message-box', options),
  // ========== 文件系统相关 ==========
  // 文件/目录状态获取
  getFileStats: (filePath) => ipcInvoke('get-file-stats', filePath),
  // 文件写入
  writeFile: (filePath, content) => ipcInvoke('write-file', filePath, content),
  // 文件读取
  readFile: (filePath) => ipcInvoke('read-file', filePath),
  // 文件/目录打开
  openPath: (filePath) => ipcInvoke('open-path', filePath),
  // 便捷封装 - 文件/目录选择
  selectFile: (options: DialogOptions = {}) => {
    const props = Array.isArray(options.properties) ? [...options.properties] : []
    if (!props.includes('openFile')) props.push('openFile')
    const opts = { ...options, properties: props }
    return ipcInvoke('show-open-dialog', opts)
  },
  selectDirectory: (options: DialogOptions = {}) => {
    const props = Array.isArray(options.properties) ? [...options.properties] : []
    if (!props.includes('openDirectory')) props.push('openDirectory')
    const opts = { ...options, properties: props }
    return ipcInvoke('show-open-dialog', opts)
  },
  // ========== 日志相关 ==========
  // 日志相关 - 混合调用
  logMessage: (level, message, category) => ipcInvoke('log-message', level, message, category),
  getLogPreview: (lines) => callBackendAPI('log.preview', { lines: lines }),

  // ========== 存储相关 electron-store支持 ==========
  // App 配置
  appConfig: {
    get: (key) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getAppConfig, key),
    set: (key, value) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.setAppConfig, key, value),
    setMany: (updates) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.setManyAppConfig, updates),
    getAll: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getAllAppConfig),
    reset: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.resetAppConfig)
  },
  // 用户配置
  userConfig: {
    get: (key) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getUserConfig, key),
    set: (key, value) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.setUserConfig, key, value),
    getAll: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getAllUserConfig),
    reset: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.resetUserConfig)
  },
  settings: {
    getViewModel: () => ipcRenderer.invoke(IPC_CHANNEL_NAMES.getSettingsViewModel),
    resolvePaths: (paths) => ipcRenderer.invoke(IPC_CHANNEL_NAMES.resolveSettingsPaths, paths)
  },
  // 监听配置变化
  onAppConfigChange: (callback) => {
    const handler = (_event: any, key: any, value: any) => callback(key, value);
    ipcRenderer.on(IPC_CHANNEL_NAMES.appConfigChanged, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.appConfigChanged, handler);
  },
  // 监听配置变化
  onUserConfigChange: (callback) => {
    const handler = (_event: any, key: any, value: any) => callback(key, value);
    ipcRenderer.on(IPC_CHANNEL_NAMES.userConfigChanged, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.userConfigChanged, handler);
  },


  // 缓存相关 - 使用统一后端API
  getCacheInfo: () => callBackendAPI('cache.info'),
  clearCache: (cacheTypes, confirm) => callBackendAPI('cache.clear', { cache_types: cacheTypes, confirm: confirm }),
  clearOutput: () => callBackendAPI('output.clear'),
  clearStorage: (target) => callBackendAPI('storage.clear', { target: target }),

  // 系统相关 - 使用统一后端API
  getSystemInfo: () => callBackendAPI('system.info'),
  getBackendBuildInfo: () => callBackendAPI('build.info'),
    // 磁盘空间获取
  getDiskUsage: () => ipcInvoke('get-disk-usage'),
  
  getStatus: () => callBackendAPI('system.status'),

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
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on(IPC_CHANNEL_NAMES.deviceChange, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.deviceChange, handler);
  },

  onLogUpdate: (callback) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on(IPC_CHANNEL_NAMES.logUpdate, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.logUpdate, handler);
  },

  onLogcatOutput: (callback) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on(IPC_CHANNEL_NAMES.logcatOutput, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.logcatOutput, handler);
  },
  onLogcatStarted: (callback) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on(IPC_CHANNEL_NAMES.logcatStarted, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.logcatStarted, handler);
  },
  onLogcatFinished: (callback) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on(IPC_CHANNEL_NAMES.logcatFinished, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.logcatFinished, handler);
  },
  onLogcatError: (callback) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on(IPC_CHANNEL_NAMES.logcatError, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.logcatError, handler);
  },

  removeLogcatListener: () => {
    ipcRenderer.removeAllListeners(IPC_CHANNEL_NAMES.logcatOutput);
  },
  onStreamEvent: (callback: (data: unknown) => void) => {
    const handler = (_event: any, data: any) => callback(data)
    ipcRenderer.on(IPC_CHANNEL_NAMES.streamEvent, handler)
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.streamEvent, handler)
  },
  onQuitDialog: (callback: () => void) => {
    const handler = () => callback()
    ipcRenderer.on(IPC_CHANNEL_NAMES.showQuitDialog, handler)
    return () => ipcRenderer.removeListener(IPC_CHANNEL_NAMES.showQuitDialog, handler)
  },
  respondQuitDialog: (action: string) => {
    ipcRenderer.invoke(IPC_CHANNEL_NAMES.respondQuitDialog, action)
  }
};

contextBridge.exposeInMainWorld('electronAPI', electronApi);
