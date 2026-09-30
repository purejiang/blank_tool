/**
 * Shared types and small helpers for the workflow editor components
 * (ToolNode, WorkflowNodePalette, WorkflowEditorPage).
 *
 * Tool categories and status values are deliberately local to the renderer:
 * the backend `tool.list` payload (see
 * cli/app/handlers/workflow_handler.py) only carries name/is_valid/
 * version/tool_path/ports/builtin (+ kind since todo 8), so the category
 * is derived from the dotted tool-name prefix.
 */

export type ToolStatus = 'idle' | 'running' | 'success' | 'error' | 'skipped' | 'cancelled'

export type ToolCategory = 'file' | 'net' | 'exec' | 'flow' | 'tool'

/**
 * Provenance of a tool, as emitted by backend `tool.list`
 * (todo 8/16): 'shipped-native' = built-in workflow primitives,
 * 'native' = Tier-1 native plugin, 'descriptor' = Tier-2 descriptor tool.
 * Optional — older backends omit it, in which case callers fall back to
 * the legacy `builtin` boolean.
 */
export type ToolKind = 'shipped-native' | 'native' | 'descriptor'

/** A port's type annotation, as serialized by backend Port.to_dict(). */
export interface PortTypeRef {
  base: string
  subtype: string | null
}

/** A single I/O port, as serialized by backend Port.to_dict(). */
export interface ToolPort {
  name: string
  type: PortTypeRef
  required: boolean
  description: string
  /** Allowed values for select-like ports (T2; backend always emits this). */
  options?: string[]
  /** Whether a select-like port accepts multiple values (T2). */
  multi?: boolean
}

/**
 * One named operation of a descriptor tool (T7), as exposed additively by
 * `tool.list` for descriptor tools that declare operations
 * (cli/app/handlers/workflow_handler.py). Ports are PortJSON-compatible.
 */
export interface ToolOperation {
  name: string
  description?: string
  inputs?: ToolPort[]
  outputs?: ToolPort[]
}

/** PortSet.to_dict() shape: {"inputs": [...], "outputs": [...]}. */
export interface ToolPorts {
  inputs: ToolPort[]
  outputs: ToolPort[]
}

/** Node payload handed to ToolNode via vue-flow's `data` prop. */
export interface ToolNodeData {
  /** Backend tool name, e.g. "file.read". */
  tool: string
  status?: ToolStatus
  ports?: ToolPorts
  [key: string]: unknown
}

/**
 * One upstream node offered by the parameter-binding picker: only nodes that
 * execute BEFORE the edited node can be referenced with `$nodes.<id>.*`
 * (the engine accumulates results as it walks the chain).
 */
export interface UpstreamNodeRef {
  id: string
  /** Display name — the node label, falling back to the tool name. */
  label: string
  tool: string
  /** Output ports of the node's effective operation (or of the tool). */
  outputs: ToolPort[]
  /** Keys of the node's already-bound params (for `.params.<key>` refs). */
  paramKeys: string[]
}

/** One entry of the `tool.list` response `tools` array. */
export interface WorkflowToolInfo {
  name: string
  is_valid: boolean
  version: string
  tool_path: string
  ports?: ToolPorts
  builtin?: boolean
  /** Tool provenance (todo 16); absent on older backends — see ToolKind. */
  kind?: ToolKind
  description?: string
  /** Descriptor tools only (T7): present and non-empty for operation-capable tools. */
  operations?: ToolOperation[]
}

/** MIME type used when dragging a tool from the palette onto the canvas. */
export const TOOL_DRAG_MIME = 'application/vnd.blanktool.workflow-tool'

/**
 * Map a dotted tool name to its display category.
 * "file.read" → file, "net.download" → net, "exec.shell"/"exec.code" → exec,
 * "flow.assert" → flow, anything else (descriptor tools, ...) → tool.
 */
const CATEGORY_BY_PREFIX: Record<string, ToolCategory> = {
  file: 'file',
  dir: 'file',
  text: 'file',
  archive: 'file',
  net: 'net',
  exec: 'exec',
  flow: 'flow',
}

export function categoryOfToolName(name: string): ToolCategory {
  const prefix = name.split('.')[0]
  return CATEGORY_BY_PREFIX[prefix] ?? 'tool'
}

/** Group keys in the workflow node palette (labels are i18n'd by the consumer). */
export type WorkflowGroupKey = ToolCategory

/** Fixed group order in the palette (labels are i18n'd by the consumer). */
export const CATEGORY_ORDER: ToolCategory[] = ['file', 'net', 'exec', 'flow', 'tool']

/** One grouped set of tools in the workflow node palette. */
export interface WorkflowToolGroup {
  key: WorkflowGroupKey
  tools: WorkflowToolInfo[]
}

/**
 * 工具来源判定：`shipped-native` = 内置工作流原语；`native`/`descriptor` = 插件。
 * 老后端不带 `kind`，回落到遗留的 `builtin` 布尔。调色板用它给插件条目标一个
 * 小标记（不再用「内置 / 插件」两个大分组——那会把 10 个内置原语堆成一坨）。
 */
export function isBuiltinTool(tool: WorkflowToolInfo): boolean {
  return tool.kind ? tool.kind === 'shipped-native' : tool.builtin === true
}

/**
 * Group tools for the node palette by DOMAIN (todo 16 + 09-28 改版):
 * `file.*`/`dir.*`/`text.*`/`archive.*` → file, `net.*` → net, `exec.*` → exec,
 * `flow.*` → flow, 其余（插件、第三方工具）→ tool。
 *
 * 每个组内按工具名排序；空组丢弃；组顺序固定为 CATEGORY_ORDER，所以列表每次
 * 渲染都是稳定的。插件不再单独成组（那样 `file.read` 和插件 `file.xxx` 会分家），
 * 而是由条目上的插件标记区分——见 isBuiltinTool。
 */
export function groupWorkflowTools(tools: WorkflowToolInfo[]): WorkflowToolGroup[] {
  const byName = (a: WorkflowToolInfo, b: WorkflowToolInfo) => a.name.localeCompare(b.name)
  const buckets = new Map<ToolCategory, WorkflowToolInfo[]>()
  for (const tool of tools ?? []) {
    if (!tool || typeof tool.name !== 'string' || tool.name.length === 0) continue
    const key = categoryOfToolName(tool.name)
    const bucket = buckets.get(key)
    if (bucket) bucket.push(tool)
    else buckets.set(key, [tool])
  }
  return CATEGORY_ORDER.filter((key) => (buckets.get(key)?.length ?? 0) > 0).map((key) => ({
    key,
    tools: (buckets.get(key) as WorkflowToolInfo[]).slice().sort(byName),
  }))
}

/**
 * 工具类别 → 图标名（对应 assets/icons/sprite.ts 的 symbol）。
 * 渲染方一律用 <AppIcon :name="..." />；这里只放名字，不再内联 SVG 串
 * —— 内联串是历史遗留的第三套图标，描边/端点跟设计契约对不上。
 */
export const CATEGORY_ICONS: Record<ToolCategory, string> = {
  file: 'file',
  net: 'globe',
  exec: 'term',
  flow: 'wf',
  tool: 'tool',
}

/** Human-readable label for a type annotation: "file", or "file/apk" with a subtype. */
export function portTypeLabel(type: PortTypeRef): string {
  return type.subtype ? `${type.base}/${type.subtype}` : type.base
}

/**
 * ToolNode 头部在运行期显示的终态标记 (todo 38)：成功打勾 / 失败打叉。
 * 只放 sprite 名，渲染方用 <AppIcon :name="..." />。
 */
export const STATUS_MARKS: Record<'success' | 'error', string> = {
  success: 'check',
  error: 'x',
}

