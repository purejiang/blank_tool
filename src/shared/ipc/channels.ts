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

  // Main → Renderer (send/on)
  appConfigChanged: { name: 'app-config-changed', direction: 'main-to-renderer', payload: '{ key: string, value: unknown }' },
  userConfigChanged: { name: 'user-config-changed', direction: 'main-to-renderer', payload: '{ key: string, value: unknown }' },
  deviceChange: { name: 'device-change', direction: 'main-to-renderer', payload: 'AdbDevice[]' },
  logUpdate: { name: 'log-update', direction: 'main-to-renderer', payload: 'string' },
  logcatOutput: { name: 'logcat-output', direction: 'main-to-renderer', payload: 'string' },
  logcatStarted: { name: 'logcat-started', direction: 'main-to-renderer' },
  logcatFinished: { name: 'logcat-finished', direction: 'main-to-renderer' },
  logcatError: { name: 'logcat-error', direction: 'main-to-renderer', payload: 'string' },
  streamEvent: { name: 'stream-event', direction: 'main-to-renderer', payload: 'BackendStreamEvent' },
  showQuitDialog: { name: 'show-quit-dialog', direction: 'main-to-renderer' },
  respondQuitDialog: { name: 'respond-quit-dialog', direction: 'renderer-to-main', payload: 'string' },

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
