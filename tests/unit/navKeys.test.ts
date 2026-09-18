/**
 * handleNavKeydown — 左侧 tablist 的键盘模型。
 *
 * 之前设置页 / 运行配置弹窗的左栏只有 @click：键盘既聚焦不到也切不了。
 * 这里锁住标准 tablist 行为（方向键循环切换 + 焦点跟随、Home/End、Enter/Space）。
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { handleNavKeydown } from '@utils/navKeys'

const KEYS = ['general', 'signing', 'runtime', 'storage'] as const

/** 造一个真实的 tablist DOM（事件绑在每一项上，与组件里的写法一致）。
 *  select 回调会像组件那样同步更新「当前项」与 roving tabindex —— 这样连续按键
 *  才会读到新状态（组件的 activePanel 是响应式的，下一个 keydown 读到的是新值）。 */
function makeNav(keys: readonly string[], initial: string) {
  const nav = document.createElement('div')
  nav.setAttribute('role', 'tablist')
  const items = keys.map((key) => {
    const el = document.createElement('div')
    el.setAttribute('role', 'tab')
    el.tabIndex = key === initial ? 0 : -1
    el.textContent = key
    nav.appendChild(el)
    return el
  })
  document.body.appendChild(nav)

  let current = initial
  const select = vi.fn((key: string) => {
    current = key
    items.forEach((el, i) => { el.tabIndex = keys[i] === key ? 0 : -1 })
  })
  for (const el of items) {
    el.addEventListener('keydown', (e) =>
      handleNavKeydown(e as KeyboardEvent, keys, current, select),
    )
  }
  return { nav, items, select }
}

function press(el: HTMLElement, key: string): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
  el.dispatchEvent(event)
  return event
}

const navs: HTMLElement[] = []

afterEach(() => {
  for (const nav of navs.splice(0)) nav.remove()
})

describe('handleNavKeydown', () => {
  it('ArrowDown / ArrowRight 切到下一项，并把焦点一起移过去', () => {
    const { nav, items, select } = makeNav(KEYS, 'general')
    navs.push(nav)

    press(items[0], 'ArrowDown')
    expect(select).toHaveBeenLastCalledWith('signing')
    expect(document.activeElement).toBe(items[1])

    press(items[1], 'ArrowRight')
    expect(select).toHaveBeenLastCalledWith('runtime')
    expect(document.activeElement).toBe(items[2])
  })

  it('ArrowUp / ArrowLeft 切到上一项', () => {
    const { nav, items, select } = makeNav(KEYS, 'runtime')
    navs.push(nav)

    press(items[2], 'ArrowUp')
    expect(select).toHaveBeenLastCalledWith('signing')
    expect(document.activeElement).toBe(items[1])
  })

  it('在两端循环（末尾下一项 = 第一项；第一项上一项 = 末尾）', () => {
    const { nav, items, select } = makeNav(KEYS, 'storage')
    navs.push(nav)

    press(items[3], 'ArrowDown')
    expect(select).toHaveBeenLastCalledWith('general')
    expect(document.activeElement).toBe(items[0])

    const second = makeNav(KEYS, 'general')
    navs.push(second.nav)
    press(second.items[0], 'ArrowUp')
    expect(second.select).toHaveBeenLastCalledWith('storage')
    expect(document.activeElement).toBe(second.items[3])
  })

  it('Home / End 跳到首尾', () => {
    const { nav, items, select } = makeNav(KEYS, 'runtime')
    navs.push(nav)

    press(items[2], 'End')
    expect(select).toHaveBeenLastCalledWith('storage')
    press(items[3], 'Home')
    expect(select).toHaveBeenLastCalledWith('general')
  })

  it('Enter / Space 选中当前项（不移动）', () => {
    const { nav, items, select } = makeNav(KEYS, 'signing')
    navs.push(nav)

    const enter = press(items[1], 'Enter')
    expect(select).toHaveBeenLastCalledWith('signing')
    expect(enter.defaultPrevented).toBe(true)

    select.mockClear()
    const space = press(items[1], ' ')
    expect(select).toHaveBeenLastCalledWith('signing')
    expect(space.defaultPrevented).toBe(true)
  })

  it('方向键会 preventDefault（避免页面跟着滚动）', () => {
    const { nav, items } = makeNav(KEYS, 'general')
    navs.push(nav)
    expect(press(items[0], 'ArrowDown').defaultPrevented).toBe(true)
  })

  it('无关按键不处理：不选中、不拦截默认行为', () => {
    const { nav, items, select } = makeNav(KEYS, 'general')
    navs.push(nav)

    const event = press(items[0], 'a')
    expect(select).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it('列表为空时是安全 no-op', () => {
    const select = vi.fn()
    const el = document.createElement('div')
    const event = new KeyboardEvent('keydown', { key: 'ArrowDown', cancelable: true })
    handleNavKeydown(event, [], '', select)
    expect(select).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
    expect(el).toBeTruthy()
  })

  it('current 不在 keys 里时从第一项开始算', () => {
    const { nav, items, select } = makeNav(KEYS, 'nope')
    navs.push(nav)
    press(items[0], 'ArrowDown')
    expect(select).toHaveBeenLastCalledWith('signing')
  })
})
