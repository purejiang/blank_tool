import { describe, expect, it } from 'vitest'

import {
  LAYOUT_X_SPACING,
  LAYOUT_X_START,
  LAYOUT_Y,
  appendAnchor,
  chainOrder,
  extraOutgoingEdges,
  horizontalLayout,
  resolveNextMap,
  upstreamNodeIds,
} from '@/renderer/components/workflow/graphLayout'

/**
 * graphLayout unit tests: the linear-model rules shared by the serializer and
 * the canvas guard, plus the horizontal auto-layout and the upstream set that
 * feeds the parameter-binding picker.
 */

function edge(source: string, target: string) {
  return { id: `${source}->${target}`, source, target }
}

describe('resolveNextMap', () => {
  it('keeps the first outgoing edge per source (linear rule)', () => {
    const next = resolveNextMap([edge('a', 'b'), edge('a', 'c'), edge('b', 'c')])

    expect(next.get('a')).toBe('b')
    expect(next.get('b')).toBe('c')
    expect(next.size).toBe(2)
  })

  it('ignores edges with a missing source or target', () => {
    const next = resolveNextMap([
      { source: '', target: 'b' },
      { source: 'a', target: undefined },
      null as any,
      edge('a', 'b'),
    ])

    expect([...next.entries()]).toEqual([['a', 'b']])
  })

  it('tolerates null/undefined edge lists', () => {
    expect(resolveNextMap(null).size).toBe(0)
    expect(resolveNextMap(undefined).size).toBe(0)
  })
})

describe('extraOutgoingEdges', () => {
  it('reports only edges beyond the first per source', () => {
    const extra = extraOutgoingEdges(['a', 'b', 'c'], [edge('a', 'b'), edge('a', 'c')])

    expect(extra).toEqual([{ source: 'a', target: 'c' }])
  })

  it('does not count a duplicate source→target edge (next is unchanged)', () => {
    expect(extraOutgoingEdges(['a', 'b'], [edge('a', 'b'), edge('a', 'b')])).toEqual([])
  })

  it('does not count edges whose source or target node is gone', () => {
    const extra = extraOutgoingEdges(['a'], [edge('a', 'b'), edge('a', 'c'), edge('ghost', 'a')])

    expect(extra).toEqual([])
  })

  it('lists conflicts in edge order for a stable banner', () => {
    const extra = extraOutgoingEdges(
      ['a', 'b', 'c', 'd'],
      [edge('a', 'b'), edge('a', 'c'), edge('a', 'd')],
    )

    expect(extra).toEqual([
      { source: 'a', target: 'c' },
      { source: 'a', target: 'd' },
    ])
  })
})

describe('chainOrder', () => {
  it('follows next pointers from the entry node', () => {
    expect(chainOrder(['c', 'a', 'b'], [edge('a', 'b'), edge('b', 'c')])).toEqual(['a', 'b', 'c'])
  })

  it('appends unreachable nodes in their original order', () => {
    // 'b' and 'c' form a cycle with no entry; 'a' is standalone.
    expect(chainOrder(['a', 'b', 'c'], [edge('b', 'c'), edge('c', 'b')])).toEqual(['a', 'b', 'c'])
  })

  it('returns an empty list for an empty canvas', () => {
    expect(chainOrder([], [])).toEqual([])
  })
})

describe('horizontalLayout', () => {
  it('lays the chain out in one row, left to right', () => {
    const positions = horizontalLayout(['c', 'a', 'b'], [edge('a', 'b'), edge('b', 'c')])

    expect(positions).toEqual({
      a: { x: LAYOUT_X_START, y: LAYOUT_Y },
      b: { x: LAYOUT_X_START + LAYOUT_X_SPACING, y: LAYOUT_Y },
      c: { x: LAYOUT_X_START + 2 * LAYOUT_X_SPACING, y: LAYOUT_Y },
    })
  })

  it('assigns a position to every node id (no undefined entries)', () => {
    const positions = horizontalLayout(['a', 'b'], [])

    expect(Object.keys(positions).sort()).toEqual(['a', 'b'])
  })
})

describe('appendAnchor', () => {
  it('returns null on an empty canvas (the new node becomes the entry)', () => {
    expect(appendAnchor([], [])).toBeNull()
    expect(appendAnchor(null, null)).toBeNull()
  })

  it('anchors on the only node when there are no edges', () => {
    expect(appendAnchor(['a'], [])).toBe('a')
  })

  it('anchors on the tail of the chain', () => {
    expect(appendAnchor(['a', 'b', 'c'], [edge('a', 'b'), edge('b', 'c')])).toBe('c')
  })

  it('returns null when the tail already has an outgoing edge', () => {
    // b -> a would be a second outgoing edge for b (the linear rule keeps the
    // first one), so appending there must be refused.
    expect(appendAnchor(['a', 'b'], [edge('a', 'b'), edge('b', 'a')])).toBeNull()
  })

  it('still anchors on the chain-order tail of a disconnected canvas', () => {
    // Two entry nodes: appending cannot repair the chain, but it must not make
    // the new node an extra orphan either — the save guard reports the rest.
    expect(appendAnchor(['a', 'b'], [])).toBe('b')
  })
})

describe('upstreamNodeIds', () => {
  it('collects transitive predecessors, not the node itself', () => {
    const edges = [edge('a', 'b'), edge('b', 'c'), edge('c', 'd')]

    expect([...upstreamNodeIds('c', edges)].sort()).toEqual(['a', 'b'])
    expect([...upstreamNodeIds('a', edges)]).toEqual([])
    expect([...upstreamNodeIds('d', edges)].sort()).toEqual(['a', 'b', 'c'])
  })

  it('never includes a downstream node', () => {
    const edges = [edge('a', 'b'), edge('b', 'c')]

    expect(upstreamNodeIds('b', edges).has('c')).toBe(false)
  })

  it('is cycle-safe', () => {
    const edges = [edge('a', 'b'), edge('b', 'a')]

    expect([...upstreamNodeIds('a', edges)]).toEqual(['b'])
  })
})
