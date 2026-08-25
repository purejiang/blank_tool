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
  id: string
  method: M
  params: P
}

// ---- Response ----
// The Python backend (cli/app/api_handler.py) emits exactly ONE envelope:
//   { id, result: { type: 'success' | 'error', payload }, finished, stream_id? }
//   - finished: false → streaming frame (forwarded to renderer via `streamEvent`)
//   - finished: true  → terminal frame (the final `result` is the payload)
// There is no `{ error: ... }` / `{ type: 'event' }` frame in the current backend.
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
  id: string
  result: BackendResult<T>
  finished: boolean
  stream_id?: string
}

export type BackendStdioMessage<T = unknown> = BackendResponse<T>

// ---- Domain Types ----
export interface AppInfo {
  packageName: string
  versionName: string
  installTime: string
}

// ---- Types added for backend API_MAP coverage (T15) ----

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

/** Single plugin entry in plugin.list / plugin.add / plugin.delete */
export interface PluginEntry {
  module: string
  kind: string
  version: string
  loaded: boolean
  error: string
}

// ---- Method-to-Type Map ----
// New entries added for backend API_MAP coverage (T15):
//   All keys from cli/app/handlers/*.py API_MAP dicts.
//   Streaming handlers → result: void.
//   Aliases → same params/result as canonical.
export interface ApiMethodMap {
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
  'tool.version': { params: { tool_name: string }; result: { version: string } }
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

  // --- template_handler.py ---
  'template.save': { params: { name: string; definition: Record<string, unknown> }; result: Record<string, unknown> }
  'template.load': { params: { name: string }; result: Record<string, unknown> }
  'template.list': { params: Record<string, never>; result: Record<string, unknown>[] }
  'template.delete': { params: { name: string }; result: Record<string, unknown> }
  'template.import_path': { params: { path: string }; result: Record<string, unknown> }
  'template.execute': { params: { name: string; inputs?: Record<string, unknown> }; result: Record<string, unknown> }

  // --- env_handler.py ---
  'env.list': { params: Record<string, never>; result: Record<string, unknown> }
  'env.add': { params: { descriptor: Record<string, unknown> }; result: Record<string, unknown> }
  'env.delete': { params: { name: string }; result: Record<string, unknown> }

  // --- tool_handler.py (extended) ---
  'tool.add': { params: { descriptor: Record<string, unknown> }; result: Record<string, unknown> }
  'tool.delete': { params: { name: string }; result: Record<string, unknown> }
  'tool.import_pack': { params: { path: string }; result: Record<string, unknown> }

  // --- history_handler.py ---
  'history.list': { params: { limit?: number; offset?: number }; result: { runs: Record<string, unknown>[] } }
  'history.get': { params: { run_id: string }; result: { run: Record<string, unknown> } }
  'history.delete': { params: { run_id: string }; result: { deleted: string } }
  'history.clear': { params: Record<string, never>; result: { cleared: number } }

  // --- workflow_handler.py ---
  'workflow.execute': { params: { definition: Record<string, unknown>; inputs?: Record<string, unknown> }; result: Record<string, unknown> }
  'workflow.validate': { params: { definition: Record<string, unknown> }; result: Record<string, unknown> }
  'workflow.list_tools': { params: Record<string, never>; result: Record<string, unknown>[] }
  'workflow.list_envs': { params: Record<string, never>; result: Record<string, unknown>[] }

  // --- plugin_handler.py ---
  'plugin.list': { params: Record<string, never>; result: { plugins: PluginEntry[] } }
  'plugin.add': { params: { module: string; path?: string; config?: Record<string, unknown> }; result: { plugins: PluginEntry[] } }
  'plugin.delete': { params: { module: string }; result: { plugins: PluginEntry[] } }
  'plugin.reload': { params: Record<string, never>; result: { ok: boolean } }
}
