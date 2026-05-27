// ============================================================
// Generic JSON-RPC protocol types for Python backend IPC
// ============================================================

// ---- Primitives ----
export type JsonObject = Record<string, unknown>

// ---- Request ----
export interface BackendApiRequest<
  M extends string = string,
  P extends JsonObject = JsonObject
> {
  id: string | number
  method: M
  params: P
}

// ---- Response ----
export interface BackendSuccessPayload<T = unknown> {
  type: 'success'
  payload: T
}

export interface BackendErrorPayload {
  type: 'error'
  payload: {
    code?: number
    message: string
  }
}

export type BackendResult<T = unknown> =
  | BackendSuccessPayload<T>
  | BackendErrorPayload

export interface BackendResponse<T = unknown> {
  id: string | number
  result: BackendResult<T>
  finished: boolean
  stream_id?: string
}

// ---- Streaming ----
export interface BackendStreamEvent<T = unknown> {
  id: string | number
  result: BackendResult<T>
  stream_id: string
  finished: false
}

// ---- Event message (reserved, unused by current Python backend) ----
export interface BackendEventMessage {
  type: 'event'
  event: string
  data: unknown
}

export type BackendStdioMessage<T = unknown> =
  | BackendResponse<T>
  | BackendEventMessage

// ---- Domain Types ----
export interface AdbDevice {
  serial: string
  state: string
  model: string
  product: string
}

export interface InstallResult {
  success: boolean
  message: string
}

export interface ApkInfo {
  packageName: string
  versionName: string
  versionCode: number
  label: string
}

export interface ToolInfo {
  name: string
  version: string
  path: string
  available: boolean
}

export interface CacheClearResult {
  cleared: string[]
  freedBytes: number
}

export interface AppInfo {
  packageName: string
  versionName: string
  installTime: string
}

// ---- Method-to-Type Map ----
export interface ApiMethodMap {
  'adb.devices': { params: Record<string, never>; result: AdbDevice[] }
  'adb.shell': { params: { command: string; serial?: string }; result: string }
  'adb.install': { params: { apkPath: string; serial?: string }; result: InstallResult }
  'adb.uninstall': { params: { packageName: string; serial?: string }; result: void }
  'apk.parse': { params: { apkPath: string }; result: ApkInfo }
  'apk.extract': { params: { apkPath: string; outputDir: string }; result: void }
  'aab.install': { params: { aabPath: string; serial?: string }; result: InstallResult }
  'tool.list': { params: Record<string, never>; result: ToolInfo[] }
  'cache.clear': { params: { target?: string }; result: CacheClearResult }
  'app.info': { params: { packageName: string; serial?: string }; result: AppInfo }
}
