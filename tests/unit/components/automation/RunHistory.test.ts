/**
 * RunHistory row semantics.
 *
 * Since the backend keeps a `summary.json` index from the moment a run STARTS,
 * the history list can contain two rows the old UI never had to render:
 *
 *  - `running`   — a run executing right now (no report.json yet)
 *  - `orphan`    — an interrupted leftover: artifacts but no report
 *
 * Neither has a readable report, so selecting them used to fail with
 * 「报告读取失败」. They must therefore be inert (no `select` emit) while still
 * offering the delete affordance — deleting the orphan is the whole point.
 *
 * vue-i18n is mocked to an identity t() (keys render as themselves).
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import RunHistory from '@/renderer/components/automation/RunHistory.vue'

const finished = {
  task_id: 't-ok',
  started_at: '2026-09-14T10:00:00',
  duration_ms: 1200,
  success: true,
  passed: 3,
  total: 3,
}
const orphan = {
  task_id: 't-dead',
  started_at: '2026-09-14T09:00:00',
  orphan: true,
  interrupted: true,
  running: false,
  size: 2048,
  files: 4,
  success: false,
  passed: 0,
  total: 5,
}
const running = {
  task_id: 't-live',
  started_at: '2026-09-14T11:00:00',
  running: true,
  success: true,
  passed: 1,
  total: 5,
}

function mountHistory(runs: any[]) {
  return mount(RunHistory, {
    props: { runs },
    global: { stubs: { 'n-scrollbar': { template: '<div><slot /></div>' } } },
  })
}

function rows(w: ReturnType<typeof mountHistory>) {
  return w.findAll('.run-row')
}

describe('RunHistory', () => {
  it('renders one row per run', () => {
    expect(rows(mountHistory([finished, orphan, running]))).toHaveLength(3)
  })

  it('emits select for a finished run', async () => {
    const w = mountHistory([finished])
    await rows(w)[0].trigger('click')
    expect(w.emitted('select')).toEqual([['t-ok']])
  })

  it('does not emit select for an orphan row (no report to read)', async () => {
    const w = mountHistory([orphan])
    await rows(w)[0].trigger('click')
    expect(w.emitted('select')).toBeUndefined()
  })

  it('does not emit select for a running row', async () => {
    const w = mountHistory([running])
    await rows(w)[0].trigger('click')
    expect(w.emitted('select')).toBeUndefined()
  })

  it('marks orphan and running rows as inert', () => {
    const w = mountHistory([orphan, running, finished])
    expect(rows(w)[0].classes()).toContain('inert')
    expect(rows(w)[1].classes()).toContain('inert')
    expect(rows(w)[2].classes()).not.toContain('inert')
  })

  it('badges an orphan and shows its size instead of a duration', () => {
    const w = mountHistory([orphan])
    expect(rows(w)[0].find('.run-tag').text()).toBe('automation.runOrphan')
    expect(rows(w)[0].find('.run-dur').text()).toBe('2KB')
  })

  it('badges a running run', () => {
    const w = mountHistory([running])
    expect(rows(w)[0].find('.run-tag').text()).toBe('automation.runRunning')
    expect(rows(w)[0].find('.run-dur').text()).toBe('0ms')
  })

  it('still deletes an orphan (the delete button stays live)', async () => {
    const w = mountHistory([orphan])
    await rows(w)[0].find('.run-del').trigger('click')
    expect(w.emitted('remove')).toEqual([['t-dead']])
  })

  it('keeps the success/failure colour coding for finished runs', () => {
    const w = mountHistory([finished, { ...finished, task_id: 't-bad', success: false }])
    expect(rows(w)[0].classes()).toContain('ok')
    expect(rows(w)[1].classes()).toContain('bad')
  })

  it('shows the empty state when there is no run', () => {
    expect(mountHistory([]).find('.rh-empty').exists()).toBe(true)
  })
})
