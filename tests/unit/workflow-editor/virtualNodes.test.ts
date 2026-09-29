import { describe, expect, it } from 'vitest'

import {
  LAYOUT_X_SPACING,
  LAYOUT_X_START,
  LAYOUT_Y,
} from '@/renderer/components/workflow/graphLayout'
import {
  VIRTUAL_END_ID,
  VIRTUAL_START_ID,
  appendAnchorBeforeEnd,
  bridgeAfterDelete,
  deleteSelectionGraph,
  endpointPositions,
  ensureEndpointGraph,
  insertBeforeEnd,
  isVirtualNodeId,
  realGraph,
  virtualKindOf,
} from '@/renderer/components/workflow/virtualNodes'

/**
 * virtualNodes unit tests: the canvas-only 开始 / 结束 endpoints. They must
 * never reach the wire (see serializer.test.ts for the serialization side) and
 * the chain helpers have to look THROUGH them, otherwise appending a node would
 * chain it after 结束 and deleting a middle node would leave two entries.
 */

function node(id: string, x = LAYOUT_X_START, y = LAYOUT_Y) {
  return { id, type: 'tool', position: { x, y }, data: { tool: id } }
}

function edge(source: string, target: string) {
  return { id: `${source}->${target}`, source, target }
}

/** 开始 → a → b → 结束, on the canvas that `ensureEndpointGraph` produces. */
function chainedCanvas() {
  const a = node('a', LAYOUT_X_START + LAYOUT_X_SPACING)
  const b = node('b', LAYOUT_X_START + 2 * LAYOUT_X_SPACING)
  return {
    ...ensureEndpointGraph([a, b], [edge('a', 'b')]),
    a,
    b,
  }
}

describe('isVirtualNodeId / virtualKindOf', () => {
  it('recognises exactly the two reserved ids', () => {
    expect(isVirtualNodeId(VIRTUAL_START_ID)).toBe(true)
    expect(isVirtualNodeId(VIRTUAL_END_ID)).toBe(true)
    expect(isVirtualNodeId('a')).toBe(false)
    expect(isVirtualNodeId(undefined)).toBe(false)
  })

  it('maps ids to their endpoint kind', () => {
    expect(virtualKindOf(VIRTUAL_START_ID)).toBe('start')
    expect(virtualKindOf(VIRTUAL_END_ID)).toBe('end')
    expect(virtualKindOf('tool-x-1')).toBe(null)
  })
})

describe('realGraph', () => {
  it('drops the endpoints and every edge touching them', () => {
    const { nodes, edges } = chainedCanvas()
    const real = realGraph(nodes, edges)

    expect(real.nodes.map((entry) => entry.id)).toEqual(['a', 'b'])
    expect(real.edges.map((entry) => entry.id)).toEqual(['a->b'])
  })

  it('tolerates null/undefined graphs', () => {
    expect(realGraph(null, undefined)).toEqual({ nodes: [], edges: [] })
  })
})

describe('endpointPositions', () => {
  it('puts Start one slot left of the entry and End one slot right of the tail', () => {
    const a = node('a', 340)
    const b = node('b', 600)
    const positions = endpointPositions([a, b], [edge('a', 'b')])

    expect(positions.start).toEqual({ x: 340 - LAYOUT_X_SPACING, y: LAYOUT_Y })
    expect(positions.end).toEqual({ x: 600 + LAYOUT_X_SPACING, y: LAYOUT_Y })
  })

  it('falls back to the default slot on an empty canvas', () => {
    const positions = endpointPositions([], [])

    expect(positions.start).toEqual({ x: LAYOUT_X_START, y: LAYOUT_Y })
    expect(positions.end.x).toBe(LAYOUT_X_START + LAYOUT_X_SPACING)
  })
})

describe('ensureEndpointGraph', () => {
  it('creates 开始 → 结束 on an empty canvas', () => {
    const graph = ensureEndpointGraph([], [])

    expect(graph.nodes.map((entry) => entry.id)).toEqual([VIRTUAL_START_ID, VIRTUAL_END_ID])
    expect(graph.nodes.map((entry) => entry.type)).toEqual(['start', 'end'])
    expect(graph.edges.map((entry) => entry.id)).toEqual([`${VIRTUAL_START_ID}->${VIRTUAL_END_ID}`])
  })

  it('wraps a loaded chain with both endpoints', () => {
    const { nodes, edges } = chainedCanvas()
    const ids = edges.map((entry) => entry.id)

    expect(nodes.map((entry) => entry.id)).toEqual(['a', 'b', VIRTUAL_START_ID, VIRTUAL_END_ID])
    expect(ids).toEqual(['a->b', `${VIRTUAL_START_ID}->a`, `b->${VIRTUAL_END_ID}`])
  })

  it('is idempotent — an intact graph is returned untouched', () => {
    const first = chainedCanvas()
    const second = ensureEndpointGraph(first.nodes, first.edges)

    expect(second.nodes).toEqual(first.nodes)
    expect(second.edges).toEqual(first.edges)
  })

  it('re-creates a deleted Start and reconnects it to the entry', () => {
    const { nodes, edges } = chainedCanvas()
    const withoutStart = {
      nodes: nodes.filter((entry) => entry.id !== VIRTUAL_START_ID),
      edges: edges.filter((entry) => entry.source !== VIRTUAL_START_ID),
    }

    const restored = ensureEndpointGraph(withoutStart.nodes, withoutStart.edges)

    expect(restored.nodes.map((entry) => entry.id)).toContain(VIRTUAL_START_ID)
    expect(restored.edges.map((entry) => entry.id)).toContain(`${VIRTUAL_START_ID}->a`)
  })

  it('re-creates a deleted End and reconnects the tail to it', () => {
    const { nodes, edges } = chainedCanvas()
    const withoutEnd = {
      nodes: nodes.filter((entry) => entry.id !== VIRTUAL_END_ID),
      edges: edges.filter((entry) => entry.target !== VIRTUAL_END_ID),
    }

    const restored = ensureEndpointGraph(withoutEnd.nodes, withoutEnd.edges)

    expect(restored.nodes.map((entry) => entry.id)).toContain(VIRTUAL_END_ID)
    expect(restored.edges.map((entry) => entry.id)).toContain(`b->${VIRTUAL_END_ID}`)
  })

  it('does not re-add a chain edge while both endpoints exist', () => {
    const a = node('a')
    const start = { id: VIRTUAL_START_ID, type: 'start', position: { x: 0, y: 0 } }
    const end = { id: VIRTUAL_END_ID, type: 'end', position: { x: 400, y: 0 } }
    // both endpoints present, edges deliberately cleared by the user
    const graph = ensureEndpointGraph([start, a, end], [])

    expect(graph.nodes).toEqual([start, a, end])
    expect(graph.edges).toEqual([])
  })
})

describe('appendAnchorBeforeEnd', () => {
  it('anchors on Start when the canvas has no tool node yet', () => {
    expect(appendAnchorBeforeEnd([], [])).toBe(VIRTUAL_START_ID)

    const { nodes, edges } = ensureEndpointGraph([], [])
    expect(appendAnchorBeforeEnd(nodes, edges)).toBe(VIRTUAL_START_ID)
  })

  it('anchors on the tail of the REAL chain, not on 结束', () => {
    const { nodes, edges } = chainedCanvas()

    expect(appendAnchorBeforeEnd(nodes, edges)).toBe('b')
  })

  it('returns null when the real tail already carries a real outgoing edge', () => {
    const { nodes } = chainedCanvas()
    const edges = [edge('a', 'b'), edge('b', 'c'), edge('b', VIRTUAL_END_ID)]

    expect(appendAnchorBeforeEnd(nodes, edges)).toBe(null)
  })
})

describe('insertBeforeEnd', () => {
  it('splices the new node between the anchor and 结束', () => {
    const { edges } = chainedCanvas()
    const next = insertBeforeEnd(edges, 'b', 'c')

    expect(next.map((entry) => entry.id)).toEqual([
      'a->b',
      `${VIRTUAL_START_ID}->a`,
      'b->c',
      `c->${VIRTUAL_END_ID}`,
    ])
  })

  it('replaces 开始 → 结束 when the first tool is appended', () => {
    const { nodes, edges } = ensureEndpointGraph([], [])
    expect(nodes.length).toBe(2)

    const next = insertBeforeEnd(edges, VIRTUAL_START_ID, 'a')

    expect(next.map((entry) => entry.id)).toEqual([
      `${VIRTUAL_START_ID}->a`,
      `a->${VIRTUAL_END_ID}`,
    ])
  })
})

describe('bridgeAfterDelete', () => {
  it('splices predecessor onto successor when a middle node goes away', () => {
    const { edges } = chainedCanvas()
    const next = bridgeAfterDelete(edges, 'a')

    expect(next.map((entry) => entry.id)).toEqual([
      `b->${VIRTUAL_END_ID}`,
      `${VIRTUAL_START_ID}->b`,
    ])
  })

  it('restores 开始 → 结束 when the last tool node goes away', () => {
    const edges = [edge(VIRTUAL_START_ID, 'a'), edge('a', VIRTUAL_END_ID)]
    const next = bridgeAfterDelete(edges, 'a')

    expect(next.map((entry) => entry.id)).toEqual([`${VIRTUAL_START_ID}->${VIRTUAL_END_ID}`])
  })

  it('leaves the graph alone when the node had no predecessor', () => {
    const next = bridgeAfterDelete([edge('a', 'b')], 'a')

    expect(next).toEqual([])
  })

  it('never creates a self-loop when predecessor and successor are the same', () => {
    // X → A and A → X: deleting A would bridge X → X.
    const next = bridgeAfterDelete([edge('x', 'a'), edge('a', 'x')], 'a')

    expect(next).toEqual([])
  })
})

describe('deleteSelectionGraph', () => {
  it('deletes a middle node and splices its predecessor onto its successor', () => {
    const { nodes, edges } = chainedCanvas()
    const result = deleteSelectionGraph(nodes, edges, ['a'], [])

    expect(result.removedNodeIds).toEqual(['a'])
    expect(result.blockedEndpoint).toBe(false)
    expect(result.nodes.map((entry) => entry.id)).toEqual(['b', VIRTUAL_START_ID, VIRTUAL_END_ID])
    expect(result.edges.map((entry) => entry.id)).toEqual([
      `b->${VIRTUAL_END_ID}`,
      `${VIRTUAL_START_ID}->b`,
    ])
  })

  it('keeps the endpoints and reports them as blocked', () => {
    const { nodes, edges } = chainedCanvas()
    const result = deleteSelectionGraph(nodes, edges, [VIRTUAL_START_ID, VIRTUAL_END_ID], [])

    expect(result.blockedEndpoint).toBe(true)
    expect(result.removedNodeIds).toEqual([])
    expect(result.nodes).toHaveLength(4)
    expect(result.edges).toHaveLength(3)
  })

  it('deletes the selected edges and nothing else', () => {
    const { nodes, edges } = chainedCanvas()
    const result = deleteSelectionGraph(nodes, edges, [], ['a->b'])

    expect(result.blockedEndpoint).toBe(false)
    expect(result.nodes).toHaveLength(4)
    expect(result.edges.map((entry) => entry.id)).toEqual([
      `${VIRTUAL_START_ID}->a`,
      `b->${VIRTUAL_END_ID}`,
    ])
  })

  it('restores 开始 → 结束 when the last tool node is deleted', () => {
    const graph = ensureEndpointGraph([node('a')], [])
    const result = deleteSelectionGraph(graph.nodes, graph.edges, ['a'], [])

    expect(result.nodes.map((entry) => entry.id)).toEqual([VIRTUAL_START_ID, VIRTUAL_END_ID])
    expect(result.edges.map((entry) => entry.id)).toEqual([`${VIRTUAL_START_ID}->${VIRTUAL_END_ID}`])
  })

  it('tolerates an empty selection and null graphs', () => {
    const result = deleteSelectionGraph(null, undefined, null, undefined)

    expect(result).toEqual({ nodes: [], edges: [], removedNodeIds: [], blockedEndpoint: false })
  })
})
