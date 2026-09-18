/**
 * TaskExecutionService — global FIFO queue with a bounded concurrency limit.
 *
 * Tasks created on PackagePage are enqueued instead of executing immediately;
 * at most `MAX_CONCURRENT` tasks run at once (default 3). Waiting tasks stay
 * in `queued` status in the task store, so the UI shows them as pending.
 *
 * Low-risk design: no store dependency, no lifecycle — a plain module-level
 * semaphore. `run()` rejections are swallowed here (executeTask already
 * transitions the task to `failed` internally, so a rejection here is a
 * bookkeeping signal only).
 */

export const MAX_CONCURRENT = 3

// Configurable cap (defaults to MAX_CONCURRENT). Set from the Settings page
// ("Max concurrent tasks"); if unset or invalid it stays at MAX_CONCURRENT.
let maxConcurrent = MAX_CONCURRENT

/**
 * Update the bound concurrency limit at runtime (e.g. when the user changes
 * the setting). Clamped to a sane [1, 64] range.
 */
export function setMaxConcurrent(value: number): void {
  const n = Number(value)
  if (!Number.isFinite(n)) return
  maxConcurrent = Math.min(64, Math.max(1, Math.floor(n)))
}

type Runner = () => Promise<void>

interface QueueEntry {
  id: number
  run: Runner
}

const waiting: QueueEntry[] = []
let active = 0

function pump(): void {
  while (active < maxConcurrent && waiting.length > 0) {
    const next = waiting.shift()!
    active++
    void next
      .run()
      .catch(() => {})
      .finally(() => {
        active--
        pump()
      })
  }
}

/**
 * Enqueue a task for execution. If the same task id is already waiting
 * (e.g. re-queued by a retry before the stale entry ran), the stale entry
 * is replaced so the task never double-executes.
 */
export function enqueueTask(id: number, run: Runner): void {
  const idx = waiting.findIndex(w => w.id === id)
  if (idx !== -1) waiting.splice(idx, 1)
  waiting.push({ id, run })
  pump()
}

/** Current queue depth (waiting + active) — exposed for tests/debug. */
export function queueStats(): { waiting: number; active: number } {
  return { waiting: waiting.length, active }
}

/** Test-only: reset the queue state between unit tests. */
export function __resetQueue(): void {
  waiting.length = 0
  active = 0
}
