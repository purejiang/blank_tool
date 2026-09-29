import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'
import { createI18n } from 'vue-i18n'

import RunLogPanel from '@/renderer/components/workflow/RunLogPanel.vue'
import type { RunLogLine } from '@/renderer/components/workflow/runLog'

/**
 * RunLogPanel (docs/08 §3·S2 的「运行日志」).
 *
 * The panel is deliberately presentational: the page owns the lines (live
 * stream buffer, then `task.read_log`) and the side effects. These tests pin the
 * rendering contract — one row per line with its kind class, both empty states,
 * the truncation note — plus the three button emits and the disabled state of
 * 「打开日志文件」 before a `log_path` is known.
 */

// Empty messages: t() returns the key, so assertions ride on stable i18n keys.
const i18n = createI18n({
  legacy: false,
  locale: 'en-US',
  messages: { 'en-US': {} },
  missingWarn: false,
  fallbackWarn: false,
})

/** Minimal n-button stand-in that forwards clicks and honours `disabled`. */
const NButtonStub = {
  name: 'Button',
  props: { disabled: Boolean, loading: Boolean },
  emits: ['click'],
  setup(props: any, { emit, slots }: any) {
    return () =>
      h(
        'button',
        {
          class: 'n-button-stub',
          disabled: props.disabled || undefined,
          onClick: () => emit('click'),
        },
        [slots.icon?.(), slots.default?.()],
      )
  },
}

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(RunLogPanel, {
    props: { lines: [] as RunLogLine[], ...props },
    global: {
      plugins: [i18n],
      // Keyed by the component's own `name` (naive-ui's NButton is "Button"),
      // which is how @vue/test-utils resolves stubs.
      stubs: { Button: NButtonStub, AppIcon: true },
    },
  })
}

const LINES: RunLogLine[] = [
  { kind: 'node', text: '[node_started] write (file.write)' },
  { kind: 'log', text: '[log] [info] 命中 2 行' },
  { kind: 'workflow', text: '[workflow_completed] success=true' },
  { kind: 'plain', text: 'raw stdio line' },
]

describe('RunLogPanel', () => {
  it('renders one row per line, tagged with its kind', () => {
    const wrapper = mountPanel({ lines: LINES })
    const rows = wrapper.findAll('.rl-line')
    expect(rows).toHaveLength(4)
    expect(rows.map((row) => row.text())).toEqual(LINES.map((line) => line.text))
    // 行样式走 tone（文字色），不是 kind。上面这 4 行各自的语义：
    //   node 无 status → dim；log 无 level → info → normal；
    //   workflow 文本不匹配 success=true → warn；plain → dim。
    expect(rows.map((row) => row.classes().find((c) => c.startsWith('rl-tone--')))).toEqual([
      'rl-tone--dim',
      'rl-tone--normal',
      'rl-tone--warn',
      'rl-tone--dim',
    ])
  })

  it('maps node status / log level / workflow outcome onto the five tones', () => {
    const tones = (line: Pick<RunLogLine, 'kind' | 'text'> & Partial<RunLogLine>) =>
      mountPanel({ lines: [{ time: '', node: '', ...line } as RunLogLine] })
        .find('.rl-line')
        .classes()
        .find((c) => c.startsWith('rl-tone--'))

    expect(tones({ kind: 'node', text: 'a', status: 'succeeded' })).toBe('rl-tone--normal')
    expect(tones({ kind: 'node', text: 'a', status: 'failed' })).toBe('rl-tone--error')
    expect(tones({ kind: 'node', text: 'a', status: 'skipped' })).toBe('rl-tone--warn')
    expect(tones({ kind: 'node', text: 'a', status: 'cancelled' })).toBe('rl-tone--warn')

    expect(tones({ kind: 'log', text: 'a', level: 'info' })).toBe('rl-tone--normal')
    expect(tones({ kind: 'log', text: 'a', level: 'debug' })).toBe('rl-tone--dim')
    expect(tones({ kind: 'log', text: 'a', level: 'warning' })).toBe('rl-tone--warn')
    expect(tones({ kind: 'log', text: 'a', level: 'error' })).toBe('rl-tone--error')

    expect(tones({ kind: 'workflow', text: 'success=true' })).toBe('rl-tone--ok')
    expect(tones({ kind: 'workflow', text: 'success=false' })).toBe('rl-tone--error')
    expect(tones({ kind: 'workflow', text: 'still running' })).toBe('rl-tone--warn')

    expect(tones({ kind: 'plain', text: 'raw' })).toBe('rl-tone--dim')
  })

  it('switches the empty state on `running`', () => {
    expect(mountPanel().find('.rl-empty').text()).toBe('workflow.editor.runLog.empty')
    expect(mountPanel({ running: true }).find('.rl-empty').text()).toBe(
      'workflow.editor.runLog.waiting',
    )
  })

  it('shows the line count, the file path and the truncation note', () => {
    const wrapper = mountPanel({
      lines: LINES,
      logPath: 'C:\\Users\\me\\AppData\\Local\\blanks\\tasks\\wf-1\\logs\\task_exec.log',
      truncated: true,
    })
    expect(wrapper.find('.rl-count').text()).toBe('workflow.editor.runLog.lineCount')
    expect(wrapper.find('.rl-path').attributes('title')).toContain('task_exec.log')
    expect(wrapper.find('.rl-note').text()).toBe('workflow.editor.runLog.truncated')

    // No path → no path line, no truncation note.
    const bare = mountPanel({ lines: LINES })
    expect(bare.find('.rl-path').exists()).toBe(false)
    expect(bare.find('.rl-note').exists()).toBe(false)
  })

  it('forwards refresh / openFile / close, and blocks openFile without a path', async () => {
    const wrapper = mountPanel({ lines: LINES })
    const buttons = wrapper.findAll('.n-button-stub')
    expect(buttons).toHaveLength(3)

    // [refresh, openFile, close] — openFile is the only one bound to logPath.
    expect(buttons[1].attributes('disabled')).toBeDefined()
    await buttons[0].trigger('click')
    await buttons[2].trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.emitted('openFile')).toBeUndefined()

    const withPath = mountPanel({ lines: LINES, logPath: '/tmp/task_exec.log' })
    const pathButtons = withPath.findAll('.n-button-stub')
    expect(pathButtons[1].attributes('disabled')).toBeUndefined()
    await pathButtons[1].trigger('click')
    expect(withPath.emitted('openFile')).toHaveLength(1)
  })

  it('exposes resetScroll for the page to re-arm following on a new run', () => {
    const wrapper = mountPanel({ lines: LINES })
    expect(typeof (wrapper.vm as any).resetScroll).toBe('function')
    expect(() => (wrapper.vm as any).resetScroll()).not.toThrow()
  })
})
