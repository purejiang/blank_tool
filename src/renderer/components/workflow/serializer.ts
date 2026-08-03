/**
 * Bidirectional serializer between the vue-flow canvas state (nodes/edges)
 * and the backend WorkflowDefinition JSON wire format.
 *
 * Wire contract (must stay in sync with backend/app/workflow/definition.py
 * and backend/app/protocol/ports.py — those modules own the schema):
 *
 *   WorkflowDefinition.to_dict() produces
 *   {
 *     name, version, description,
 *     inputs:  [Port.to_dict()],   // {name, type:{base, subtype}, required, description}
 *     outputs: [Port.to_dict()],
 *     nodes:   [WorkflowNode.to_dict()],  // {id, type, tool, params, next, on_success, on_failure, condition, retry}
 *     edges:   []                  // linear mode: ALWAYS empty
 *   }
 *
 * Linear-mode rule: `node.next` is the SOLE source of truth for control flow.
 * `edges` is reserved for a future DAG mode and must be empty; connectivity
 * is derived from canvas edges on serialize and rebuilt from `next` on
 * deserialize.
 *
 * Node positions are a canvas-only concern and are NEVER serialized. On
 * deserialize a simple vertical stack layout is recomputed
 * (x = 400, y = index * 150).
 */

import type { Edge, Node } from '@vue-flow/core'

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
}

/** One workflow step (mirrors WorkflowNode.to_dict; optional keys use backend defaults when absent). */
export interface WorkflowNodeJSON {
  id: string
  /** Node type, reserved for future DAG mode; "step" is the only meaningful value today. */
  type?: string
  tool: string
  params: Record<string, any>
  /** Id of the next node in the linear chain; null/absent means last node. */
  next?: string | null
  /** Reserved for future DAG mode (stored, unused by the linear executor). */
  on_success?: string | null
  /** "fail" (default), "skip", or "retry:N". */
  on_failure?: string
  /** Reserved for future branching (stored, not evaluated). */
  condition?: string | null
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
  /** Reserved for future DAG mode; MUST be empty in linear mode. */
  edges?: any[]
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
  // Advanced fields — carried through for roundtrip fidelity. Absent while
  // they equal their defaults ("step" / null / "fail" / null / 0).
  type?: string
  on_success?: string | null
  on_failure?: string
  condition?: string | null
  retry?: number
}

/** A workflow node as it lives on the vue-flow canvas. */
export type WorkflowFlowNode = Node<WorkflowNodeData>

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Auto-layout for deserialized workflows: vertical stack. Canvas-only, never serialized. */
const LAYOUT_X = 400
const LAYOUT_Y_SPACING = 150

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
 * Structural validation shared by validateOnDeserialize and deserializeWorkflow.
 *
 * Mirrors the backend checks (WorkflowDefinition.__post_init__ plus the
 * connectivity pass of validate_workflow): name present, edges empty, node
 * ids unique, next references valid, exactly one entry node, no cycles, no
 * orphan nodes. An empty `nodes` list is valid (matches the backend).
 *
 * Input is `any` because callers hand us untrusted JSON (files, IPC payloads);
 * every field is checked at runtime regardless of the static type.
 *
 * @param checkEdges when false, a non-empty edges list is NOT reported —
 *   deserializeWorkflow treats that case as a warning (edges are ignored and
 *   connectivity is rebuilt from `next`), while validateOnDeserialize reports
 *   it as a hard error.
 * @returns all findings as human-readable error strings; empty means valid.
 */
function collectStructuralErrors(json: any, checkEdges: boolean): string[] {
  const errors: string[] = []
  if (json === null || json === undefined || typeof json !== 'object' || Array.isArray(json)) {
    return ['workflow definition must be an object']
  }

  if (typeof json.name !== 'string' || json.name.length === 0) {
    errors.push("missing required field: 'name'")
  }

  if (checkEdges) {
    if (!Array.isArray(json.edges)) {
      errors.push("'edges' must be an array (empty in linear mode)")
    } else if (json.edges.length > 0) {
      errors.push("'edges' must be empty in linear mode")
    }
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
 * Validate a workflow definition JSON before loading it into the canvas.
 *
 * Basic structural checks: name present, `nodes` is an array, node ids are
 * unique and non-empty, `next` references point at existing nodes, `edges`
 * is empty (linear mode), plus the linear-chain connectivity checks
 * (one entry node, no cycles, no orphans).
 *
 * @param json untrusted workflow definition JSON (e.g. from a file or IPC).
 * @returns list of error strings; an empty list means the JSON is valid.
 */
export function validateOnDeserialize(json: WorkflowDefinitionJSON): string[] {
  return collectStructuralErrors(json, true)
}

/**
 * Serialize the vue-flow canvas state into a WorkflowDefinition JSON document.
 *
 * Mapping:
 *  - node id/tool/params come straight from `node.data` (advanced node fields
 *    — type/on_success/on_failure/condition/retry — are carried through when
 *    present, otherwise backend defaults are emitted);
 *  - `next` is derived from the edges: the FIRST outgoing edge of a node
 *    becomes its next pointer (linear mode — extra outgoing edges are
 *    ignored); a node with no outgoing edge gets next = null (chain end);
 *  - `edges` is always [] in the output — connectivity lives in `next`;
 *  - meta supplies the workflow-level name/version/description/inputs/outputs.
 *
 * The output key set matches Python WorkflowDefinition.to_dict exactly, so
 * the backend accepts it via WorkflowDefinition.from_dict unchanged.
 * Positions are intentionally NOT serialized (layout is recomputed on load).
 */
export function serializeWorkflow(
  nodes: Node[],
  edges: Edge[],
  meta: WorkflowMeta,
): WorkflowDefinitionJSON {
  const nextBySource = new Map<string, string>()
  for (const edge of edges ?? []) {
    if (!edge) continue
    if (typeof edge.source !== 'string' || typeof edge.target !== 'string') continue
    if (!nextBySource.has(edge.source)) nextBySource.set(edge.source, edge.target)
  }

  const serializedNodes: WorkflowNodeJSON[] = (nodes ?? []).map((node) => {
    const data = (node.data ?? {}) as WorkflowNodeData
    return {
      id: node.id,
      type: typeof data.type === 'string' && data.type.length > 0 ? data.type : NODE_DEFAULTS.type,
      tool: typeof data.tool === 'string' ? data.tool : '',
      params: cloneJson(data.params ?? {}),
      next: nextBySource.get(node.id) ?? null,
      on_success: data.on_success ?? null,
      on_failure:
        typeof data.on_failure === 'string' && data.on_failure.length > 0
          ? data.on_failure
          : NODE_DEFAULTS.on_failure,
      condition: data.condition ?? null,
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
    edges: [],
  }
}

/**
 * Deserialize a WorkflowDefinition JSON document into vue-flow canvas state.
 *
 * Mapping:
 *  - each WorkflowNodeJSON becomes a Node at an auto-layout position
 *    (vertical stack: x = 400, y = index * 150) with
 *    data = { tool, params, label } plus any advanced fields preserved for
 *    roundtrip fidelity;
 *  - each non-null `next` becomes an Edge { id: `${id}->${next}`, source, target };
 *  - meta carries name/version/description/inputs/outputs (backend defaults
 *    applied for absent optional fields).
 *
 * Structural validation runs first: a structurally invalid document throws
 * an Error listing every finding (see validateOnDeserialize). A non-empty
 * `edges` list is the exception — linear mode should have edges: [], but the
 * list is only warned about and ignored, since connectivity can be rebuilt
 * from `next` regardless.
 *
 * @throws Error naming every structural problem found in the JSON.
 */
export function deserializeWorkflow(json: WorkflowDefinitionJSON): {
  nodes: WorkflowFlowNode[]
  edges: Edge[]
  meta: WorkflowMeta
} {
  if (json && Array.isArray(json.edges) && json.edges.length > 0) {
    console.warn(
      `[workflow serializer] workflow '${json.name}' has ${json.edges.length} edge(s) in ` +
        'its edges list — linear mode expects edges: []; edges are ignored and ' +
        'connectivity is rebuilt from node.next',
    )
  }

  const errors = collectStructuralErrors(json, false)
  if (errors.length > 0) {
    throw new Error(`Invalid workflow definition: ${errors.join('; ')}`)
  }

  const flowNodes: WorkflowFlowNode[] = json.nodes.map((nodeJson, index) => {
    const data: WorkflowNodeData = {
      tool: nodeJson.tool,
      params: cloneJson(nodeJson.params ?? {}),
      label: nodeJson.tool,
    }
    // Preserve advanced fields for the serialize roundtrip, but only store
    // them when they differ from their defaults.
    if (typeof nodeJson.type === 'string' && nodeJson.type !== NODE_DEFAULTS.type) {
      data.type = nodeJson.type
    }
    if (nodeJson.on_success != null) data.on_success = nodeJson.on_success
    if (typeof nodeJson.on_failure === 'string' && nodeJson.on_failure !== NODE_DEFAULTS.on_failure) {
      data.on_failure = nodeJson.on_failure
    }
    if (nodeJson.condition != null) data.condition = nodeJson.condition
    if (typeof nodeJson.retry === 'number' && nodeJson.retry !== NODE_DEFAULTS.retry) {
      data.retry = nodeJson.retry
    }

    return {
      id: nodeJson.id,
      type: 'default',
      position: { x: LAYOUT_X, y: index * LAYOUT_Y_SPACING },
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
