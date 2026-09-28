import { describe, expect, it } from 'vitest'

import {
  collectBindings,
  completeTrigger,
  findTrigger,
  hasBlockingIssue,
  insertBinding,
  inputPath,
  matchesTrigger,
  nodeOutputPath,
  nodeParamPath,
  removeBinding,
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
