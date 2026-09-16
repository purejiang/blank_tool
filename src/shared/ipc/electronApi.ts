import type { ApiMethodMap, BackendApiRequest, JsonObject } from './protocol'

type MethodParams<M extends keyof ApiMethodMap> = ApiMethodMap[M]['params']
type MethodResult<M extends keyof ApiMethodMap> = ApiMethodMap[M]['result']

export interface TypedCallBackendAPI {
  <M extends keyof ApiMethodMap>(method: M, params: MethodParams<M>): Promise<MethodResult<M>>
  <M extends string>(method: M, params?: JsonObject): Promise<unknown>
}

/** See also src/shared/stores/appConfigStore.ts for the broader AppConfigStoreLike used inside renderer services. */
export interface AppConfigApi {
  get: (key?: string) => Promise<unknown>
  set: (key: string, value: unknown) => Promise<unknown>
  setMany: (updates: Record<string, unknown>) => Promise<unknown>
  getAll: () => Promise<Record<string, unknown>>
  reset: () => Promise<unknown>
}

export interface UserConfigApi {
  get: (key?: string) => Promise<unknown>
  set: (key: string, value: unknown) => Promise<unknown>
  getAll: () => Promise<Record<string, unknown>>
  reset: () => Promise<unknown>
}

export interface SettingsViewModel {
  settings: Record<string, unknown>
  displayPaths: { server: string; runtimeExecutable: string }
}

export interface SettingsApi {
  getViewModel: () => Promise<SettingsViewModel>
  resolvePaths: (paths: {
    server?: unknown
    runtimeExecutable?: unknown
  }) => Promise<{ server: string; runtimeExecutable: string }>
}

/**
 * Options bag for the native dialog wrappers. `properties` follows Electron's
 * `OpenDialogOptions.properties`; `selectFile` / `selectDirectory` inject
 * `openFile` / `openDirectory` themselves.
 */
export interface DialogOptions {
  title?: string
  defaultPath?: string
  filters?: { name: string; extensions: string[] }[]
  properties?: string[]
  [key: string]: unknown
}

export interface OpenDialogResult {
  canceled?: boolean
  filePaths?: string[]
}

export interface SaveDialogResult {
  canceled?: boolean
  filePath?: string
}

/** Shape of every `ipcRenderer.on(...)` subscription helper's return value. */
export type Unsubscribe = () => void

// ---------------------------------------------------------------------------
// Group interfaces
//
// Return types on backend-backed methods are intentionally `Promise<any>`:
// `callBackendAPI` silently falls back to its loose overload whenever a
// wrapper's params do not line up with `ApiMethodMap` (several do drift, e.g.
// `apk.getInfo` sends `file_path` while the map declares `apk_path`), so a
// precise declaration here would not be satisfiable. What *is* enforced is the
// method name and its parameter list — which is where the real bugs came from.
// ---------------------------------------------------------------------------

/** APK analysis / decompile / recompile / sign (`apk.*`). */
export interface ApkApiGroup {
  analyzeApk: (apkPath: string) => Promise<any>
  getApkInfo: (filePath: string) => Promise<any>
  decompileApk: (filePath: string, options?: Record<string, unknown>) => Promise<any>
  recompileApk: (projectPath: string, options?: Record<string, unknown>) => Promise<any>
  signApk: (apkPath: string, keystore?: Record<string, unknown>, options?: Record<string, unknown>) => Promise<any>
  getApkProgress: (taskId?: string) => Promise<any>
  cancelApkTask: (taskId?: string) => Promise<any>
}

/** Device / adb operations. */
export interface DeviceApiGroup {
  getAdbDevices: () => Promise<any>
  adbConnect: (address: string) => Promise<any>
  adbDisconnect: (address?: string) => Promise<any>
  rebootDevice: (deviceId: string, mode?: string) => Promise<any>
  executeShell: (deviceId: string, command: string) => Promise<any>
  startLogcat: (deviceId: string) => Promise<any>
  stopLogcat: (processId: string) => Promise<any>
  startDeviceMonitoring: () => Promise<any>
  startRealtimeDeviceMonitoring: () => Promise<any>
  stopRealtimeDeviceMonitoring: () => Promise<any>
  getDeviceInfo: (deviceId: string) => Promise<any>
  installApk: (apkPath: string, deviceId: string, taskId?: string) => Promise<any>
  installAab: (aabPath: string, deviceId: string, taskId?: string) => Promise<any>
  installApks: (apksPath: string, deviceId: string, taskId?: string) => Promise<any>
  convertAabToApks: (aabPath: string, deviceId: string) => Promise<any>
  uninstallApp: (packageName: string, deviceId: string) => Promise<any>
  launchApp: (packageName: string, deviceId: string) => Promise<any>
  clearAppData: (packageName: string, deviceId: string) => Promise<any>
  screenshot: (deviceId: string, filePath?: string) => Promise<any>
  getInstalledApps: (deviceId: string, appType: string) => Promise<any>
  exportApk: (packageName: string, deviceId: string, outputDir?: string) => Promise<any>
  exportDeviceLog: (params: JsonObject) => Promise<any>
}

/** Bundled tool discovery / custom paths (`tool.*`). */
export interface ToolApiGroup {
  getTools: (params?: JsonObject) => Promise<any>
  checkTool: (toolName?: string, refresh?: boolean) => Promise<any>
  setToolSearchMode: (systemSearch: boolean) => Promise<any>
  setToolCustomPath: (toolName: string, path: string) => Promise<any>
  resetToolCustomPath: (toolName: string) => Promise<any>
  getToolCustomPaths: () => Promise<Record<string, string>>
}

/** Storage / cache size reporting and clearing. */
export interface CacheApiGroup {
  getCacheInfo: (force?: boolean) => Promise<any>
  clearOutput: () => Promise<any>
  clearStorage: (target?: string) => Promise<any>
}

export interface SystemApiGroup {
  getSystemInfo: () => Promise<any>
  getBackendBuildInfo: () => Promise<any>
}

export interface DownloadApiGroup {
  downloadFile: (url: string, filename?: string, taskId?: string) => Promise<any>
}

export interface TaskApiGroup {
  readLog: (taskId: string, tailBytes?: number) => Promise<any>
  appendLog: (taskId: string, line: string) => Promise<any>
  deleteOutput: (paths: string[]) => Promise<any>
  deleteTaskDir: (taskId: string) => Promise<any>
  list: () => Promise<any>
  cancelRequest: (requestId: string) => Promise<any>
}

export interface LogsApiGroup {
  logsTail: (lines?: number) => Promise<{ lines: string[]; truncated?: boolean }>
}

export interface AppApiGroup {
  getBackendInfo: () => Promise<any>
}

export interface DialogApiGroup {
  showOpenDialog: (options: DialogOptions) => Promise<any>
  showSaveDialog: (options: DialogOptions) => Promise<any>
  showMessageBox: (options: DialogOptions) => Promise<any>
  /** Adds `openFile` to `properties` when the caller did not pick a mode. */
  selectFile: (options?: DialogOptions) => Promise<any>
  /** Adds `openDirectory` to `properties` when the caller did not pick a mode. */
  selectDirectory: (options?: DialogOptions) => Promise<any>
}

export interface FsApiGroup {
  getFileStats: (filePath: string) => Promise<any>
  writeFile: (filePath: string, content: string) => Promise<any>
  readFile: (filePath: string) => Promise<any>
  readImageAsDataURL: (filePath: string) => Promise<any>
  openPath: (filePath: string, opts?: { reveal?: boolean } | null) => Promise<any>
}

export interface ClipboardApiGroup {
  readClipboardText: () => Promise<string>
  writeClipboardText: (text: string) => Promise<any>
}

export interface WindowApiGroup {
  toggleDevTools: () => Promise<any>
  openDevTools: () => Promise<any>
}

export interface AppInfoApiGroup {
  resolvePath: (pathStr: string) => Promise<string>
  getAppInfo: () => Promise<any>
  /** @deprecated typo kept for wire compatibility — see SystemService.getFontendBuildInfo */
  getFontendBuildInfo: () => Promise<any>
  // Both go through `ipcInvoke`, which is deliberately untyped (`Promise<unknown>`).
  // Typing their payloads here would be a claim the boundary cannot back, so `any`.
  getBackendHealth: () => Promise<any>
  readElectronLogTail: (lines?: number) => Promise<any>
}

export interface RendererLogApiGroup {
  rendererLog: (level: 'error' | 'warn' | 'info', message: string) => Promise<unknown>
}

export interface DeviceEventsApiGroup {
  onDeviceChange: (callback: (devices: unknown) => void) => Unsubscribe
  onLogcatOutput: (callback: (output: unknown) => void) => Unsubscribe
  onLogcatStarted: (callback: (payload: unknown) => void) => Unsubscribe
  onLogcatFinished: (callback: (payload?: unknown) => void) => Unsubscribe
  removeLogcatListener: () => void
  onBackendStderrTail: (callback: (data: { lines: string[]; reason: string }) => void) => Unsubscribe
}

export interface StreamEventsApiGroup {
  onStreamEvent: (callback: (data: unknown) => void) => Unsubscribe
}

export interface UpdateEventsApiGroup {
  checkForUpdates: () => Promise<any>
  downloadUpdate: () => Promise<any>
  quitAndInstall: () => Promise<any>
  onUpdateAvailable: (callback: (data: unknown) => void) => Unsubscribe
  onUpdateNotAvailable: (callback: (data: unknown) => void) => Unsubscribe
  onDownloadProgress: (callback: (data: unknown) => void) => Unsubscribe
  onUpdateDownloaded: (callback: (data: unknown) => void) => Unsubscribe
  onUpdateError: (callback: (data: unknown) => void) => Unsubscribe
}

export interface QuitDialogApiGroup {
  onQuitDialog: (callback: () => void) => Unsubscribe
  respondQuitDialog: (action: string) => void
}

export interface ConfigEventsApiGroup {
  onAppConfigChange: (callback: (key: string, value: unknown) => void) => Unsubscribe
  onUserConfigChange: (callback: (key: string, value: unknown) => void) => Unsubscribe
}

/**
 * The full `window.electronAPI` surface.
 *
 * This is the contract between `src/preload/index.ts` (the only producer) and
 * the renderer (the only consumer). The preload object is declared
 * `satisfies ElectronApi`, so adding a preload method without declaring it
 * here — or mistyping a name anywhere — fails the build instead of silently
 * producing `undefined` at runtime.
 *
 * There is deliberately **no index signature**: an index signature makes every
 * typo compile, which is how the dead `restart` / `openExternal` /
 * `getDiskUsage` channels survived unnoticed.
 */
export interface ElectronApi
  extends ApkApiGroup,
    DeviceApiGroup,
    ToolApiGroup,
    CacheApiGroup,
    SystemApiGroup,
    DownloadApiGroup,
    TaskApiGroup,
    LogsApiGroup,
    AppApiGroup,
    DialogApiGroup,
    FsApiGroup,
    ClipboardApiGroup,
    WindowApiGroup,
    AppInfoApiGroup,
    RendererLogApiGroup,
    DeviceEventsApiGroup,
    StreamEventsApiGroup,
    UpdateEventsApiGroup,
    QuitDialogApiGroup,
    ConfigEventsApiGroup {
  callBackendAPI: TypedCallBackendAPI
  callBackendByRequest: (request: BackendApiRequest) => Promise<unknown>
  appConfig: AppConfigApi
  userConfig: UserConfigApi
  settings: SettingsApi
  showSystemNotification: (title: string, body: string) => Promise<unknown>
}

declare global {
  interface Window {
    electronAPI: ElectronApi
  }
}
