import { describe, it, expect } from 'vitest'
import { createI18n } from 'vue-i18n'
import zh from '@/renderer/i18n/locales/zh-CN'
import en from '@/renderer/i18n/locales/en-US'

/**
 * vue-i18n 的消息语法里裸 `|` 是**复数分支分隔符**：
 *
 *   'v{app} | 本地服务 {service}'   →  "v2.5.0"          （后半句被当成分支丢掉）
 *   "v{app} {'|'} 本地服务 {service}" →  "v2.5.0 | 本地服务 2.5.0"
 *
 * 丢的是静默的——不报错、不警告，只是渲染短了一截。statusBar.versionLine
 * 就这么少显示了半句，一直没人发现。这个测试扫全部文案，拦住下一次。
 */

type Entry = [path: string, message: string]

/** 展开嵌套命名空间，只收字符串叶子（数组/数字等跳过）。 */
function flattenStrings(node: unknown, prefix = ''): Entry[] {
  if (node === null || typeof node !== 'object') return []
  const out: Entry[] = []
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (Array.isArray(value)) continue
    if (value !== null && typeof value === 'object') out.push(...flattenStrings(value, path))
    else if (typeof value === 'string') out.push([path, value])
  }
  return out
}

/** 字面量竖线的写法是 {'|'}；把它剥掉后还剩 `|` 才是被当分隔符的那种。 */
const LITERAL_INTERPOLATION = /\{[^}]*\}/g
function hasBarePipe(message: string): boolean {
  return message.replace(LITERAL_INTERPOLATION, '').includes('|')
}

describe('i18n locale message safety', () => {
  const cases = [
    ['zh-CN', zh] as const,
    ['en-US', en] as const,
  ]

  for (const [locale, messages] of cases) {
    it(`${locale}: 没有裸竖线（会被当成复数分支静默截断）`, () => {
      const offenders = flattenStrings(messages)
        .filter(([, message]) => hasBarePipe(message))
        .map(([path, message]) => `${path} → ${JSON.stringify(message)}`)
      expect(offenders, `\n${offenders.join('\n')}\n`).toEqual([])
    })
  }

  it('statusBar.versionLine 两半句都渲染出来', () => {
    for (const [locale, messages] of cases) {
      const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } })
      const line = i18n.global.t('statusBar.versionLine', { app: '2.5.0', service: '9.9.9' })
      expect(line, locale).toContain('2.5.0')
      expect(line, locale).toContain('9.9.9')
      expect(line, locale).toContain('|')
    }
  })
})
