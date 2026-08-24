export const IPC_CHANNEL_NAMES = {
  // Renderer → Main (invoke)
  callBackendApi: 'call-backend-api',
  getAppConfig: 'get-app-config',
  getAllAppConfig: 'app-config-get-all',
  setAppConfig: 'set-app-config',
  setManyAppConfig: 'set-app-config-many',
  resetAppConfig: 'reset-app-config',
  getUserConfig: 'get-user-config',
  setUserConfig: 'set-user-config',
  getAllUserConfig: 'user-config-get-all',
  resetUserConfig: 'reset-user-config',
  getSettingsViewModel: 'get-settings-view-model',
  resolveSettingsPaths: 'resolve-settings-paths',
  showSystemNotification: 'show-system-notification',
  rendererLog: 'renderer-log',
  showOpenDialog: 'show-open-dialog',
  getFileStats: 'get-file-stats',
  openPath: 'open-path',
  getAppInfo: 'get-app-info',
  getFontendBuildInfo: 'get-fontend-build-info',
  writeClipboardText: 'write-clipboard-text',
  pathResolve: 'path-resolve',
  // Main → Renderer (send/on)
  appConfigChanged: 'app-config-changed',
  userConfigChanged: 'user-config-changed',
  streamEvent: 'stream-event',
  showQuitDialog: 'show-quit-dialog',
  respondQuitDialog: 'respond-quit-dialog',
  // Backend health & log tail (T23)
  getBackendHealth: 'get-backend-health',
  readElectronLogTail: 'read-electron-log-tail',

  // Update — Renderer → Main
  checkForUpdates: 'check-for-updates',
  downloadUpdate: 'download-update',
  quitAndInstall: 'quit-and-install',

  // Update — Main → Renderer
  updateAvailable: 'update-available',
  updateNotAvailable: 'update-not-available',
  downloadProgress: 'download-progress',
  updateDownloaded: 'update-downloaded',
  updateError: 'update-error',
} as const
