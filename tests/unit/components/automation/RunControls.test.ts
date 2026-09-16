/**
 * RunControls unit tests.
 *
 * The run row is exactly: device select · run/stop · the 「功能」 menu button.
 * The secondary entries (run settings, run history) live in that menu; the run
 * settings dialog itself is RunConfigDialog (tested separately) and the history
 * list is owned by the page, so this component only emits `openHistory`.
 *
 * vue-i18n is mocked to an identity t() (keys render as themselves); the
 * teleport stub keeps n-modal's content inside the wrapper so it is
 * queryable without touching document.body.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { NDropdown } from 'naive-ui'

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import RunControls from '@/renderer/components/automation/RunControls.vue'
import RunConfigDialog from '@/renderer/components/automation/RunConfigDialog.vue'

function mountControls(props: Record<string, unknown> = {}) {
  setActivePinia(createPinia())
  return mount(RunControls, {
    props: {
      autoDeviceId: '',
      captureTraffic: false,
      trafficHostFilter: '',
      continueOnError: false,
      abortOnCrash: true,
      stepIntervalMs: 300,
      running: false,
      canRun: true,
      ...props,
    },
    global: { stubs: { teleport: true } },
  })
}

/**
 * Drive the 「功能」 menu through the dropdown's own `select` event. The menu
 * itself is teleported to <body>, so poking at its DOM would be fragile —
 * this exercises exactly the handler the real item click would call.
 */
async function pickMenu(w: VueWrapper, key: 'settings' | 'history') {
  w.findComponent(NDropdown).vm.$emit('select', key)
  await w.vm.$nextTick()
}

function menuOptions(w: VueWrapper) {
  return w.findComponent(NDropdown).props('options') as Array<{ key: string; label: string }>
}

function configDialog(w: VueWrapper) {
  return w.findComponent(RunConfigDialog)
}

describe('RunControls — row layout', () => {
  it('is exactly: device select · run · the 「功能」 menu', () => {
    const w = mountControls()
    const row = w.get('.run-controls-row')
    const kids = [...row.element.children]

    expect(kids.length).toBe(3)
    expect(kids[1].textContent?.trim()).toBe('automation.run')
    // the menu button is the LAST element → to the right of Run
    // （IconButton 的根是一层包裹 span，按钮本身在它里面）
    expect(kids[2].querySelector('.run-menu-btn')).toBeTruthy()
  })

  it('menu button is icon-only (no label text)', () => {
    const w = mountControls()
    const btn = w.get('.run-menu-btn')

    expect(btn.text()).toBe('')
    expect(btn.find('svg').exists()).toBe(true)
    // the label lives on as the accessible name
    expect(btn.attributes('aria-label')).toBe('automation.runMenu')
  })

  it('keeps no capture control inline (toggle + filter moved into the dialog)', () => {
    const w = mountControls({ captureTraffic: true, trafficHostFilter: 'a.com' })
    const row = w.get('.run-controls-row')

    expect(row.find('.capture-toggle').exists()).toBe(false)
    expect(row.find('.capture-filter').exists()).toBe(false)
    expect(row.find('input').exists()).toBe(false)
    expect(row.find('.n-switch').exists()).toBe(false)
    expect(row.find('.n-dynamic-tags').exists()).toBe(false)
  })

  it('swaps run → stop while running but keeps the menu button', () => {
    const w = mountControls({ running: true })
    const kids = [...w.get('.run-controls-row').element.children]

    expect(kids.length).toBe(3)
    expect(kids[1].textContent?.trim()).toBe('automation.stop')
    expect(kids[2].querySelector('.run-menu-btn')).toBeTruthy()
  })
})

describe('RunControls — 「功能」 menu', () => {
  it('offers run settings + run history, with the count when there is one', () => {
    const opts = menuOptions(mountControls({ historyCount: 3 }))
    expect(opts.map((o) => o.key)).toEqual(['settings', 'history'])
    expect(opts[0].label).toBe('automation.runConfig')
    expect(opts[1].label).toBe('automation.runHistory (3)')

    // no history yet → no "(0)"
    expect(menuOptions(mountControls())[1].label).toBe('automation.runHistory')
  })

  it('选「运行记录」只发请求，不开设置弹窗', async () => {
    const w = mountControls()
    await pickMenu(w, 'history')
    expect(w.emitted('openHistory')).toHaveLength(1)
    expect(configDialog(w).props('show')).toBe(false)
  })

  it('抓包开着时菜单按钮上有圆点（收进菜单后这是唯一的常驻提示）', () => {
    expect(mountControls({ captureTraffic: true }).find('.run-dot').exists()).toBe(true)
    expect(mountControls({ captureTraffic: false }).find('.run-dot').exists()).toBe(false)
  })
})

describe('RunControls — run settings dialog wiring', () => {
  it('is closed by default and opens from the menu', async () => {
    const w = mountControls()
    expect(configDialog(w).props('show')).toBe(false)

    await pickMenu(w, 'settings')
    expect(configDialog(w).props('show')).toBe(true)
  })

  it('passes the live state + probe results into the dialog', async () => {
    const trafficStatus = { ready: true, installed: true, lib_path: 'x', python_mismatch: null, ca_cert_exists: true }
    const imeStatus = { device_id: 'dev-1', package: 'p', installed: true, active: false }
    const w = mountControls({
      autoDeviceId: 'dev-1',
      captureTraffic: true,
      trafficHostFilter: 'a.com',
      continueOnError: true,
      abortOnCrash: false,
      enableChineseInput: false,
      stepIntervalMs: 250,
      trafficStatus,
      imeStatus,
      detecting: 'traffic',
    })
    await pickMenu(w, 'settings')

    const d = configDialog(w)
    expect(d.props('deviceId')).toBe('dev-1')
    expect(d.props('captureTraffic')).toBe(true)
    expect(d.props('trafficHostFilter')).toBe('a.com')
    expect(d.props('continueOnError')).toBe(true)
    expect(d.props('abortOnCrash')).toBe(false)
    expect(d.props('enableChineseInput')).toBe(false)
    expect(d.props('stepIntervalMs')).toBe(250)
    expect(d.props('trafficStatus')).toEqual(trafficStatus)
    expect(d.props('imeStatus')).toEqual(imeStatus)
    expect(d.props('detecting')).toBe('traffic')
  })

  it('forwards every run-level setting back to the page', async () => {
    const w = mountControls()
    await pickMenu(w, 'settings')
    const d = configDialog(w)

    d.vm.$emit('update:captureTraffic', true)
    d.vm.$emit('update:trafficHostFilter', 'b.com')
    d.vm.$emit('update:continueOnError', true)
    d.vm.$emit('update:abortOnCrash', false)
    d.vm.$emit('update:enableChineseInput', false)
    d.vm.$emit('update:stepIntervalMs', 0)
    await w.vm.$nextTick()

    expect(w.emitted('update:captureTraffic')).toEqual([[true]])
    expect(w.emitted('update:trafficHostFilter')).toEqual([['b.com']])
    expect(w.emitted('update:continueOnError')).toEqual([[true]])
    expect(w.emitted('update:abortOnCrash')).toEqual([[false]])
    expect(w.emitted('update:enableChineseInput')).toEqual([[false]])
    // 0 是合法值（不插入间隔），必须原样转发，不能被当成 "没传"
    expect(w.emitted('update:stepIntervalMs')).toEqual([[0]])
  })

  it('forwards 检测 / 安装 / 证书 / 代理修复 请求（后端调用都在页面）', async () => {
    const w = mountControls()
    await pickMenu(w, 'settings')
    const d = configDialog(w)

    d.vm.$emit('detect', 'traffic')
    d.vm.$emit('detect', 'ime')
    d.vm.$emit('openTools', 'ime')
    d.vm.$emit('installCa')
    d.vm.$emit('resetTraffic')
    await w.vm.$nextTick()

    expect(w.emitted('detect')).toEqual([['traffic'], ['ime']])
    expect(w.emitted('openTools')).toEqual([['ime']])
    expect(w.emitted('installCa')).toHaveLength(1)
    expect(w.emitted('resetTraffic')).toHaveLength(1)
  })

  it('closing the dialog comes back through update:show', async () => {
    const w = mountControls()
    await pickMenu(w, 'settings')
    configDialog(w).vm.$emit('update:show', false)
    await w.vm.$nextTick()
    expect(configDialog(w).props('show')).toBe(false)
  })
})
