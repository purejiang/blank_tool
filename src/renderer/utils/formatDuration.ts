import type { Task } from '@stores/taskStore'

/**
 * Format task duration as human-readable string.
 * For completed tasks, uses finishedAt - (startedAt || createdAt).
 * For running tasks, pass nowOverride to compute live duration.
 *
 * @param task The task object
 * @param nowOverride Optional timestamp for live-duration calculation (injected by caller or tests)
 * @returns Formatted duration string (e.g. "3s", "1m 2s", "1h 3m 5s"), or '' if duration is negative
 */
export function formatDuration(task: Task, nowOverride?: number): string {
  const end = task.finishedAt ?? nowOverride ?? 0
  const start = task.startedAt ?? task.createdAt
  const ms = end - start
  if (ms < 0) return ''
  const secs = Math.floor(ms / 1000)
  const mins = Math.floor(secs / 60)
  const hrs = Math.floor(mins / 60)
  if (hrs > 0) return `${hrs}h ${mins % 60}m ${secs % 60}s`
  if (mins > 0) return `${mins}m ${secs % 60}s`
  return `${secs}s`
}
