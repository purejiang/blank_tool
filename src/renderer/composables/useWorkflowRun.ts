/**
 * One-shot workflow run with terminal-state resolution.
 *
 * The engine's `@streaming` handlers (`workflow.execute` / `template.execute`)
 * resolve the invoke on the FIRST streamed event, so awaiting the call only
 * proves the run started. The terminal outcome arrives on the shared
 * `stream-event` channel instead — correlated by the `task_id` the caller
 * passes (api_handler stamps it onto every event; the event's own
 * `workflow_id` is the definition name and its `run_id` is the JSON-RPC
 * request id, which the renderer cannot know in advance).
 *
 * Used by the workflow list's 「试运行」 and (later) the task page. The editor
 * keeps its own handler because it also maps per-node statuses.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

import unifiedApi from '@/api/unifiedApi'
import { withNodeDefaults } from '@components/workflow/nodeDefaults'
import { log } from '@utils/logger'

/** Terminal outcomes of one run. */
export type RunOutcomeStatus = 'success' | 'failed' | 'cancelled'

export interface RunOutcome {
  status: RunOutcomeStatus
  error?: string
}

const TERMINAL_TYPES = new Set(['workflow_completed', 'workflow_failed', 'workflow_cancelled'])

/** Which backend method starts a run. */
export type RunMethod = 'workflow.execute' | 'template.execute'

export interface StartRunOptions {
  method: RunMethod
  /** Exactly the params the method takes (definition/name + inputs). */
  params: Record<string, unknown>
}

export function useWorkflowRun() {
  const isRunning = ref(false)

  let activeRunId: string | null = null
  let settle: ((outcome: RunOutcome) => void) | null = null
  let unsubscribe: (() => void) | null = null

  function makeRunId(): string {
    return `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  }

  function handleRaw(raw: unknown) {
    if (!activeRunId || !settle) return
    try {
      const envelope = raw as Record<string, any>
      const event = (
        envelope?.data && typeof envelope.data === 'object' ? envelope.data : envelope
      ) as Record<string, any>
      const type = typeof event?.type === 'string' ? event.type : ''
      if (!TERMINAL_TYPES.has(type)) return
      // Correlation: our own run id arrives as `task_id`; a mismatch is another
      // run's event (e.g. the editor's).
      if (typeof event.task_id === 'string' && event.task_id !== activeRunId) return

      const finish = settle
      settle = null
      if (type === 'workflow_completed') {
        finish({ status: 'success' })
      } else if (type === 'workflow_failed') {
        finish({ status: 'failed', error: typeof event.error === 'string' ? event.error : undefined })
      } else {
        finish({ status: 'cancelled' })
      }
    } catch (error) {
      log.error('[useWorkflowRun] stream event handling error:', error)
    }
  }

  onMounted(() => {
    const api = window.electronAPI
    if (api && typeof api.onStreamEvent === 'function') {
      unsubscribe = api.onStreamEvent((raw: any) => handleRaw(raw))
    } else {
      log.warn('[useWorkflowRun] onStreamEvent unavailable — terminal state cannot be observed')
    }
  })

  onBeforeUnmount(() => {
    try {
      unsubscribe?.()
    } catch {}
    unsubscribe = null
    settle = null
    activeRunId = null
  })

  /**
   * Start a run and resolve when it reaches a terminal state.
   *
   * @returns the outcome, or `null` when the run started but its events cannot
   *   be observed (no stream channel, or another run is already in flight) —
   *   callers should then point the user at the run records.
   */
  async function start(options: StartRunOptions): Promise<RunOutcome | null> {
    if (isRunning.value) return null
    // 「跟随系统」的节点在引擎里靠这个参数拿到默认行为；两条运行路径
    // （workflow.execute / template.execute）都在这里统一注入，避免各调用点各写一份。
    const params = await withNodeDefaults(options.params)
    const api = window.electronAPI
    if (!api || typeof api.onStreamEvent !== 'function') {
      // No correlation channel: still start the run, but report it as
      // unobservable rather than pretending it finished.
      const runId = makeRunId()
      await unifiedApi.call(options.method, { ...params, task_id: runId })
      return null
    }

    const runId = makeRunId()
    isRunning.value = true
    // Set the correlation id BEFORE awaiting: the invoke resolves on the first
    // streamed frame, and for a trivially failing run that frame can already be
    // the terminal event — it must not be dropped.
    activeRunId = runId
    const settled = new Promise<RunOutcome>((resolve) => {
      settle = resolve
    })

    try {
      await unifiedApi.call(options.method, { ...params, task_id: runId })
    } catch (error) {
      settle = null
      activeRunId = null
      isRunning.value = false
      throw error
    }

    try {
      return await settled
    } finally {
      isRunning.value = false
      activeRunId = null
    }
  }

  return { isRunning, start }
}
