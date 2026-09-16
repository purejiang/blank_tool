/**
 * StepListEditor / StepEditForm / stepTypes / stepMeta unit tests — **v2 model**.
 *
 * The step model is v2 (see stepTypes.ts): every step carries `id`, tap/wait
 * carry a `mode` discriminator, and coordinates/paths/targets are NESTED
 * (`coord` / `path` / `target`). Legacy flat actions (`tap_element` …) are gone
 * by design. Row interaction: a row CLICK expands/collapses the inline editor
 * (there is no pencil button any more) and reordering is a drag from the front
 * grip handle, which hands the browser the whole row as its drag image.
 *
 * vue-i18n identity t() (keys render as themselves).
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

const tap = (x = 1, y = 2): Step => ({ id: `tap-${x}-${y}`, action: 'tap', mode: 'coord', coord: { x, y } })
const swipe = (): Step => ({
  id: 'swipe',
  action: 'swipe',
  path: { x1: 1, y1: 2, x2: 3, y2: 4, duration_ms: 300 },
})
/** Minimal DataTransfer stand-in for drag events. */
function dt(extra: Record<string, unknown> = {}) {
  return { effectAllowed: '', setData: () => {}, setDragImage: () => {}, ...extra }
}

describe('stepTypes', () => {
  it('defaultStep fills schema defaults (v2 shape: id + mode + nested params)', () => {
    expect(defaultStep('wait')).toMatchObject({ action: 'wait', mode: 'time', ms: 500 })
    expect(defaultStep('tap')).toMatchObject({ action: 'tap', mode: 'coord', coord: { x: 540, y: 960 } })
    // element-target fields stay out of the coord default (visibleWhen guard)
    expect(defaultStep('tap').target).toBeUndefined()
    // every step gets a stable id
    expect(typeof defaultStep('back').id).toBe('string')
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
    expect(stepSummary(tap(422, 779))).toBe('422, 779')
    expect(stepSummary(swipe())).toBe('(1, 2) → (3, 4) · 300ms')
    expect(stepSummary({ id: 'w', action: 'wait', mode: 'time', ms: 800 })).toBe('800ms')
    expect(stepSummary({ id: 'i', action: 'input', text: 'hello' })).toBe('hello')
    expect(stepSummary({ id: 'i', action: 'input' })).toBe('')
  })

  it('summarizes element/parameterized actions (nested target)', () => {
    expect(stepSummary({
      id: 't', action: 'tap', mode: 'element',
      target: { by: 'text', value: '登录', timeout_ms: 10000 },
    })).toBe('text: 登录 · 10000ms')
    expect(stepSummary({
      id: 'a', action: 'assert_element',
      target: { by: 'resource_id', value: 'btn', timeout_ms: 10000 },
    })).toBe('resource_id: btn · 10000ms · exists')
    expect(stepSummary({ id: 'b', action: 'back' })).toBe('')
  })
})

describe('StepListEditor', () => {
  it('renders one row per step with index and summary', () => {
    const w = mountEditor([tap(), swipe()])
    const rows = w.findAll('.step-row')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('automation.act.tap')
    expect(rows[0].text()).toContain('1, 2')
    expect(rows[1].text()).toContain('(1, 2) → (3, 4) · 300ms')
  })

  it('emits a cloned array without the deleted step', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2), tap(3, 3)])
    // row ops are [delete, insert-below] — the pencil is gone (a row click
    // expands the editor) and reorder is long-press drag & drop now
    await w.findAll('.step-row')[1].findAll('button')[0].trigger('click')
    const evt = w.emitted('update:modelValue')
    expect(evt![0][0]).toEqual([tap(1, 1), tap(3, 3)])
    // cloned, not the same reference
    expect(evt![0][0]).not.toBe(w.props('modelValue'))
  })

  it('reorders rows by dragging the handle', async () => {
    const w = mountEditor([tap(1, 1), swipe()])
    await w.findAll('.step-handle')[1].trigger('dragstart', { dataTransfer: dt() })
    await w.findAll('.step-item')[0].trigger('drop')
    expect(w.emitted('update:modelValue')![0][0]).toEqual([swipe(), tap(1, 1)])
  })

  it('uses the WHOLE row as the drag image so it follows the cursor', async () => {
    const w = mountEditor([tap(1, 1), swipe()])
    const setDragImage = vi.fn()
    await w.findAll('.step-handle')[1].trigger('dragstart', {
      clientX: 30,
      clientY: 40,
      dataTransfer: dt({ setDragImage }),
    })
    expect(setDragImage).toHaveBeenCalledTimes(1)
    // the drag image must be the row, not the 20px grip the browser defaults to
    const el = setDragImage.mock.calls[0][0] as HTMLElement
    expect(el.classList.contains('step-item')).toBe(true)
    // and offset to where the pointer grabbed it, so it is picked up in place
    expect(setDragImage.mock.calls[0][1]).toBe(30 - el.getBoundingClientRect().left)
    expect(setDragImage.mock.calls[0][2]).toBe(40 - el.getBoundingClientRect().top)
  })

  it('only the handle is a drag source — the row itself never is', () => {
    const w = mountEditor([tap(1, 1), swipe()])
    expect(w.findAll('.step-handle')[1].attributes('draggable')).toBe('true')
    expect(w.findAll('.step-item')[1].attributes('draggable')).toBeUndefined()
  })

  it('row click expands + selects, a second click collapses + deselects', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2)])
    const items = w.findAll('.step-item')
    await items[0].trigger('click')
    expect(w.findComponent({ name: 'StepEditForm' }).exists()).toBe(true)
    expect(w.emitted('update:selectedIndex')![0][0]).toBe(0)
    await items[0].trigger('click')
    expect(w.findComponent({ name: 'StepEditForm' }).exists()).toBe(false)
    expect(w.emitted('update:selectedIndex')![1][0]).toBe(-1)
  })

  it('edits a row in place and saves back at that index', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2)])
    await w.findAll('.step-item')[0].trigger('click') // row click = expand
    const form = w.findComponent({ name: 'StepEditForm' })
    expect(form.exists()).toBe(true)
    expect(w.emitted('update:selectedIndex')![0][0]).toBe(0)

    const updated = tap(9, 9)
    form.vm.$emit('save', updated)
    await w.vm.$nextTick()
    expect(w.emitted('update:modelValue')![0][0]).toEqual([updated, tap(2, 2)])
    // form closed — and the selection drops with it (open row == selected row)
    expect(w.findComponent({ name: 'StepEditForm' }).exists()).toBe(false)
    expect(w.emitted('update:selectedIndex')![1][0]).toBe(-1)
  })

  it('openEditor opens the edit form for an externally appended step and selects it', async () => {
    // The add-step flow lives on the page (dropdown) — it appends the step and
    // calls openEditor(index) through the component ref.
    const w = mountEditor([tap()])
    ;(w.vm as unknown as { openEditor: (i: number) => void }).openEditor(0)
    await w.vm.$nextTick()
    expect(w.findComponent({ name: 'StepEditForm' }).exists()).toBe(true)
    expect(w.emitted('update:selectedIndex')![0][0]).toBe(0)
  })

  it('has no pencil/edit button any more — delete and insert-below remain', () => {
    const w = mountEditor([tap(1, 1)])
    // 图标按钮的可访问名/提示由 IconButton 提供（label → aria-label + tooltip），
    // 不再是原生 title
    const labels = w.findAll('button').map((b) => b.attributes('aria-label'))
    expect(labels).not.toContain('automation.stepEdit')
    expect(labels).toContain('automation.stepDelete')
    expect(labels).toContain('automation.addStep')
  })

  it('renders the note as a second line only when the step carries one', () => {
    const w = mountEditor([{ ...tap(1, 2), note: '打开设置页' }, tap(3, 4)])
    const notes = w.findAll('.step-note')
    expect(notes.length).toBe(1)
    expect(notes[0].text()).toBe('打开设置页')
    // whitespace-only notes count as absent
    expect(mountEditor([{ ...tap(1, 2), note: '   ' }]).findAll('.step-note').length).toBe(0)
  })

  it('shows empty hint when no steps', () => {
    const w = mountEditor([])
    expect(w.text()).toContain('automation.noStepsHint')
  })
})

describe('StepEditForm', () => {
  it('emits a numeric-normalized step on save', async () => {
    const { default: StepEditForm } = await import('@/renderer/components/automation/StepEditForm.vue')
    const step = defaultStep('wait')
    const w = mount(StepEditForm, {
      props: { step },
    })
    // drive the internal reactive form (script-setup internals)
    ;(w.vm.$ as any).setupState.form.ms = 1200
    const btns = w.findAll('button')
    const confirm = btns.find((b: any) => b.text().includes('common.confirm'))!
    await confirm.trigger('click')
    const evt = w.emitted('save')
    expect(evt![0][0]).toMatchObject({ id: step.id, action: 'wait', ms: 1200 })
  })

  it('blocks save when a required field is empty', async () => {
    const { default: StepEditForm } = await import('@/renderer/components/automation/StepEditForm.vue')
    const w = mount(StepEditForm, {
      props: { step: { id: 'i', action: 'input', text: '' } },
    })
    ;(w.vm.$ as any).setupState.form.text = ''
    const btns = w.findAll('button')
    const confirm = btns.find((b: any) => b.text().includes('common.confirm'))!
    await confirm.trigger('click')
    expect(w.emitted('save')).toBeUndefined()
    expect(w.text()).toContain('automation.f.required')
  })
})
