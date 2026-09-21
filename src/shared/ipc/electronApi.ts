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
  displayPaths: { runtime: string; server: string }
}

export interface SettingsApi {
  getViewModel: () => Promise<SettingsViewModel>
  resolvePaths: (paths: { runtime?: unknown; server?: unknown }) => Promise<{ runtime: string; server: string }>
}

/** Options accepted by the open/save dialogs (passthrough to Electron). */
export interface DialogOptions {
  title?: string
  defaultPath?: string
  filters?: { name: string; extensions: string[] }[]
  properties?: string[]
  [key: string]: unknown
}

export interface OpenDialogResult {
  canceled: boolean
  filePaths: string[]
}

export interface SaveDialogResult {
  canceled: boolean
  filePath?: string
}

export interface FileStatsResult {
  success: boolean
  size?: number
  isFile?: boolean
  isDirectory?: boolean
  mtime?: Date
  ctime?: Date
  error?: string
}

export interface PathActionResult {
  success: boolean
  error?: string
}

export interface ReadTextFileResult {
  success: boolean
  content?: string
  error?: string
}

export interface WriteTextFileResult {
  success: boolean
  error?: string
}

export interface BackendHealthResult {
  healthy: boolean
  /** Always null — the main-process probe only checks process liveness (see 08 #16). */
  uptime_s: number | null
  pending_requests?: unknown
}

export interface ElectronLogTailResult {
  lines: string[]
  truncated: boolean
  log_path: string
  process: 'backend' | 'main'
  error?: string
}

export interface ElectronApi {
  callBackendAPI: TypedCallBackendAPI
  callBackendByRequest: (request: BackendApiRequest) => Promise<unknown>
  appConfig: AppConfigApi
  userConfig: UserConfigApi
  settings: SettingsApi
  // --- dialogs / filesystem (called out explicitly by 09 WP1) ---
  selectFile: (options?: DialogOptions) => Promise<OpenDialogResult>
  selectDirectory: (options?: DialogOptions) => Promise<OpenDialogResult>
  showSave: (options?: DialogOptions) => Promise<SaveDialogResult>
  readTextFile: (path: string, maxBytes?: number) => Promise<ReadTextFileResult>
  writeTextFile: (path: string, content: string) => Promise<WriteTextFileResult>
  getFileStats: (path: string) => Promise<FileStatsResult>
  openPath: (path: string) => Promise<PathActionResult>
  resolvePath: (path: string) => Promise<string>
  writeClipboardText: (text: string) => Promise<boolean>
  // --- app / diagnostics ---
  getAppInfo: () => Promise<AppInfoResult>
  getFontendBuildInfo: () => Promise<FrontendBuildInfoResult>
  getBackendHealth: () => Promise<BackendHealthResult>
  readElectronLogTail: (lines?: number) => Promise<ElectronLogTailResult>
  rendererLog: (level: 'error' | 'warn' | 'info', message: string) => Promise<unknown>
  showSystemNotification: (title: string, body: string) => Promise<boolean>
  // --- streaming events ---
  onStreamEvent: (callback: (data: unknown) => void) => () => void
  onQuitDialog?: (callback: () => void) => () => void
  respondQuitDialog?: (action: string) => void
  // --- backend tool helpers (thin wrappers over callBackendAPI) ---
  getTools: (params?: JsonObject) => Promise<unknown>
  checkTool: (toolName?: string, refresh?: boolean) => Promise<unknown>
  setToolSearchMode: (systemSearch: boolean) => Promise<unknown>
  setToolCustomPath?: (toolName: string, path: string) => Promise<unknown>
  resetToolCustomPath?: (toolName: string) => Promise<unknown>
  getToolCustomPaths?: () => Promise<Record<string, string>>
  logsTail?: (lines?: number) => Promise<{ lines: string[]; truncated?: boolean }>
  // Index signature is load-bearing: the preload exposes additional IPC
  // wrappers (cache/system/update helpers, ...) that are not yet enumerated
  // here. Keep it until those are typed.
  [key: string]: unknown
}

export interface AppInfoResult {
  version: string
}

export interface FrontendBuildInfoResult {
  appName: string
  appVersion: string
  appDescription: string
  nodeVersion: string
  chromeVersion: string
  electronVersion: string
}

declare global {
  interface Window {
    electronAPI: ElectronApi
  }
}
