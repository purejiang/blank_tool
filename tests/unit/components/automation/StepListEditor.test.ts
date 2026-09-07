/**
 * StepListEditor / StepEditForm / stepTypes / stepMeta unit tests.
 *
 * vue-i18n identity t() (keys render as themselves); NDropdown is stubbed
 * with a clickable div that emits `select` so the add-step path is
 * testable without overlay plumbing.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import StepListEditor from '@/renderer/components/automation/StepListEditor.vue'
import {
  defaultStep, STEP_FIELDS, ADDABLE_ACTIONS, type Step,
} from '@/renderer/components/automation/stepTypes'
import { stepSummary, stepActionLabel } from '@/renderer/components/automation/stepMeta'

function mountEditor(steps: Step[]) {
  return mount(StepListEditor, {
    props: { modelValue: steps },
  })
}

const tap = (x = 1, y = 2): Step => ({ action: 'tap', x, y })
const swipe = (): Step => ({ action: 'swipe', x1: 1, y1: 2, x2: 3, y2: 4, duration_ms: 300 })

describe('stepTypes', () => {
  it('defaultStep fills schema defaults', () => {
    expect(defaultStep('wait')).toEqual({ action: 'wait', ms: 500 })
    expect(defaultStep('tap')).toEqual({ action: 'tap', x: 540, y: 960 })
    const kw = defaultStep('keyevent')
    expect(kw.action).toBe('keyevent')
    expect(kw.key).toBe('BACK')
  })

  it('every addable action has a schema and an i18n label key', () => {
    for (const a of ADDABLE_ACTIONS) {
      expect(STEP_FIELDS[a]).toBeDefined()
      expect(stepActionLabel(a, (k) => k)).toBe(`automation.act.${a}`)
    }
  })
})

describe('stepMeta.stepSummary', () => {
  it('summarizes tap/swipe/wait/input', () => {
    expect(stepSummary({ action: 'tap', x: 422, y: 779 })).toBe('(422, 779)')
    expect(stepSummary(swipe())).toBe('(1, 2) → (3, 4) · 300ms')
    expect(stepSummary({ action: 'wait', ms: 800 })).toBe('800ms')
    expect(stepSummary({ action: 'input', text: 'hello' })).toBe('“hello”')
    expect(stepSummary({ action: 'input' })).toBe('—')
  })

  it('summarizes element/parameterized actions', () => {
    expect(stepSummary({ action: 'tap_element', by: 'text', value: '登录', timeout_ms: 10000 }))
      .toBe('text: 登录 · 10000ms')
    expect(stepSummary({ action: 'assert_element', by: 'resource_id', value: 'btn' }))
      .toBe('resource_id: btn · exists')
    expect(stepSummary({ action: 'back' })).toBe('')
  })
})

describe('StepListEditor', () => {
  it('renders one row per step with index and summary', () => {
    const w = mountEditor([tap(), swipe()])
    const rows = w.findAll('.step-row')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('automation.act.tap')
    expect(rows[0].text()).toContain('(1, 2)')
    expect(rows[1].text()).toContain('(1, 2) → (3, 4) · 300ms')
  })

  it('emits a cloned array without the deleted step', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2), tap(3, 3)])
    await w.findAll('.step-row')[1].findAll('button')[3].trigger('click')
    const evt = w.emitted('update:modelValue')
    expect(evt![0][0]).toEqual([tap(1, 1), tap(3, 3)])
    // cloned, not the same reference
    expect(evt![0][0]).not.toBe(w.props('modelValue'))
  })

  it('move up swaps rows via emit', async () => {
    const w = mountEditor([tap(1, 1), swipe()])
    // first row buttons: [up, down, edit, delete]
    await w.findAll('.step-row')[1].findAll('button')[0].trigger('click')
    expect(w.emitted('update:modelValue')![0][0]).toEqual([swipe(), tap(1, 1)])
  })

  it('add appends a defaulted step and opens its edit form', async () => {
    const w = mountEditor([tap()])
    // invoke the dropdown select handler directly (script-setup internals)
    ;(w.vm.$ as any).setupState.onAdd('wait')
    const evt = w.emitted('update:modelValue')!
    expect(evt[0][0]).toEqual([tap(), { action: 'wait', ms: 500 }])
    // parent feeds the new array back (v-model contract)
    await w.setProps({ modelValue: evt[0][0] as Step[] })
    // new step enters edit mode -> StepEditForm rendered
    expect(w.findComponent({ name: 'StepEditForm' }).exists()).toBe(true)
  })

  it('saving the edit form replaces the step at the right index', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2)])
    await w.findAll('.step-row')[0].findAll('button')[2].trigger('click') // edit
    const form = w.findComponent({ name: 'StepEditForm' })
    expect(form.exists()).toBe(true)
    form.vm.$emit('save', { action: 'tap', x: 9, y: 9 })
    await w.vm.$nextTick()
    expect(w.emitted('update:modelValue')![0][0]).toEqual([{ action: 'tap', x: 9, y: 9 }, tap(2, 2)])
    // form closed after save
    expect(w.findComponent({ name: 'StepEditForm' }).exists()).toBe(false)
  })

  it('shows empty hint when no steps', () => {
    const w = mountEditor([])
    expect(w.text()).toContain('automation.noStepsHint')
  })
})

describe('StepEditForm', () => {
  it('emits a numeric-normalized step on save', async () => {
    const { default: StepEditForm } = await import('@/renderer/components/automation/StepEditForm.vue')
    const w = mount(StepEditForm, {
      props: { step: defaultStep('wait') },
    })
    // drive the internal reactive form (script-setup internals)
    ;(w.vm.$ as any).setupState.form.ms = 1200
    const btns = w.findAll('button')
    const confirm = btns.find((b: any) => b.text().includes('common.confirm'))!
    await confirm.trigger('click')
    const evt = w.emitted('save')
    expect(evt![0][0]).toEqual({ action: 'wait', ms: 1200 })
  })

  it('blocks save when a required field is empty', async () => {
    const { default: StepEditForm } = await import('@/renderer/components/automation/StepEditForm.vue')
    const w = mount(StepEditForm, {
      props: { step: { action: 'input', text: '' } },
    })
    ;(w.vm.$ as any).setupState.form.text = ''
    const btns = w.findAll('button')
    const confirm = btns.find((b: any) => b.text().includes('common.confirm'))!
    await confirm.trigger('click')
    expect(w.emitted('save')).toBeUndefined()
    expect(w.text()).toContain('automation.f.required')
  })
})
