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
import { NSelect } from 'naive-ui'

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
/** 拾取/抓取都是图标按钮（IconButton）：动作文案在 aria-label 与 tooltip 上，
 *  不再占用行内宽度（这正是「按钮被挡住」的修法）。 */
function buttonLabels(w: ReturnType<typeof mountForm>): Array<string | undefined> {
  return w.findAll('button').map((b) => b.attributes('aria-label'))
}
function buttonByLabel(w: ReturnType<typeof mountForm>, label: string) {
  return w.findAll('button').find((b) => b.attributes('aria-label') === label)
}

const coordTap = (): Step => ({ id: 't', action: 'tap', mode: 'coord', coord: { x: 1, y: 2 } })

describe('StepEditForm pick buttons', () => {
  it('renders the screenshot pick icon for a coordinate tap', () => {
    const w = mountForm(coordTap())
    expect(buttonLabels(w)).toContain(COORD_BTN)
    expect(buttonLabels(w)).not.toContain(ELEMENT_BTN)
  })

  it('emits pick { mode: "screenshot" } from that icon', async () => {
    const w = mountForm(coordTap())
    const btn = buttonByLabel(w, COORD_BTN)
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(w.emitted('pick')![0][0]).toEqual({ mode: 'screenshot' })
  })

  it('keeps x and y as real number inputs side by side, each with its own axis prefix', () => {
    const w = mountForm(coordTap())
    // 两个坐标输入都在（X / Y 仍分别必填），且同属一个两列网格
    // （全表单的第 3 个数字输入是通用的「间隔 (ms)」行，与坐标对无关）
    expect(w.findAll('.n-input-number').length).toBe(3)
    expect(w.findAll('.coord-pair .n-input-number').length).toBe(2)
    // X / Y 各自带前缀标记 —— 一眼分清哪个是哪个
    const prefixes = w.findAll('.coord-pair .n-input__prefix').map((p) => p.text())
    expect(prefixes).toEqual(['X', 'Y'])
  })

  it('action buttons live in their own column, NEVER inside the inputs', () => {
    const w = mountForm(coordTap())
    // 坐标行的动作列里是「选坐标」按钮
    const coordRow = w.findAll('.form-row').find((r) => r.find('.coord-pair').exists())!
    expect(coordRow.find('.form-actions-cell button').exists()).toBe(true)
    // 输入框内部（前缀/后缀）不许再塞「拾取/抓取」这类动作按钮 —— 按钮与输入框不混在一起。
    // 数字输入自带的加减步进器不算（它不是动作按钮），所以按 aria-label 判断。
    const insideLabels = w
      .findAll('.n-input__suffix button, .n-input__prefix button')
      .map((b) => b.attributes('aria-label'))
      .filter((l) => l !== undefined)
    expect(insideLabels).toEqual([])
    // 坐标行控制区里只有两个输入，没有按钮
    expect(w.get('.coord-pair').find('button').exists()).toBe(false)
  })

  it('every field row reserves the action column so all inputs share a right edge', () => {
    const w = mountForm(coordTap())
    const rows = w.findAll('.form-row')
    expect(rows.length).toBeGreaterThan(1)
    for (const row of rows) {
      expect(row.find('.form-actions-cell').exists()).toBe(true)
    }
  })

  it('renders the UI-dump pick icon for an element tap instead', () => {
    const w = mountForm({
      id: 't2',
      action: 'tap',
      mode: 'element',
      target: { by: 'text', value: '登录', timeout_ms: 10000 },
    })
    expect(buttonLabels(w)).toContain(ELEMENT_BTN)
    expect(buttonLabels(w)).not.toContain(COORD_BTN)
  })

  it('offers no pick icon for a fixed-duration wait', () => {
    const w = mountForm({ id: 'w', action: 'wait', mode: 'time', ms: 500 })
    expect(buttonLabels(w)).not.toContain(COORD_BTN)
    expect(buttonLabels(w)).not.toContain(ELEMENT_BTN)
  })
})

/**
 * assert_element is an unconditional element target (no mode discriminator),
 * so its `target.value` row must carry the same UI-dump pick icon as
 * input/tap-element. assert_activity is an Activity-string assertion — it has
 * no element target and must never grow an element-pick icon.
 */
describe('StepEditForm pick buttons — assert_element', () => {
  const assertElement = (): Step => ({
    id: 'ae',
    action: 'assert_element',
    target: { by: 'text', value: '首页', timeout_ms: 10000 },
  })

  it('renders the UI-dump pick icon for an assert_element step', () => {
    const w = mountForm(assertElement())
    expect(buttonLabels(w)).toContain(ELEMENT_BTN)
    expect(buttonLabels(w)).not.toContain(COORD_BTN)
  })

  it('emits pick { mode: "element" } from the assert_element pick icon', async () => {
    const w = mountForm(assertElement())
    const btn = buttonByLabel(w, ELEMENT_BTN)
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(w.emitted('pick')![0][0]).toEqual({ mode: 'element' })
  })

  it('renders no element-pick icon for an assert_activity step', () => {
    const w = mountForm({ id: 'aa', action: 'assert_activity', activity: '' })
    expect(buttonLabels(w)).not.toContain(ELEMENT_BTN)
    expect(buttonLabels(w)).not.toContain(COORD_BTN)
  })
})

/**
 * assert_activity's Activity string can be grabbed off the device instead of
 * typed. The form owns only the icon + the disabled state; the PAGE owns the
 * backend call (mirrors the element picker split). `canGrab` comes from the
 * page as `!!autoDeviceId` and, when false, the tooltip text itself becomes the
 * reason ("未连接设备") — one tooltip, no extra element in the row.
 */
const GRAB_BTN = 'automation.f.grabActivity'
const GRAB_TOOLTIP = 'automation.f.grabActivityNoDevice'

describe('StepEditForm — assert_activity grab button', () => {
  const assertActivity = (): Step => ({ id: 'aa', action: 'assert_activity', activity: '' })

  it('renders the grab icon for an assert_activity step', () => {
    // canGrab=true（选了设备）时提示文案就是动作本身
    const w = mount(StepEditForm, { props: { step: assertActivity(), canGrab: true } })
    expect(buttonLabels(w)).toContain(GRAB_BTN)
  })

  it('renders no grab icon for assert_element or tap steps', () => {
    const el = mountForm({ id: 'ae', action: 'assert_element', target: { by: 'text', value: 'x' } })
    expect(buttonLabels(el)).not.toContain(GRAB_BTN)
    expect(buttonLabels(mountForm(coordTap()))).not.toContain(GRAB_BTN)
  })

  it('emits grabActivity when clicked (device selected)', async () => {
    const w = mount(StepEditForm, { props: { step: assertActivity(), canGrab: true } })
    const btn = buttonByLabel(w, GRAB_BTN)
    expect(btn).toBeTruthy()
    expect(btn!.attributes('disabled')).toBeUndefined()
    await btn!.trigger('click')
    expect(w.emitted('grabActivity')).toBeTruthy()
  })

  it('没设备时禁用，并把提示换成「未连接设备」', () => {
    const w = mountForm(assertActivity()) // canGrab omitted → false
    // 提示文案本身就是原因，所以可访问名也跟着换
    const btn = buttonByLabel(w, GRAB_TOOLTIP)
    expect(btn).toBeTruthy()
    expect(btn!.attributes('disabled')).toBeDefined()
    expect(buttonByLabel(w, GRAB_BTN)).toBeUndefined()
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
    expect((w.findAll('.form-row input')[0].element as HTMLInputElement).value).toBe('first')
    await w.setProps({ step: { ...coordTap(), note: 'second' } })
    expect((w.findAll('.form-row input')[0].element as HTMLInputElement).value).toBe('second')
  })

  it('lets the user type a note that then survives save', async () => {
    const w = mountForm(coordTap())
    await w.findAll('.form-row input')[0].setValue('点了登录按钮')
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
      expect(w.find('.form-row .n-select').exists()).toBe(true)
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

/**
 * 录制带入的实测停顿（`recorded_gap_ms`）是**只读**的：它由录制时间线算出，
 * 显示出来是为了让用户看得见录制节奏（也看得见它会叠加在默认间隔之上）。
 * `save()` 从可见 schema 字段重建步骤，所以这个键必须显式写回 —— 否则用户点
 * 一次「确定」就把它静默丢掉（与 note / on_error 完全同一类坑）。
 */
describe('StepEditForm recorded pause', () => {
  async function confirm(w: ReturnType<typeof mountForm>) {
    const btn = w.findAll('button').find((b) => b.text() === 'common.confirm')!
    await btn.trigger('click')
  }
  const coordTap = (): Step => ({ id: 't', action: 'tap', mode: 'coord', coord: { x: 1, y: 2 } })

  it('shows the recorded pause as read-only text, not as another input', () => {
    const w = mountForm({ ...coordTap(), recorded_gap_ms: 1500 } as Step)
    const line = w.get('.form-readonly')
    expect(line.text()).toBe('automation.f.intervalRecordedValue')
    expect(line.attributes('title')).toBe('automation.f.intervalRecordedHint')
    // 只读：一个输入框都不许多出来（x + y + 间隔 = 3 个数字输入）
    expect(w.findAll('.n-input-number').length).toBe(3)
  })

  it('renders no such line for a hand-written step', () => {
    const w = mountForm(coordTap())
    expect(w.find('.form-readonly').exists()).toBe(false)
  })

  it('hides the line for a non-positive / malformed value (nothing to add on top)', () => {
    for (const v of [0, -5, Number.NaN, '1500' as unknown as number]) {
      const w = mountForm({ ...coordTap(), recorded_gap_ms: v } as Step)
      expect(w.find('.form-readonly').exists()).toBe(false)
    }
  })

  it('keeps the recorded pause through save', async () => {
    const w = mountForm({ ...coordTap(), recorded_gap_ms: 1500 } as Step)
    await confirm(w)
    expect(w.emitted('save')![0][0]).toMatchObject({ action: 'tap', recorded_gap_ms: 1500 })
  })

  it('writes nothing when the step has no recorded pause', async () => {
    const w = mountForm(coordTap())
    await confirm(w)
    const saved = w.emitted('save')![0][0] as Record<string, unknown>
    expect('recorded_gap_ms' in saved).toBe(false)
  })

  it('keeps BOTH the manual interval and the recorded pause (delay_ms does not delete it)', async () => {
    // 语义上 delay_ms 会在运行时取代实测停顿，但步骤数据里两者都该留着 ——
    // 用户清空「间隔」时，录制节奏必须还在。
    const w = mountForm({ ...coordTap(), delay_ms: 120, recorded_gap_ms: 1500 } as Step)
    await confirm(w)
    expect(w.emitted('save')![0][0]).toMatchObject({ delay_ms: 120, recorded_gap_ms: 1500 })
  })
})
