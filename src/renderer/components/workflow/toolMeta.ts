/**
 * Shared types and small helpers for the workflow editor components
 * (ToolNode, WorkflowNodePalette, WorkflowEditorPage).
 *
 * Tool categories and status values are deliberately local to the renderer:
 * the backend `workflow.list_tools` payload (see
 * backend/app/handlers/workflow_handler.py) only carries name/is_valid/
 * version/tool_path/ports/builtin, so the category is derived from the
 * dotted tool-name prefix.
 */

export type ToolStatus = 'idle' | 'running' | 'success' | 'error'

export type ToolCategory = 'file' | 'net' | 'exec' | 'flow' | 'tool'

/** A single I/O port, as serialized by backend Port.to_dict(). */
export interface ToolPort {
  name: string
  type: { base: string; subtype: string | null }
  required: boolean
  description: string
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

/** One entry of the `workflow.list_tools` response `tools` array. */
export interface WorkflowToolInfo {
  name: string
  is_valid: boolean
  version: string
  tool_path: string
  ports?: ToolPorts
  builtin?: boolean
  description?: string
}

/** MIME type used when dragging a tool from the palette onto the canvas. */
export const TOOL_DRAG_MIME = 'application/vnd.blanktool.workflow-tool'

/**
 * Map a dotted tool name to its display category.
 * "file.read" → file, "net.download" → net, "shell.exec"/"code.exec" → exec,
 * "flow.assert" → flow, anything else (descriptor tools, ...) → tool.
 */
const CATEGORY_BY_PREFIX: Record<string, ToolCategory> = {
  file: 'file',
  dir: 'file',
  text: 'file',
  archive: 'file',
  net: 'net',
  shell: 'exec',
  code: 'exec',
  exec: 'exec',
  flow: 'flow',
}

export function categoryOfToolName(name: string): ToolCategory {
  const prefix = name.split('.')[0]
  return CATEGORY_BY_PREFIX[prefix] ?? 'tool'
}

/**
 * Static inline SVG icons per category (16x16, stroke uses currentColor).
 * Rendered via v-html — these strings are static, never user-supplied.
 */
export const CATEGORY_ICONS: Record<ToolCategory, string> = {
  file: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 1.5h5L13 5v9.5H4.5z"/><path d="M9.5 1.5V5H13"/><path d="M6.5 8.5h4M6.5 11h4"/></svg>',
  net: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6.2"/><path d="M1.8 8h12.4"/><path d="M8 1.8c2.3 2 2.3 10.4 0 12.4M8 1.8c-2.3 2-2.3 10.4 0 12.4"/></svg>',
  exec: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4l3.5 4L3 12"/><path d="M8.5 12H13"/></svg>',
  flow: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="4.5" cy="3.5" r="2"/><circle cx="4.5" cy="12.5" r="2"/><circle cx="11.5" cy="12.5" r="2"/><path d="M4.5 5.5v5"/><path d="M11.5 10.5V10a3.5 3.5 0 0 0-3.5-3.5H6.5"/></svg>',
  tool: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="2.4"/><path d="M8 1.5l5.63 3.25v6.5L8 14.5l-5.63-3.25v-6.5z"/></svg>',
}

/** Human-readable tooltip for a port label. */
export function portTitle(port: ToolPort): string {
  const typeLabel = port.type.subtype
    ? `${port.type.base}/${port.type.subtype}`
    : port.type.base
  const title = `${port.name}: ${typeLabel}`
  return port.description ? `${title} — ${port.description}` : title
}

/*
 * ToolNode layout constants shared between the template (handle offsets)
 * and the scoped CSS. Handles are positioned absolutely on the node, so the
 * CSS row metrics must stay in sync with these values.
 */
export const NODE_HEADER_HEIGHT_PX = 28
export const PORT_ROW_HEIGHT_PX = 18
export const PORTS_PADDING_Y_PX = 6

/** Vertical center (px from node top) of port row `index`. */
export function portRowCenterY(index: number): number {
  return NODE_HEADER_HEIGHT_PX + PORTS_PADDING_Y_PX + index * PORT_ROW_HEIGHT_PX + PORT_ROW_HEIGHT_PX / 2
}
