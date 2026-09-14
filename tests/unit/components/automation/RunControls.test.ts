/**
 * RunControls unit tests.
 *
 * The run options (traffic capture + host filter) used to sit inline on the
 * run row; they now live in the "run settings" dialog behind a button placed
 * to the RIGHT of Run. These tests pin that layout, the two-way wiring of the
 * dialog fields, and the mitmproxy warning the dialog shows.
 *
 * vue-i18n is mocked to an identity t() (keys render as themselves); the
 * teleport stub keeps n-modal's content inside the wrapper so it is
 * queryable without touching document.body.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

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
      running: false,
      canRun: true,
      ...props,
    },
    global: { stubs: { teleport: true } },
  })
}

/** The dashed "+" trigger of n-dynamic-tags. Each tag's close is a <button>
 *  too, so filtering by `closest('.n-tag')` is the only reliable pick. */
function addTrigger(w: VueWrapper) {
  const btn = w.get('.rcf-input').findAll('button').find((b) => !b.element.closest('.n-tag'))
  if (!btn) throw new Error('n-dynamic-tags "+" trigger not found')
  return btn
}

describe('RunControls — row layout', () => {
  it('is exactly: device select · run · run settings', () => {
    const w = mountControls()
    const row = w.get('.run-controls-row')
    const kids = [...row.element.children]

    expect(kids.length).toBe(3)
    expect(kids[1].textContent?.trim()).toBe('automation.run')
    // the settings button is the LAST element → to the right of Run
    expect(kids[2].classList.contains('run-config-btn')).toBe(true)
  })

  it('settings button is icon-only (no label text)', () => {
    const w = mountControls()
    const btn = w.get('.run-config-btn')

    expect(btn.text()).toBe('')
    expect(btn.find('svg').exists()).toBe(true)
    // the label lives on as the accessible name + the dialog title
    expect(btn.attributes('aria-label')).toBe('automation.runConfig')
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

  it('swaps run → stop while running but keeps the settings button', () => {
    const w = mountControls({ running: true })
    const kids = [...w.get('.run-controls-row').element.children]

    expect(kids.length).toBe(3)
    expect(kids[1].textContent?.trim()).toBe('automation.stop')
    expect(kids[2].classList.contains('run-config-btn')).toBe(true)
  })
})

describe('RunControls — run settings dialog', () => {
  it('is closed by default and opens with both blocks', async () => {
    const w = mountControls()
    expect(w.find('.rcf-block').exists()).toBe(false)

    await w.get('.run-config-btn').trigger('click')

    expect(w.findAll('.rcf-block').length).toBe(2)
    expect(w.get('.n-switch').exists()).toBe(true)
    expect(w.get('.rcf-input').exists()).toBe(true)
  })

  it('closes again from the footer button', async () => {
    const w = mountControls()
    await w.get('.run-config-btn').trigger('click')
    const close = w.findAll('.n-modal button, .n-card button').find((b) => b.text() === 'common.close')
    expect(close).toBeTruthy()
    await close!.trigger('click')
    expect(w.find('.rcf-block').exists()).toBe(false)
  })

  it('filter is disabled while capture is off, enabled once it is on', async () => {
    const off = mountControls({ captureTraffic: false })
    await off.get('.run-config-btn').trigger('click')
    // the "+" trigger of the tag list is the disabled surface
    expect(addTrigger(off).attributes('disabled')).toBeDefined()
    expect(off.get('.rcf-block.is-off').exists()).toBe(true)

    const on = mountControls({ captureTraffic: true })
    await on.get('.run-config-btn').trigger('click')
    expect(addTrigger(on).attributes('disabled')).toBeUndefined()
    expect(on.find('.rcf-block.is-off').exists()).toBe(false)
  })

  it('switch emits its update', async () => {
    const w = mountControls({ captureTraffic: true })
    await w.get('.run-config-btn').trigger('click')

    await w.get('.n-switch').trigger('click')
    expect(w.emitted('update:captureTraffic')).toEqual([[false]])
  })

  it('filter is a tag list, not a comma-separated string field', async () => {
    const w = mountControls({ captureTraffic: true, trafficHostFilter: 'a.com, b.com' })
    await w.get('.run-config-btn').trigger('click')

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
    await w.get('.run-config-btn').trigger('click')

    await addTrigger(w).trigger('click') // reveal the input
    const input = w.get('.rcf-input input')
    await input.setValue('api.example.com')
    await input.trigger('keydown', { key: 'Enter' })

    expect(w.emitted('update:trafficHostFilter')?.at(-1)).toEqual(['a.com,api.example.com'])
  })

  it('a pasted comma never survives inside one condition', async () => {
    const w = mountControls({ captureTraffic: true, trafficHostFilter: '' })
    await w.get('.run-config-btn').trigger('click')

    await addTrigger(w).trigger('click')
    const input = w.get('.rcf-input input')
    await input.setValue('a.com,b.com')
    await input.trigger('keydown', { key: 'Enter' })

    expect(w.emitted('update:trafficHostFilter')?.at(-1)).toEqual(['a.com b.com'])
  })

  it('warns about a broken capture only while capture is on', async () => {
    const off = mountControls({ captureUnavailable: true, captureTraffic: false })
    await off.get('.run-config-btn').trigger('click')
    expect(off.find('.rcf-warn').exists()).toBe(false)

    const on = mountControls({ captureUnavailable: true, captureTraffic: true })
    await on.get('.run-config-btn').trigger('click')
    expect(on.get('.rcf-warn').text()).toBe('automation.captureTrafficUnavailable')

    const fine = mountControls({ captureUnavailable: false, captureTraffic: true })
    await fine.get('.run-config-btn').trigger('click')
    expect(fine.find('.rcf-warn').exists()).toBe(false)
  })
})
