/**
 * Full locale parity — repo convention: "UI 文案改动需同步两个语言文件".
 *
 * The automation-record test locks the `automation` namespace only, so a key
 * added to `settings.*` (or any other namespace) in one locale can ship as a
 * raw key path in the UI of the other. This flattens BOTH files completely.
 */
import { describe, it, expect } from 'vitest'
import zh from '@/renderer/i18n/locales/zh-CN'
import en from '@/renderer/i18n/locales/en-US'

function flatten(obj: Record<string, unknown>, prefix = ''): string[] {
  const out: string[] = []
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object') out.push(...flatten(value as Record<string, unknown>, path))
    else out.push(path)
  }
  return out
}

const zhKeys = flatten(zh as Record<string, unknown>)
const enKeys = flatten(en as Record<string, unknown>)

describe('i18n locale parity', () => {
  it('zh-CN and en-US declare the identical key set', () => {
    const zhSet = new Set(zhKeys)
    const enSet = new Set(enKeys)
    expect(zhKeys.filter((k) => !enSet.has(k))).toEqual([])
    expect(enKeys.filter((k) => !zhSet.has(k))).toEqual([])
  })

  it('has no duplicate leaf keys in either locale', () => {
    expect(new Set(zhKeys).size).toBe(zhKeys.length)
    expect(new Set(enKeys).size).toBe(enKeys.length)
  })

  it('never ships an empty string (a blank label is worse than the key)', () => {
    const empties = (locale: string, obj: Record<string, unknown>) => {
      const bad: string[] = []
      const walk = (node: any, path: string) => {
        for (const [key, value] of Object.entries(node)) {
          const p = path ? `${path}.${key}` : key
          if (value !== null && typeof value === 'object') walk(value, p)
          else if (typeof value === 'string' && value.trim() === '') bad.push(`${locale}:${p}`)
        }
      }
      walk(obj, '')
      return bad
    }
    expect(empties('zh-CN', zh as any).concat(empties('en-US', en as any))).toEqual([])
  })
})
