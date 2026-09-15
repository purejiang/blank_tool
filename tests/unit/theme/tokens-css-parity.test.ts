import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { colorTokens, staticTokens } from '@/renderer/theme/tokens'

/**
 * tokens.ts ↔ 生成 CSS 的一致性守卫。
 *
 * themes.css / variables.css 由 `npm run theme:css` 从 tokens.ts 生成；
 * 手改任一 CSS 都会被本测试拒绝（防止双份色值再次漂移）。
 */

const STYLES = resolve(process.cwd(), 'src/renderer/assets/styles')

function parseCss(css: string) {
  const map = new Map<string, string>()
  const selectors: string[] = []
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, '')
  for (const block of clean.split('}')) {
    const brace = block.indexOf('{')
    if (brace < 0) continue
    const selector = block.slice(0, brace).trim().replace(/\s+/g, ' ')
    if (selector) selectors.push(selector)
    for (const decl of block.slice(brace + 1).split(';')) {
      const m = decl.match(/^\s*(--app-[a-z0-9-]+)\s*:\s*([\s\S]+)$/)
      if (m) map.set(`${selector} | ${m[1]}`, m[2].replace(/\s+/g, ' ').trim())
    }
  }
  return { map, selectors }
}

describe('theme tokens ↔ CSS parity', () => {
  const themesCss = readFileSync(resolve(STYLES, 'themes.css'), 'utf8')
  const variablesCss = readFileSync(resolve(STYLES, 'variables.css'), 'utf8')

  it('两个 CSS 都标记为自动生成', () => {
    expect(themesCss).toContain('自动生成')
    expect(variablesCss).toContain('自动生成')
  })

  it('themes.css 的亮/暗取值与 colorTokens 完全一致，且无多余 token', () => {
    const { map, selectors } = parseCss(themesCss)
    expect(selectors).toEqual([':root, [data-theme="light"]', '[data-theme="dark"]'])

    const expected = new Map<string, string>()
    for (const [name, value] of Object.entries(colorTokens.light)) {
      expected.set(`:root, [data-theme="light"] | --app-${name}`, value)
    }
    for (const [name, value] of Object.entries(colorTokens.dark)) {
      expected.set(`[data-theme="dark"] | --app-${name}`, value)
    }

    expect(Object.fromEntries(map)).toEqual(Object.fromEntries(expected))
  })

  it('variables.css 与 staticTokens 完全一致，且无多余 token', () => {
    const { map, selectors } = parseCss(variablesCss)
    expect(selectors).toEqual([':root'])

    const expected = new Map<string, string>()
    for (const [name, value] of Object.entries(staticTokens)) {
      expected.set(`:root | --app-${name}`, value)
    }

    expect(Object.fromEntries(map)).toEqual(Object.fromEntries(expected))
  })

  it('亮/暗两套颜色 token 的键集合一致（新增色相必须两边都加）', () => {
    expect(Object.keys(colorTokens.light).sort()).toEqual(Object.keys(colorTokens.dark).sort())
  })
})
