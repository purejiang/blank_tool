import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deserializeWorkflow,
  serializeWorkflow,
  validateOnDeserialize,
  type WorkflowDefinitionJSON,
  type WorkflowMeta,
} from '@/renderer/components/workflow/serializer'

/**
 * Workflow serializer unit tests (todo 40).
 *
 * Wire contract under test: canvas nodes/edges ⇄ WorkflowDefinition JSON.
 * `next` is the sole source of truth for linear control flow; `edges` must
 * always serialize to [] and is only warned about (never fatal) when found
 * non-empty on deserialize. Positions are canvas-only and recomputed on load
 * (x = 400, y = index * 150).
 */

/** Minimal canvas node factory (vue-flow Node with workflow data payload). */
function makeNode(id: string, tool = 'file.read', extra: Record<string, any> = {}) {
  return {
    id,
    type: 'tool',
    position: { x: 12, y: 34 },
    data: { tool, label: tool, params: {}, ...extra },
  } as any
}

/** Minimal canvas edge factory. */
function makeEdge(source: string, target: string) {
  return { id: `${source}->${target}`, source, target } as any
}

const META: WorkflowMeta = { name: 'wf-test', version: '1.0', description: 'unit test workflow' }

/** A valid 3-node linear wire document (a → b → c). */
function validChainJSON(): WorkflowDefinitionJSON {
  return {
    name: 'wf-chain',
    version: '1.0',
    description: 'linear chain',
    inputs: [],
    outputs: [],
    nodes: [
      { id: 'a', type: 'step', tool: 'net.download', params: { url: 'https://example.com' }, next: 'b', on_failure: 'fail', retry: 0 },
      { id: 'b', type: 'step', tool: 'apk.analyze', params: {}, next: 'c', on_failure: 'fail', retry: 0 },
      { id: 'c', type: 'step', tool: 'file.write', params: {}, next: null, on_failure: 'fail', retry: 0 },
    ],
    edges: [],
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('serializeWorkflow', () => {
  it('serializes 2 nodes + 1 edge into next pointers with edges=[]', () => {
    const nodes = [makeNode('a'), makeNode('b')]
    const edges = [makeEdge('a', 'b')]

    const result = serializeWorkflow(nodes, edges, META)

    expect(result.nodes).toHaveLength(2)
    expect(result.nodes[0].next).toBe('b')
    expect(result.nodes[1].next).toBeNull() // chain end
    expect(result.edges).toEqual([]) // ALWAYS empty in linear mode
    expect(result.name).toBe('wf-test')
  })

  it('serializes a 3-node linear chain with the correct next chain', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [makeEdge('a', 'b'), makeEdge('b', 'c')]

    const result = serializeWorkflow(nodes, edges, META)

    expect(result.nodes.map((n) => n.next)).toEqual(['b', 'c', null])
    expect(result.edges).toEqual([])
  })

  it('serializes an empty canvas as an empty nodes array', () => {
    const result = serializeWorkflow([], [], META)
    expect(result.nodes).toEqual([])
    expect(result.edges).toEqual([])
    expect(result.name).toBe('wf-test')
  })

  it('keeps only the first outgoing edge per node (linear mode)', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [makeEdge('a', 'b'), makeEdge('a', 'c')]

    const result = serializeWorkflow(nodes, edges, META)

    expect(result.nodes[0].next).toBe('b') // first outgoing edge wins
  })

  it('carries node tool/params and applies backend defaults for absent advanced fields', () => {
    const nodes = [makeNode('a', 'net.download', { params: { url: 'https://example.com/app.apk' } })]

    const result = serializeWorkflow(nodes, [], META)

    const node = result.nodes[0]
    expect(node.tool).toBe('net.download')
    expect(node.params).toEqual({ url: 'https://example.com/app.apk' })
    expect(node.type).toBe('step')
    expect(node.on_failure).toBe('fail')
    expect(node.retry).toBe(0)
    expect(node.next).toBeNull()
  })
})

describe('deserializeWorkflow', () => {
  it('roundtrip: serialize then deserialize restores nodes, edges and meta', () => {
    const canvasNodes = [
      makeNode('a', 'net.download', { params: { url: 'https://example.com' } }),
      makeNode('b', 'apk.analyze', { params: { verbose: true } }),
      makeNode('c', 'file.write'),
    ]
    const canvasEdges = [makeEdge('a', 'b'), makeEdge('b', 'c')]

    const json = serializeWorkflow(canvasNodes, canvasEdges, META)
    const restored = deserializeWorkflow(json)

    expect(restored.nodes.map((n) => n.id)).toEqual(['a', 'b', 'c'])
    expect(restored.nodes.map((n) => n.data.tool)).toEqual(['net.download', 'apk.analyze', 'file.write'])
    expect(restored.nodes[0].data.params).toEqual({ url: 'https://example.com' })
    expect(restored.nodes[1].data.params).toEqual({ verbose: true })
    expect(restored.edges).toHaveLength(2)
    expect(restored.edges[0]).toMatchObject({ source: 'a', target: 'b' })
    expect(restored.edges[1]).toMatchObject({ source: 'b', target: 'c' })
    expect(restored.meta.name).toBe('wf-test')
    expect(restored.meta.version).toBe('1.0')
  })

  it('warns when the JSON has a non-empty edges list but still loads (edges rebuilt from next)', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const json = validChainJSON()
    json.edges = [{ source: 'a', target: 'b' }]

    const result = deserializeWorkflow(json)

    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0][0])).toContain('linear mode expects edges: []')
    // Edges come from next, not the stale edges array.
    expect(result.edges).toHaveLength(2)
    expect(result.edges.map((e) => e.id)).toEqual(['a->b', 'b->c'])
  })

  it('auto-layout assigns positions x=400, y=index*150', () => {
    const result = deserializeWorkflow(validChainJSON())

    expect(result.nodes.map((n) => n.position)).toEqual([
      { x: 400, y: 0 },
      { x: 400, y: 150 },
      { x: 400, y: 300 },
    ])
  })

  it('throws an Error listing every structural problem for invalid JSON', () => {
    const json = validChainJSON()
    json.nodes[1].id = 'a' // duplicate id

    expect(() => deserializeWorkflow(json)).toThrowError(/Invalid workflow definition/)
    expect(() => deserializeWorkflow(json)).toThrowError(/duplicate node id: 'a'/)
  })

  it('preserves non-default advanced node fields for roundtrip fidelity', () => {
    const nodes = [
      makeNode('a', 'shell.exec', {
        on_failure: 'skip',
        retry: 2,
        condition: 'inputs.skip != true',
        on_success: 'b',
        type: 'branch',
      }),
      makeNode('b'),
    ]
    const json = serializeWorkflow(nodes, [makeEdge('a', 'b')], META)
    const restored = deserializeWorkflow(json)

    expect(restored.nodes[0].data.on_failure).toBe('skip')
    expect(restored.nodes[0].data.retry).toBe(2)
    expect(restored.nodes[0].data.condition).toBe('inputs.skip != true')
    expect(restored.nodes[0].data.on_success).toBe('b')
    expect(restored.nodes[0].data.type).toBe('branch')
    // Defaults are NOT re-stored on canvas data.
    expect(restored.nodes[1].data.on_failure).toBeUndefined()
    expect(restored.nodes[1].data.retry).toBeUndefined()
  })
})

describe('validateOnDeserialize', () => {
  it('returns no errors for a valid linear workflow', () => {
    expect(validateOnDeserialize(validChainJSON())).toEqual([])
  })

  it('accepts an empty workflow (nodes: []) as valid', () => {
    expect(validateOnDeserialize({ name: 'empty', nodes: [], edges: [] })).toEqual([])
  })

  it('reports duplicate node ids', () => {
    const json = validChainJSON()
    json.nodes[2].id = 'b'

    const errors = validateOnDeserialize(json)
    expect(errors.some((e) => e.includes("duplicate node id: 'b'"))).toBe(true)
  })

  it('reports next references pointing at nonexistent nodes', () => {
    const json = validChainJSON()
    json.nodes[0].next = 'ghost'

    const errors = validateOnDeserialize(json)
    expect(errors.some((e) => e.includes("unknown next node 'ghost'"))).toBe(true)
  })

  it('reports a non-empty edges list as an error (linear mode)', () => {
    const json = validChainJSON()
    json.edges = [{ source: 'a', target: 'b' }]

    const errors = validateOnDeserialize(json)
    expect(errors.some((e) => e.includes("'edges' must be empty in linear mode"))).toBe(true)
  })

  it('reports a missing workflow name', () => {
    const json = validChainJSON()
    ;(json as any).name = ''

    const errors = validateOnDeserialize(json)
    expect(errors.some((e) => e.includes("'name'"))).toBe(true)
  })
})
