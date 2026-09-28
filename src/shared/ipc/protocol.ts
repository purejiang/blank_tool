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
// Shapes below mirror the ACTUAL payloads returned by cli/app/handlers/*.py.
// WP0 of docs/09 aligned them with the code (they previously described
// non-existent fields / wrong envelopes and made list pages read `undefined`).

/** Return type of app.info (main-process handler) — it only reports the version. */
export interface AppInfo {
  version: string
}

/** Return type of the main-process `health` probe... see also HealthResult. */
export interface HealthResult {
  status: string
  uptime_s: number
}

/** One directory block inside cache.info. */
export interface DirInfo {
  path: string | null
  size: number
  files: number
}

/** Return type of cache.info / cache.get_info */
export interface CacheInfoResult {
  tasks: DirInfo
  output: DirInfo
  logs: DirInfo
  total: { size: number; files: number }
  /** Managed subdirectories of output/ — excluded from output.clear by default (WP4). */
  managed: {
    templates: DirInfo
    /** Saved task definitions (workflow + inputs), added with the task entity. */
    task_defs: DirInfo
    history: DirInfo
    runs: DirInfo
    registry: DirInfo
  }
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

/** Where a tool's binary was found (backend `_source_for`). */
export type ToolSource = 'system' | 'none'

/** Whether a tool resolved to a usable binary. */
export type ToolStatus = 'available' | 'unavailable'

/** One value of the `tool.get_tools` full-listing map (keyed by tool name). */
export interface ToolStatusEntry {
  is_valid: boolean
  version: string
  path: string
  source: ToolSource
  status: ToolStatus
}

/** `tool.get_tools { tool_name }` — a single tool, including its name. */
export interface ToolDetail extends ToolStatusEntry {
  name: string
  /**
   * Descriptor-declared environment dependencies; present only for descriptor
   * tools (WP3 #14). The full listing stays `Record<string, ToolStatusEntry>`.
   */
  env_deps?: string[]
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

/**
 * Single entry in the `run.list` response — an IN-FLIGHT run registered with
 * the backend TaskManager (history only stores terminal runs).
 *
 * Renamed from `TaskListItem` when `task.*` was given to the task-definition
 * entity (`task.list` / `get` / `save` / `delete` / `execute`); this listing
 * is keyed by a RUN identity, not by a task definition name.
 */
export interface RunListItem {
  run_id: string
  task_id: string
  cancelled: boolean
  started_at: number | null
  has_process: boolean
}

/** Return type of run.list */
export interface RunListResult {
  runs: RunListItem[]
}

/**
 * A saved task definition — a workflow name plus the input values to run it
 * with (backend `app.task.store`).  What the task pages and the headless
 * `run --task <name>` both operate on.
 */
export interface TaskDefinition {
  name: string
  /** Name of the saved template this task runs (never an embedded definition). */
  workflow: string
  /** Stored input values, exactly as submitted (validated at run time). */
  inputs: Record<string, unknown>
  /** Optional working directory; `''` means "the workflow's own directory". */
  work_dir: string
  description: string
  created_at: string | null
  updated_at: string | null
}

/**
 * One row of the `task.list` response.
 *
 * `workflow_exists: false` marks a task whose bound workflow was renamed or
 * deleted: the task is kept, cannot run, and must be re-pointed.
 */
export interface TaskDefinitionSummary extends TaskDefinition {
  workflow_exists: boolean
  input_count: number
  has_work_dir: boolean
}

/** Return type of task.list */
export interface TaskDefinitionListResult {
  tasks: TaskDefinitionSummary[]
}

/** Return type of task.get */
export interface TaskGetResult {
  task: TaskDefinition
  workflow_exists: boolean
}

/** Return type of task.save */
export interface TaskSaveResult {
  saved: boolean
  name: string
}

/** Return type of task.delete */
export interface TaskDeleteResult {
  deleted: boolean
  name: string
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

/**
 * Single plugin entry in plugin.list / plugin.add / plugin.delete.
 *
 * After WP3 (#8) the loader records per-plugin failures, so `loaded`/`error`
 * carry real information and `source` says which manifest contributed the
 * entry (`shipped` = shipped-native, `user` = user manifest).
 */
export interface PluginEntry {
  module: string
  kind: string
  version: string
  loaded: boolean
  error: string
  source?: 'shipped' | 'user'
}

/** Return type of plugin.list / plugin.add / plugin.delete */
export interface PluginListResult {
  plugins: PluginEntry[]
}

// ---- Workflow / tool / port shapes (workflow.list_tools) ----

/** One port as serialized by the backend `Port.to_dict()`. */
export interface PortJson {
  name: string
  type: { base: string; subtype?: string }
  required: boolean
  description?: string
  options?: string[]
  multi?: boolean
  direction?: 'input' | 'output'
}

/** A tool's declared port set. */
export interface PortsJson {
  inputs: PortJson[]
  outputs: PortJson[]
}

/** One operation of a descriptor tool (T7 operation model). */
export interface OperationJson {
  name: string
  description: string
  inputs: PortJson[]
  outputs: PortJson[]
}

/** One entry of the `workflow.list_tools` response `tools` array. */
export interface ToolEntry {
  name: string
  kind: 'shipped-native' | 'native' | 'descriptor'
  is_valid: boolean
  version: string
  tool_path: string
  /** Legacy boolean kept for the palette's grouping until it migrates to `kind`. */
  builtin?: boolean
  description?: string
  ports?: PortsJson
  operations?: OperationJson[]
  /** Environment dependencies declared by a descriptor (added by WP3, #14). */
  env_deps?: string[]
}

/** Return type of workflow.list_tools */
export interface ToolListResult {
  tools: ToolEntry[]
}

// ---- Environments (env.list / workflow.list_envs) ----

export type EnvType = 'jre' | 'python' | 'node' | 'custom'

/**
 * One resolved environment. WP3 (#3) added `display_name` / `type` /
 * `env_var_override` / `path_override` / `source`; older payloads simply omit
 * them, hence the optional markers.
 */
export interface EnvEntry {
  name: string
  display_name?: string
  type?: EnvType
  is_valid: boolean
  binary_path: string
  version: string
  root_path?: string
  env_var_override?: string
  /** Path override set via env.set_path (WP3, #13). */
  path_override?: string
  source?: 'bundled' | 'overlay'
}

/** Return type of env.list / workflow.list_envs */
export interface EnvListResult {
  environments: EnvEntry[]
}

// ---- Templates ----

/** One entry of the `template.list` response. */
export interface TemplateInfo {
  name: string
  description: string
  created_at: string | null
  updated_at: string | null
  tags: string[]
  node_count: number
}

/** Return type of template.list */
export interface TemplateListResult {
  templates: TemplateInfo[]
}

/**
 * Return type of template.load. WP5 (#12) extended the response with the
 * wrapper metadata that `FileTemplateStore.load()` used to discard; a raw
 * (bare-definition) template file yields the defaults.
 */
export interface TemplateLoadResult {
  definition: Record<string, unknown>
  description: string
  tags: string[]
  created_at: string | null
  updated_at: string | null
}

/** One per-file entry of the template.import_path report. */
export interface TemplateImportEntry {
  file: string
  status: string
  name?: string
  reason?: string
  renamed_from?: string
}

/** Return type of template.import_path (M2 import report). */
export interface TemplateImportResult {
  ok: boolean
  imported: number
  failed: number
  results: TemplateImportEntry[]
}

/** One per-descriptor entry of the tool.import_pack report. */
export interface ToolImportEntry {
  name: string
  status: string
  reason?: string
  warnings?: string[]
}

/**
 * Return type of tool.import_pack (M2 import report). Invalid input
 * (missing directory / no *.json descriptors) now raises on the backend
 * (#7), so a returned report always describes a two-phase import outcome.
 */
export interface ToolImportReport {
  ok: boolean
  imported: number
  updated: number
  failed: number
  results: ToolImportEntry[]
}

// ---- Run history ----

/** Terminal status recorded for a run (`succeeded` | `failed` | `cancelled`). */
export type RunStatus = 'succeeded' | 'failed' | 'cancelled'

/**
 * One run summary (`history.list`). WP2 (#11) added `status`, `cancelled` and
 * `run_dir` to the 9-key projection; `node_results` / `inputs` stay excluded.
 */
export interface RunSummary {
  run_id: string
  task_id: string
  /**
   * Saved task definition this run belongs to (`task.execute`); `null` for
   * template / inline / CLI runs. Records written before the task entity was
   * added project it as `null` rather than absent.
   */
  task_name?: string | null
  workflow_name: string
  source: string
  started_at: string | null
  ended_at: string | null
  duration_ms: number
  success: boolean
  error: string | null
  /**
   * `status` / `cancelled` / `run_dir` are projected with `record.get(...)`,
   * so a record written before WP2 carries them as `null` rather than absent
   * — consumers must tolerate both.
   */
  status?: RunStatus | null
  cancelled?: boolean | null
  /** Per-run artifact directory (`<output_dir>/runs/<slug>`), added by WP2 (#4). */
  run_dir?: string | null
}

/** One node inside a run record (keyed by run-root-relative node path). */
export interface NodeResultEntry {
  status: string
  duration_ms?: number
  attempts?: number
  error?: string | null
  outputs?: Record<string, unknown>
}

/** Full run record (`history.get`). */
export interface RunRecord extends RunSummary {
  inputs: Record<string, unknown>
  node_results: Record<string, NodeResultEntry>
  /**
   * The run identity the executor used for cancellation / `$rundir` (the IPC
   * request id, or the CLI run id). `run_id` above is the history *file* id
   * (uuid4 hex) and the two are deliberately different values (WP2, #4).
   */
  exec_run_id?: string
}

/** Return type of history.list */
export interface HistoryListResult {
  runs: RunSummary[]
}

/** Return type of history.get */
export interface HistoryGetResult {
  run: RunRecord
}

/** Return type of history.get_config / history.set_config (WP4, #5). */
export interface HistoryConfigResult {
  enabled: boolean
  max_runs: number
  max_bytes: number
  config_path: string
}

// ---- Workflow execution / validation ----

/**
 * The wire shape returned by workflow.execute and template.execute (and
 * mirrored into the history record). WP2 added `run_dir`.
 */
export interface WorkflowRunResult {
  success: boolean
  status: string
  cancelled: boolean
  outputs: Record<string, unknown>
  node_results: Record<string, NodeResultEntry>
  error: string | null
  run_dir: string
}

/** One finding of workflow.validate. */
export interface ValidationFinding {
  node_id: string
  field: string
  message: string
  severity: string
}

/** Return type of workflow.validate */
export interface WorkflowValidateResult {
  errors: ValidationFinding[]
}

// ---- Method-to-Type Map ----
// Every key of cli/app/handlers/*.py API_MAP must appear here
// (tests/shared-contracts.test.mjs asserts 100% coverage); TS-only keys are
// reported by that test as informational warnings only.
export interface ApiMethodMap {
  // --- app_handler.py ---
  'system.info': { params: Record<string, never>; result: SystemInfoResult }
  'build.info': { params: Record<string, never>; result: BuildInfoResult }
  'app.info': { params: Record<string, never>; result: AppInfo }
  // Backend health (injected by cli/main.py, not in any handler API_MAP):
  // the only source of a real uptime. TS-only key — the main-process
  // `get-backend-health` probe stays a process-liveness check with uptime_s: null.
  'health': { params: Record<string, never>; result: HealthResult }

  // --- cache_handler.py ---
  'cache.get_info': { params: Record<string, never>; result: CacheInfoResult }
  'cache.info': { params: Record<string, never>; result: CacheInfoResult }
  'output.clear': { params: Record<string, never>; result: ClearResult }
  'tasks.clear': { params: Record<string, never>; result: ClearResult }
  'logs.clear': { params: Record<string, never>; result: ClearResult }
  'storage.clear': { params: { target?: 'all' | 'tasks' | 'output' | 'logs' | 'templates' | 'task_defs' | 'history' | 'runs' | 'registry'; include_managed?: boolean }; result: ClearResult }

  // --- tool_handler.py ---
  'tool.version': { params: { tool_name: string }; result: { version: string } }
  'tool.get_tools': { params: { tool_name?: string; refresh?: boolean }; result: ToolDetail | Record<string, ToolStatusEntry> }
  'tool.set_search_mode': { params: { system_search?: boolean }; result: { system_search: boolean } }
  'tool.set_custom_path': { params: { tool_name: string; path: string }; result: Record<string, unknown> }
  'tool.reset_custom_path': { params: { tool_name: string }; result: Record<string, unknown> }
  'tool.get_custom_paths': { params: Record<string, never>; result: Record<string, string> }
  'tool.add': { params: { descriptor: Record<string, unknown> }; result: Record<string, unknown> }
  'tool.delete': { params: { name: string }; result: Record<string, unknown> }
  'tool.import_pack': { params: { path: string }; result: ToolImportReport }

  // --- task_handler.py (RUN-scoped: task_id is a run identity) ---
  'task.delete_output': { params: { paths: string[] }; result: DeleteOutputResult }
  'task.read_log': { params: { task_id: string; tail_bytes?: number }; result: TaskLogResult }
  'task.append_log': { params: { task_id: string; line: string }; result: { written: boolean } }
  'task.delete_task_dir': { params: { task_id: string }; result: DeleteTaskDirResult }
  'run.list': { params: Record<string, never>; result: RunListResult }
  'request.cancel': { params: { request_id?: string; task_id?: string }; result: CancelRequestResult }

  // --- task_def_handler.py (task DEFINITIONS: workflow + saved inputs) ---
  'task.list': { params: Record<string, never>; result: TaskDefinitionListResult }
  'task.get': { params: { name: string }; result: TaskGetResult }
  'task.save': { params: { name: string; workflow: string; inputs?: Record<string, unknown>; work_dir?: string; description?: string }; result: TaskSaveResult }
  'task.delete': { params: { name: string }; result: TaskDeleteResult }
  'task.execute': { params: { name: string; inputs?: Record<string, unknown>; task_id?: string; work_dir?: string }; result: WorkflowRunResult }

  // --- log_handler.py ---
  'logs.tail': { params: { lines?: number }; result: LogTailResult }

  // --- template_handler.py ---
  'template.save': { params: { name: string; definition: Record<string, unknown>; description?: string; tags?: string[] }; result: { saved: boolean; name: string } }
  'template.load': { params: { name: string }; result: TemplateLoadResult }
  'template.list': { params: Record<string, never>; result: TemplateListResult }
  'template.delete': { params: { name: string }; result: { deleted: boolean; name: string } }
  'template.import_path': { params: { path: string }; result: TemplateImportResult }
  'template.execute': { params: { name: string; inputs?: Record<string, unknown>; task_id?: string; work_dir?: string }; result: WorkflowRunResult }

  // --- env_handler.py ---
  'env.list': { params: Record<string, never>; result: EnvListResult }
  'env.add': { params: { descriptor: Record<string, unknown> }; result: Record<string, unknown> }
  'env.delete': { params: { name: string }; result: Record<string, unknown> }
  'env.set_path': { params: { name: string; path: string }; result: EnvEntry }
  'env.reset_path': { params: { name: string }; result: EnvEntry }

  // --- history_handler.py ---
  'history.list': { params: { limit?: number; offset?: number }; result: HistoryListResult }
  'history.get': { params: { run_id: string }; result: HistoryGetResult }
  'history.delete': { params: { run_id: string }; result: { deleted: string } }
  'history.clear': { params: Record<string, never>; result: { cleared: number } }
  'history.get_config': { params: Record<string, never>; result: HistoryConfigResult }
  'history.set_config': { params: { enabled?: boolean; max_runs?: number; max_bytes?: number }; result: HistoryConfigResult }

  // --- workflow_handler.py ---
  'workflow.execute': { params: { definition?: Record<string, unknown>; path?: string; inputs?: Record<string, unknown>; task_id?: string; work_dir?: string }; result: WorkflowRunResult }
  'workflow.validate': { params: { definition: Record<string, unknown> }; result: WorkflowValidateResult }
  'workflow.list_tools': { params: Record<string, never>; result: ToolListResult }
  'workflow.list_envs': { params: Record<string, never>; result: EnvListResult }

  // --- plugin_handler.py ---
  'plugin.list': { params: Record<string, never>; result: PluginListResult }
  'plugin.add': { params: { module: string; path?: string; config?: Record<string, unknown> }; result: PluginListResult }
  'plugin.delete': { params: { module: string }; result: PluginListResult }
  'plugin.reload': { params: Record<string, never>; result: { ok: boolean } }
}

/**
 * Extract a task id from a backend request params object.
 *
 * Mirrors the extraction order used by the Python backend
 * (`cli/app/api_handler.py`) so the two sides stay in sync: a top-level
 * `task_id`, then `options.task_id`, then `keystore.task_id`.
 */
export function extractTaskId(params: unknown): string {
  const p = (params || {}) as Record<string, unknown>;
  const options = (p.options || {}) as Record<string, unknown>;
  const keystore = (p.keystore || {}) as Record<string, unknown>;
  return String(p.task_id || options.task_id || keystore.task_id || '');
}
