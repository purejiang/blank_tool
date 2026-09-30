import { describe, expect, it } from 'vitest'

import {
  baseOfTypeKey,
  buildReferenceGroups,
  collectBindings,
  completeTrigger,
  describeBindingToken,
  findTrigger,
  hasBlockingIssue,
  insertBinding,
  insertBindingAt,
  inputPath,
  matchesTrigger,
  nodeOutputPath,
  nodeParamPath,
  removeBinding,
  sortByCompatibility,
  splitPipes,
  toInterpolationRef,
  toWholeValueRef,
  validateValue,
  withPipes,
  type BindingContext,
} from '@/renderer/components/workflow/expressionBinding'

/**
 * Expression-binding unit tests: the insertion rules (whole value vs
 * interpolation), trigger detection for the `$`-type-ahead, scanning, and the
 * static validation that mirrors cli/app/workflow/expression.py.
 */

const CTX: BindingContext = {
  inputNames: ['target_dir', 'min_matches'],
  nodes: {
    scan: {
      label: 'scan',
      tool: 'text.grep',
      outputs: [
        { name: 'count', type: { base: 'number', subtype: null } },
        { name: 'matches_path', type: { base: 'file', subtype: null } },
      ],
      paramKeys: ['pattern', 'source'],
    },
    write: { label: 'write', tool: 'file.write', outputs: [{ name: 'written_path', type: { base: 'file' } }] },
  },
  upstreamIds: ['scan'],
  targetBase: 'file',
}

describe('reference builders', () => {
  it('builds whole-value and interpolation forms', () => {
    expect(toWholeValueRef('inputs.target_dir')).toBe('$inputs.target_dir')
    expect(toInterpolationRef('inputs.target_dir')).toBe('${inputs.target_dir}')
  })

  it('appends pipes verbatim', () => {
    expect(withPipes('nodes.scan.outputs.count', ['basename', 'default:0'])).toBe(
      'nodes.scan.outputs.count | basename | default:0',
    )
    expect(toWholeValueRef('nodes.a.outputs.p', ['basename'])).toBe('$nodes.a.outputs.p | basename')
    expect(toInterpolationRef('nodes.a.outputs.p', ['dirname'])).toBe('${nodes.a.outputs.p | dirname}')
  })

  it('builds paths for inputs, node outputs and node params', () => {
    expect(inputPath('target_dir')).toBe('inputs.target_dir')
    expect(nodeOutputPath('scan', 'count')).toBe('nodes.scan.outputs.count')
    expect(nodeParamPath('scan', 'pattern')).toBe('nodes.scan.params.pattern')
  })
})

describe('insertBinding', () => {
  it('inserts a whole-value reference into an empty field (type preserved)', () => {
    expect(insertBinding('', 'nodes.scan.outputs.count')).toBe('$nodes.scan.outputs.count')
    expect(insertBinding(undefined, 'inputs.target_dir')).toBe('$inputs.target_dir')
    expect(insertBinding('   ', 'inputs.target_dir')).toBe('$inputs.target_dir')
  })

  it('appends an interpolation when the field already has text', () => {
    expect(insertBinding('report-', 'inputs.target_dir')).toBe('report- ${inputs.target_dir}')
    expect(insertBinding('report ', 'inputs.target_dir')).toBe('report ${inputs.target_dir}')
  })

  it('completes a typed trigger instead of appending', () => {
    expect(insertBinding('$inp', 'inputs.target_dir')).toBe('$inputs.target_dir')
    expect(insertBinding('x ${nod', 'nodes.scan.outputs.count')).toBe('x ${nodes.scan.outputs.count}')
  })

  it('never produces a bare expression mixed with text', () => {
    // A whole-value expression with surrounding text would be a literal string
    // at runtime, so the mixed case must use `${...}`.
    expect(insertBinding('a', 'nodes.scan.outputs.count')).toContain('${nodes.scan.outputs.count}')
  })
})

describe('findTrigger', () => {
  it('detects a bare whole-value trigger and its fragment', () => {
    expect(findTrigger('$inp')).toEqual({ start: 0, fragment: 'inp', interpolation: false })
    expect(findTrigger('prefix $nod')).toEqual({ start: 7, fragment: 'nod', interpolation: false })
  })

  it('detects an open interpolation', () => {
    expect(findTrigger('${nod')).toEqual({ start: 0, fragment: 'nod', interpolation: true })
    expect(findTrigger('a ${inputs.tar')).toEqual({ start: 2, fragment: 'inputs.tar', interpolation: true })
  })

  it('ignores escaped dollars and non-trigger text', () => {
    expect(findTrigger('$${HOME}')).toBeNull()
    expect(findTrigger('plain text')).toBeNull()
    expect(findTrigger('$inputs.a and')).toBeNull()
  })

  it('filters candidates by fragment (full path or last segment)', () => {
    const trigger = findTrigger('$apks')
    expect(matchesTrigger('nodes.convert.outputs.apks_path', trigger)).toBe(true)
    expect(matchesTrigger('nodes.convert.outputs.count', trigger)).toBe(false)
    expect(matchesTrigger('anything', null)).toBe(true)
  })

  it('completeTrigger keeps the whole-value form only when nothing precedes', () => {
    const empty = findTrigger('$co')
    expect(empty && completeTrigger('$co', empty, 'nodes.scan.outputs.count')).toBe(
      '$nodes.scan.outputs.count',
    )
    const inside = findTrigger('result-${co')
    expect(inside && completeTrigger('result-${co', inside, 'nodes.scan.outputs.count')).toBe(
      'result-${nodes.scan.outputs.count}',
    )
  })
})

describe('collectBindings', () => {
  it('finds interpolations anywhere in a value', () => {
    const tokens = collectBindings('a ${nodes.scan.outputs.count} b ${inputs.x}')
    expect(tokens.map((token) => token.path)).toEqual(['nodes.scan.outputs.count', 'inputs.x'])
    expect(tokens.every((token) => token.wholeValue === false)).toBe(true)
  })

  it('treats a bare leading expression as one whole-value binding', () => {
    const tokens = collectBindings('$nodes.scan.outputs.count | basename')
    expect(tokens).toHaveLength(1)
    expect(tokens[0].wholeValue).toBe(true)
    expect(tokens[0].path).toBe('nodes.scan.outputs.count')
    expect(tokens[0].pipes).toEqual(['basename'])
  })

  it('does not report a bare expression when interpolations are present (it is literal text)', () => {
    const tokens = collectBindings('$nodes.a.outputs.b ${inputs.x}')
    expect(tokens.map((token) => token.raw)).toEqual(['${inputs.x}'])
  })

  it('skips escaped interpolation markers', () => {
    expect(collectBindings('$${HOME}')).toEqual([])
  })

  it('splits pipes off the expression body', () => {
    expect(splitPipes('nodes.a.outputs.b | dirname | default:x')).toEqual({
      path: 'nodes.a.outputs.b',
      pipes: ['dirname', 'default:x'],
    })
  })

  it('removes a token for the chip affordance', () => {
    const value = 'found ${nodes.scan.outputs.count} matches'
    const [token] = collectBindings(value)
    expect(removeBinding(value, token)).toBe('found matches')
  })
})

describe('validateValue', () => {
  it('accepts plain values without bindings', () => {
    expect(validateValue('hello', CTX)).toEqual([])
    expect(validateValue(42, CTX)).toEqual([])
  })

  it('accepts resolvable references', () => {
    expect(validateValue('$inputs.target_dir', CTX)).toEqual([])
    expect(validateValue('$nodes.scan.outputs.matches_path', CTX)).toEqual([])
    expect(validateValue('${workdir}/x', CTX)).toEqual([])
    expect(validateValue('$rundir', CTX)).toEqual([])
    expect(validateValue('$env.HOME', CTX)).toEqual([])
  })

  it('rejects unknown roots and private components', () => {
    expect(validateValue('$foo.bar', CTX).map((i) => i.code)).toEqual(['unknownRoot'])
    expect(validateValue('$nodes.scan.__class__', CTX).map((i) => i.code)).toEqual(['privateAccess'])
  })

  it('rejects malformed templates', () => {
    expect(validateValue('${nodes.a.outputs.b', CTX).map((i) => i.code)).toEqual([
      'unterminatedInterpolation',
    ])
    expect(validateValue('${}', CTX).map((i) => i.code)).toEqual(['emptyExpression'])
    expect(validateValue('$inputs.a.b', CTX).map((i) => i.code)).toEqual(['malformedPath'])
    expect(validateValue('$workdir.sub', CTX).map((i) => i.code)).toEqual(['rootTakesNoKeys'])
    // `count` is a number and the target is a file → the warning is expected
    // alongside the pipe error (both are reported, piping does not mask it).
    expect(validateValue('$nodes.scan.outputs.count | nope', CTX).map((i) => i.code)).toEqual([
      'typeMismatch',
      'unknownPipe',
    ])
  })

  it('rejects references to unknown or downstream nodes (runtime missing node)', () => {
    expect(validateValue('$nodes.ghost.outputs.x', CTX).map((i) => i.code)).toEqual(['unknownNode'])
    expect(validateValue('$nodes.write.outputs.written_path', CTX).map((i) => i.code)).toEqual([
      'notUpstream',
    ])
  })

  it('warns about unknown ports, keys, inputs and type mismatches', () => {
    const unknownPort = validateValue('$nodes.scan.outputs.nope', CTX)
    expect(unknownPort.map((i) => i.code)).toEqual(['unknownOutputPort'])
    expect(unknownPort[0].severity).toBe('warning')

    expect(validateValue('$nodes.scan.params.nope', CTX).map((i) => i.code)).toEqual([
      'unknownParamKey',
    ])
    expect(validateValue('$inputs.nope', CTX).map((i) => i.code)).toEqual(['unknownInput'])

    // matches_path is a file → compatible with a file target; count is a number.
    expect(validateValue('$nodes.scan.outputs.matches_path', CTX)).toEqual([])
    const mismatch = validateValue('$nodes.scan.outputs.count', CTX)
    expect(mismatch.map((i) => i.code)).toEqual(['typeMismatch'])
    expect(mismatch[0].severity).toBe('warning')
  })

  it('warns when a bare expression is mixed with interpolation (it stays literal)', () => {
    const issues = validateValue('$nodes.scan.outputs.count and ${inputs.x}', CTX)
    expect(issues.map((i) => i.code)).toContain('mixedBindingForms')
    expect(issues.find((i) => i.code === 'mixedBindingForms')?.severity).toBe('warning')
  })

  it('uses i18n message keys and reports blocking issues', () => {
    const errors = validateValue('$foo.bar', CTX)
    expect(errors[0].messageKey).toBe('workflow.editor.binding.errors.unknownRoot')
    expect(hasBlockingIssue(errors)).toBe(true)
    expect(hasBlockingIssue(validateValue('$inputs.nope', CTX))).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Candidate discovery (the picker's data source)
// ---------------------------------------------------------------------------

const UPSTREAM = [
  {
    id: 'node-a',
    label: '解压 APK',
    tool: 'apktool',
    outputs: [
      { name: 'apk_path', type: { base: 'file', subtype: 'apk' } },
      { name: 'force', type: { base: 'boolean', subtype: null } },
    ],
    paramKeys: ['sdk', 'sdk'],
  },
]

describe('buildReferenceGroups', () => {
  it('groups workflow inputs, one group per upstream node, and runtime', () => {
    const groups = buildReferenceGroups(
      [
        { name: 'target', type: { base: 'file', subtype: null } },
        { name: 'mode', type: { base: 'text', subtype: null }, options: ['a', 'b'] } as never,
      ],
      UPSTREAM,
    )

    expect(groups.map((g) => g.key)).toEqual(['inputs', 'node:node-a', 'runtime'])
    expect(groups[0].items.map((i) => i.path)).toEqual(['inputs.target', 'inputs.mode'])
    // Select-like ports are recognized by the same reverse mapping the panel uses.
    expect(groups[0].items[1].typeKey).toBe('single_select')

    const nodeGroup = groups[1]
    expect(nodeGroup.nodeLabel).toBe('解压 APK')
    expect(nodeGroup.nodeTool).toBe('apktool')
    expect(nodeGroup.items.map((i) => i.kind)).toEqual(['output', 'output', 'param', 'param'])
    expect(nodeGroup.items[0].path).toBe('nodes.node-a.outputs.apk_path')
    expect(nodeGroup.items[0].typeKey).toBe('file')
    expect(nodeGroup.items[0].subtype).toBe('apk')
    expect(nodeGroup.items[0].detail).toBe('file/apk')
    expect(nodeGroup.items[2].path).toBe('nodes.node-a.params.sdk')

    // Runtime group: two real candidates plus the "type an env name" entry.
    expect(groups[2].items.map((i) => i.kind)).toEqual(['runtime', 'runtime', 'env'])
    expect(groups[2].items[0].runtimeKey).toBe('workdir')
  })

  it('omits empty groups', () => {
    expect(buildReferenceGroups([], []).map((g) => g.key)).toEqual(['runtime'])
  })

  it('skips malformed ports and nodes', () => {
    const groups = buildReferenceGroups(
      [{ name: '' } as never, null as never],
      [{ id: '', outputs: [] } as never, { id: 'b', outputs: [{ name: '' } as never] }],
    )
    expect(groups.map((g) => g.key)).toEqual(['runtime'])
  })
})

describe('sortByCompatibility', () => {
  const items = [
    { path: 'nodes.a.outputs.count', label: 'count', group: 'nodes', kind: 'output', typeKey: 'number' },
    { path: 'nodes.a.outputs.path', label: 'path', group: 'nodes', kind: 'output', typeKey: 'file' },
  ]

  it('puts compatible candidates first', () => {
    const sorted = sortByCompatibility(items as never, 'file')
    expect(sorted.map((i) => i.path)).toEqual(['nodes.a.outputs.path', 'nodes.a.outputs.count'])
  })

  it('keeps the input order when the target type is unknown', () => {
    expect(sortByCompatibility(items as never, null).map((i) => i.path)).toEqual(
      items.map((i) => i.path),
    )
  })

  it('orders compatible first, unknown-type next, incompatible last', () => {
    const mixed = [
      ...items,
      { path: 'nodes.a.params.sdk', label: 'sdk', group: 'nodes', kind: 'param' },
    ]
    const sorted = sortByCompatibility(mixed as never, 'file')
    expect(sorted.map((i) => i.path)).toEqual([
      'nodes.a.outputs.path', // compatible (file)
      'nodes.a.params.sdk', // unknown type: neither promoted nor demoted
      'nodes.a.outputs.count', // incompatible (number)
    ])
  })
})

describe('baseOfTypeKey', () => {
  it('maps both select kinds back onto text', () => {
    expect(baseOfTypeKey('single_select')).toBe('text')
    expect(baseOfTypeKey('multi_select')).toBe('text')
    expect(baseOfTypeKey('file')).toBe('file')
  })
})

describe('describeBindingToken', () => {
  const ctx = { nodes: { 'node-a': { label: '解压 APK' } }, inputs: ['target'] }

  it('describes workflow inputs, env vars and runtime roots', () => {
    expect(describeBindingToken({ path: 'inputs.target', pipes: [] }, ctx)).toMatchObject({
      messageKey: 'workflow.editor.binding.chip.input',
      params: { name: 'target' },
    })
    expect(describeBindingToken({ path: 'env.PATH', pipes: [] }, ctx).messageKey).toBe(
      'workflow.editor.binding.chip.env',
    )
    expect(describeBindingToken({ path: 'workdir', pipes: [] }, ctx).messageKey).toBe(
      'workflow.editor.binding.chip.workdir',
    )
    expect(describeBindingToken({ path: 'rundir', pipes: [] }, ctx).messageKey).toBe(
      'workflow.editor.binding.chip.rundir',
    )
  })

  it('uses the node display name for node references', () => {
    const label = describeBindingToken({ path: 'nodes.node-a.outputs.apk_path', pipes: [] }, ctx)
    expect(label.messageKey).toBe('workflow.editor.binding.chip.output')
    expect(label.params).toMatchObject({ node: '解压 APK', name: 'apk_path' })

    const param = describeBindingToken({ path: 'nodes.node-a.params.sdk', pipes: [] }, ctx)
    expect(param.messageKey).toBe('workflow.editor.binding.chip.param')
  })

  it('falls back to the raw expression for unknown shapes and keeps pipes visible', () => {
    // Unknown node → the id stands in for the display name (still readable).
    const unknownNode = describeBindingToken({ path: 'nodes.x.outputs.y', pipes: [] }, { nodes: {} })
    expect(unknownNode.messageKey).toBe('workflow.editor.binding.chip.output')
    expect(unknownNode.params.node).toBe('x')

    // A shape the engine accepts but this helper does not know → raw text.
    const unknownShape = describeBindingToken({ path: 'something.else', pipes: [] }, { nodes: {} })
    expect(unknownShape.messageKey).toBe('')
    expect(unknownShape.raw).toBe('$something.else')

    const piped = describeBindingToken({ path: 'workdir', pipes: ['basename'] }, ctx)
    expect(piped.params.pipes).toBe(' · basename')
  })
})

describe('insertBindingAt', () => {
  it('inserts at the caret inside existing text as an interpolation', () => {
    const result = insertBindingAt('echo  > log.txt', 'inputs.target', null, { start: 5, end: 5 })
    expect(result.value).toBe('echo ${inputs.target} > log.txt')
    expect(result.caret).toBe('echo ${inputs.target}'.length)
  })

  it('replaces the selection', () => {
    const result = insertBindingAt('echo OLD', 'inputs.target', [], { start: 5, end: 8 })
    expect(result.value).toBe('echo ${inputs.target}')
  })

  it('keeps the whole-value form for an effectively empty field', () => {
    expect(insertBindingAt('   ', 'inputs.target', null, { start: 3, end: 3 }).value).toBe(
      '$inputs.target',
    )
  })

  it('completes a `$` trigger typed right before the caret', () => {
    const result = insertBindingAt('$inp', 'inputs.target', null, { start: 4, end: 4 })
    expect(result.value).toBe('$inputs.target')
    expect(result.caret).toBe(result.value.length)
  })

  it('falls back to insertBinding without a selection', () => {
    expect(insertBindingAt('', 'inputs.target', null, null).value).toBe('$inputs.target')
    expect(insertBindingAt('echo', 'inputs.target', null, null).value).toBe(
      'echo ${inputs.target}',
    )
  })
})
