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
import { mount, type VueWrapper } from '@vue/test-utils'
import { NDropdown } from 'naive-ui'

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import StepListEditor from '@/renderer/components/automation/StepListEditor.vue'
import {
  defaultStep, STEP_FIELDS, ADDABLE_ACTIONS, type Step,
} from '@/renderer/components/automation/stepTypes'
import { stepSummary, stepActionLabel } from '@/renderer/components/automation/stepMeta'

const ADD_OPTIONS = [
  { key: '__record__', label: 'record' },
  { key: 'tap', label: 'tap' },
]

function mountEditor(steps: Step[], extra: Record<string, unknown> = {}) {
  return mount(StepListEditor, {
    props: { modelValue: steps, addOptions: ADD_OPTIONS, ...extra },
  })
}

/** 行内「⋮」菜单：按 DOM 顺序取第 i 行的那个下拉（用 duplicate 选项认出来）。 */
function rowMenu(w: VueWrapper, i: number) {
  return w
    .findAllComponents(NDropdown)
    .filter((d) => (d.props('options') as any[])?.some((o) => o.key === 'duplicate'))[i]
}

/** 底部常驻「添加步骤」的下拉：不是行内「⋮」菜单（那些都带 duplicate 项）。 */
function addMenu(w: VueWrapper) {
  return w
    .findAllComponents(NDropdown)
    .find((d) => !(d.props('options') as any[])?.some((o) => o.key === 'duplicate'))
}

async function pickRowMenu(w: VueWrapper, i: number, key: string) {
  rowMenu(w, i).vm.$emit('select', key)
  await w.vm.$nextTick()
}

function option(w: VueWrapper, i: number, key: string) {
  return (rowMenu(w, i).props('options') as any[]).find((o) => o.key === key)
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

  it('emits a cloned array without the deleted step (via the row menu)', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2), tap(3, 3)])
    await pickRowMenu(w, 1, 'delete')
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

  it('has no pencil/edit button any more — every row carries ONE ⋮ menu', () => {
    const w = mountEditor([tap(1, 1)])
    const labels = w.findAll('button').map((b) => b.attributes('aria-label'))
    expect(labels).not.toContain('automation.stepEdit')
    // 删除/插入都收进了「⋮」菜单，行内不再有常驻的删除 / ＋ 按钮
    expect(labels).not.toContain('automation.stepDelete')
    expect(labels.filter((l) => l === 'common.more')).toHaveLength(1)
    // 添加步骤入口是列表底部的文字按钮（常驻）
    expect(w.get('.add-step').text()).toContain('automation.addStep')
  })

  it('renders the note as a second line only when the step carries one', () => {
    const w = mountEditor([{ ...tap(1, 2), note: '打开设置页' }, tap(3, 4)])
    const notes = w.findAll('.step-note')
    expect(notes.length).toBe(1)
    expect(notes[0].text()).toBe('打开设置页')
    // whitespace-only notes count as absent
    expect(mountEditor([{ ...tap(1, 2), note: '   ' }]).findAll('.step-note').length).toBe(0)
  })

  it('shows empty hint when no steps — and the bottom add entry stays', () => {
    const w = mountEditor([])
    expect(w.text()).toContain('automation.noStepsHint')
    expect(w.get('.add-step').exists()).toBe(true)
  })
})

/**
 * 行内「⋮」菜单 + 底部常驻「添加步骤」。
 *
 * 设计：添加步骤的入口固定在列表底部（不再有顶部幽灵行）；行内操作收进一个
 * 竖排菜单（向下添加步骤 / 上移 / 下移 / 置顶 / 复制 / 删除），拖拽排序保留。
 */
describe('StepListEditor — row menu & bottom add entry', () => {
  it('菜单项完整，且首行/末行的排序项按边界禁用', () => {
    const w = mountEditor([tap(1, 1), tap(2, 2)])
    const keys = (rowMenu(w, 0).props('options') as any[]).map((o) => o.key)
    expect(keys).toEqual([
      'insert', 'runFrom', 'd0', 'up', 'down', 'top', 'duplicate', 'd1', 'delete',
    ])
    // 「向下添加步骤」的子菜单 = 页面给的同一份动作清单
    expect((option(w, 0, 'insert').children as any[]).map((o) => o.key)).toEqual(['__record__', 'tap'])

    // 第一行：上移 / 置顶禁用，下移可用
    expect(option(w, 0, 'up').disabled).toBe(true)
    expect(option(w, 0, 'top').disabled).toBe(true)
    expect(option(w, 0, 'down').disabled).toBe(false)
    // 最后一行：下移禁用，上移可用
    expect(option(w, 1, 'down').disabled).toBe(true)
    expect(option(w, 1, 'up').disabled).toBe(false)
  })

  it('「从此步开始运行」：抛 runFrom 带行下标，且不当作插入 key', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2), tap(3, 3)])
    expect((option(w, 0, 'runFrom').label)).toBe('automation.runFromStep')

    await pickRowMenu(w, 2, 'runFrom')
    expect(w.emitted('runFrom')).toEqual([[2]])
    // 起点是运行参数，不能落进「插入步骤」那条路径
    expect(w.emitted('insertBelow')).toBeUndefined()
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })

  it('置顶 / 上移 / 下移改变顺序', async () => {
    const up = mountEditor([tap(1, 1), tap(2, 2)])
    await pickRowMenu(up, 1, 'up')
    expect(up.emitted('update:modelValue')![0][0]).toEqual([tap(2, 2), tap(1, 1)])

    const down = mountEditor([tap(1, 1), tap(2, 2)])
    await pickRowMenu(down, 0, 'down')
    expect(down.emitted('update:modelValue')![0][0]).toEqual([tap(2, 2), tap(1, 1)])

    const top = mountEditor([tap(1, 1), tap(2, 2), tap(3, 3)])
    await pickRowMenu(top, 2, 'top')
    expect(top.emitted('update:modelValue')![0][0]).toEqual([tap(3, 3), tap(1, 1), tap(2, 2)])
  })

  it('复制：内容一致、id 不同、插在该行下方并选中副本', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2)])
    await pickRowMenu(w, 0, 'duplicate')

    const list = w.emitted('update:modelValue')![0][0] as Step[]
    expect(list).toHaveLength(3)
    expect(list[0]).toEqual(tap(1, 1))
    expect(list[1]).toMatchObject({ action: 'tap', mode: 'coord', coord: { x: 1, y: 1 } })
    expect(list[1].id).not.toBe(list[0].id)   // 新 id，避免两步同 id
    expect(list[2]).toEqual(tap(2, 2))
    expect(w.emitted('update:selectedIndex')![0][0]).toBe(1)
  })

  it('子菜单里的动作 key = 插到该行下方（沿用 insertBelow 契约）', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2)])
    await pickRowMenu(w, 0, 'tap')
    expect(w.emitted('insertBelow')).toEqual([[{ index: 0, key: 'tap' }]])

    await pickRowMenu(w, 1, '__record__')
    expect(w.emitted('insertBelow')![1][0]).toEqual({ index: 1, key: '__record__' })
  })

  it('底部「添加步骤」：落点 = 最后一行；空列表取 0（即第一行）', async () => {
    const w = mountEditor([tap(1, 1), tap(2, 2)])
    addMenu(w)!.vm.$emit('select', 'tap')
    await w.vm.$nextTick()
    expect(w.emitted('insertBelow')).toEqual([[{ index: 1, key: 'tap' }]])

    const empty = mountEditor([])
    addMenu(empty)!.vm.$emit('select', 'tap')
    await empty.vm.$nextTick()
    expect(empty.emitted('insertBelow')).toEqual([[{ index: -1, key: 'tap' }]])
  })

  it('只读（disabled）时底部入口与行内菜单都禁用', () => {
    const w = mountEditor([tap(1, 1)], { disabled: true })
    expect((w.get('.add-step').element as HTMLButtonElement).disabled).toBe(true)
    expect(rowMenu(w, 0).props('disabled')).toBe(true)
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

  /**
   * 步骤间隔（`delay_ms`）——通用字段，和备注 / 失败策略一样不进 per-action schema。
   * 留空 = 跟随运行配置里的默认间隔（键都不写）；0 = 这一步显式不等待。
   */
  it('间隔留空 = 不写 delay_ms（跟随运行配置的默认间隔）', async () => {
    const { default: StepEditForm } = await import('@/renderer/components/automation/StepEditForm.vue')
    const w = mount(StepEditForm, {
      props: { step: defaultStep('wait'), defaultInterval: 300 },
    })
    // 占位提示显示的是运行配置里的默认值（这里 i18n 是恒等 t）
    expect(w.find('input[placeholder="automation.f.intervalDefault"]').exists()).toBe(true)

    const confirm = w.findAll('button').find((b: any) => b.text().includes('common.confirm'))!
    await confirm.trigger('click')
    expect(w.emitted('save')![0][0]).not.toHaveProperty('delay_ms')
  })

  it('填了间隔就写进 delay_ms —— 0 是显式的「这一步不等待」', async () => {
    const { default: StepEditForm } = await import('@/renderer/components/automation/StepEditForm.vue')
    const w = mount(StepEditForm, { props: { step: defaultStep('wait') } })
    ;(w.vm.$ as any).setupState.interval = 0
    const confirm = w.findAll('button').find((b: any) => b.text().includes('common.confirm'))!
    await confirm.trigger('click')
    expect(w.emitted('save')![0][0]).toMatchObject({ action: 'wait', delay_ms: 0 })
  })

  it('已有的 delay_ms 会回填进表单，保存后原样保留', async () => {
    const { default: StepEditForm } = await import('@/renderer/components/automation/StepEditForm.vue')
    const w = mount(StepEditForm, {
      props: { step: { ...defaultStep('wait'), delay_ms: 800 } },
    })
    expect((w.vm.$ as any).setupState.interval).toBe(800)

    const confirm = w.findAll('button').find((b: any) => b.text().includes('common.confirm'))!
    await confirm.trigger('click')
    expect(w.emitted('save')![0][0]).toMatchObject({ action: 'wait', delay_ms: 800 })
  })
})
