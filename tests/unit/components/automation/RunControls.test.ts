/**
 * RunControls unit tests.
 *
 * The run row is exactly: device select · run/stop · the 「功能」 menu button.
 * The secondary entries (run settings = traffic capture + host filter, and run
 * history) live in that menu and open dialogs; the history list itself is owned
 * by the page, so this component only emits `openHistory`.
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

function mountControls(props: Record<string, unknown> = {}) {
  setActivePinia(createPinia())
  return mount(RunControls, {
    props: {
      autoDeviceId: '',
      captureTraffic: false,
      trafficHostFilter: '',
      continueOnError: false,
      abortOnCrash: true,
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

/** The dashed "+" trigger of n-dynamic-tags. Each tag's close is a <button>
 *  too, so filtering by `closest('.n-tag')` is the only reliable pick. */
function addTrigger(w: VueWrapper) {
  const btn = w.get('.rcf-input').findAll('button').find((b) => !b.element.closest('.n-tag'))
  if (!btn) throw new Error('n-dynamic-tags "+" trigger not found')
  return btn
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
    expect(w.find('.rcf-block').exists()).toBe(false)
  })

  it('抓包开着时菜单按钮上有圆点（收进菜单后这是唯一的常驻提示）', () => {
    expect(mountControls({ captureTraffic: true }).find('.run-dot').exists()).toBe(true)
    expect(mountControls({ captureTraffic: false }).find('.run-dot').exists()).toBe(false)
  })
})

describe('RunControls — run settings dialog', () => {
  it('is closed by default and opens with every block', async () => {
    const w = mountControls()
    expect(w.find('.rcf-block').exists()).toBe(false)

    await pickMenu(w, 'settings')

    // capture switch · host filter · 失败后继续 · 崩溃即中止
    expect(w.findAll('.rcf-block').length).toBe(4)
    expect(w.get('.n-switch').exists()).toBe(true)
    expect(w.get('.rcf-input').exists()).toBe(true)
  })

  it('closes again from the footer button', async () => {
    const w = mountControls()
    await pickMenu(w, 'settings')
    const close = w.findAll('.n-modal button, .n-card button').find((b) => b.text() === 'common.close')
    expect(close).toBeTruthy()
    await close!.trigger('click')
    expect(w.find('.rcf-block').exists()).toBe(false)
  })

  it('filter is disabled while capture is off, enabled once it is on', async () => {
    const off = mountControls({ captureTraffic: false })
    await pickMenu(off, 'settings')
    // the "+" trigger of the tag list is the disabled surface
    expect(addTrigger(off).attributes('disabled')).toBeDefined()
    expect(off.get('.rcf-block.is-off').exists()).toBe(true)

    const on = mountControls({ captureTraffic: true })
    await pickMenu(on, 'settings')
    expect(addTrigger(on).attributes('disabled')).toBeUndefined()
    expect(on.find('.rcf-block.is-off').exists()).toBe(false)
  })

  it('switch emits its update', async () => {
    const w = mountControls({ captureTraffic: true })
    await pickMenu(w, 'settings')

    await w.get('.n-switch').trigger('click')
    expect(w.emitted('update:captureTraffic')).toEqual([[false]])
  })

  it('offers both failure-policy switches, defaulting to the old behaviour', async () => {
    // The dialog is live-bound: no confirm step, the page reads the values
    // when a run starts. Defaults must be "abort on first failure" + "abort
    // on crash", i.e. exactly what the renderer used to hard-code.
    const w = mountControls()
    await pickMenu(w, 'settings')

    const switches = w.findAll('.n-switch')
    expect(switches.length).toBe(3)
    // [0] capture · [1] 失败后继续 (off) · [2] 崩溃即中止 (on)
    expect(switches[1].classes()).not.toContain('n-switch--active')
    expect(switches[2].classes()).toContain('n-switch--active')

    await switches[1].trigger('click')
    expect(w.emitted('update:continueOnError')).toEqual([[true]])
    await switches[2].trigger('click')
    expect(w.emitted('update:abortOnCrash')).toEqual([[false]])
  })

  it('filter is a tag list, not a comma-separated string field', async () => {
    const w = mountControls({ captureTraffic: true, trafficHostFilter: 'a.com, b.com' })
    await pickMenu(w, 'settings')

    // existing conditions render as one chip each — no "a.com, b.com" blob,
    // and no always-on text field to hand-type the separator into.
    // NB: `.rcf-input > button` is the dashed "+" trigger; each tag's close
    // is also a <button>, just nested inside .n-tag.
    const tags = w.get('.rcf-input').findAll('.n-tag')
    expect(tags.map((t) => t.text())).toEqual(['a.com', 'b.com'])
    expect(w.find('.rcf-input input').exists()).toBe(false)
    expect(addTrigger(w).element.tagName).toBe('BUTTON')
  })

  it('adding a condition appends a chip and keeps the comma wire format', async () => {
    const w = mountControls({ captureTraffic: true, trafficHostFilter: 'a.com' })
    await pickMenu(w, 'settings')

    await addTrigger(w).trigger('click') // reveal the input
    const input = w.get('.rcf-input input')
    await input.setValue('api.example.com')
    await input.trigger('keydown', { key: 'Enter' })

    expect(w.emitted('update:trafficHostFilter')?.at(-1)).toEqual(['a.com,api.example.com'])
  })

  it('a pasted comma never survives inside one condition', async () => {
    const w = mountControls({ captureTraffic: true, trafficHostFilter: '' })
    await pickMenu(w, 'settings')

    await addTrigger(w).trigger('click')
    const input = w.get('.rcf-input input')
    await input.setValue('a.com,b.com')
    await input.trigger('keydown', { key: 'Enter' })

    expect(w.emitted('update:trafficHostFilter')?.at(-1)).toEqual(['a.com b.com'])
  })

  it('warns about a broken capture only while capture is on', async () => {
    const off = mountControls({ captureUnavailable: true, captureTraffic: false })
    await pickMenu(off, 'settings')
    expect(off.find('.rcf-warn').exists()).toBe(false)

    const on = mountControls({ captureUnavailable: true, captureTraffic: true })
    await pickMenu(on, 'settings')
    expect(on.get('.rcf-warn').text()).toBe('automation.captureTrafficUnavailable')

    const fine = mountControls({ captureUnavailable: false, captureTraffic: true })
    await pickMenu(fine, 'settings')
    expect(fine.find('.rcf-warn').exists()).toBe(false)
  })
})
