/**
 * IconButton unit tests — 全站图标按钮共用的那一个组件。
 *
 * 锁住的规则（其余用法都从这里派生）：
 *   - 只有图标、没有可见文案 → 提示由 label 强制提供，label 同时是可访问名
 *   - $attrs 全部下沉到内部 button → 替换 n-button 不影响既有选择器与测试
 *   - 根节点是一层 <span> → disabled 按钮也能悬停出提示，且能当 dropdown trigger
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { h, nextTick } from 'vue'

// 用最简单的函数式组件代替 lucide 图标，避免测到图标库本身
const FakeIcon = () => h('svg', { class: 'fake-icon' })

import IconButton from '@/renderer/components/common/IconButton.vue'

function mountBtn(props: Record<string, unknown> = {}, attrs: Record<string, unknown> = {}) {
  return mount(IconButton, {
    props: { icon: FakeIcon, label: 'device.refresh', ...props },
    attrs,
    attachTo: document.body,
  })
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('IconButton', () => {
  it('图标按钮没有可见文案，可访问名取 label', () => {
    const w = mountBtn()
    const btn = w.find('button')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toBe('')
    expect(btn.attributes('aria-label')).toBe('device.refresh')
    expect(w.find('.fake-icon').exists()).toBe(true)
  })

  it('label 进 tooltip 内容，hover 后出现在 body 里', async () => {
    const w = mountBtn({ label: '打开所在位置' })
    await w.find('button').trigger('mouseenter')
    // Naive 的 hover 触发有 100ms 延迟（popover delay 默认值）
    await new Promise((resolve) => setTimeout(resolve, 200))
    await nextTick()
    expect(document.body.textContent).toContain('打开所在位置')
  })

  it('ariaLabel 可以覆盖可访问名（提示文案与可访问名不同的场合）', () => {
    const w = mountBtn({ label: '随状态变化的说明', ariaLabel: 'automation.runMenu' })
    expect(w.find('button').attributes('aria-label')).toBe('automation.runMenu')
  })

  it('$attrs 下沉到内部 button：type / disabled / data-testid / class', () => {
    const w = mountBtn({}, {
      type: 'error',
      disabled: true,
      'data-testid': 'new-project',
      class: 'pl-del',
    })
    const btn = w.find('button')
    expect(btn.attributes('data-testid')).toBe('new-project')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.classes()).toContain('pl-del')
    // 包裹层仍在：disabled 时悬停事件靠它冒泡
    expect(w.find('.app-icon-btn').exists()).toBe(true)
  })

  it('点击 emit 出原生事件（.stop 修饰符依赖它）', async () => {
    const w = mountBtn()
    await w.find('button').trigger('click')
    const events = w.emitted('click')
    expect(events).toHaveLength(1)
    expect(events![0][0]).toBeInstanceOf(Event)
  })

  it('默认插槽透传（图标之外的角标）', () => {
    const w = mount(IconButton, {
      props: { icon: FakeIcon, label: 'x' },
      slots: { default: '<span class="run-dot" />' },
    })
    expect(w.find('.run-dot').exists()).toBe(true)
  })
})
