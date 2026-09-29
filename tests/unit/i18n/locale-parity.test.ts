import { describe, expect, it } from 'vitest'

import zhCN from '@/renderer/i18n/locales/zh-CN'
import enUS from '@/renderer/i18n/locales/en-US'

/**
 * i18n key 奇偶性守卫。
 *
 * 背景（实测）：`UpdateDialog.vue` 里曾硬编码英文 `Latest`——因为 `update.latest`
 * 这个 key 两边都没有。这类漏 key 平时不报错：`$t('x.y')` 在 vue-i18n 里会**原样
 * 返回 key 字符串**，界面上就出现一串 `update.latest`，或者被写成死文案。
 *
 * AGENTS.md 要求「UI 文案改动需同步两个语言文件」，但没有东西在强制它。
 * 本测试把它变成红灯：zh-CN 与 en-US 的**叶子 key 集合必须完全一致**。
 *
 * 只比 key，不比文案内容——文案长短由语言决定，不该被测试约束。
 */

type Tree = Record<string, unknown>

/** 收集叶子 key 的完整路径。数组/标量都算叶子（数组整体是一个文案单元）。 */
function leafPaths(node: unknown, prefix = ''): string[] {
  if (node === null || typeof node !== 'object' || Array.isArray(node)) return [prefix]
  const out: string[] = []
  for (const [key, value] of Object.entries(node as Tree)) {
    out.push(...leafPaths(value, prefix ? `${prefix}.${key}` : key))
  }
  return out
}

const zhKeys = leafPaths(zhCN).sort()
const enKeys = leafPaths(enUS).sort()

describe('i18n locale 奇偶性', () => {
  it('扫描到了足够多的 key（守卫自身要有效）', () => {
    expect(zhKeys.length).toBeGreaterThan(300)
    expect(enKeys.length).toBeGreaterThan(300)
  })

  it('zh-CN 与 en-US 的 key 集合完全一致', () => {
    const zhSet = new Set(zhKeys)
    const enSet = new Set(enKeys)
    const missingInEn = zhKeys.filter((k) => !enSet.has(k))
    const missingInZh = enKeys.filter((k) => !zhSet.has(k))
    expect(missingInEn, `en-US 缺少这些 key：\n${missingInEn.join('\n')}`).toEqual([])
    expect(missingInZh, `zh-CN 缺少这些 key：\n${missingInZh.join('\n')}`).toEqual([])
  })

  it('没有空文案（空串会被 vue-i18n 渲染成什么都不显示）', () => {
    const collectEmpty = (node: unknown, prefix = ''): string[] => {
      if (typeof node === 'string') return node.trim() === '' ? [prefix] : []
      if (node === null || typeof node !== 'object' || Array.isArray(node)) return []
      return Object.entries(node as Tree).flatMap(([key, value]) =>
        collectEmpty(value, prefix ? `${prefix}.${key}` : key),
      )
    }
    const empty = [...collectEmpty(zhCN), ...collectEmpty(enUS)].map((k) => k)
    expect(empty, `空的 i18n 文案：${empty.join(', ')}`).toEqual([])
  })
})
