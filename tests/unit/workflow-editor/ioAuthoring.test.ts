import { describe, expect, it } from 'vitest'

import {
  IO_ERRORS,
  PORT_TYPE_KEYS,
  commitPort,
  createEmptyDraft,
  draftFromPort,
  portFromDraft,
  portJsonToTypeKey,
  removePortByName,
  typeKeyUsesOptions,
  type PortDraft,
  type PortTypeKey,
} from '@/renderer/components/workflow/ioAuthoring'
import {
  deserializeWorkflow,
  serializeWorkflow,
  type PortJSON,
  type WorkflowMeta,
} from '@/renderer/components/workflow/serializer'

/**
 * Workflow-level inputs/outputs authoring tests (T6).
 *
 * Contract under test: the pure authoring helpers that the editor panel uses
 * to add/edit/remove workflow-level ports on `meta.inputs` / `meta.outputs`,
 * including the 8-way UI type model (no SELECT BaseType exists on the wire —
 * 单选/多选 are carried as base 'text' + options [+ multi], T2 constraint)
 * and the snake_case name rules enforced by the backend.
 *
 * Every persistence assertion runs the real serialize → deserialize round-trip
 * and compares EXACT shapes (options array values, multi flag values) — not
 * mere presence — so silently dropped fields cannot pass.
 */

/** Build a minimal draft; tests override what they care about. */
function makeDraft(overrides: Partial<PortDraft> = {}): PortDraft {
  return { ...createEmptyDraft(), ...options(overrides) }
}

/** Defaults the options array per draft so callers can spread safely. */
function options(overrides: Partial<PortDraft>): Partial<PortDraft> {
  return { options: [], ...overrides }
}

/** serialize → deserialize round-trip of a meta doc with the given ports. */
function roundTrip(meta: WorkflowMeta): WorkflowMeta {
  const json = serializeWorkflow([], [], meta)
  return deserializeWorkflow(json).meta
}

describe('type model — 8 UI choices map to the wire format', () => {
  it('PORT_TYPE_KEYS exposes exactly the 8 decision-complete choices', () => {
    expect(PORT_TYPE_KEYS).toEqual([
      'file',
      'directory',
      'text',
      'number',
      'boolean',
      'json',
      'single_select',
      'multi_select',
    ])
  })

  it.each([
    ['file', 'file'],
    ['directory', 'directory'],
    ['text', 'text'],
    ['number', 'number'],
    ['boolean', 'boolean'],
    ['json', 'json'],
  ] as [PortTypeKey, string][])('%s → type.base %s without options/multi', (typeKey, base) => {
    const port = portFromDraft(makeDraft({ name: 'p', typeKey }))

    expect(port.type.base).toBe(base)
    expect(port.options).toBeUndefined()
    expect(port.multi).toBeUndefined()
  })

  it('单选 (single_select) → base text + options, no multi flag', () => {
    const port = portFromDraft(
      makeDraft({ name: 'env', typeKey: 'single_select', options: ['dev', 'staging', 'prod'] }),
    )

    expect(port.type.base).toBe('text')
    expect(port.options).toEqual(['dev', 'staging', 'prod'])
    expect(port.multi).toBeUndefined()
  })

  it('多选 (multi_select) → base text + options + multi:true', () => {
    const port = portFromDraft(
      makeDraft({ name: 'targets', typeKey: 'multi_select', options: ['a', 'b'] }),
    )

    expect(port.type.base).toBe('text')
    expect(port.options).toEqual(['a', 'b'])
    expect(port.multi).toBe(true)
  })

  it('typeKeyUsesOptions is true only for the two select kinds', () => {
    for (const key of PORT_TYPE_KEYS) {
      const expected = key === 'single_select' || key === 'multi_select'
      expect(typeKeyUsesOptions(key)).toBe(expected)
    }
  })
})

describe('reverse mapping — wire PortJSON back to the UI type key', () => {
  function wirePort(partial: Partial<PortJSON> = {}): PortJSON {
    return { name: 'p', type: { base: 'text' }, ...partial }
  }

  it('base text + options + multi:true → 多选', () => {
    expect(portJsonToTypeKey(wirePort({ options: ['a'], multi: true }))).toBe('multi_select')
  })

  it('base text + non-empty options → 单选', () => {
    expect(portJsonToTypeKey(wirePort({ options: ['a', 'b'] }))).toBe('single_select')
  })

  it('base text + empty options → plain text (empty options are not a select)', () => {
    expect(portJsonToTypeKey(wirePort({ options: [] }))).toBe('text')
  })

  it('base text without options → text', () => {
    expect(portJsonToTypeKey(wirePort())).toBe('text')
  })

  it('non-select bases map to themselves', () => {
    expect(portJsonToTypeKey(wirePort({ type: { base: 'file' } }))).toBe('file')
    expect(portJsonToTypeKey(wirePort({ type: { base: 'directory' } }))).toBe('directory')
    expect(portJsonToTypeKey(wirePort({ type: { base: 'number' } }))).toBe('number')
    expect(portJsonToTypeKey(wirePort({ type: { base: 'boolean' } }))).toBe('boolean')
    expect(portJsonToTypeKey(wirePort({ type: { base: 'json' } }))).toBe('json')
  })

  it('unknown bases degrade to text, mirroring the run-dialog portBase()', () => {
    expect(portJsonToTypeKey(wirePort({ type: { base: 'list' } }))).toBe('text')
    expect(portJsonToTypeKey(wirePort({ type: { base: '' } }))).toBe('text')
  })

  it('draftFromPort reconstructs an editable draft from every wire shape', () => {
    const select = wirePort({
      name: 'env',
      required: false,
      description: 'target env',
      options: ['dev', 'prod'],
    })
    expect(draftFromPort(select)).toEqual({
      name: 'env',
      typeKey: 'single_select',
      required: false,
      description: 'target env',
      options: ['dev', 'prod'],
    })

    const file = wirePort({ name: 'apk_path', type: { base: 'file' }, required: true })
    expect(draftFromPort(file)).toEqual({
      name: 'apk_path',
      typeKey: 'file',
      required: true,
      description: '',
      options: [],
    })
  })
})

describe('commitPort — add/edit ports (acceptance criteria a–e)', () => {
  it('(a) adds a text input port into meta.inputs and survives serialize→deserialize', () => {
    // Given a workflow meta without inputs
    const meta: WorkflowMeta = { name: 'wf-io', inputs: [], outputs: [] }
    // When committing a new text input draft
    const result = commitPort(
      meta.inputs ?? [],
      makeDraft({ name: 'apk_path', typeKey: 'text', required: true, description: 'path to the apk' }),
    )
    // Then no validation error and the port lands in meta.inputs
    expect(result.error).toBeNull()
    meta.inputs = result.ports

    // And the exact shape survives the persist path to template.save and back
    const restored = roundTrip(meta)
    expect(restored.inputs).toEqual([
      { name: 'apk_path', type: { base: 'text' }, required: true, description: 'path to the apk' },
    ])
  })

  it('(b) a 单选 port with 3 options keeps its options array intact through round-trip', () => {
    const meta: WorkflowMeta = { name: 'wf-select', inputs: [], outputs: [] }
    const result = commitPort(
      meta.inputs ?? [],
      makeDraft({ name: 'env', typeKey: 'single_select', required: true, options: ['dev', 'staging', 'prod'] }),
    )
    expect(result.error).toBeNull()
    meta.inputs = result.ports

    const restored = roundTrip(meta)
    // Exact values, exact order — not just presence.
    expect(restored.inputs?.[0]?.options).toEqual(['dev', 'staging', 'prod'])
    expect(restored.inputs?.[0]?.multi).not.toBe(true)
    expect(restored.inputs?.[0]?.type.base).toBe('text')
    // And the editor would reopen it as 单选 again.
    expect(portJsonToTypeKey(restored.inputs![0])).toBe('single_select')
  })

  it('(c) a 多选 port keeps multi:true and its options through round-trip', () => {
    const meta: WorkflowMeta = { name: 'wf-multi', inputs: [], outputs: [] }
    const result = commitPort(
      meta.inputs ?? [],
      makeDraft({ name: 'targets', typeKey: 'multi_select', required: false, options: ['x86', 'arm64'] }),
    )
    expect(result.error).toBeNull()
    meta.inputs = result.ports

    const restored = roundTrip(meta)
    expect(restored.inputs?.[0]?.multi).toBe(true)
    expect(restored.inputs?.[0]?.options).toEqual(['x86', 'arm64'])
    expect(portJsonToTypeKey(restored.inputs![0])).toBe('multi_select')
  })

  it('(d) rejects a duplicate port name within inputs with an error message', () => {
    const inputs: PortJSON[] = [{ name: 'apk_path', type: { base: 'file' }, required: true }]

    const result = commitPort(inputs, makeDraft({ name: 'apk_path', typeKey: 'text' }))

    expect(result.error).toBe(IO_ERRORS.nameDuplicate)
    expect(result.ports).toBeUndefined() // nothing saved
  })

  it('(d) rejects duplicates within outputs independently of inputs', () => {
    const outputs: PortJSON[] = [{ name: 'report', type: { base: 'file' } }]

    const dup = commitPort(outputs, makeDraft({ name: 'report', typeKey: 'text' }))
    expect(dup.error).toBe(IO_ERRORS.nameDuplicate)

    // The SAME name is fine on the other side — inputs and outputs are separate lists.
    const ok = commitPort([], makeDraft({ name: 'report', typeKey: 'text' }))
    expect(ok.error).toBeNull()
  })

  it('(e) removed ports stay gone after round-trip', () => {
    // Given two inputs and one output
    const meta: WorkflowMeta = {
      name: 'wf-remove',
      inputs: [
        { name: 'first', type: { base: 'text' }, required: true },
        { name: 'second', type: { base: 'number' }, required: false },
      ],
      outputs: [{ name: 'result_file', type: { base: 'file' } }],
    }
    // When removing 'first'
    meta.inputs = removePortByName(meta.inputs ?? [], 'first')

    // Then the survivor round-trips alone
    const restored = roundTrip(meta)
    expect(restored.inputs).toEqual([{ name: 'second', type: { base: 'number' }, required: false }])
    expect(restored.outputs).toEqual([{ name: 'result_file', type: { base: 'file' } }])
  })

  it('editing a port while keeping its name does not trip the duplicate check', () => {
    const inputs: PortJSON[] = [{ name: 'env', type: { base: 'text' }, required: true }]

    const result = commitPort(
      inputs,
      makeDraft({ name: 'env', typeKey: 'single_select', options: ['a', 'b'] }),
      'env',
    )

    expect(result.error).toBeNull()
    expect(result.ports).toHaveLength(1)
    expect(result.ports![0].options).toEqual(['a', 'b'])
  })

  it('editing preserves the port position within the list (rename in place)', () => {
    const inputs: PortJSON[] = [
      { name: 'a', type: { base: 'text' } },
      { name: 'b', type: { base: 'text' } },
      { name: 'c', type: { base: 'text' } },
    ]

    const result = commitPort(inputs, makeDraft({ name: 'b2', typeKey: 'text' }), 'b')

    expect(result.error).toBeNull()
    expect(result.ports!.map((p) => p.name)).toEqual(['a', 'b2', 'c'])
  })

  it('adding appends after existing ports', () => {
    const inputs: PortJSON[] = [{ name: 'a', type: { base: 'text' } }]

    const result = commitPort(inputs, makeDraft({ name: 'z', typeKey: 'text' }))

    expect(result.error).toBeNull()
    expect(result.ports!.map((p) => p.name)).toEqual(['a', 'z'])
  })

  it('never mutates the caller-provided port array (immutable updates)', () => {
    const inputs: PortJSON[] = [
      { name: 'a', type: { base: 'text' }, options: ['keep'] },
    ]
    const before = JSON.stringify(inputs)

    commitPort(inputs, makeDraft({ name: 'b', typeKey: 'text' }))
    removePortByName(inputs, 'a')

    expect(JSON.stringify(inputs)).toBe(before)
  })
})

describe('validation — malformed input never saves', () => {
  it('rejects an empty/whitespace name', () => {
    expect(commitPort([], makeDraft({ name: '' })).error).toBe(IO_ERRORS.nameRequired)
    expect(commitPort([], makeDraft({ name: '   ' })).error).toBe(IO_ERRORS.nameRequired)
  })

  it.each(['Bad-Name', 'UPPER', '1abc', 'foo-bar', 'has space', '中文', '_leading'])(
    'rejects %s (must match ^[a-z][a-z0-9_]*$)',
    (name) => {
      expect(commitPort([], makeDraft({ name })).error).toBe(IO_ERRORS.nameInvalid)
    },
  )

  it('accepts valid snake_case names (trimmed)', () => {
    expect(commitPort([], makeDraft({ name: 'apk_path' })).error).toBeNull()
    expect(commitPort([], makeDraft({ name: 'a' })).error).toBeNull()
    expect(commitPort([], makeDraft({ name: '  out_apk  ' })).error).toBeNull()
    // Trimmed name is what gets stored.
    const result = commitPort([], makeDraft({ name: '  out_apk  ' }))
    expect(result.ports![0].name).toBe('out_apk')
  })

  it('rejects select kinds with no usable option', () => {
    expect(commitPort([], makeDraft({ name: 'env', typeKey: 'single_select', options: [] })).error)
      .toBe(IO_ERRORS.optionsRequired)
    expect(commitPort([], makeDraft({ name: 'env', typeKey: 'multi_select', options: ['', '  '] })).error)
      .toBe(IO_ERRORS.optionsRequired)
  })

  it('trims options and drops empty ones on commit', () => {
    const result = commitPort(
      [],
      makeDraft({ name: 'env', typeKey: 'single_select', options: [' dev ', '', 'prod'] }),
    )

    expect(result.error).toBeNull()
    expect(result.ports![0].options).toEqual(['dev', 'prod'])
  })

  it('non-select kinds never carry options even if the draft has leftovers', () => {
    const result = commitPort(
      [],
      makeDraft({ name: 'count', typeKey: 'number', options: ['leftover'] }),
    )

    expect(result.error).toBeNull()
    expect(result.ports![0].options).toBeUndefined()
  })

  it('stores required and description verbatim; omits empty description', () => {
    const withDesc = commitPort(
      [],
      makeDraft({ name: 'a', typeKey: 'text', required: true, description: '  keep me  ' }),
    )
    expect(withDesc.ports![0].required).toBe(true)
    expect(withDesc.ports![0].description).toBe('keep me')

    const noDesc = commitPort([], makeDraft({ name: 'b', typeKey: 'text', required: false, description: '  ' }))
    expect(noDesc.ports![0].required).toBe(false)
    expect(noDesc.ports![0].description).toBeUndefined()
  })
})

describe('removePortByName', () => {
  it('removes only the named port', () => {
    const ports: PortJSON[] = [
      { name: 'a', type: { base: 'text' } },
      { name: 'b', type: { base: 'text' } },
    ]

    expect(removePortByName(ports, 'a').map((p) => p.name)).toEqual(['b'])
  })

  it('returns an equivalent list when the name does not exist', () => {
    const ports: PortJSON[] = [{ name: 'a', type: { base: 'text' } }]

    expect(removePortByName(ports, 'ghost')).toEqual(ports)
  })
})
