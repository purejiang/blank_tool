import { describe, it, expect, afterEach } from 'vitest'
import { ThemeService } from '@/renderer/services/ThemeService'

/**
 * happy-dom 的 matchMedia 无法模拟「系统主题翻转」，这里整体替换成一个可手动
 * 触发的桩：fire() 改 matches 并回调所有订阅者，等同于 OS 偏好变化事件。
 */
function stubMatchMedia(initialMatches: boolean) {
  const listeners: Array<(e: { matches: boolean }) => void> = []
  const mql = {
    matches: initialMatches,
    addEventListener: (_type: string, cb: (e: { matches: boolean }) => void) => {
      listeners.push(cb)
    },
    removeEventListener: () => {},
  }
  const original = window.matchMedia
  window.matchMedia = ((_query: string) => mql) as unknown as typeof window.matchMedia

  return {
    fire(matches: boolean) {
      mql.matches = matches
      listeners.forEach((cb) => cb({ matches }))
    },
    restore() {
      window.matchMedia = original
    },
  }
}

describe('ThemeService', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('data-theme')
  })

  it('auto 模式下系统主题翻转同步更新 data-theme（Naive 与自定义 CSS 不割裂）', async () => {
    const os = stubMatchMedia(false)
    const svc = new ThemeService()

    await svc.initialize()
    await svc.applyTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    // 回归点：修复前这里只 notifyListeners()，data-theme 会停在 light，
    // 造成「Naive 组件变暗、自定义区域仍亮」的割裂。
    os.fire(true)
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')

    os.fire(false)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    svc.destroy()
    os.restore()
  })

  it('固定模式下系统主题翻转不改变 data-theme', async () => {
    const os = stubMatchMedia(false)
    const svc = new ThemeService()

    await svc.initialize()
    await svc.setTheme('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    os.fire(true)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    svc.destroy()
    os.restore()
  })

  it('onChange 订阅者收到的主题对象与 data-theme 一致', async () => {
    const os = stubMatchMedia(false)
    const svc = new ThemeService()
    const seen: Array<unknown> = []
    svc.onChange((theme) => seen.push(theme))

    await svc.initialize()
    await svc.applyTheme()
    os.fire(true)

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(seen.length).toBeGreaterThanOrEqual(2)
    expect(seen[seen.length - 1]).not.toBeNull()

    svc.destroy()
    os.restore()
  })
})
