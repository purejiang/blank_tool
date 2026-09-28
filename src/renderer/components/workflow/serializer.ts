/**
 * Bidirectional serializer between the vue-flow canvas state (nodes/edges)
 * and the backend WorkflowDefinition JSON wire format.
 *
 * Wire contract (must stay in sync with cli/app/workflow/definition.py
 * and cli/app/protocol/ports.py — those modules own the schema):
 *
 *   WorkflowDefinition.to_dict() produces
 *   {
 *     name, version, description,
 *     inputs:  [Port.to_dict()],   // {name, type:{base, subtype}, required, description, options, multi}
 *     outputs: [Port.to_dict()],
 *     nodes:   [WorkflowNode.to_dict()]   // {id, type, tool, params, next, on_failure, retry}
 *   }
 *
 * Retired DAG fields (`edges`, `node.condition`, `node.on_success`) no longer
 * exist in the backend schema; this serializer neither emits them nor carries
 * them through a load/save round trip (see the legacy warning in
 * deserializeWorkflow). Connectivity is fully described by `next`.
 *
 * Linear-mode rule: `node.next` is the SOLE source of truth for control flow;
 * connectivity is derived from canvas edges on serialize and rebuilt from
 * `next` on deserialize. The "first outgoing edge wins" rule lives in
 * graphLayout.ts (`resolveNextMap`) and is shared with the canvas guard.
 *
 * Node positions are a canvas-only concern and are NEVER serialized. On
 * deserialize a horizontal chain layout is recomputed (one row, left→right,
 * matching the left/right port handles) by graphLayout.ts.
 */

import type { Edge, Node } from '@vue-flow/core'

import { LAYOUT_X_START, LAYOUT_Y, horizontalLayout, resolveNextMap } from './graphLayout'

// ---------------------------------------------------------------------------
// Wire-format types (mirror the backend Python dataclasses)
// ---------------------------------------------------------------------------

/** Port type annotation on the wire (mirrors TypeAnnotation serialized inline by Port.to_dict). */
export interface PortTypeJSON {
  /** One of the BaseType values: "text", "file", "number", "bool", "list", "dict". */
  base: string
  /** Advisory subtype. Python emits null when unset, so both null and absent occur on the wire. */
  subtype?: string | null
}

/** A workflow-level input/output port (mirrors Port.to_dict). */
export interface PortJSON {
  name: string
  type: PortTypeJSON
  required?: boolean
  description?: string
  /** Allowed values for select-like ports (T2; advisory until a SELECT base type exists). */
  options?: string[]
  /** Whether a select-like port accepts multiple values (T2). */
  multi?: boolean
}

/** One workflow step (mirrors WorkflowNode.to_dict; optional keys use backend defaults when absent). */
export interface WorkflowNodeJSON {
  id: string
  /** Node type ("step"); informational, kept because the backend field exists. */
  type?: string
  tool: string
  params: Record<string, any>
  /** Id of the next node in the linear chain; null/absent means last node. */
  next?: string | null
  /** "fail" (default) or "skip". */
  on_failure?: string
  /** Extra attempts on failure (0 = no retry). */
  retry?: number
}

/** A complete workflow definition (mirrors WorkflowDefinition.to_dict). */
export interface WorkflowDefinitionJSON {
  name: string
  version?: string
  description?: string
  inputs?: PortJSON[]
  outputs?: PortJSON[]
  nodes: WorkflowNodeJSON[]
}

/** Workflow-level metadata edited outside the canvas (name/version/ports form). */
export interface WorkflowMeta {
  name: string
  version?: string
  description?: string
  inputs?: PortJSON[]
  outputs?: PortJSON[]
}

// ---------------------------------------------------------------------------
// Canvas-side types
// ---------------------------------------------------------------------------

/** Payload stored in a workflow node's vue-flow `data` slot. */
export interface WorkflowNodeData {
  /** Name of the tool to invoke, e.g. "bundletool" or "net.download". */
  tool: string
  /** Parameters passed to the tool (must stay JSON-serializable). */
  params: Record<string, any>
  /** Display label; defaults to the tool name. */
  label: string
  /**
   * Operation-mode state (T7): for descriptor tools exposing operations,
   * NodeConfigPanel edits the chosen operation and its typed input bindings
   * here instead of free-form `params`. On serialize these map to the engine
   * wire shape `{operation, <input_name>: value}` (operation first); on
   * deserialize a raw `params.operation` string hydrates both fields.
   */
  operation?: string
  inputs?: Record<string, any>
  // Node behavior — carried through the canvas for roundtrip fidelity. Absent
  // while they equal their defaults ("fail" / 0).
  on_failure?: string
  retry?: number
}

/** A workflow node as it lives on the vue-flow canvas. */
export type WorkflowFlowNode = Node<WorkflowNodeData>

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Defaults shared with the backend (WorkflowNode dataclass defaults). */
const NODE_DEFAULTS = {
  type: 'step',
  on_failure: 'fail',
  retry: 0,
} as const

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** JSON-roundtrip clone so canvas state and serialized JSON never share refs. */
function cloneJson<T>(value: T): T {
  if (value === undefined || value === null) return value
  return JSON.parse(JSON.stringify(value))
}

/**
 * Warn once when a loaded document still carries the retired DAG fields
 * (`edges` / `node.condition` / `node.on_success`).
 *
 * They are ignored on load and dropped on the next save: the backend removed
 * them from the schema (`WorkflowNode.from_dict` no longer reads them), so the
 * only alternative to this warning is losing data silently.
 */
function warnAboutRetiredFields(json: any): void {
  if (!json || typeof json !== 'object') return

  const findings: string[] = []
  if (Array.isArray(json.edges) && json.edges.length > 0) {
    findings.push(`${json.edges.length} entry(ies) in 'edges'`)
  }
  for (const node of Array.isArray(json.nodes) ? json.nodes : []) {
    if (!node || typeof node !== 'object') continue
    if (node.condition != null) findings.push(`'condition' on node '${node.id}'`)
    if (node.on_success != null) findings.push(`'on_success' on node '${node.id}'`)
  }
  if (findings.length === 0) return

  console.warn(
    `[workflow serializer] workflow '${json.name}' carries retired DAG fields (${findings.join(', ')}) — ` +
      'ignored on load and dropped on save; connectivity lives in node.next',
  )
}

/**
 * Structural validation shared by validateOnDeserialize and deserializeWorkflow.
 *
 * Mirrors the backend checks (WorkflowDefinition.__post_init__ plus the
 * connectivity pass of validate_workflow): name present, node ids unique,
 * next references valid, exactly one entry node, no cycles, no orphan nodes.
 * An empty `nodes` list is valid (matches the backend).
 *
 * Input is `any` because callers hand us untrusted JSON (files, IPC payloads);
 * every field is checked at runtime regardless of the static type. Unknown
 * keys — including the retired DAG fields `edges` / `condition` /
 * `on_success` — are ignored, exactly like the backend's `from_dict`.
 *
 * @returns all findings as human-readable error strings; empty means valid.
 */
function collectStructuralErrors(json: any): string[] {
  const errors: string[] = []
  if (json === null || json === undefined || typeof json !== 'object' || Array.isArray(json)) {
    return ['workflow definition must be an object']
  }

  if (typeof json.name !== 'string' || json.name.length === 0) {
    errors.push("missing required field: 'name'")
  }

  if (!Array.isArray(json.nodes)) {
    errors.push("'nodes' must be an array")
    return errors
  }

  // Per-node checks: object shape, non-empty unique id, non-empty tool.
  const nodeErrorStart = errors.length
  const seen = new Set<string>()
  const ids: string[] = []
  const nodeEntries: any[] = json.nodes
  for (let i = 0; i < nodeEntries.length; i++) {
    const raw = nodeEntries[i]
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
      errors.push(`node at index ${i} is not an object`)
      continue
    }
    const id = raw.id
    if (typeof id !== 'string' || id.length === 0) {
      errors.push(`node at index ${i} has a missing or empty id`)
      continue
    }
    if (seen.has(id)) {
      errors.push(`duplicate node id: '${id}'`)
      continue
    }
    seen.add(id)
    ids.push(id)
    if (typeof raw.tool !== 'string' || raw.tool.length === 0) {
      errors.push(`node '${id}': tool must be a non-empty string`)
    }
  }

  // `next` references must point at existing node ids.
  for (const raw of nodeEntries) {
    if (raw === null || typeof raw !== 'object') continue
    const next = raw.next
    if (next === undefined || next === null) continue
    if (typeof next !== 'string' || !seen.has(next)) {
      errors.push(`node '${raw.id}' references unknown next node '${next}'`)
    }
  }

  // Connectivity checks need clean ids/next refs (the backend likewise stops
  // at the first structural failure), and skip trivially for empty workflows.
  if (errors.length > nodeErrorStart || ids.length === 0) return errors

  const byId = new Map<string, any>(nodeEntries.map((raw) => [raw.id, raw]))
  const referenced = new Set<string>(
    nodeEntries.map((raw) => raw.next).filter((next) => typeof next === 'string'),
  )
  const entryNodes = ids.filter((id) => !referenced.has(id))
  if (entryNodes.length !== 1) {
    errors.push(
      entryNodes.length === 0
        ? 'no entry node: every node is referenced by another node (cycle or missing start)'
        : `linear workflow must have exactly one entry node (no incoming 'next' reference), got: [${entryNodes.join(', ')}]`,
    )
    return errors
  }

  // Cycle detection: follow `next` from the entry; a revisit means a loop.
  const visited = new Set<string>()
  let cursor: string | null = entryNodes[0]
  while (cursor !== null) {
    if (visited.has(cursor)) {
      errors.push(`cycle detected: node '${cursor}' is visited twice following 'next'`)
      return errors
    }
    visited.add(cursor)
    const next = byId.get(cursor)?.next
    cursor = typeof next === 'string' ? next : null
  }

  // Orphan detection: every node must be reachable from the entry.
  for (const id of ids) {
    if (!visited.has(id)) {
      errors.push(`orphan node not reachable from entry: '${id}'`)
    }
  }

  return errors
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Map a node's canvas data to the engine wire params (T7).
 *
 * Operation mode (data.operation set): emits `{operation, ...data.inputs}`
 * with `operation` FIRST — matching the T5 example shapes and the T4 engine
 * contract (params["operation"] + named bindings). Legacy free-form nodes
 * keep emitting `data.params` verbatim.
 */
function nodeParamsToWire(data: WorkflowNodeData): Record<string, any> {
  if (typeof data.operation === 'string' && data.operation.length > 0) {
    const params: Record<string, any> = { operation: data.operation }
    const inputs = data.inputs
    if (inputs && typeof inputs === 'object' && !Array.isArray(inputs)) {
      for (const [key, value] of Object.entries(inputs)) params[key] = value
    }
    return cloneJson(params)
  }
  return cloneJson(data.params ?? {})
}

/**
 * Validate a workflow definition JSON before loading it into the canvas.
 *
 * Basic structural checks: name present, `nodes` is an array, node ids are
 * unique and non-empty, `next` references point at existing nodes, plus the
 * linear-chain connectivity checks (one entry node, no cycles, no orphans).
 * Unknown keys (retired DAG fields included) are ignored, matching the
 * backend's `from_dict`.
 *
 * @param json untrusted workflow definition JSON (e.g. from a file or IPC).
 * @returns list of error strings; an empty list means the JSON is valid.
 */
export function validateOnDeserialize(json: WorkflowDefinitionJSON): string[] {
  return collectStructuralErrors(json)
}

/**
 * Serialize the vue-flow canvas state into a WorkflowDefinition JSON document.
 *
 * Mapping:
 *  - node id/tool come from `node.data`; params go through nodeParamsToWire
 *    (operation-mode nodes map data.{operation, inputs} to the engine shape
 *    `{operation, <binding>}`; legacy nodes pass data.params through);
 *    node behavior fields — on_failure/retry — are carried through when
 *    present, otherwise backend defaults are emitted;
 *  - `next` is derived from the edges: the FIRST outgoing edge of a node
 *    becomes its next pointer (linear mode — extra outgoing edges are
 *    ignored and reported by graphLayout.extraOutgoingEdges, see the canvas
 *    guard); a node with no outgoing edge gets next = null (chain end);
 *  - meta supplies the workflow-level name/version/description/inputs/outputs.
 *
 * The output key set matches Python WorkflowDefinition.to_dict exactly (no
 * `edges`, no `condition`/`on_success` — those were removed from the backend
 * schema), so the backend accepts it via WorkflowDefinition.from_dict
 * unchanged. Positions are intentionally NOT serialized (layout is recomputed
 * on load).
 */
export function serializeWorkflow(
  nodes: Node[],
  edges: Edge[],
  meta: WorkflowMeta,
): WorkflowDefinitionJSON {
  const nextBySource = resolveNextMap(edges)

  const serializedNodes: WorkflowNodeJSON[] = (nodes ?? []).map((node) => {
    const data = (node.data ?? {}) as WorkflowNodeData
    return {
      id: node.id,
      type: NODE_DEFAULTS.type,
      tool: typeof data.tool === 'string' ? data.tool : '',
      params: nodeParamsToWire(data),
      next: nextBySource.get(node.id) ?? null,
      on_failure:
        typeof data.on_failure === 'string' && data.on_failure.length > 0
          ? data.on_failure
          : NODE_DEFAULTS.on_failure,
      retry: typeof data.retry === 'number' ? data.retry : NODE_DEFAULTS.retry,
    }
  })

  return {
    name: typeof meta?.name === 'string' ? meta.name : '',
    version: typeof meta?.version === 'string' && meta.version.length > 0 ? meta.version : '1.0',
    description: typeof meta?.description === 'string' ? meta.description : '',
    inputs: cloneJson(meta?.inputs ?? []),
    outputs: cloneJson(meta?.outputs ?? []),
    nodes: serializedNodes,
  }
}

/**
 * Deserialize a WorkflowDefinition JSON document into vue-flow canvas state.
 *
 * Mapping:
 *  - each WorkflowNodeJSON becomes a Node at an auto-layout position
 *    (horizontal chain: one row, left→right — see graphLayout.horizontalLayout)
 *    with data = { tool, params, label, on_failure?, retry? }; params carrying
 *    an `operation` string additionally hydrate data.operation/data.inputs for
 *    the operation-mode config UI;
 *  - each non-null `next` becomes an Edge { id: `${id}->${next}`, source, target };
 *  - meta carries name/version/description/inputs/outputs (backend defaults
 *    applied for absent optional fields).
 *
 * Structural validation runs first: a structurally invalid document throws an
 * Error listing every finding (see validateOnDeserialize). Retired DAG fields
 * (`edges` / `node.condition` / `node.on_success`) are NOT part of the schema
 * any more — a document still carrying them loads fine (the backend ignores
 * unknown keys too), warns once, and is re-saved without them.
 *
 * @throws Error naming every structural problem found in the JSON.
 */
export function deserializeWorkflow(json: WorkflowDefinitionJSON): {
  nodes: WorkflowFlowNode[]
  edges: Edge[]
  meta: WorkflowMeta
} {
  warnAboutRetiredFields(json)

  const errors = collectStructuralErrors(json)
  if (errors.length > 0) {
    throw new Error(`Invalid workflow definition: ${errors.join('; ')}`)
  }

  // Auto-layout input: the `next` pointers ARE the chain, so feed them to the
  // layout helper as edges. Nodes unreachable from the entry (only possible in
  // a hand-edited document — we validated above) are appended in order.
  const nextEdges = json.nodes
    .map((nodeJson) => ({ source: nodeJson.id, target: nodeJson.next }))
    .filter((edge): edge is { source: string; target: string } => typeof edge.target === 'string' && edge.target.length > 0)
  const positions = horizontalLayout(
    json.nodes.map((nodeJson) => nodeJson.id),
    nextEdges,
  )

  const flowNodes: WorkflowFlowNode[] = json.nodes.map((nodeJson) => {
    const params = cloneJson(nodeJson.params ?? {})
    const data: WorkflowNodeData = {
      tool: nodeJson.tool,
      params,
      label: nodeJson.tool,
    }
    // Operation-node hydration (T7): raw wire params `{operation, <bindings>}`
    // — the T4/T5 engine contract — become the editor's operation-mode state
    // `data.operation` + `data.inputs`. `data.params` stays as the raw copy
    // for roundtrip fidelity; serialize prefers the operation branch. Legacy
    // free-form params without an `operation` key are untouched.
    if (typeof params.operation === 'string' && params.operation.length > 0) {
      data.operation = params.operation
      const inputs: Record<string, any> = {}
      for (const [key, value] of Object.entries(params)) {
        if (key === 'operation') continue
        inputs[key] = value
      }
      data.inputs = inputs
    }
    // Behavior fields, stored only when they differ from their defaults.
    if (typeof nodeJson.on_failure === 'string' && nodeJson.on_failure !== NODE_DEFAULTS.on_failure) {
      data.on_failure = nodeJson.on_failure
    }
    if (typeof nodeJson.retry === 'number' && nodeJson.retry !== NODE_DEFAULTS.retry) {
      data.retry = nodeJson.retry
    }

    return {
      id: nodeJson.id,
      type: 'default',
      position: positions[nodeJson.id] ?? { x: LAYOUT_X_START, y: LAYOUT_Y },
      data,
    }
  })

  const flowEdges: Edge[] = []
  for (const nodeJson of json.nodes) {
    if (typeof nodeJson.next === 'string' && nodeJson.next.length > 0) {
      flowEdges.push({
        id: `${nodeJson.id}->${nodeJson.next}`,
        source: nodeJson.id,
        target: nodeJson.next,
      })
    }
  }

  const meta: WorkflowMeta = {
    name: json.name,
    version: typeof json.version === 'string' && json.version.length > 0 ? json.version : '1.0',
    description: typeof json.description === 'string' ? json.description : '',
    inputs: cloneJson(Array.isArray(json.inputs) ? json.inputs : []),
    outputs: cloneJson(Array.isArray(json.outputs) ? json.outputs : []),
  }

  return { nodes: flowNodes, edges: flowEdges, meta }
}
