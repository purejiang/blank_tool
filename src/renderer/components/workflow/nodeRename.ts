/**
 * Node-id renaming for the workflow editor.
 *
 * A node's id is not just a canvas key: `$nodes.<id>.outputs.<port>` bindings
 * embed it, and the id is the only node identity the backend schema has. So
 * renaming a node must rewrite, in one shot:
 *
 *  1. the node's own id;
 *  2. every edge's source/target that pointed at the old id;
 *  3. every binding elsewhere in the graph that references `nodes.<oldId>.`
 *     (a plain substring rewrite of `nodes.<oldId>.` covers both the
 *     whole-value form `$nodes.<oldId>.x` and the interpolation form
 *     `${nodes.<oldId>.x}`).
 *
 * Pure and Vue-free so the rewrite is unit-testable; the editor page applies
 * the result through vue-flow's setNodes/setEdges.
 */

/** Minimal node shape needed here (vue-flow `Node` is assignable). */
export interface RenamableNode {
  id: string
  data?: Record<string, any> | undefined
  [key: string]: any
}

/** Minimal edge shape needed here (vue-flow `Edge` is assignable). */
export interface RenamableEdge {
  id?: string
  source: string
  target: string
  [key: string]: any
}

/** Reason a rename cannot be applied. */
export type RenameError = 'empty' | 'dot' | 'duplicate' | 'missing'

/**
 * Result of a rename attempt. A flat shape (rather than a discriminated
 * union) because this repository runs with `strictNullChecks: false`, where
 * control-flow narrowing on a discriminant is unreliable.
 */
export interface RenameResult {
  ok: boolean
  /** Set when `ok` is false. */
  error?: RenameError
  nodes: any[]
  edges: any[]
  edgesChanged: number
  bindingsChanged: number
}

function failure(error: RenameError, nodes: readonly RenamableNode[] | null | undefined, edges: readonly RenamableEdge[] | null | undefined): RenameResult {
  return { ok: false, error, nodes: [...(nodes ?? [])], edges: [...(edges ?? [])], edgesChanged: 0, bindingsChanged: 0 }
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Rewrite `nodes.<oldId>.` occurrences inside a JSON-ish value (strings,
 * nested objects and arrays). Returns the new value plus how many string
 * values changed.
 */
function rewriteValue(value: any, pattern: RegExp, newId: string): { value: any; changed: number } {
  if (typeof value === 'string') {
    const next = value.replace(pattern, (_match, prefix: string) => `${prefix}${newId}`)
    return { value: next, changed: next === value ? 0 : 1 }
  }
  if (Array.isArray(value)) {
    let changed = 0
    const next = value.map((item) => {
      const result = rewriteValue(item, pattern, newId)
      changed += result.changed
      return result.value
    })
    return { value: next, changed }
  }
  if (value && typeof value === 'object') {
    let changed = 0
    const next: Record<string, any> = {}
    for (const [key, item] of Object.entries(value)) {
      const result = rewriteValue(item, pattern, newId)
      changed += result.changed
      next[key] = result.value
    }
    return { value: next, changed }
  }
  return { value, changed: 0 }
}

/**
 * Rename node *oldId* to *newId* across the canvas graph.
 *
 * Validation mirrors the editor's rules: the new id must be non-empty, must
 * not contain `.` (the engine's reference separator), and must not collide
 * with another node. On failure nothing is returned for the caller to apply.
 */
export function renameNodeId(
  nodes: readonly RenamableNode[] | null | undefined,
  edges: readonly RenamableEdge[] | null | undefined,
  oldId: string,
  newId: string,
): RenameResult {
  const list = [...(nodes ?? [])]
  const trimmed = typeof newId === 'string' ? newId.trim() : ''
  if (!trimmed) return failure('empty', list, edges)
  if (trimmed.includes('.')) return failure('dot', list, edges)
  if (!list.some((node) => node?.id === oldId)) return failure('missing', list, edges)
  if (trimmed === oldId) {
    return { ok: true, nodes: list, edges: [...(edges ?? [])], edgesChanged: 0, bindingsChanged: 0 }
  }
  if (list.some((node) => node?.id === trimmed)) return failure('duplicate', list, edges)

  // `(nodes\.)<oldId>(?=\.)` — the lookahead keeps `nodes.<oldId>foo` intact.
  const pattern = new RegExp(`(nodes\\.)${escapeRegExp(oldId)}(?=\\.)`, 'g')

  let bindingsChanged = 0
  const nextNodes = list.map((node) => {
    if (!node) return node
    const result = rewriteValue(node.data, pattern, trimmed)
    bindingsChanged += result.changed
    const isRenamed = node.id === oldId
    if (!isRenamed && result.changed === 0) return node
    return { ...node, ...(isRenamed ? { id: trimmed } : {}), data: result.value }
  })

  let edgesChanged = 0
  const nextEdges = (edges ?? []).map((edge) => {
    if (!edge) return edge
    const touches = edge.source === oldId || edge.target === oldId
    if (!touches) return edge
    edgesChanged += 1
    const source = edge.source === oldId ? trimmed : edge.source
    const target = edge.target === oldId ? trimmed : edge.target
    const id = typeof edge.id === 'string' ? `${source}->${target}` : edge.id
    return { ...edge, source, target, ...(id ? { id } : {}) }
  })

  return { ok: true, nodes: nextNodes, edges: nextEdges, edgesChanged, bindingsChanged }
}
