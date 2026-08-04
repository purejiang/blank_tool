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

// ---- Types added for backend API_MAP coverage (T15) ----

/** Return type of device_info / device.get_device_info handler */
export interface DeviceInfo {
  deviceId: string
  state: string
  serial: string
  model: string
  brand: string
  manufacturer: string
  device: string
  product: string
  androidVersion: string
  apiLevel: string
  buildId: string
  buildNumber: string
  fingerprint: string
  securityPatch: string
  hardware: string
  architecture: string
  abiList: string
  locale: string
  screenResolution: string
  density: string
  ipAddress: string
  batteryLevel: string
  batteryStatus: string
  ramTotal: string
  totalStorage: string
  availableStorage: string
  systemActivationDate: string
  pageSize: string
}

/** Return type of device.shell handler */
export interface DeviceShellResult {
  output: string
  returncode: number
}

/** Return type of adb.connect / adb.disconnect */
export interface AdbConnectionResult {
  success: boolean
  output: string
  address: string
}

/** Return type of adb.stop_logcat */
export interface AdbStopLogcatResult {
  message?: string
  type?: string
  payload?: { message: string }
}

/** Return type of adb.export_logcat */
export interface AdbExportLogcatResult {
  success: boolean
  file_path: string
}

/** Return type of device.reboot */
export interface DeviceRebootResult {
  device_id: string
  mode: string
}

/** Return type of device.export_apk */
export interface ExportApkResult {
  success: boolean
  exported_files: string[]
  output_dir: string
}

/** Return type of cache.info / cache.get_info */
export interface CacheInfoResult {
  tasks: { path: string; size: number; files: number }
  output: { path: string; size: number; files: number }
  logs: { path: string; size: number; files: number }
  total: { size: number; files: number }
}

/** Return type of system.info */
export interface SystemInfoResult {
  system_info: Record<string, unknown>
}

/** Return type of build.info */
export interface BuildInfoResult {
  python_version: string
  java_version: string
  python_path: string
  java_path: string
}

/** Return type of apk.get_progress / apk.getProgress */
export interface ApkProgressResult {
  task_id: string
  progress: number
}

/** Return type of apk.cancel_task / apk.cancelTask */
export interface CancelTaskResult {
  cancelled: boolean
  task_id: string
  message?: string
}

/** Keystore configuration for signing operations */
export interface KeystoreConfig {
  path?: string
  alias?: string
  storepass?: string
  keypass?: string
  task_id?: string
}

/** Options for apk.decompile */
export interface DecompileOptions {
  task_id?: string
  output_dir?: string
  cwd?: string
}

/** Options for apk.recompile */
export interface RecompileOptions {
  task_id?: string
  output_apk?: string
  cwd?: string
  zipalign?: boolean
  sign?: boolean
  keystore?: KeystoreConfig
  v2?: boolean
}

/** Options for apk.sign */
export interface SignOptions {
  v2?: boolean
  v3?: boolean
  task_id?: string
}

/** Return type of aab.sign */
export interface AabSignResult {
  aab_path: string
  cancelled?: boolean
  task_id?: string
}

/** Return type of device.convert_aab_to_apks */
export interface ConvertAabToApksResult {
  apks_path: string
  cancelled?: boolean
  task_id?: string
}

/** Return type of storage.clear / output.clear / tasks.clear / logs.clear */
export interface ClearResult {
  path?: string
  size?: number
  files?: number
  success?: boolean
  cleared_paths?: string[]
}

/** Single tool detail from tool.get_tools */
export interface ToolDetail {
  name: string
  is_valid: boolean
  version: string
  path: string
  source: string
  status: string
}

/** Return type of task.read_log */
export interface TaskLogResult {
  content: string
  truncated: boolean
  size: number
  log_path: string
  error?: string
}

/** Return type of task.delete_output */
export interface DeleteOutputResult {
  deleted: string[]
  failed: Record<string, unknown>[]
}

/** Return type of task.delete_task_dir */
export interface DeleteTaskDirResult {
  deleted: boolean
  path: string
  error?: string
}

/** Single task entry in task.list response */
export interface TaskListItem {
  task_id: string
  type: 'blocking' | 'streaming'
  started_at: number | null
  cancelled: boolean
  has_process: boolean
}

/** Return type of task.list */
export interface TaskListResult {
  tasks: TaskListItem[]
}

/** Return type of request.cancel */
export interface CancelRequestResult {
  cancelled: boolean
  task_id?: string
  message?: string
}

/** Return type of logs.tail */
export interface LogTailResult {
  lines: string[]
  truncated: boolean
  log_path: string
  error?: string
  process: 'backend' | 'main'
}

// ---- Method-to-Type Map ----
// Existing entries (backward compat — preserved verbatim):
//   'adb.devices', 'adb.shell', 'adb.install', 'adb.uninstall',
//   'apk.parse', 'apk.extract', 'aab.install', 'tool.list',
//   'cache.clear', 'app.info'
//
// New entries added for backend API_MAP coverage (T15):
//   All keys from backend/app/handlers/*.py API_MAP dicts.
//   Streaming handlers → result: void.
//   Aliases → same params/result as canonical.
export interface ApiMethodMap {
  // --- Existing entries (preserved verbatim) ---
  'tool.list': { params: Record<string, never>; result: ToolInfo[] }

  // --- app_handler.py ---
  'system.info': { params: Record<string, never>; result: SystemInfoResult }
  'build.info': { params: Record<string, never>; result: BuildInfoResult }
  'app.info': { params: Record<string, never>; result: AppInfo }

  // --- cache_handler.py ---
  'cache.get_info': { params: Record<string, never>; result: CacheInfoResult }
  'cache.info': { params: Record<string, never>; result: CacheInfoResult }
  'output.clear': { params: Record<string, never>; result: ClearResult }
  'tasks.clear': { params: Record<string, never>; result: ClearResult }
  'logs.clear': { params: Record<string, never>; result: ClearResult }
  'storage.clear': { params: { target?: string }; result: ClearResult }

  // --- tool_handler.py ---
  'tool.version': { params: Record<string, never>; result: { version: string } }
  'tool.get_tools': { params: { tool_name?: string; refresh?: boolean }; result: ToolDetail | Record<string, ToolDetail> }
  'tool.set_search_mode': { params: { system_search?: boolean }; result: { system_search: boolean } }
  'tool.set_custom_path': { params: { tool_name: string; path: string }; result: Record<string, unknown> }
  'tool.reset_custom_path': { params: { tool_name: string }; result: Record<string, unknown> }
  'tool.get_custom_paths': { params: Record<string, never>; result: Record<string, string> }

  // --- task_handler.py ---
  'task.delete_output': { params: { paths: string[] }; result: DeleteOutputResult }
  'task.read_log': { params: { task_id: string; tail_bytes?: number }; result: TaskLogResult }
  'task.append_log': { params: { task_id: string; line: string }; result: { written: boolean } }
  'task.delete_task_dir': { params: { task_id: string }; result: DeleteTaskDirResult }
  'task.list': { params: Record<string, never>; result: TaskListResult }
  'request.cancel': { params: { request_id?: string; task_id?: string }; result: CancelRequestResult }

  // --- log_handler.py ---
  'logs.tail': { params: { lines?: number }; result: LogTailResult }

  // --- plugin_handler.py ---
  'plugin.list': { params: Record<string, never>; result: Record<string, unknown>[] }
  'plugin.run': { params: { name: string; params?: Record<string, unknown> }; result: Record<string, unknown> }
  'plugin.reload': { params: Record<string, never>; result: Record<string, unknown>[] }

  // --- template_handler.py ---
  'template.save': { params: { name: string; definition: Record<string, unknown> }; result: Record<string, unknown> }
  'template.load': { params: { name: string }; result: Record<string, unknown> }
  'template.list': { params: Record<string, never>; result: Record<string, unknown>[] }
  'template.delete': { params: { name: string }; result: Record<string, unknown> }
  'template.execute': { params: { name: string; inputs?: Record<string, unknown> }; result: Record<string, unknown> }

  // --- env_handler.py ---
  'env.list': { params: Record<string, never>; result: Record<string, unknown> }
  'env.add': { params: { descriptor: Record<string, unknown> }; result: Record<string, unknown> }
  'env.delete': { params: { name: string }; result: Record<string, unknown> }
  'env.set_custom': { params: { name: string; overrides: Record<string, unknown> }; result: Record<string, unknown> }
  'env.reset_custom': { params: { name: string }; result: Record<string, unknown> }

  // --- tool_handler.py (extended) ---
  'tool.add': { params: { descriptor: Record<string, unknown> }; result: Record<string, unknown> }
  'tool.delete': { params: { name: string }; result: Record<string, unknown> }

  // --- workflow_handler.py ---
  'workflow.execute': { params: { definition: Record<string, unknown>; inputs?: Record<string, unknown> }; result: Record<string, unknown> }
  'workflow.validate': { params: { definition: Record<string, unknown> }; result: Record<string, unknown> }
  'workflow.list_tools': { params: Record<string, never>; result: Record<string, unknown>[] }
  'workflow.list_envs': { params: Record<string, never>; result: Record<string, unknown>[] }
}
