import { describe, expect, it } from 'vitest'
import { isProxy, reactive, ref } from 'vue'

import { toJsonPayload } from '@/renderer/utils/jsonPayload'

/**
 * `toJsonPayload` guards the IPC boundary: contextBridge copies arguments with
 * structured-clone semantics and a Vue reactive proxy is NOT cloneable, which
 * surfaced as `DataCloneError: An object could not be cloned.` in the workflow
 * editor's ▶ 运行 (a 多选 input read out of a `reactive()` form).
 */

describe('toJsonPayload', () => {
  it('returns plain, non-proxy data (deep equal, new identity)', () => {
    const source = { definition: { name: 'wf', nodes: [{ id: 'a', params: { url: 'x' } }] }, inputs: {} }
    const payload = toJsonPayload(source)

    expect(payload).toEqual(source)
    expect(payload).not.toBe(source)
    expect(payload.definition).not.toBe(source.definition)
  })

  it('flattens a reactive object (the IPC blocker)', () => {
    const form = reactive({ name: 'wf', nested: { list: [1, 2] } })
    const payload = toJsonPayload({ definition: form })

    expect(isProxy(payload.definition)).toBe(false)
    expect(isProxy(payload.definition.nested)).toBe(false)
    expect(isProxy(payload.definition.nested.list)).toBe(false)
    expect(payload.definition.nested.list).toEqual([1, 2])
  })

  it('flattens the array proxy produced by reading a nested array (多选 input)', () => {
    // 这正是 RunInputsDialog / TaskEditorPage 的写法：
    //   const inputs = reactive({ tags: [] }); payload.tags = inputs.tags
    const inputs = reactive<Record<string, unknown>>({ tags: ['a', 'b'] })
    const payload = { tags: inputs.tags }

    expect(isProxy(payload.tags)).toBe(true) // 直接发出去就会 DataCloneError

    const safe = toJsonPayload(payload)
    expect(isProxy(safe.tags)).toBe(false)
    expect(Array.isArray(safe.tags)).toBe(true)
    expect(safe.tags).toEqual(['a', 'b'])
  })

  it('flattens values read through a ref', () => {
    const meta = ref({ inputs: [{ name: 'tag', type: { base: 'text' }, multi: true }] })
    const safe = toJsonPayload({ definition: { ...meta.value } })

    expect(isProxy(safe.definition.inputs)).toBe(false)
    expect(safe.definition.inputs[0].multi).toBe(true)
  })

  it('passes undefined / null through untouched', () => {
    expect(toJsonPayload(undefined)).toBeUndefined()
    expect(toJsonPayload(null)).toBeNull()
  })

  it('applies JSON semantics (Date → ISO string, NaN → null)', () => {
    const date = new Date('2026-09-29T00:00:00.000Z')
    const safe = toJsonPayload({ at: date, bad: Number.NaN })

    expect(safe.at).toBe('2026-09-29T00:00:00.000Z')
    expect(safe.bad).toBeNull()
  })

  it('throws a readable error instead of a DataCloneError for circular data', () => {
    const circular: Record<string, unknown> = { name: 'wf' }
    circular.self = circular

    expect(() => toJsonPayload(circular)).toThrowError(/not JSON-serializable/)
  })

  it('throws a readable error for functions at the top level', () => {
    expect(() => toJsonPayload(() => undefined)).toThrowError(/not JSON-serializable/)
  })
})
