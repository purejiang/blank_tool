import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { h } from 'vue'
import { NConfigProvider } from 'naive-ui'

import AppButton, { type ButtonVariant } from '@/renderer/components/ui/AppButton.vue'
import AppBadge from '@/renderer/components/ui/AppBadge.vue'
import EmptyState from '@/renderer/components/ui/EmptyState.vue'
import { selectOverrides } from '@/renderer/theme/overrides'

/**
 * UI 原语的解析值护栏。
 *
 * 为什么必须测「解析出来的 CSS 变量」而不是 class 名：Naive 的 Button 会按
 * `type` + `secondary/tertiary/quaternary/ghost/dashed` 走**完全不同的取值分支**，
 * 而其中几个分支读的是**无后缀**的 `textColor` / `border` 键（见 Button.mjs 的
 * typeTextColor 与 borderProps）。只断言 class 名的话，把文字色配成底色也测不出来
 * —— 这正是实测踩到的坑：
 *
 *   `type="error" quaternary`（全仓 14+ 个删除按钮）解析出的文字色曾是
 *   `--danger-bg`（#FEF2F2），在浅色主题下几乎不可见。
 *
 * 本测试把每个变体的 color / text / border / height 四元组钉死。
 */

// ---- 解析 tokens.css 的浅色值，用来把 `var(--x)` 归一化成字面量 ----------------
const CSS = readFileSync(resolve(process.cwd(), 'src/renderer/assets/styles/tokens.css'), 'utf8')

/**
 * 取浅色主题的值。⚠️ 不能按 `:root,\n[data-theme="light"]` 字面量 indexOf 定位：
 * 仓库文件是 CRLF，`\n` 匹配不上。这里按块扫，只收以 `:root` 开头的块
 * （第一块是 `:root, [data-theme="light"]`，最后一块是「非颜色维度」），
 * `[data-theme="dark"]` 天然被排除。
 */
const LIGHT: Record<string, string> = {}
for (const block of CSS.matchAll(/:root[^{]*\{([^}]*)\}/gs)) {
  for (const m of block[1].matchAll(/(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);/g)) {
    LIGHT[m[1]] = m[2].trim()
  }
}

/** 把 `var(--x)` 递归解析成字面量；普通值原样返回。 */
function resolveVar(value: string, depth = 0): string {
  if (depth > 5) return value
  const m = value.match(/^var\(\s*(--[A-Za-z0-9_-]+)\s*\)$/)
  if (!m) {
    // `1px solid var(--border)` 这类组合值，逐个替换
    return value.replace(/var\(\s*(--[A-Za-z0-9_-]+)\s*\)/g, (_all, name: string) =>
      LIGHT[name] === undefined ? _all : resolveVar(LIGHT[name], depth + 1),
    )
  }
  const next = LIGHT[m[1]]
  return next === undefined ? value : resolveVar(next, depth + 1)
}

function cssVarsFor(component: unknown, props: Record<string, unknown>) {
  const wrapper = mount(NConfigProvider, {
    props: { themeOverrides: selectOverrides(null) },
    slots: { default: () => h(component as never, props, { default: () => 'x' }) },
  })
  const style = wrapper.find('button, span').attributes('style') ?? ''
  const pick = (name: string) => {
    const m = style.match(new RegExp(`--${name}:\\s*([^;]+)`))
    return m ? resolveVar(m[1].trim()) : '(unset)'
  }
  return { color: pick('n-color'), text: pick('n-text-color'), border: pick('n-border'), height: pick('n-height') }
}

describe('AppButton 变体解析值', () => {
  const CASES: Array<{ variant: ButtonVariant; text: string; color: string; border: string }> = [
    { variant: 'primary', text: '#FFFFFF', color: '#2563EB', border: '1px solid #2563EB' },
    { variant: 'secondary', text: '#2563EB', color: '#EFF6FF', border: '1px solid #BFDBFE' },
    { variant: 'outline', text: '#2563EB', color: 'transparent', border: '1px solid #E2E8F0' },
    { variant: 'ghost', text: '#334155', color: 'transparent', border: '1px solid transparent' },
    { variant: 'danger', text: '#991B1B', color: '#FEF2F2', border: '1px solid #FECACA' },
    { variant: 'danger-ghost', text: '#991B1B', color: 'transparent', border: '1px solid transparent' },
    { variant: 'warning', text: '#92400E', color: '#FFFBEB', border: '1px solid #FDE68A' },
    // dashed 走 Naive 的 `ghost || dashed` 分支：底色被写死成 `#0000`，覆盖不了；
    // 文字色读 textColorGhost*，边框读无后缀 border。
    { variant: 'dashed', text: '#2563EB', color: '#0000', border: '1px solid #BFDBFE' },
  ]

  for (const c of CASES) {
    it(`${c.variant} 的取色正确`, () => {
      const v = cssVarsFor(AppButton, { variant: c.variant })
      expect({ text: v.text, color: v.color, border: v.border }).toEqual({
        text: c.text,
        color: c.color,
        border: c.border,
      })
    })
  }

  it('危险类变体的文字色绝不能被配成浅底色（回归守卫）', () => {
    for (const variant of ['danger', 'danger-ghost'] as const) {
      const { text } = cssVarsFor(AppButton, { variant })
      expect(text, `${variant} 的文字色不该是危险浅底 #FEF2F2`).not.toBe('#FEF2F2')
    }
  })

  it('三档尺寸解析为 24 / 30 / 34px', () => {
    expect(cssVarsFor(AppButton, { size: 'tiny' }).height).toBe('24px')
    expect(cssVarsFor(AppButton, { size: 'small' }).height).toBe('30px')
    expect(cssVarsFor(AppButton, { size: 'medium' }).height).toBe('34px')
  })

  it('默认档是 small（30px）—— 与设计稿 .btn 一致', () => {
    expect(cssVarsFor(AppButton, {}).height).toBe('30px')
  })
})

describe('AppBadge', () => {
  it('tone 决定色调类，size 决定尺寸类，bordered=false 去掉描边', () => {
    const w = mount(AppBadge, { props: { tone: 'success', size: 'xs', bordered: false }, slots: { default: 'ok' } })
    const cls = w.find('span').classes()
    expect(cls).toContain('app-badge--success')
    expect(cls).toContain('app-badge--xs')
    expect(cls).toContain('app-badge--plain')
  })

  it('默认是 sm + 有描边（保持首页现状）', () => {
    const cls = mount(AppBadge, { slots: { default: 'x' } }).find('span').classes()
    expect(cls).toContain('app-badge--sm')
    expect(cls).not.toContain('app-badge--plain')
    expect(cls).toContain('app-badge--neutral')
  })
})

describe('EmptyState', () => {
  it('page 档渲染虚线 art + 标题 + 说明 + 动作', () => {
    const w = mount(EmptyState, {
      props: { title: 'T', description: 'D' },
      slots: { icon: '<i/>', actions: '<button>b</button>' },
    })
    expect(w.find('.app-empty--page').exists()).toBe(true)
    expect(w.find('.app-empty-art').exists()).toBe(true)
    expect(w.find('h3').text()).toBe('T')
    expect(w.find('p').text()).toBe('D')
    expect(w.find('.app-empty-acts').exists()).toBe(true)
  })

  it('inline 档只渲染一行占位文字，没有 art/标题结构', () => {
    const w = mount(EmptyState, { props: { size: 'inline', title: 'none' } })
    expect(w.find('.app-empty--inline').exists()).toBe(true)
    expect(w.find('.app-empty-art').exists()).toBe(false)
    expect(w.find('h3').exists()).toBe(false)
    expect(w.text()).toBe('none')
  })

  it('inline 档支持用默认插槽传更复杂的占位内容', () => {
    const w = mount(EmptyState, { props: { size: 'inline' }, slots: { default: '<em>自定义</em>' } })
    expect(w.find('em').text()).toBe('自定义')
  })
})
