/**
 * Canvas graph helpers for the workflow editor.
 *
 * The editor's canvas can hold any vue-flow graph, but the engine only
 * understands a LINEAR chain: `node.next` is a single pointer, so exactly one
 * outgoing edge per node survives serialization.  Everything in this module
 * exists to keep that rule in ONE place:
 *
 *  - `resolveNextMap` is the single implementation of "the first outgoing
 *    edge wins" (serializer.ts and the canvas guard both consume it, so the
 *    warning shown on the canvas can never drift from what gets saved);
 *  - `extraOutgoingEdges` reports the edges that will be dropped, which the
 *    editor turns into the linear-model warning banner;
 *  - `chainOrder` + `horizontalLayout` produce the left→right auto-layout used
 *    when a definition is loaded (positions are canvas-only and never
 *    serialized — the backend schema has no coordinate fields);
 *  - `upstreamNodeIds` feeds the parameter-binding picker: only nodes that
 *    execute BEFORE the selected node have results in the engine's
 *    `$nodes.<id>` context, so referencing anything else is a runtime error.
 *
 * Pure and Vue-free so it is unit-testable without mounting the canvas (see
 * tests/unit/workflow-editor/graphLayout.test.ts). It deliberately does not
 * import vue-flow types: only the structural shape `{ source, target }` is
 * needed, and vue-flow's `Edge` is assignable to it.
 */

/** Canvas-only layout constants. Positions are NEVER serialized. */
export const LAYOUT_X_START = 80
/**
 * 260 = 节点卡宽 200 + 60px 间隙。卡片在 09-28 改版后固定 200px 宽（改版前按端口
 * 行数撑高撑宽，间距 320 是照着那时的宽卡片定的），太松会让加载后的整条链在画布
 * 里显得又小又空。
 */
export const LAYOUT_X_SPACING = 260
export const LAYOUT_Y = 140

/** One node position on the canvas. */
export interface NodePosition {
  x: number
  y: number
}

/** Minimal edge shape these helpers need (vue-flow `Edge` is assignable). */
export interface GraphEdgeLike {
  source?: string | null
  target?: string | null
}

function idOf(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

/**
 * Map every source node to the target of its FIRST outgoing edge.
 *
 * This is the linear-model rule ("每个节点只保留第一条出边") and the sole
 * source of truth shared by `serializeWorkflow` and the canvas guard.
 * Edges with a missing/empty source or target are ignored; a self-edge is
 * kept (it becomes `next = self`, which the backend rejects as a cycle — the
 * editor blocks creating one in the first place).
 */
export function resolveNextMap(edges: readonly GraphEdgeLike[] | null | undefined): Map<string, string> {
  const next = new Map<string, string>()
  for (const edge of edges ?? []) {
    if (!edge) continue
    const source = idOf(edge.source)
    const target = idOf(edge.target)
    if (!source || !target) continue
    if (!next.has(source)) next.set(source, target)
  }
  return next
}

/**
 * Outgoing edges that serialization would silently drop.
 *
 * An edge is "extra" when its source already has an earlier outgoing edge.
 * Not counted as conflicts (see docs/08 §3-S2「不算命中的情况」):
 *  - edges whose source or target node is no longer on the canvas;
 *  - duplicate edges between the same source and target (`next` is identical,
 *    so nothing is lost).
 *
 * Order follows the input edge order, so the banner lists them stably.
 */
export function extraOutgoingEdges(
  nodeIds: readonly string[] | null | undefined,
  edges: readonly GraphEdgeLike[] | null | undefined,
): Array<{ source: string; target: string }> {
  const known = new Set((nodeIds ?? []).filter((id) => typeof id === 'string' && id.length > 0))
  const firstTarget = new Map<string, string>()
  const seenPairs = new Set<string>()
  const extra: Array<{ source: string; target: string }> = []

  for (const edge of edges ?? []) {
    if (!edge) continue
    const source = idOf(edge.source)
    const target = idOf(edge.target)
    if (!source || !target) continue
    if (!known.has(source) || !known.has(target)) continue

    const pair = `${source}\u0000${target}`
    if (seenPairs.has(pair)) continue // same source→target twice: no data loss
    seenPairs.add(pair)

    const first = firstTarget.get(source)
    if (first === undefined) {
      firstTarget.set(source, target)
      continue
    }
    extra.push({ source, target })
  }
  return extra
}

/**
 * Order node ids along the linear chain, for auto-layout.
 *
 * Starts at the entry node (the one no edge points at) and follows `next`
 * pointers; nodes that are unreachable (orphans, cycles, several entries)
 * are appended afterwards in their original order so a malformed canvas
 * still lays out deterministically. Never throws.
 */
export function chainOrder(
  nodeIds: readonly string[] | null | undefined,
  edges: readonly GraphEdgeLike[] | null | undefined,
): string[] {
  const ids = (nodeIds ?? []).filter((id) => typeof id === 'string' && id.length > 0)
  if (ids.length === 0) return []
  const known = new Set(ids)
  const next = resolveNextMap(edges)
  const referenced = new Set<string>()
  for (const target of next.values()) {
    if (known.has(target)) referenced.add(target)
  }

  const ordered: string[] = []
  const visited = new Set<string>()
  const entries = ids.filter((id) => !referenced.has(id))
  // Defensive: a cycle over every node has no entry — start from the first id.
  const cursorSeeds = entries.length > 0 ? entries : [ids[0]]

  for (const seed of cursorSeeds) {
    let cursor: string | undefined = seed
    while (cursor !== undefined && !visited.has(cursor)) {
      visited.add(cursor)
      ordered.push(cursor)
      const target = next.get(cursor)
      cursor = target !== undefined && known.has(target) ? target : undefined
    }
  }

  for (const id of ids) {
    if (!visited.has(id)) {
      visited.add(id)
      ordered.push(id)
    }
  }
  return ordered
}

/**
 * Id of the node a newly appended node should be chained FROM — the tail of the
 * current chain — or null when there is nothing safe to chain onto.
 *
 * Returns null in two cases:
 *  - the canvas has no nodes (the appended node becomes the entry itself);
 *  - the chain tail already has an outgoing edge. A second one would be dropped
 *    by the linear rule (`resolveNextMap` keeps the FIRST outgoing edge) and
 *    reported as a conflict by `extraOutgoingEdges`, so the caller must not
 *    create it.
 *
 * On an already-disconnected canvas (several entry nodes) this still anchors on
 * the chain-order tail: appending cannot repair a broken chain, it only avoids
 * making it worse — the save guard reports the rest.
 */
export function appendAnchor(
  nodeIds: readonly string[] | null | undefined,
  edges: readonly GraphEdgeLike[] | null | undefined,
): string | null {
  const order = chainOrder(nodeIds, edges)
  if (order.length === 0) return null
  const tail = order[order.length - 1]
  const hasOutgoing = (edges ?? []).some((edge) => edge && idOf(edge.source) === tail)
  return hasOutgoing ? null : tail
}

/**
 * Auto-layout positions for a loaded definition: one horizontal row, left→right.
 *
 * The node handles are on the left (targets) and right (sources), so a
 * horizontal chain renders straight edges; a vertical stack of left/right
 * handles used to make every edge loop back in a U shape.
 */
export function horizontalLayout(
  nodeIds: readonly string[] | null | undefined,
  edges: readonly GraphEdgeLike[] | null | undefined,
): Record<string, NodePosition> {
  const positions: Record<string, NodePosition> = {}
  chainOrder(nodeIds, edges).forEach((id, index) => {
    positions[id] = { x: LAYOUT_X_START + index * LAYOUT_X_SPACING, y: LAYOUT_Y }
  })
  return positions
}

/**
 * Ids of every node that runs BEFORE *nodeId* in the linear chain — the set
 * of nodes whose `$nodes.<id>.outputs.<port>` references can resolve at
 * runtime (the engine only accumulates results of already-executed nodes).
 *
 * Walks INCOMING edges transitively (reverse of execution order). A node with
 * no incoming edges returns an empty set. Cycle-safe.
 */
export function upstreamNodeIds(
  nodeId: string,
  edges: readonly GraphEdgeLike[] | null | undefined,
): Set<string> {
  const incoming = new Map<string, string[]>()
  for (const edge of edges ?? []) {
    if (!edge) continue
    const source = idOf(edge.source)
    const target = idOf(edge.target)
    if (!source || !target || source === target) continue
    const bucket = incoming.get(target)
    if (bucket) bucket.push(source)
    else incoming.set(target, [source])
  }

  const upstream = new Set<string>()
  const stack = [...(incoming.get(nodeId) ?? [])]
  while (stack.length > 0) {
    const current = stack.pop() as string
    if (current === nodeId || upstream.has(current)) continue
    upstream.add(current)
    for (const parent of incoming.get(current) ?? []) {
      if (!upstream.has(parent)) stack.push(parent)
    }
  }
  return upstream
}
