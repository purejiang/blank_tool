/**
 * Shared types and small helpers for the workflow editor components
 * (ToolNode, WorkflowNodePalette, WorkflowEditorPage).
 *
 * Tool categories and status values are deliberately local to the renderer:
 * the backend `workflow.list_tools` payload (see
 * cli/app/handlers/workflow_handler.py) only carries name/is_valid/
 * version/tool_path/ports/builtin (+ kind since todo 8), so the category
 * is derived from the dotted tool-name prefix.
 */

export type ToolStatus = 'idle' | 'running' | 'success' | 'error' | 'skipped' | 'cancelled'

export type ToolCategory = 'file' | 'net' | 'exec' | 'flow' | 'tool'

/**
 * Provenance of a tool, as emitted by backend `workflow.list_tools`
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
 * `workflow.list_tools` for descriptor tools that declare operations
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

/** One entry of the `workflow.list_tools` response `tools` array. */
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
export type WorkflowGroupKey = 'builtin' | 'plugins'

/** One grouped set of tools in the workflow node palette. */
export interface WorkflowToolGroup {
  key: WorkflowGroupKey
  tools: WorkflowToolInfo[]
}

/**
 * Group tools for the node palette (todo 16): `shipped-native` goes to the
 * `builtin` group, `native`/`descriptor` to `plugins`. When `kind` is absent
 * (older backends), fall back to the legacy `builtin` boolean
 * (`builtin === true` → builtin, else plugins). Each group is sorted by
 * tool name; empty groups are dropped. Ordering is stable: builtin first.
 * The group `key` is translated to a display label by the palette via i18n.
 */
export function groupWorkflowTools(tools: WorkflowToolInfo[]): WorkflowToolGroup[] {
  const byName = (a: WorkflowToolInfo, b: WorkflowToolInfo) => a.name.localeCompare(b.name)
  const isBuiltin = (tool: WorkflowToolInfo) =>
    tool.kind ? tool.kind === 'shipped-native' : tool.builtin === true
  const builtin = tools.filter(isBuiltin).sort(byName)
  const plugins = tools.filter((tool) => !isBuiltin(tool)).sort(byName)
  const groups: WorkflowToolGroup[] = [
    { key: 'builtin', tools: builtin },
    { key: 'plugins', tools: plugins },
  ]
  return groups.filter((group) => group.tools.length > 0)
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

/** Human-readable tooltip for a port label. */
export function portTitle(port: ToolPort): string {
  const title = `${port.name}: ${portTypeLabel(port.type)}`
  return port.description ? `${title} — ${port.description}` : title
}

/*
 * ToolNode layout constants shared between the template (handle offsets)
 * and the scoped CSS. Handles are positioned absolutely on the node, so the
 * CSS row metrics must stay in sync with these values.
 */
export const NODE_HEADER_HEIGHT_PX = 34
export const PORT_ROW_HEIGHT_PX = 18
export const PORTS_PADDING_Y_PX = 6

/** Vertical center (px from node top) of port row `index`. */
export function portRowCenterY(index: number): number {
  return NODE_HEADER_HEIGHT_PX + PORTS_PADDING_Y_PX + index * PORT_ROW_HEIGHT_PX + PORT_ROW_HEIGHT_PX / 2
}
