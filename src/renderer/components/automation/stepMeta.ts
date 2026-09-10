/**
 * Presentation helpers for automation steps (v2 model): action labels
 * (i18n) and one-line parameter summaries used by the step list rows.
 */
import type { Step, StepAction, ElementTarget } from './stepTypes'

type T = (key: string, params?: Record<string, unknown>) => string

export function stepActionLabel(action: string, t: T): string {
  return t(`automation.act.${action}`)
}

function num(v: unknown, fallback = 0): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

function str(v: unknown): string {
  return v === undefined || v === null ? '' : String(v)
}

function targetSummary(tg: ElementTarget | undefined): string {
  if (!tg || !str(tg.value)) return '—'
  // `instance` selects the N-th same-selector match (class locators);
  // 0 = first (default) and stays hidden in the summary.
  const inst = num(tg.instance, 0)
  const instPart = inst > 0 ? ` · #${inst}` : ''
  return `${str(tg.by)}: ${str(tg.value)} · ${num(tg.timeout_ms, 10000)}ms${instPart}`
}

/** One-line human-readable parameter summary (numbers verbatim, no i18n). */
export function stepSummary(step: Step): string {
  switch (step.action as StepAction) {
    case 'tap': {
      if (step.mode === 'element' || step.target?.value) return targetSummary(step.target)
      const c = step.coord
      return c ? `${num(c.x)}, ${num(c.y)}` : '—'
    }
    case 'swipe': {
      const p = step.path
      return p ? `(${num(p.x1)}, ${num(p.y1)}) → (${num(p.x2)}, ${num(p.y2)}) · ${num(p.duration_ms, 300)}ms` : '—'
    }
    case 'input': {
      const t = str(step.text)
      const focus = step.target?.value ? ` @${str(step.target.by)}:${str(step.target.value)}` : ''
      return t.length > 24 ? t.slice(0, 24) + '…' + focus : t + focus
    }
    case 'keyevent':
      return str(step.key) || '—'
    case 'launch_app':
    case 'clear_app_data':
      return str(step.package) || '—'
    case 'shell':
      return str(step.command) || '—'
    case 'wait':
      if (step.mode === 'element' || step.target?.value) return targetSummary(step.target)
      return `${num(step.ms, 0)}ms`
    case 'assert_element':
      return `${targetSummary(step.target)} · ${str(step.expect) || 'exists'}`
    case 'assert_activity':
      return str(step.activity) || '—'
    case 'screenshot':
      return str(step.name) || '—'
    case 'back':
    case 'home':
      return ''
    default:
      return ''
  }
}
