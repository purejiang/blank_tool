/**
 * Start / End virtual nodes for the workflow editor.
 *
 * The engine's wire schema is a LINEAR chain expressed by `node.next`: it has
 * no Start/End entity — the entry node is simply "the node nothing points at".
 * So Start (`__start__`) / End (`__end__`) are PURE CANVAS affordances:
 *
 *  - they exist only in the editor and are (re-)created on mount, on template
 *    load, and whenever one of them disappears;
 *  - `serializeWorkflow` drops them AND every edge touching them, which keeps
 *    the saved JSON byte-identical to what the backend expects;
 *  - appending a tool inserts it right BEFORE End, so the visible chain always
 *    reads 开始 → … → 结束 without the endpoints ever reaching the wire.
 *
 * Only structural shapes (`{id, position}`, `{source, target}`) are used, so
 * the module stays Vue-free and unit-testable without mounting the canvas.
 */

import type { Edge, Node } from '@vue-flow/core'

import {
  LAYOUT_X_SPACING,
  LAYOUT_X_START,
  LAYOUT_Y,
  appendAnchor,
  chainOrder,
  type NodePosition,
} from './graphLayout'

/** Reserved canvas id of the Start endpoint. */
export const VIRTUAL_START_ID = '__start__'
/** Reserved canvas id of the End endpoint. */
export const VIRTUAL_END_ID = '__end__'

/** Which endpoint a virtual node represents. */
export type VirtualNodeKind = 'start' | 'end'

/** `data` slot of a virtual node (no tool, no params — nothing is executed). */
export interface VirtualNodeData {
  label?: string
}

/** True for the two reserved endpoint ids (`__start__` / `__end__`). */
export function isVirtualNodeId(id: unknown): boolean {
  return id === VIRTUAL_START_ID || id === VIRTUAL_END_ID
}

/** Kind of a virtual node id, or null for a regular tool node. */
export function virtualKindOf(id: unknown): VirtualNodeKind | null {
  if (id === VIRTUAL_START_ID) return 'start'
  if (id === VIRTUAL_END_ID) return 'end'
  return null
}

function edgeId(source: string, target: string): string {
  return `${source}->${target}`
}

function hasEdge(edges: readonly Edge[], source: string, target: string): boolean {
  return edges.some((edge) => edge && edge.source === source && edge.target === target)
}

/**
 * Split a canvas graph into "real" nodes/edges, dropping both endpoints and
 * every edge that touches one. This is the projection the serializer and the
 * chain helpers work on.
 */
export function realGraph(
  nodes: readonly Node[] | null | undefined,
  edges: readonly Edge[] | null | undefined,
): { nodes: Node[]; edges: Edge[] } {
  return {
    nodes: (nodes ?? []).filter((node) => node && !isVirtualNodeId(node.id)),
    edges: (edges ?? []).filter(
      (edge) => edge && !isVirtualNodeId(edge.source) && !isVirtualNodeId(edge.target),
    ),
  }
}

/** A tool node, or a placeholder if the id is not on the canvas. */
function positionOf(nodes: readonly Node[], id: string | undefined): NodePosition | null {
  if (!id) return null
  const node = nodes.find((entry) => entry?.id === id)
  const position = node?.position
  return position ? { x: position.x, y: position.y } : null
}

/**
 * Where the endpoints belong: one slot to the LEFT of the chain entry, one slot
 * to the RIGHT of the chain tail. Falls back to the default first slot when the
 * canvas has no real node yet.
 */
export function endpointPositions(
  realNodes: readonly Node[] | null | undefined,
  realEdges: readonly Edge[] | null | undefined,
): { start: NodePosition; end: NodePosition } {
  const nodes = realNodes ?? []
  const order = chainOrder(
    nodes.map((node) => node?.id),
    realEdges,
  )
  const entry = positionOf(nodes, order[0])
  // Empty canvas: 开始 takes the default first slot and 结束 sits right after it.
  if (!entry) {
    return {
      start: { x: LAYOUT_X_START, y: LAYOUT_Y },
      end: { x: LAYOUT_X_START + LAYOUT_X_SPACING, y: LAYOUT_Y },
    }
  }
  const tail = positionOf(nodes, order[order.length - 1]) ?? entry
  return {
    start: { x: entry.x - LAYOUT_X_SPACING, y: entry.y },
    end: { x: tail.x + LAYOUT_X_SPACING, y: tail.y },
  }
}

/** A fresh endpoint node at `position`. */
export function makeEndpointNode(kind: VirtualNodeKind, position: NodePosition): Node {
  return {
    id: kind === 'start' ? VIRTUAL_START_ID : VIRTUAL_END_ID,
    type: kind,
    position: { ...position },
    data: {} as VirtualNodeData,
  }
}

/**
 * Ensure both endpoints exist, wiring only the ones that had to be created.
 *
 * Used on mount, after every template load and whenever an endpoint vanished
 * (Backspace / 删除). Edges the user drew by hand are never rewritten: a
 * *missing endpoint* is re-created together with its chain edge, an endpoint
 * that is already there is left exactly as-is.
 *
 * Newly created on an otherwise empty canvas → `开始 → 结束`; created around a
 * chain → `开始 → entry` and `tail → 结束`.
 */
export function ensureEndpointGraph(
  nodes: readonly Node[] | null | undefined,
  edges: readonly Edge[] | null | undefined,
): { nodes: Node[]; edges: Edge[] } {
  const allNodes = [...(nodes ?? [])]
  const allEdges = [...(edges ?? [])]
  const present = new Set(allNodes.map((node) => node?.id))
  const real = realGraph(allNodes, allEdges)
  const order = chainOrder(
    real.nodes.map((node) => node.id),
    real.edges,
  )
  const entryId = order[0] ?? null
  const tailId = order.length > 0 ? order[order.length - 1] : null
  const positions = endpointPositions(real.nodes, real.edges)

  const created: VirtualNodeKind[] = []
  if (!present.has(VIRTUAL_START_ID)) {
    allNodes.push(makeEndpointNode('start', positions.start))
    created.push('start')
  }
  if (!present.has(VIRTUAL_END_ID)) {
    allNodes.push(makeEndpointNode('end', positions.end))
    created.push('end')
  }
  if (created.length === 0) return { nodes: allNodes, edges: allEdges }

  const connect = (source: string, target: string) => {
    if (source === target) return
    if (hasEdge(allEdges, source, target)) return
    allEdges.push({ id: edgeId(source, target), source, target })
  }

  if (entryId && tailId) {
    // A chain is already on the canvas: only bridge the side(s) we just built.
    if (created.includes('start')) connect(VIRTUAL_START_ID, entryId)
    if (created.includes('end')) connect(tailId, VIRTUAL_END_ID)
  } else {
    connect(VIRTUAL_START_ID, VIRTUAL_END_ID)
  }

  return { nodes: allNodes, edges: allEdges }
}

/**
 * Id of the node a newly appended tool should be chained FROM, or null when it
 * must be left unconnected.
 *
 * The visible tail of the chain is always End, so the anchor is computed on the
 * REAL graph: the tail of the real chain (or Start when there is none). Null
 * means that tail already carries a real outgoing edge — a second one would be
 * dropped by the linear rule and reported by the canvas guard, exactly as
 * before the endpoints existed.
 */
export function appendAnchorBeforeEnd(
  nodes: readonly Node[] | null | undefined,
  edges: readonly Edge[] | null | undefined,
): string | null {
  const real = realGraph(nodes, edges)
  const ids = real.nodes.map((node) => node.id)
  if (ids.length === 0) return VIRTUAL_START_ID
  return appendAnchor(ids, real.edges)
}

/**
 * Edge list after inserting `newId` between `anchorId` and End: the
 * `anchor → 结束` edge (if any) is replaced by `anchor → new → 结束`.
 */
export function insertBeforeEnd(
  edges: readonly Edge[] | null | undefined,
  anchorId: string,
  newId: string,
): Edge[] {
  const kept = (edges ?? []).filter(
    (edge) => !(edge && edge.source === anchorId && edge.target === VIRTUAL_END_ID),
  )
  kept.push({ id: edgeId(anchorId, newId), source: anchorId, target: newId })
  kept.push({ id: edgeId(newId, VIRTUAL_END_ID), source: newId, target: VIRTUAL_END_ID })
  return kept
}

/**
 * Edge list after deleting `nodeId` from the middle of the chain: its
 * predecessor is spliced onto its successor so the chain stays connected
 * (deleting a node used to leave two dangling halves and block the save).
 *
 * Does nothing when the node had no predecessor or no successor — the caller
 * has already dropped every edge touching it. `Start → End` is restored when
 * the last real node disappears.
 */
export function bridgeAfterDelete(
  edges: readonly Edge[] | null | undefined,
  nodeId: string,
): Edge[] {
  const kept = (edges ?? []).filter(
    (edge) => !(edge && (edge.source === nodeId || edge.target === nodeId)),
  )
  const source = (edges ?? []).find((edge) => edge && edge.target === nodeId)?.source
  const target = (edges ?? []).find((edge) => edge && edge.source === nodeId)?.target
  if (typeof source !== 'string' || typeof target !== 'string') return kept
  // never bridge into a self-loop (Start → Start / End → End)
  if (source === target) return kept
  if (kept.some((edge) => edge && edge.source === source && edge.target === target)) return kept
  kept.push({ id: edgeId(source, target), source, target })
  return kept
}

/** Outcome of removing a canvas selection. */
export interface DeleteSelectionResult {
  nodes: Node[]
  edges: Edge[]
  /** Real nodes that were actually removed (endpoints are never in here). */
  removedNodeIds: string[]
  /** True when the selection contained 开始 / 结束, which cannot be deleted. */
  blockedEndpoint: boolean
}

/**
 * Remove a canvas selection (nodes + edges) in one pure pass — the single
 * implementation behind BOTH the keyboard shortcut and the inspector's
 * 「删除节点」 button.
 *
 * Rules:
 *  - the two endpoints are never deleted (they are canvas structure, not
 *    content); `blockedEndpoint` lets the caller explain that instead of
 *    silently restoring them;
 *  - selected edges are dropped as-is;
 *  - every removed node additionally drops the edges touching it and splices
 *    its predecessor onto its successor (`bridgeAfterDelete`), so deleting a
 *    middle step keeps ONE linear chain instead of leaving two entry nodes.
 */
export function deleteSelectionGraph(
  nodes: readonly Node[] | null | undefined,
  edges: readonly Edge[] | null | undefined,
  selectedNodeIds: readonly string[] | null | undefined,
  selectedEdgeIds: readonly string[] | null | undefined,
): DeleteSelectionResult {
  const nodeSelection = (selectedNodeIds ?? []).filter((id) => typeof id === 'string' && id.length > 0)
  const edgeSelection = new Set(
    (selectedEdgeIds ?? []).filter((id) => typeof id === 'string' && id.length > 0),
  )
  const blockedEndpoint = nodeSelection.some((id) => isVirtualNodeId(id))
  const removedNodeIds = nodeSelection.filter((id) => !isVirtualNodeId(id))
  const removedIds = new Set(removedNodeIds)

  let nextEdges = (edges ?? []).filter((edge) => !(edge && edgeSelection.has(edge.id)))
  for (const id of removedNodeIds) nextEdges = bridgeAfterDelete(nextEdges, id)

  return {
    nodes: (nodes ?? []).filter((node) => !(node && removedIds.has(node.id))),
    edges: nextEdges,
    removedNodeIds,
    blockedEndpoint,
  }
}
