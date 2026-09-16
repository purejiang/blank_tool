/**
 * 录制落库：把录制时间线（`ts`，设备时间秒）换算成每步的**实测停顿**。
 *
 * 契约（与后端 `orchestrator._step_gap_ms` 配对）：
 *  - 步骤模型里**不存 `ts`**，只存换算出来的 `recorded_gap_ms`；
 *  - `recorded_gap_ms` = 上一步触摸结束 → 这一步触摸结束 的时间差；
 *  - 第一步没有前序可比 → 不写这个键；0 / 负数（时钟回跳）也不写（没有可叠加的量）；
 *  - 运行时它是**叠加**在默认步骤间隔之上的，录制节奏不会被默认间隔抹掉。
 *
 * 一旦这里算错，脚本跑起来的节奏就与录制时不一致 —— 而且是静默的。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const setAppConfig = vi.fn()
const getAppConfig = vi.fn()

vi.mock('@services/ConfigService', () => ({
  ConfigService: class {
    setAppConfig = setAppConfig
    getAppConfig = getAppConfig
  },
}))

vi.mock('naive-ui', () => ({
  useMessage: () => ({ error: () => {}, success: () => {}, warning: () => {} }),
  useDialog: () => ({ warning: () => {}, error: () => {} }),
}))

vi.mock('vue-i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-i18n')>()
  return { ...actual, useI18n: () => ({ t: (k: string) => k }) }
})

import { useAutomationStore } from '@/renderer/composables/automation/useAutomationStore'

const PID = 'p1'
const SID = 's1'

const DOC = {
  version: 3,
  projects: [
    {
      id: PID,
      name: 'demo',
      scripts: [{ id: SID, name: 'main', updated_at: '2024-01-01T00:00:00Z', steps: [] }],
    },
  ],
  ui: {},
}

/** Store with the demo script selected and its editor loaded. */
async function store() {
  getAppConfig.mockResolvedValue(JSON.parse(JSON.stringify(DOC)))
  const s = useAutomationStore()
  await s.loadConfig()
  s.selectProject(PID)
  s.selectScript(PID, SID)
  return s
}

function gaps(steps: any[]): Array<number | undefined> {
  return steps.map((x) => x.recorded_gap_ms)
}

beforeEach(() => {
  setAppConfig.mockReset()
  setAppConfig.mockResolvedValue(undefined)
  getAppConfig.mockReset()
  localStorage.clear()
})

describe('onRecorded — 实测停顿换算', () => {
  it('把相邻两步的 ts 差值写成后一步的 recorded_gap_ms', async () => {
    const s = await store()
    s.onRecorded({
      steps: [
        { action: 'tap', x: 1, y: 2, ts: 10.0 },
        { action: 'tap', x: 3, y: 4, ts: 11.5 },
        { action: 'swipe', x1: 1, y1: 2, x2: 3, y2: 4, duration_ms: 300, ts: 18.0 },
      ],
      insertAt: 'end',
    })

    expect(s.editor.steps.map((x: any) => x.action)).toEqual(['tap', 'tap', 'swipe'])
    expect(gaps(s.editor.steps)).toEqual([undefined, 1500, 6500])
  })

  it('录到的 ts 不进入步骤模型（只留换算后的停顿）', async () => {
    const s = await store()
    s.onRecorded({
      steps: [
        { action: 'tap', x: 1, y: 2, ts: 10.0 },
        { action: 'tap', x: 3, y: 4, ts: 10.25 },
      ],
      insertAt: 'end',
    })

    for (const step of s.editor.steps as any[]) {
      expect('ts' in step).toBe(false)
    }
    expect(s.editor.steps[1].recorded_gap_ms).toBe(250)
  })

  it('第一步没有前序 → 不写这个键（不是写 0）', async () => {
    const s = await store()
    s.onRecorded({
      steps: [{ action: 'tap', x: 1, y: 2, ts: 10.0 }],
      insertAt: 'end',
    })
    expect('recorded_gap_ms' in (s.editor.steps[0] as any)).toBe(false)
  })

  it('0 / 负数差值（两步同刻、时钟回跳）不写键 —— 没有可叠加的量', async () => {
    const s = await store()
    s.onRecorded({
      steps: [
        { action: 'tap', x: 1, y: 2, ts: 10.0 },
        { action: 'tap', x: 3, y: 4, ts: 10.0 },   // 同一时刻
        { action: 'tap', x: 5, y: 6, ts: 9.0 },    // 回跳
      ],
      insertAt: 'end',
    })
    expect(gaps(s.editor.steps)).toEqual([undefined, undefined, undefined])
  })

  it('缺 ts / 非数字 ts 一律不写键（旧片段或缺字段的载荷）', async () => {
    const s = await store()
    s.onRecorded({
      steps: [
        { action: 'tap', x: 1, y: 2 },                 // 无 ts
        { action: 'tap', x: 3, y: 4, ts: 11.0 },        // 前一步无 ts → 无从算起
        { action: 'tap', x: 5, y: 6, ts: 'soon' },      // 非数字 → 不写
      ],
      insertAt: 'end',
    })
    expect(gaps(s.editor.steps)).toEqual([undefined, undefined, undefined])
  })

  it('插在选中行之后时，片段内部照常换算（不与上方老步骤牵连）', async () => {
    const s = await store()
    s.editor.steps = [{ id: 'old', action: 'tap', mode: 'coord', coord: { x: 0, y: 0 } }] as any
    s.selectedStepIndex = 0

    s.onRecorded({
      steps: [
        { action: 'tap', x: 1, y: 2, ts: 100.0 },
        { action: 'tap', x: 3, y: 4, ts: 100.75 },
      ],
      insertAt: 'after',
    })

    const steps = s.editor.steps as any[]
    expect(steps.map((x) => (x.id === 'old' ? 'old' : x.action))).toEqual(['old', 'tap', 'tap'])
    // 老步骤没有停顿；片段第一步也没有（它在片段里是第一步，且老步骤没有 ts）
    expect(steps[0].recorded_gap_ms).toBeUndefined()
    expect(steps[1].recorded_gap_ms).toBeUndefined()
    expect(steps[2].recorded_gap_ms).toBe(750)
  })

  it('插到开头时，实测停顿跟随各自的步骤一起走', async () => {
    const s = await store()
    s.editor.steps = [{ id: 'old', action: 'tap', mode: 'coord', coord: { x: 0, y: 0 } }] as any

    s.onRecorded({
      steps: [
        { action: 'tap', x: 1, y: 2, ts: 1.0 },
        { action: 'tap', x: 3, y: 4, ts: 2.25 },
      ],
      insertAt: 'start',
    })

    const steps = s.editor.steps as any[]
    expect(steps.map((x) => (x.id === 'old' ? 'old' : x.action))).toEqual(['tap', 'tap', 'old'])
    expect(steps[0].recorded_gap_ms).toBeUndefined()
    expect(steps[1].recorded_gap_ms).toBe(1250)
  })
})
