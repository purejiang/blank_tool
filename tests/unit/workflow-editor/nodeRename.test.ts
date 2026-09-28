import { describe, expect, it } from 'vitest'

import { renameNodeId } from '@/renderer/components/workflow/nodeRename'

/**
 * Node-id rename: the id is embedded in `$nodes.<id>.…` bindings, so a rename
 * must rewrite the node, its edges and every reference in one shot.
 */

function node(id: string, data: Record<string, any> = {}) {
  return { id, type: 'tool', position: { x: 0, y: 0 }, data }
}

function edge(source: string, target: string) {
  return { id: `${source}->${target}`, source, target }
}

describe('renameNodeId', () => {
  it('renames the node, rewrites its edges and renames references', () => {
    const nodes = [
      node('a', { tool: 'file.read', params: {} }),
      node('b', {
        tool: 'file.write',
        params: { path: '$nodes.a.outputs.text_path', note: 'see ${nodes.a.outputs.text_path} too' },
      }),
    ]
    const result = renameNodeId(nodes, [edge('a', 'b')], 'a', 'reader')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.nodes.map((n) => n.id)).toEqual(['reader', 'b'])
    expect(result.nodes[1].data.params).toEqual({
      path: '$nodes.reader.outputs.text_path',
      note: 'see ${nodes.reader.outputs.text_path} too',
    })
    expect(result.edgesChanged).toBe(1)
    expect(result.bindingsChanged).toBe(2)
    expect(result.edges[0]).toMatchObject({ source: 'reader', target: 'b' })
  })

  it('leaves unrelated nodes untouched (same object identity)', () => {
    const untouched = node('c', { params: { x: 1 } })
    const result = renameNodeId([node('a'), untouched], [], 'a', 'a2')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.nodes[1]).toBe(untouched)
  })

  it('does not rename a prefix-sharing id', () => {
    const nodes = [node('a'), node('b', { params: { p: '$nodes.ab.outputs.x' } })]
    const result = renameNodeId(nodes, [], 'a', 'a2')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    // `nodes.ab.` must survive a rename of `a`.
    expect(result.nodes[1].data.params.p).toBe('$nodes.ab.outputs.x')
  })

  it('rewrites references nested in objects and arrays', () => {
    const nodes = [
      node('a'),
      node('b', { params: { items: [{ cmd: '$nodes.a.outputs.p' }] } }),
    ]
    const result = renameNodeId(nodes, [], 'a', 'z')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.nodes[1].data.params.items[0].cmd).toBe('$nodes.z.outputs.p')
  })

  it('rejects empty, dotted and duplicate ids, and unknown nodes', () => {
    const nodes = [node('a'), node('b')]

    const empty = renameNodeId(nodes, [], 'a', '  ')
    expect(empty.ok).toBe(false)
    expect(empty.error).toBe('empty')

    const dotted = renameNodeId(nodes, [], 'a', 'x.y')
    expect(dotted.ok).toBe(false)
    expect(dotted.error).toBe('dot')

    const duplicate = renameNodeId(nodes, [], 'a', 'b')
    expect(duplicate.ok).toBe(false)
    expect(duplicate.error).toBe('duplicate')

    const missing = renameNodeId(nodes, [], 'ghost', 'c')
    expect(missing.ok).toBe(false)
    expect(missing.error).toBe('missing')

    // Failures never hand back a mutated graph.
    expect(missing.nodes.map((n) => n.id)).toEqual(['a', 'b'])
  })

  it('is a no-op when the id is unchanged', () => {
    const nodes = [node('a', { params: { p: '$nodes.a.outputs.x' } })]
    const result = renameNodeId(nodes, [], 'a', 'a')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.bindingsChanged).toBe(0)
    expect(result.nodes[0].data.params.p).toBe('$nodes.a.outputs.x')
  })
})
