/**
 * Run / node presentation helpers for the task pages (docs/08 §5-3 状态徽章语义).
 *
 * The backend has three overlapping notions of "how did it go": `success`
 * (coarse boolean), `status` ("succeeded" / "failed" / "cancelled"), and
 * `cancelled` (its own flag). docs/08 fixes one display order — **cancelled
 * outranks failed** — and that order lives here so the run list and the run
 * detail drawer can never disagree.
 *
 * Pure and Vue-free (see tests/unit/tasks/runFormat.test.ts).
 */

/** Unified status vocabulary for the whole app (docs/08 §5-3). */
export type RunStatusKey = 'running' | 'succeeded' | 'failed' | 'cancelled' | 'skipped' | 'unknown'

/** Fields a `RunSummary` / `RunRecord` may carry (all optional on old records). */
export interface RunStatusInput {
  success?: boolean | null
  status?: string | null
  cancelled?: boolean | null
}

/**
 * Resolve the display status of a run.
 *
 * Precedence: `cancelled` flag → `status` string → `success` boolean. Records
 * written before WP2 have `status`/`cancelled` as `null`, hence the fallback.
 */
export function runStatusOf(run: RunStatusInput | null | undefined): RunStatusKey {
  if (!run) return 'unknown'
  if (run.cancelled === true) return 'cancelled'
  const status = typeof run.status === 'string' ? run.status.toLowerCase() : ''
  if (status === 'cancelled' || status === 'canceled') return 'cancelled'
  if (status === 'succeeded' || status === 'success' || status === 'ok') return 'succeeded'
  if (status === 'failed' || status === 'failure' || status === 'error') return 'failed'
  if (status === 'running') return 'running'
  if (run.success === true) return 'succeeded'
  if (run.success === false) return 'failed'
  return 'unknown'
}

/** Resolve the display status of one node inside a run record. */
export function nodeStatusOf(status: unknown): RunStatusKey {
  const value = typeof status === 'string' ? status.toLowerCase() : ''
  if (value === 'ok' || value === 'succeeded' || value === 'success') return 'succeeded'
  if (value === 'failed' || value === 'error') return 'failed'
  if (value === 'skipped' || value === 'skip') return 'skipped'
  if (value === 'cancelled' || value === 'canceled') return 'cancelled'
  if (value === 'running') return 'running'
  return 'unknown'
}

/** i18n key for a status label (`tasks.status.*`). */
export function statusI18nKey(status: RunStatusKey): string {
  return `tasks.status.${status}`
}

/** Naive UI tag type for a status (colour semantics from docs/08 §5-3). */
export function statusTagType(status: RunStatusKey): 'default' | 'info' | 'success' | 'error' | 'warning' {
  if (status === 'running') return 'info'
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'cancelled') return 'warning'
  return 'default'
}

/**
 * Human-readable duration from a millisecond count.
 *
 * Nullish / negative input renders as an em dash rather than "0.0s" — a run
 * that never finished has no duration, and showing 0 would be a lie.
 */
export function formatMs(ms: number | null | undefined): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return '—'
  const totalSeconds = ms / 1000
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) return `${hours}h ${minutes}m ${seconds.toFixed(1)}s`
  if (minutes > 0) return `${minutes}m ${seconds.toFixed(1)}s`
  return `${seconds.toFixed(1)}s`
}

/**
 * Split a run-root-relative node path (`"loop/0/step"`) into its segments.
 * Nested executions (`flow.foreach` / branches / sub-workflows) produce these.
 */
export function parseNodePath(path: string): string[] {
  return String(path ?? '')
    .split('/')
    .filter((segment) => segment.length > 0)
}

/** Indentation depth of a node path (0 for a top-level node). */
export function nodeDepth(path: string): number {
  const segments = parseNodePath(path)
  return segments.length > 0 ? segments.length - 1 : 0
}

/** The value `shrink_outputs` writes when it truncates an oversized output. */
export interface TruncatedOutput {
  _truncated: true
  _chars?: number
  _preview?: string
  _reason?: string
  [key: string]: unknown
}

/**
 * True for the truncation marker `cli/app/workflow/output_limit.py` writes
 * (`{"_truncated": true, "_chars": n, "_preview": "…"}`). Such values must be
 * rendered as a marker, never as plain output text.
 */
export function isTruncatedOutput(value: unknown): value is TruncatedOutput {
  return !!value && typeof value === 'object' && (value as Record<string, unknown>)._truncated === true
}

/** Short description of a truncated output: how much was dropped. */
export function truncationNote(value: TruncatedOutput): string {
  const chars = typeof value._chars === 'number' ? value._chars : null
  const reason = typeof value._reason === 'string' && value._reason ? value._reason : ''
  const size = chars === null ? '' : `${chars} chars`
  return [size, reason].filter(Boolean).join(' · ')
}

/**
 * True when a value looks like a filesystem path, so the UI can offer
 * 「打开」 (`openPath`). Deliberately conservative: a plain word is not a path.
 */
export function isPathLike(value: unknown): value is string {
  if (typeof value !== 'string' || value.length === 0) return false
  if (/^[A-Za-z]:[\\/]/.test(value)) return true // C:\... / C:/...
  if (value.startsWith('/')) return true
  if (value.startsWith('.\\') || value.startsWith('./')) return true
  return false
}

/** Pretty-print any JSON-ish value for a read-only detail view. */
export function prettyValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
