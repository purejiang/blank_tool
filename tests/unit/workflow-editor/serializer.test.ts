import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deserializeWorkflow,
  serializeWorkflow,
  validateOnDeserialize,
  type WorkflowDefinitionJSON,
  type WorkflowMeta,
} from '@/renderer/components/workflow/serializer'
import {
  LAYOUT_X_SPACING,
  LAYOUT_X_START,
  LAYOUT_Y,
} from '@/renderer/components/workflow/graphLayout'
import {
  VIRTUAL_END_ID,
  VIRTUAL_START_ID,
  ensureEndpointGraph,
} from '@/renderer/components/workflow/virtualNodes'

import demoSmoke from '../../../examples/workflows/generic/demo-smoke.json'

/**
 * Workflow serializer unit tests (todo 40).
 *
 * Wire contract under test: canvas nodes/edges ⇄ WorkflowDefinition JSON.
 * `next` is the sole source of truth for linear control flow. Positions are
 * canvas-only and recomputed on load (one horizontal row, left→right — see
 * graphLayout). The retired DAG fields (`edges` / `condition` / `on_success`)
 * are neither emitted nor carried through a load/save round trip.
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
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('serializeWorkflow', () => {
  it('serializes 2 nodes + 1 edge into next pointers', () => {
    const nodes = [makeNode('a'), makeNode('b')]
    const edges = [makeEdge('a', 'b')]

    const result = serializeWorkflow(nodes, edges, META)

    expect(result.nodes).toHaveLength(2)
    expect(result.nodes[0].next).toBe('b')
    expect(result.nodes[1].next).toBeNull() // chain end
    expect(result.name).toBe('wf-test')
    // Retired DAG fields never appear on the wire.
    expect(result).not.toHaveProperty('edges')
    expect(result.nodes[0]).not.toHaveProperty('condition')
    expect(result.nodes[0]).not.toHaveProperty('on_success')
  })

  it('serializes a 3-node linear chain with the correct next chain', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [makeEdge('a', 'b'), makeEdge('b', 'c')]

    const result = serializeWorkflow(nodes, edges, META)

    expect(result.nodes.map((n) => n.next)).toEqual(['b', 'c', null])
  })

  it('serializes an empty canvas as an empty nodes array', () => {
    const result = serializeWorkflow([], [], META)
    expect(result.nodes).toEqual([])
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

  it('drops the canvas-only 开始 / 结束 endpoints (virtualNodes.ts)', () => {
    const nodes = [
      { id: VIRTUAL_START_ID, type: 'start', position: { x: 0, y: 0 }, data: {} } as any,
      makeNode('a'),
      makeNode('b'),
      { id: VIRTUAL_END_ID, type: 'end', position: { x: 900, y: 0 }, data: {} } as any,
    ]
    const edges = [
      makeEdge(VIRTUAL_START_ID, 'a'),
      makeEdge('a', 'b'),
      makeEdge('b', VIRTUAL_END_ID),
    ]

    const result = serializeWorkflow(nodes, edges, META)

    expect(result.nodes.map((n) => n.id)).toEqual(['a', 'b'])
    // 开始 is not a node anymore, so `a` is the entry (nothing points at it) and
    // `b` ends the chain — the endpoint edges must not leak into `next`.
    expect(result.nodes.map((n) => n.next)).toEqual(['b', null])
  })

  it('treats a next pointing at 结束 as "end of chain"', () => {
    const nodes = [makeNode('a'), { id: VIRTUAL_END_ID, type: 'end', position: { x: 0, y: 0 }, data: {} } as any]

    const result = serializeWorkflow(nodes, [makeEdge('a', VIRTUAL_END_ID)], META)

    expect(result.nodes).toHaveLength(1)
    expect(result.nodes[0].next).toBeNull()
  })

  it('produces a definition the loader accepts after wrapping it in endpoints again', () => {
    const real = {
      ...ensureEndpointGraph([makeNode('a'), makeNode('b')], [makeEdge('a', 'b')]),
    }
    const json = serializeWorkflow(real.nodes, real.edges, META)

    expect(validateOnDeserialize(json)).toEqual([])
    expect(deserializeWorkflow(json).nodes.map((n) => n.id)).toEqual(['a', 'b'])
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

  it('warns about retired DAG fields but still loads (edges rebuilt from next)', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const json = validChainJSON() as any
    json.edges = [{ source: 'a', target: 'b' }]
    json.nodes[0].condition = 'inputs.skip != true'
    json.nodes[1].on_success = 'c'

    const result = deserializeWorkflow(json)

    expect(warn).toHaveBeenCalledTimes(1)
    const message = String(warn.mock.calls[0][0])
    expect(message).toContain('retired DAG fields')
    expect(message).toContain("'condition' on node 'a'")
    expect(message).toContain("'on_success' on node 'b'")
    // Edges come from next, not the stale edges array.
    expect(result.edges).toHaveLength(2)
    expect(result.edges.map((e) => e.id)).toEqual(['a->b', 'b->c'])
    // Retired per-node fields are not hydrated onto the canvas either.
    expect(result.nodes[0].data).not.toHaveProperty('condition')
    expect(result.nodes[1].data).not.toHaveProperty('on_success')
  })

  it('does not warn for a document without retired fields', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    deserializeWorkflow(validChainJSON())
    expect(warn).not.toHaveBeenCalled()
  })

  it('auto-layout places the chain on one horizontal row (left → right)', () => {
    const result = deserializeWorkflow(validChainJSON())

    expect(result.nodes.map((n) => n.position)).toEqual([
      { x: LAYOUT_X_START, y: LAYOUT_Y },
      { x: LAYOUT_X_START + LAYOUT_X_SPACING, y: LAYOUT_Y },
      { x: LAYOUT_X_START + 2 * LAYOUT_X_SPACING, y: LAYOUT_Y },
    ])
  })

  it('throws an Error listing every structural problem for invalid JSON', () => {
    const json = validChainJSON()
    json.nodes[1].id = 'a' // duplicate id

    expect(() => deserializeWorkflow(json)).toThrowError(/Invalid workflow definition/)
    expect(() => deserializeWorkflow(json)).toThrowError(/duplicate node id: 'a'/)
  })

  it('preserves node behavior fields and drops retired node fields', () => {
    const nodes = [
      makeNode('a', 'exec.shell', {
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
    // Retired fields are gone from the wire and never come back on the canvas.
    expect(json.nodes[0]).not.toHaveProperty('condition')
    expect(json.nodes[0]).not.toHaveProperty('on_success')
    expect(restored.nodes[0].data).not.toHaveProperty('condition')
    expect(restored.nodes[0].data).not.toHaveProperty('on_success')
    expect(restored.nodes[0].data).not.toHaveProperty('type')
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
    expect(validateOnDeserialize({ name: 'empty', nodes: [] })).toEqual([])
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

  it('ignores a legacy non-empty edges list (it is not part of the schema any more)', () => {
    const json = validChainJSON() as any
    json.edges = [{ source: 'a', target: 'b' }]

    expect(validateOnDeserialize(json)).toEqual([])
  })

  it('reports a missing workflow name', () => {
    const json = validChainJSON()
    ;(json as any).name = ''

    const errors = validateOnDeserialize(json)
    expect(errors.some((e) => e.includes("'name'"))).toBe(true)
  })
})

describe('select/multi port fields (options + multi) — T2', () => {
  it('round-trips a single-select input port (options) through serialize/deserialize', () => {
    const meta: WorkflowMeta = {
      name: 'wf-select',
      inputs: [
        {
          name: 'env',
          type: { base: 'text', subtype: null },
          required: true,
          description: 'target environment',
          options: ['dev', 'staging', 'prod'],
        },
      ],
      outputs: [],
    }

    const json = serializeWorkflow([], [], meta)
    expect(json.inputs?.[0]?.options).toEqual(['dev', 'staging', 'prod'])

    const restored = deserializeWorkflow(json)
    expect(restored.meta.inputs?.[0]?.options).toEqual(['dev', 'staging', 'prod'])
    expect(restored.meta.inputs?.[0]?.required).toBe(true)
  })

  it('round-trips a multi-select input port (multi + options) through serialize/deserialize', () => {
    const meta: WorkflowMeta = {
      name: 'wf-multi',
      inputs: [
        {
          name: 'targets',
          type: { base: 'text', subtype: null },
          required: false,
          options: ['a', 'b'],
          multi: true,
        },
      ],
      outputs: [],
    }

    const json = serializeWorkflow([], [], meta)
    expect(json.inputs?.[0]?.multi).toBe(true)
    expect(json.inputs?.[0]?.options).toEqual(['a', 'b'])

    const restored = deserializeWorkflow(json)
    expect(restored.meta.inputs?.[0]?.multi).toBe(true)
    expect(restored.meta.inputs?.[0]?.options).toEqual(['a', 'b'])
  })

  it('keeps pre-T2 ports (no options/multi keys) backward compatible on deserialize', () => {
    const json: WorkflowDefinitionJSON = {
      name: 'wf-legacy',
      version: '1.0',
      inputs: [{ name: 'path', type: { base: 'file', subtype: null }, required: true }],
      outputs: [],
      nodes: [],
    }

    const restored = deserializeWorkflow(json)
    expect(restored.meta.inputs).toEqual([
      { name: 'path', type: { base: 'file', subtype: null }, required: true },
    ])
  })
})

/**
 * The shipped zero-dependency demo (`examples/workflows/generic/demo-smoke.json`)
 * must survive the canvas round trip: it is the workflow users import first, and
 * the one used to eyeball the editor (endpoints, I/O authoring, run dialog,
 * streamed logs).  Backend-side loadability is covered by the Python sweep
 * (`tests/cli/unit/test_examples_validity.py`); this guards the TS path.
 */
describe('shipped demo example (examples/workflows/generic/demo-smoke.json)', () => {
  const raw = demoSmoke as unknown as WorkflowDefinitionJSON

  it('passes canvas validation and keeps its chain, params and meta', () => {
    expect(validateOnDeserialize(raw)).toEqual([])

    const { nodes, edges, meta } = deserializeWorkflow(raw)

    expect(nodes.map((node) => node.id)).toEqual(raw.nodes.map((node) => node.id))
    expect(edges.map((edge) => `${edge.source}->${edge.target}`)).toEqual([
      'write_sample->scan',
      'scan->log_hits',
      'log_hits->read_sample',
      'read_sample->log_size',
      'log_size->within_limit',
      'within_limit->assert_limit',
    ])

    // Re-serializing must not lose a single param (the `${rundir}`/`$inputs.*`
    // expressions ride through verbatim) nor a declared port.
    const serialized = serializeWorkflow(nodes, edges, meta)
    expect(serialized.nodes.map((node) => ({ id: node.id, params: node.params }))).toEqual(
      raw.nodes.map((node) => ({ id: node.id, params: node.params })),
    )
    expect(serialized.nodes.map((node) => node.next)).toEqual(raw.nodes.map((node) => node.next ?? null))
    expect(serialized.inputs).toEqual(raw.inputs)
    expect(serialized.outputs).toEqual(raw.outputs)
    expect(serialized.name).toBe('demo-smoke')
  })

  it('wraps into 开始 → 7 real nodes → 结束 and drops the endpoints on save', () => {
    const { nodes, edges, meta } = deserializeWorkflow(raw)
    const graph = ensureEndpointGraph(nodes, edges)

    const ids = graph.nodes.map((node) => node.id)
    expect(new Set(ids)).toEqual(new Set([VIRTUAL_START_ID, ...raw.nodes.map((n) => n.id), VIRTUAL_END_ID]))
    // Order-insensitive (the endpoints are appended, not prepended).
    const links = graph.edges.map((edge) => `${edge.source}->${edge.target}`).sort()
    expect(links).toEqual(
      [
        `${VIRTUAL_START_ID}->write_sample`,
        'write_sample->scan',
        'scan->log_hits',
        'log_hits->read_sample',
        'read_sample->log_size',
        'log_size->within_limit',
        'within_limit->assert_limit',
        `assert_limit->${VIRTUAL_END_ID}`,
      ].sort(),
    )

    // Endpoints are canvas-only: saving the wrapped graph emits the same real
    // chain, with `next: null` on the last node (never a virtual id).
    const saved = serializeWorkflow(graph.nodes, graph.edges, meta)
    expect(saved.nodes.map((node) => ({ id: node.id, next: node.next }))).toEqual(
      raw.nodes.map((node) => ({ id: node.id, next: node.next ?? null })),
    )
  })

  it('keeps exercising the run-dialog control matrix (select / multi / number / boolean)', () => {
    const inputs = raw.inputs ?? []
    const byName = Object.fromEntries(inputs.map((port) => [port.name, port]))

    expect(byName.title.type.base).toBe('text')
    expect(byName.keyword.options).toEqual(['ERROR', 'WARN', 'INFO'])
    expect(byName.tags.multi).toBe(true)
    expect(byName.max_matches.type.base).toBe('number')
    expect(byName.recursive.type.base).toBe('boolean')
    // Every referenced `$inputs.*` must be required: the run dialog drops empty
    // optional ports, and the expression engine raises on a missing key
    // (`| default:` cannot rescue it — the pipe never runs).
    for (const port of inputs) expect(port.required).toBe(true)
  })
})
