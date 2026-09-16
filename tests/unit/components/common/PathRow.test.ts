/**
 * PathRow unit tests — 设置页所有路径设置项共用的那一行。
 *
 * 锁住的规则（其余用法都从这里派生）：
 *   - 不支持修改的路径：只展示路径文本，一个按钮都不出现
 *   - 支持修改的路径：路径后面跟一个图标按钮，点击 emit edit
 *   - 用户覆盖了默认值时：额外给出「重置」，排在修改按钮前面
 *
 * vue-i18n 被替换为恒等 t()（key 原样渲染），断言只关心结构不关心文案。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import PathRow from '@/renderer/components/common/PathRow.vue'

const JAVA_PATH = 'C:\\Java\\bin\\java.exe'

function mountRow(props: Record<string, unknown> = {}) {
  return mount(PathRow, { props: { label: 'Java', path: JAVA_PATH, ...props } })
}

describe('PathRow', () => {
  it('只读路径：只展示路径文本，不出现任何按钮', () => {
    const w = mountRow()
    expect(w.text()).toContain(JAVA_PATH)
    expect(w.findAll('button')).toHaveLength(0)
  })

  it('可修改路径：跟一个修改图标按钮，点击 emit edit', async () => {
    const w = mountRow({ editable: true })
    const buttons = w.findAll('button')
    expect(buttons).toHaveLength(1)
    await buttons[0].trigger('click')
    expect(w.emitted('edit')).toHaveLength(1)
  })

  it('已覆盖默认值：多出重置按钮，且排在修改按钮之前', async () => {
    const w = mountRow({ editable: true, overridden: true })
    const buttons = w.findAll('button')
    expect(buttons).toHaveLength(2)

    await buttons[0].trigger('click')
    expect(w.emitted('reset')).toHaveLength(1)
    expect(w.emitted('edit')).toBeUndefined()

    await buttons[1].trigger('click')
    expect(w.emitted('edit')).toHaveLength(1)
  })

  it('路径为空：展示占位文案而不是空白', () => {
    const w = mountRow({ path: '', placeholder: '未知' })
    expect(w.text()).toContain('未知')
  })

  it('hint 为空时不渲染说明行', () => {
    expect(mountRow().find('.path-row-hint').exists()).toBe(false)
    expect(mountRow({ hint: '仅记录' }).find('.path-row-hint').text()).toBe('仅记录')
  })

  it('未知存在性（不传 exists）时不渲染任何状态图标', () => {
    const w = mountRow()
    expect(w.find('.path-row-exists').exists()).toBe(false)
    expect(w.find('.path-row-value svg').exists()).toBe(false)
  })

  it('exists=true 在路径文本后面渲染勾图标，且不在操作区', () => {
    const w = mountRow({ exists: true })
    const icon = w.get('.path-row-exists')
    expect(icon.classes()).toContain('is-ok')
    // 图标属于 value 区（路径之后），不在右侧 actions 里
    expect(icon.element.closest('.path-row-value')).toBeTruthy()
    expect(icon.element.closest('.path-row-actions')).toBeNull()
    // 文本节点排在图标之前
    const text = w.get('.path-row-text')
    expect(text.element.compareDocumentPosition(icon.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('exists=false 渲染感叹号图标', () => {
    const w = mountRow({ exists: false })
    expect(w.get('.path-row-exists').classes()).toContain('is-missing')
  })

  it('存在性图标不影响编辑/重置按钮的数量与顺序', async () => {
    const w = mountRow({ editable: true, overridden: true, exists: true })
    const buttons = w.findAll('button')
    expect(buttons).toHaveLength(2)
    await buttons[0].trigger('click')
    expect(w.emitted('reset')).toHaveLength(1)
    await buttons[1].trigger('click')
    expect(w.emitted('edit')).toHaveLength(1)
  })
})
