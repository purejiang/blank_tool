import { describe, expect, it } from 'vitest'

import {
  BASE_TYPES,
  isBaseType,
  isPortCompatible,
  validateConnection,
  type PortRef,
} from '@/renderer/components/workflow/PortConnection'

/**
 * Port connection validation tests (todo 40).
 *
 * Contract under test (mirrors backend TypeAnnotation.is_compatible):
 * ports connect iff their base types are known AND equal; subtypes are
 * advisory only and never influence the decision (D7).
 */

function port(nodeId: string, portName: string, base?: string, subtype: string | null = null): PortRef {
  return {
    nodeId,
    portName,
    portType: base === undefined ? undefined : { base, subtype },
  }
}

describe('isPortCompatible (type compatibility matrix)', () => {
  it('file → file is compatible', () => {
    expect(isPortCompatible('file', 'file')).toBe(true)
  })

  it('file → text is NOT compatible', () => {
    expect(isPortCompatible('file', 'text')).toBe(false)
  })

  it('text → text is compatible', () => {
    expect(isPortCompatible('text', 'text')).toBe(true)
  })

  it('json → json is compatible', () => {
    expect(isPortCompatible('json', 'json')).toBe(true)
  })

  it('number → text is NOT compatible', () => {
    expect(isPortCompatible('number', 'text')).toBe(false)
  })

  it('directory → directory is compatible', () => {
    expect(isPortCompatible('directory', 'directory')).toBe(true)
  })

  it('unknown base types are rejected even when equal', () => {
    expect(isPortCompatible('blob', 'blob')).toBe(false)
    expect(isPortCompatible('file', '')).toBe(false)
  })

  it('isBaseType guards the full BaseType enum', () => {
    for (const base of BASE_TYPES) {
      expect(isBaseType(base)).toBe(true)
      expect(isPortCompatible(base, base)).toBe(true)
    }
    expect(isBaseType('bool')).toBe(false) // backend name is 'boolean'
    expect(isBaseType(undefined)).toBe(false)
    expect(isBaseType(null)).toBe(false)
  })
})

describe('validateConnection', () => {
  it('accepts a connection between matching base types', () => {
    const result = validateConnection(port('n1', 'out_file', 'file'), port('n2', 'in_file', 'file'))
    expect(result).toEqual({ valid: true })
  })

  it('rejects incompatible base types with a user-facing reason', () => {
    const result = validateConnection(port('n1', 'out', 'file'), port('n2', 'in', 'text'))

    expect(result.valid).toBe(false)
    expect(result.reason).toContain('Incompatible types')
    expect(result.reason).toContain('file')
    expect(result.reason).toContain('text')
  })

  it('includes the subtype in the rejection label (advisory display only)', () => {
    const result = validateConnection(
      port('n1', 'out', 'file', 'apk'),
      port('n2', 'in', 'text'),
    )

    expect(result.valid).toBe(false)
    expect(result.reason).toContain('file/apk → text')
  })

  it('rejects a source port with no type information', () => {
    const result = validateConnection(port('n1', 'mystery'), port('n2', 'in', 'file'))

    expect(result.valid).toBe(false)
    expect(result.reason).toContain('no type information')
    expect(result.reason).toContain('mystery')
  })

  it('rejects a target port with no type information', () => {
    const result = validateConnection(port('n1', 'out', 'file'), port('n2', 'mystery'))

    expect(result.valid).toBe(false)
    expect(result.reason).toContain('no type information')
  })
})
