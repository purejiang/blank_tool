export interface IpcChannelDefinition {
  name: string
  direction: 'renderer-to-main' | 'main-to-renderer'
  payload?: string
}

export const IPC_CHANNELS = {
  // Renderer → Main (invoke)
  callBackendApi: { name: 'call-backend-api', direction: 'renderer-to-main', payload: 'BackendApiRequest' },
  getAppConfig: { name: 'get-app-config', direction: 'renderer-to-main', payload: 'string | undefined' },
  getAllAppConfig: { name: 'app-config-getAll', direction: 'renderer-to-main' },
  setAppConfig: { name: 'set-app-config', direction: 'renderer-to-main', payload: '{ key: string, value: unknown }' },
  setManyAppConfig: { name: 'set-app-config-batch', direction: 'renderer-to-main', payload: 'Record<string, unknown>' },
  resetAppConfig: { name: 'reset-app-config', direction: 'renderer-to-main' },
  getUserConfig: { name: 'get-user-config', direction: 'renderer-to-main', payload: 'string | undefined' },
  setUserConfig: { name: 'set-user-config', direction: 'renderer-to-main', payload: '{ key: string, value: unknown }' },
  getAllUserConfig: { name: 'user-config-getAll', direction: 'renderer-to-main' },
  resetUserConfig: { name: 'reset-user-config', direction: 'renderer-to-main' },
  getSettingsViewModel: { name: 'get-settings-view-model', direction: 'renderer-to-main' },
  resolveSettingsPaths: { name: 'resolve-settings-paths', direction: 'renderer-to-main', payload: '{ runtime?, server? }' },
  showSystemNotification: { name: 'show-system-notification', direction: 'renderer-to-main', payload: '{ title: string, body: string }' },
  rendererLog: { name: 'renderer-log', direction: 'renderer-to-main', payload: 'level: "error" | "warn", message: string' },
  showOpenDialog: { name: 'show-open-dialog', direction: 'renderer-to-main', payload: 'OpenDialogOptions' },
  showSaveDialog: { name: 'show-save-dialog', direction: 'renderer-to-main', payload: 'SaveDialogOptions' },
  showMessagebox: { name: 'show-message-box', direction: 'renderer-to-main', payload: 'MessageBoxOptions' },
  getFileStats: { name: 'get-file-stats', direction: 'renderer-to-main', payload: 'string' },
  writeFile: { name: 'write-file', direction: 'renderer-to-main', payload: '{ path: string, content: string }' },
  readFile: { name: 'read-file', direction: 'renderer-to-main', payload: 'string' },
  readImageAsDataURL: { name: 'read-image-as-dataurl', direction: 'renderer-to-main', payload: 'string' },
  openPath: { name: 'open-path', direction: 'renderer-to-main', payload: 'string' },
  openDevTools: { name: 'open-dev-tools', direction: 'renderer-to-main' },
  toggleDevTools: { name: 'toggle-dev-tools', direction: 'renderer-to-main' },
  getAppInfo: { name: 'get-app-info', direction: 'renderer-to-main' },
  getFontendBuildInfo: { name: 'get-fontend-build-info', direction: 'renderer-to-main' },
  readClipboardText: { name: 'read-clipboard-text', direction: 'renderer-to-main' },
  writeClipboardText: { name: 'write-clipboard-text', direction: 'renderer-to-main', payload: 'string' },
  pathResolve: { name: 'path-resolve', direction: 'renderer-to-main', payload: 'string' },
  getDiskUsage: { name: 'get-disk-usage', direction: 'renderer-to-main' },
  openExternal: { name: 'open-external', direction: 'renderer-to-main', payload: 'string' },
  restart: { name: 'restart', direction: 'renderer-to-main' },
  // Main → Renderer (send/on)
  appConfigChanged: { name: 'app-config-changed', direction: 'main-to-renderer', payload: '{ key: string, value: unknown }' },
  userConfigChanged: { name: 'user-config-changed', direction: 'main-to-renderer', payload: '{ key: string, value: unknown }' },
  deviceChange: { name: 'device-change', direction: 'main-to-renderer', payload: 'AdbDevice[]' },
  logcatOutput: { name: 'logcat-output', direction: 'main-to-renderer', payload: 'string' },
  logcatStarted: { name: 'logcat-started', direction: 'main-to-renderer' },
  logcatFinished: { name: 'logcat-finished', direction: 'main-to-renderer' },
  streamEvent: { name: 'stream-event', direction: 'main-to-renderer', payload: 'BackendStreamEvent' },
  showQuitDialog: { name: 'show-quit-dialog', direction: 'main-to-renderer' },
  respondQuitDialog: { name: 'respond-quit-dialog', direction: 'renderer-to-main', payload: 'string' },
  // Backend health & stderr tail (T23)
  backendStderrTail: { name: 'backend-stderr-tail', direction: 'main-to-renderer', payload: '{ lines: string[], reason: "crash" | "traceback" }' },
  getBackendHealth: { name: 'get-backend-health', direction: 'renderer-to-main' },
  readElectronLogTail: { name: 'read-electron-log-tail', direction: 'renderer-to-main', payload: '{ lines: number }' },

  // Update — Renderer → Main
  checkForUpdates: { name: 'check-for-updates', direction: 'renderer-to-main' },
  downloadUpdate: { name: 'download-update', direction: 'renderer-to-main' },
  quitAndInstall: { name: 'quit-and-install', direction: 'renderer-to-main' },

  // Update — Main → Renderer
  updateAvailable: { name: 'update-available', direction: 'main-to-renderer', payload: '{ version: string, releaseNotes: string, releaseDate: string }' },
  updateNotAvailable: { name: 'update-not-available', direction: 'main-to-renderer', payload: '{ version: string }' },
  downloadProgress: { name: 'download-progress', direction: 'main-to-renderer', payload: '{ percent: number, bytesPerSecond: number, transferred: number, total: number }' },
  updateDownloaded: { name: 'update-downloaded', direction: 'main-to-renderer', payload: '{ version: string }' },
  updateError: { name: 'update-error', direction: 'main-to-renderer', payload: '{ message: string }' },
} as const satisfies Record<string, IpcChannelDefinition>

// Flat accessor for backward compat during migration
export const IPC_CHANNEL_NAMES: Record<keyof typeof IPC_CHANNELS, string> = Object.fromEntries(
  Object.entries(IPC_CHANNELS).map(([key, def]) => [key, def.name])
) as Record<keyof typeof IPC_CHANNELS, string>
