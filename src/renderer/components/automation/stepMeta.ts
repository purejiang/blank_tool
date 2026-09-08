/**
 * Presentation helpers for automation steps: action labels (i18n) and
 * one-line parameter summaries used by the step list rows.
 */
import type { Step, StepAction } from './stepTypes'

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

/** An element target: `by` + `value` both present (legacy or unified mode). */
function isElementTarget(step: Step): boolean {
  const mode = str((step as Record<string, unknown>).mode)
  if (mode === 'element') return true
  if (mode === 'coord' || mode === 'time') return false
  // legacy steps carry no `mode` — fall back to field presence
  return !!str(step.by) && !!str(step.value)
}

function elementSummary(step: Step): string {
  return `${str(step.by)}: ${str(step.value) || '—'} · ${num(step.timeout_ms, 10000)}ms`
}

/** One-line human-readable parameter summary (numbers verbatim, no i18n). */
export function stepSummary(step: Step): string {
  switch (step.action as StepAction) {
    case 'tap':
      return isElementTarget(step)
        ? elementSummary(step)
        : `(${num(step.x)}, ${num(step.y)})`
    case 'swipe':
      return `(${num(step.x1)}, ${num(step.y1)}) → (${num(step.x2)}, ${num(step.y2)}) · ${num(step.duration_ms, 300)}ms`
    case 'wait':
      return isElementTarget(step)
        ? elementSummary(step)
        : `${num(step.ms)}ms`
    case 'input': {
      const text = str(step.text)
      return text ? `“${text}”` : '—'
    }
    case 'keyevent':
      return str(step.key) || '—'
    case 'launch_app':
    case 'clear_app_data':
      return str(step.package) || '·'
    case 'shell':
      return str(step.command) || '—'
    case 'tap_element':
    case 'wait_element':
      return elementSummary(step)
    case 'assert_element':
      return `${str(step.by)}: ${str(step.value) || '—'} · ${str(step.expect) || 'exists'}`
    case 'assert_activity':
      return str(step.activity) || '—'
    case 'screenshot':
      return str(step.name) || '·'
    case 'back':
    case 'home':
      return ''
    default:
      return ''
  }
}
