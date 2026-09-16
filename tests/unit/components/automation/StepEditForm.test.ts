/**
 * StepEditForm pick-button rendering — regression lock.
 *
 * The screenshot-pick button hangs off the `coord.y` row because `coord.y` is
 * a `number` field, so it MUST be excluded from the generic
 * `f.type === 'number'` branch. While both claimed it, the v-if/v-else-if
 * chain stopped at the generic branch and the coordinate pick button was DEAD
 * CODE — invisible on every tap step and unnoticed by the rest of the suite.
 *
 * vue-i18n identity t() (keys render as themselves).
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { NSelect, NTooltip } from 'naive-ui'

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import StepEditForm from '@/renderer/components/automation/StepEditForm.vue'
import type { Step } from '@/renderer/components/automation/stepTypes'

const COORD_BTN = 'automation.f.pickCoord'
const ELEMENT_BTN = 'automation.f.pickElement'

function mountForm(step: Step) {
  return mount(StepEditForm, { props: { step } })
}
function buttonTexts(w: ReturnType<typeof mountForm>): string[] {
  return w.findAll('button').map((b) => b.text())
}

const coordTap = (): Step => ({ id: 't', action: 'tap', mode: 'coord', coord: { x: 1, y: 2 } })

describe('StepEditForm pick buttons', () => {
  it('renders the screenshot pick button for a coordinate tap', () => {
    const w = mountForm(coordTap())
    expect(buttonTexts(w)).toContain(COORD_BTN)
    expect(buttonTexts(w)).not.toContain(ELEMENT_BTN)
  })

  it('emits pick { mode: "screenshot" } from that button', async () => {
    const w = mountForm(coordTap())
    const btn = w.findAll('button').find((b) => b.text() === COORD_BTN)
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(w.emitted('pick')![0][0]).toEqual({ mode: 'screenshot' })
  })

  it('keeps x and y as real number inputs in coordinate mode', () => {
    const w = mountForm(coordTap())
    // the specialised row must still wrap the field, not replace it
    expect(w.findAll('.n-input-number').length).toBe(2)
    expect(w.findAll('.ctl-pick .n-input-number').length).toBe(1)
  })

  it('renders the UI-dump pick button for an element tap instead', () => {
    const w = mountForm({
      id: 't2',
      action: 'tap',
      mode: 'element',
      target: { by: 'text', value: '登录', timeout_ms: 10000 },
    })
    expect(buttonTexts(w)).toContain(ELEMENT_BTN)
    expect(buttonTexts(w)).not.toContain(COORD_BTN)
  })

  it('offers no pick button for a fixed-duration wait', () => {
    const w = mountForm({ id: 'w', action: 'wait', mode: 'time', ms: 500 })
    expect(buttonTexts(w)).not.toContain(COORD_BTN)
    expect(buttonTexts(w)).not.toContain(ELEMENT_BTN)
  })
})

/**
 * assert_element is an unconditional element target (no mode discriminator),
 * so its `target.value` row must carry the same UI-dump pick button as
 * input/tap-element. assert_activity is an Activity-string assertion — it has
 * no element target and must never grow an element-pick button.
 */
describe('StepEditForm pick buttons — assert_element', () => {
  const assertElement = (): Step => ({
    id: 'ae',
    action: 'assert_element',
    target: { by: 'text', value: '首页', timeout_ms: 10000 },
  })

  it('renders the UI-dump pick button for an assert_element step', () => {
    const w = mountForm(assertElement())
    expect(buttonTexts(w)).toContain(ELEMENT_BTN)
    expect(buttonTexts(w)).not.toContain(COORD_BTN)
  })

  it('emits pick { mode: "element" } from the assert_element pick button', async () => {
    const w = mountForm(assertElement())
    const btn = w.findAll('button').find((b) => b.text() === ELEMENT_BTN)
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(w.emitted('pick')![0][0]).toEqual({ mode: 'element' })
  })

  it('renders no element-pick button for an assert_activity step', () => {
    const w = mountForm({ id: 'aa', action: 'assert_activity', activity: '' })
    expect(buttonTexts(w)).not.toContain(ELEMENT_BTN)
    expect(buttonTexts(w)).not.toContain(COORD_BTN)
  })
})

/**
 * assert_activity's Activity string can be grabbed off the device instead of
 * typed. The form owns only the button + the disabled/tooltip UX; the PAGE
 * owns the backend call (mirrors the element picker split). `canGrab` comes
 * from the page as `!!autoDeviceId`.
 */
const GRAB_BTN = 'automation.f.grabActivity'
const GRAB_TOOLTIP = 'automation.f.grabActivityNoDevice'

/** Flatten a vnode tree from a slot render fn down to its text. */
function vnodeText(nodes: any): string {
  if (nodes == null) return ''
  if (typeof nodes === 'string') return nodes
  if (Array.isArray(nodes)) return nodes.map(vnodeText).join('')
  const children = nodes.children
  if (typeof children === 'string') return children
  if (Array.isArray(children)) return children.map(vnodeText).join('')
  return ''
}

describe('StepEditForm — assert_activity grab button', () => {
  const assertActivity = (): Step => ({ id: 'aa', action: 'assert_activity', activity: '' })

  it('renders the grab button for an assert_activity step', () => {
    const w = mountForm(assertActivity())
    expect(buttonTexts(w)).toContain(GRAB_BTN)
  })

  it('renders no grab button for assert_element or tap steps', () => {
    const el = mountForm({ id: 'ae', action: 'assert_element', target: { by: 'text', value: 'x' } })
    expect(buttonTexts(el)).not.toContain(GRAB_BTN)
    expect(buttonTexts(mountForm(coordTap()))).not.toContain(GRAB_BTN)
  })

  it('emits grabActivity when clicked', async () => {
    const w = mount(StepEditForm, { props: { step: assertActivity(), canGrab: true } })
    const btn = w.findAll('button').find((b) => b.text() === GRAB_BTN)
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(w.emitted('grabActivity')).toBeTruthy()
  })

  it('disables the button and shows the no-device tooltip when canGrab is false', () => {
    const w = mountForm(assertActivity()) // canGrab omitted → false
    const btn = w.findAll('button').find((b) => b.text() === GRAB_BTN)!
    expect(btn.attributes('disabled')).toBeDefined()
    const tip = w.findComponent(NTooltip)
    expect(tip.exists()).toBe(true)
    // tooltip ENABLED while the button is disabled — that is the whole point
    expect(tip.props('disabled')).toBe(false)
    expect(vnodeText(tip.vm.$slots.default?.())).toContain(GRAB_TOOLTIP)
  })

  it('enables the button and mutes the tooltip when canGrab is true', () => {
    const w = mount(StepEditForm, { props: { step: assertActivity(), canGrab: true } })
    const btn = w.findAll('button').find((b) => b.text() === GRAB_BTN)!
    expect(btn.attributes('disabled')).toBeUndefined()
    expect(w.findComponent(NTooltip).props('disabled')).toBe(true)
  })
})

/**
 * 备注 is metadata that is NOT part of STEP_FIELDS. `save()` rebuilds the step
 * from the visible schema fields only, so an un-preserved note is silently
 * dropped the moment the user saves — exactly what these tests lock down.
 */
describe('StepEditForm note', () => {
  async function confirm(w: ReturnType<typeof mountForm>) {
    const btn = w.findAll('button').find((b) => b.text() === 'common.confirm')
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
  }
  const coordTap = (): Step => ({ id: 't', action: 'tap', mode: 'coord', coord: { x: 1, y: 2 } })

  it('keeps a note through save', async () => {
    const w = mountForm({ ...coordTap(), note: '打开设置页' })
    await confirm(w)
    expect(w.emitted('save')![0][0]).toMatchObject({ action: 'tap', note: '打开设置页' })
  })

  it('omits a whitespace-only note from the saved step', async () => {
    const w = mountForm({ ...coordTap(), note: '   ' })
    await confirm(w)
    const saved = w.emitted('save')![0][0] as Record<string, unknown>
    expect('note' in saved).toBe(false)
  })

  it('shows the note in its own field and re-initialises when the step is replaced', async () => {
    const w = mountForm({ ...coordTap(), note: 'first' })
    expect((w.findAll('.form-field input')[0].element as HTMLInputElement).value).toBe('first')
    await w.setProps({ step: { ...coordTap(), note: 'second' } })
    expect((w.findAll('.form-field input')[0].element as HTMLInputElement).value).toBe('second')
  })

  it('lets the user type a note that then survives save', async () => {
    const w = mountForm(coordTap())
    await w.findAll('.form-field input')[0].setValue('点了登录按钮')
    await confirm(w)
    expect(w.emitted('save')![0][0]).toMatchObject({ note: '点了登录按钮' })
  })
})

/**
 * 失败策略 (`on_error`) is a per-step override of the run-level
 * `continue_on_error`, and — like 备注 — is NOT part of STEP_FIELDS, so
 * `save()` must write it back explicitly. `inherit` must store NOTHING, or
 * changing the run-level setting later would have no effect on this step.
 */
describe('StepEditForm failure policy', () => {
  const coordTap = (): Step => ({ id: 't', action: 'tap', mode: 'coord', coord: { x: 1, y: 2 } })

  /** the on_error n-select is the last select in the form */
  function policySelect(w: ReturnType<typeof mountForm>) {
    const selects = w.findAllComponents(NSelect)
    expect(selects.length).toBeGreaterThan(0)
    return selects[selects.length - 1]
  }

  async function confirm(w: ReturnType<typeof mountForm>) {
    const btn = w.findAll('button').find((b) => b.text() === 'common.confirm')!
    await btn.trigger('click')
  }

  it('renders the policy select for every action, including ones with no fields', () => {
    for (const step of [
      coordTap(),
      { id: 'b', action: 'back' } as Step,
      { id: 'w', action: 'wait', mode: 'time', ms: 100 } as Step,
    ]) {
      const w = mountForm(step)
      expect(w.find('.form-field .n-select').exists()).toBe(true)
    }
  })

  it('shows no policy select when there are no fields at all', () => {
    // guard against the field count assertion above becoming vacuous: `back`
    // has zero schema fields, so the ONLY select is the policy one.
    const w = mountForm({ id: 'b', action: 'back' } as Step)
    expect(w.findAll('.n-select').length).toBe(1)
  })

  it('defaults to inherit and stores nothing on save', async () => {
    const w = mountForm(coordTap())
    await confirm(w)
    const saved = w.emitted('save')![0][0] as Record<string, unknown>
    expect('on_error' in saved).toBe(false)
  })

  it('keeps an existing explicit policy through save', async () => {
    const w = mountForm({ ...coordTap(), on_error: 'continue' } as Step)
    await confirm(w)
    expect(w.emitted('save')![0][0]).toMatchObject({ on_error: 'continue' })
  })

  it('re-syncs the policy when the step is replaced', async () => {
    const w = mountForm({ ...coordTap(), on_error: 'abort' } as Step)
    await w.setProps({ step: { ...coordTap(), on_error: 'continue' } as Step })
    await confirm(w)
    expect(w.emitted('save')![0][0]).toMatchObject({ on_error: 'continue' })
  })

  it('offers exactly the three choices with i18n labels', () => {
    const w = mountForm(coordTap())
    const select = policySelect(w)
    const options = select.props('options') as Array<{ value: string; label: string }>
    expect(options.map((o) => o.value)).toEqual(['inherit', 'continue', 'abort'])
    expect(options.map((o) => o.label)).toEqual([
      'automation.f.onErrorInherit',
      'automation.f.onErrorContinue',
      'automation.f.onErrorAbort',
    ])
  })

  it('writes an explicit choice picked in the dropdown', async () => {
    const w = mountForm(coordTap())
    // drive the underlying n-select the same way its option click would
    policySelect(w).vm.$emit('update:value', 'abort')
    await w.vm.$nextTick()
    await confirm(w)
    expect(w.emitted('save')![0][0]).toMatchObject({ on_error: 'abort' })
  })

  it('drops a stale on_error when the user switches back to inherit', async () => {
    const w = mountForm({ ...coordTap(), on_error: 'continue' } as Step)
    policySelect(w).vm.$emit('update:value', 'inherit')
    await w.vm.$nextTick()
    await confirm(w)
    const saved = w.emitted('save')![0][0] as Record<string, unknown>
    expect('on_error' in saved).toBe(false)
  })
})
