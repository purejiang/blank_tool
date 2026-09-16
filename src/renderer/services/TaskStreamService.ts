/**
 * TaskStreamService — global singleton that subscribes to
 * `window.electronAPI.onStreamEvent` once at app startup and routes
 * streaming events by `task_id` to registered callbacks.
 *
 * Uses a **latch pattern** for phase promises to prevent a race
 * condition where the `complete` event arrives before `waitForPhase`
 * is called (the `api.downloadFile()` call triggers the event through
 * the backend-stream-main-renderer pipeline synchronously, but the
 * caller hasn't called `await waitForPhase()` yet).
 */

import { log } from '@utils/logger'

// ------------------------------------------------------------------
// Interfaces
// ------------------------------------------------------------------

interface PhaseSlot {
  promise: Promise<any>
  resolve: (value: any) => void
  reject: (reason: any) => void
  settled: boolean
  result?: any
  error?: any
}

interface PhaseState {
  currentPhase: 'download' | 'operation' | null
  download: PhaseSlot
  operation: PhaseSlot
}

/**
 * Latch retention. `unbindTask` deliberately KEEPS the phase slots so a late
 * `waitForPhase` can still read the stashed result, but nothing used to remove
 * them: every task the app ever streamed stayed in the map for the whole
 * session. Entries are now dropped once they are finished and older than
 * {@link PHASE_LATCH_TTL_MS} (and, past {@link MAX_PHASE_ENTRIES}, oldest
 * first). Evicting a stale latch is safe — `waitForPhase` on an evicted id
 * rejects with `'unbound'`, exactly what a caller already handles — and an
 * ACTIVE task (still bound, or with a pending waiter) is never evicted.
 */
export const PHASE_LATCH_TTL_MS = 10 * 60_000
export const MAX_PHASE_ENTRIES = 200

export interface TaskCallbacks {
  onDownloadProgress?: (progress: number, downloaded: number, total: number, speed: number) => void
  onComplete?: (payload: any, phase: 'download' | 'operation') => void
  onError?: (message: string, phase: 'download' | 'operation') => void
  onCancelled?: () => void
  onLog?: (line: string) => void
  /** Streaming per-step progress (automation run): a step started executing. */
  onStepStart?: (payload: any) => void
  /** Streaming per-step progress (automation run): a step finished. */
  onStep?: (payload: any) => void
}

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function createPhaseSlot(): PhaseSlot {
  let resolve: (value: any) => void = () => {}
  let reject: (reason: any) => void = () => {}
  const promise = new Promise<any>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject, settled: false }
}

function createPhaseState(): PhaseState {
  return {
    currentPhase: null,
    download: createPhaseSlot(),
    operation: createPhaseSlot(),
  }
}

// ------------------------------------------------------------------
// Service
// ------------------------------------------------------------------

class TaskStreamService {
  private unsubscribe: (() => void) | null = null
  private listeners: Map<string, TaskCallbacks> = new Map()
  private phaseState: Map<string, PhaseState> = new Map()
  /** taskId → epoch ms of unbind, for TTL pruning of the latch entries. */
  private unboundAt: Map<string, number> = new Map()
  private fakeProgressTimers: Map<string, ReturnType<typeof setInterval>> = new Map()

  /** Subscribe to stream-event IPC (idempotent). */
  async initialize(): Promise<void> {
    if (this.unsubscribe) return // already subscribed
    const api = window.electronAPI
    if (!api || typeof api.onStreamEvent !== 'function') {
      log.warn('[TaskStreamService] onStreamEvent not available — stream events will not be received')
      this.unsubscribe = () => {} // no-op to mark as initialized
      return
    }
    this.unsubscribe = api.onStreamEvent((raw: any) => this.handleStream(raw))
  }

  /**
   * Create latch slots for both `download` and `operation` phases.
   * Idempotent — if a listener already exists for `taskId`, it is
   * automatically unbound first (stale state cleaned up).
   */
  bindTask(taskId: string): void {
    const id = String(taskId)
    // Auto-unbind stale listener to prevent pollution from retries
    if (this.listeners.has(id)) {
      this.unbindTask(id)
    }
    this.listeners.set(id, {})
    this.phaseState.set(id, createPhaseState())
    this.unboundAt.delete(id)
    // A new run is the natural moment to drop the latches of long-finished
    // runs (cheap, and keeps this off any hot per-event path).
    this.prunePhaseState()
  }

  /** Register callback handlers for a bound task. */
  setCallbacks(taskId: string, callbacks: TaskCallbacks): void {
    const id = String(taskId)
    if (!this.listeners.has(id)) {
      // Auto-bind if not already bound (package call order may vary)
      this.listeners.set(id, {})
      this.phaseState.set(id, createPhaseState())
    }
    this.listeners.set(id, callbacks)
  }

  /** Track which phase the task is currently in. */
  setPhase(taskId: string, phase: 'download' | 'operation'): void {
    const id = String(taskId)
    const ps = this.phaseState.get(id)
    if (ps) {
      ps.currentPhase = phase
    }
  }

  /**
   * Return a promise for the given phase.
   *
   * **Latch**: if the event already arrived (slot is settled), the
   * promise resolves/rejects immediately with the stashed result.
   * Otherwise returns the pending promise that will settle when the
   * event arrives.
   */
  waitForPhase(taskId: string, phase: 'download' | 'operation'): Promise<any> {
    const id = String(taskId)
    const ps = this.phaseState.get(id)
    if (!ps) {
      return Promise.reject(new Error('unbound'))
    }
    const slot = phase === 'download' ? ps.download : ps.operation
    if (slot.settled) {
      if (slot.error) {
        return Promise.reject(slot.error)
      }
      return Promise.resolve(slot.result)
    }
    return slot.promise
  }

  /**
   * Remove callbacks and phase state for a task.
   * Rejects any non-settled phase promises with `'unbound'`.
   * Settled slots are kept in phaseState so latch can still resolve.
   */
  unbindTask(taskId: string): void {
    const id = String(taskId)
    this.listeners.delete(id)
    const ps = this.phaseState.get(id)
    if (ps) {
      const unboundErr = new Error('unbound')
      if (!ps.download.settled) {
        ps.download.error = unboundErr
        ps.download.settled = true
        ps.download.reject(unboundErr)
        ps.download.promise.catch(() => {})
      }
      if (!ps.operation.settled) {
        ps.operation.error = unboundErr
        ps.operation.settled = true
        ps.operation.reject(unboundErr)
        ps.operation.promise.catch(() => {})
      }
      // Keep the phaseState entry — settled slots are the latch — but stamp
      // it so `prunePhaseState` can age it out later.
      this.unboundAt.set(id, Date.now())
    }
  }

  /**
   * Drop finished, aged-out latch entries. Called from `bindTask` (once per
   * run) — never per stream event.
   *
   * An entry is evictable only when the task is unbound AND both slots are
   * settled, i.e. nothing is waiting on it: a pending `waitForPhase` keeps the
   * entry alive forever. Past {@link MAX_PHASE_ENTRIES} the oldest evictable
   * entries are dropped first (Map iteration is bind order).
   */
  private prunePhaseState(now: number = Date.now()): void {
    const evictable = (id: string, ps: PhaseState) =>
      !this.listeners.has(id) && ps.download.settled && ps.operation.settled

    const doomed: string[] = []
    for (const [id, ps] of this.phaseState) {
      if (!evictable(id, ps)) continue
      const at = this.unboundAt.get(id)
      if (at === undefined) {
        // Pre-existing entry from a build that did not stamp: age it from now.
        this.unboundAt.set(id, now)
        continue
      }
      if (now - at > PHASE_LATCH_TTL_MS) doomed.push(id)
    }

    let remaining = this.phaseState.size - doomed.length
    if (remaining > MAX_PHASE_ENTRIES) {
      for (const [id, ps] of this.phaseState) {
        if (remaining <= MAX_PHASE_ENTRIES) break
        if (doomed.includes(id) || !evictable(id, ps)) continue
        doomed.push(id)
        remaining--
      }
    }

    for (const id of doomed) {
      this.phaseState.delete(id)
      this.unboundAt.delete(id)
    }
  }

  /** Test/diagnostics hook: how many latch entries are currently retained. */
  _phaseEntryCount(): number {
    return this.phaseState.size
  }

  // ----------------------------------------------------------------
  // Stream event routing
  // ----------------------------------------------------------------

  private handleStream(raw: any): void {
    if (!raw) return

    try {
      const data = raw.data || raw
      const tid: string | undefined =
        (typeof data.task_id === 'string' || typeof data.task_id === 'number'
          ? String(data.task_id)
          : undefined) ||
        (data.payload && (typeof data.payload.task_id === 'string' || typeof data.payload.task_id === 'number')
          ? String(data.payload.task_id)
          : undefined)

      if (!tid || !this.listeners.has(tid)) return

      const callbacks = this.listeners.get(tid)!
      const ps = this.phaseState.get(tid)

      switch (data.type) {
        case 'progress': {
          const p = data.payload || {}
          callbacks.onDownloadProgress?.(
            p.progress ?? 0,
            p.downloaded ?? 0,
            p.total ?? 0,
            p.speed ?? 0,
          )
          break
        }

        case 'complete': {
          const payload = data.payload || data
          const phase = (ps?.currentPhase || 'download') as 'download' | 'operation'
          const slot = phase === 'download' ? ps?.download : ps?.operation
          if (slot && !slot.settled) {
            slot.result = payload
            slot.settled = true
            slot.resolve(payload)
          }
          callbacks.onComplete?.(payload, phase)
          // Auto-unbind ONLY after the terminal (operation) phase completes.
          // Download-phase completes must keep listeners alive so the subsequent
          // operation phase events can still be routed.
          if (phase === 'operation') {
            this.unbindTask(tid)
          }
          break
        }

        case 'error': {
          const p = data.payload
          let msg =
            (typeof p === 'string' ? p : (p && p.message)) ||
            data.message ||
            ''
          // Never surface a literal "null"/"None"/empty error — fall back to a
          // meaningful default so the UI never renders the raw string "null".
          if (!msg || msg === 'null' || msg === 'None') {
            msg = 'Unknown error'
          }
          const phase = (ps?.currentPhase || 'download') as 'download' | 'operation'

          // Reject both non-settled phase slots (task terminates on error)
          if (ps) {
            for (const key of ['download', 'operation'] as const) {
              const slot = ps[key]
              if (!slot.settled) {
                slot.error = new Error(msg)
                slot.settled = true
                slot.reject(slot.error)
                slot.promise.catch(() => {})
              }
            }
          }
          callbacks.onError?.(msg, phase)
          this.unbindTask(tid)
          break
        }

        case 'cancelled': {
          // Reject both non-settled phase slots
          if (ps) {
            const cancelErr = new Error('cancelled')
            for (const key of ['download', 'operation'] as const) {
              const slot = ps[key]
              if (!slot.settled) {
                slot.error = cancelErr
                slot.settled = true
                slot.reject(cancelErr)
                slot.promise.catch(() => {})
              }
            }
          }
          callbacks.onCancelled?.()
          this.unbindTask(tid)
          break
        }

        // Streaming step progress (automation run).
        // 'step_start' renders a pending row immediately, 'step' replaces it
        // with the finished record so results appear one by one during a run.
        case 'step_start': {
          const p = data.payload || {}
          callbacks.onStepStart?.({ index: p.index, action: p.action, pending: true })
          break
        }

        case 'step': {
          callbacks.onStep?.(data.payload || {})
          break
        }

        case 'log': {
          // Backend task log line (apk/install/aab handlers). The main
          // process forwards these verbatim on streamEvent; the backend
          // already persisted the line, so the renderer only mirrors it
          // into memory for live display (no disk write — see taskStore).
          // Streaming handlers (e.g. the automation run) send the line as a
          // bare string payload ("[automation] msg"); tolerate both string and
          // {line} payloads.
          let line: any = data.line
          if (line === undefined) {
            const p = data.payload
            if (typeof p === 'string') line = p
            else if (p && typeof p.line === 'string') line = p.line
          }
          if (line) callbacks.onLog?.(String(line))
          break
        }

        // 'started', 'process_finished' are still routed to the dedicated
        // logcat IPC channels by the main process.  Ignore them here.
        default:
          break
      }
    } catch (err) {
      // Callback errors should never break event routing
      log.error('[TaskStreamService] handleStream error:', err)
    }
  }

  // ----------------------------------------------------------------
  // Fake progress
  // ----------------------------------------------------------------

  /**
   * Start a fake progress animation (same algorithm as the original
   * PackagePage `startProgress`).
   *
   * - +2% / tick below 30%
   * - +1% / tick below 60%
   * - +0.5% / tick above 60%
   * - Capped at 85% (the terminal 15% is filled by the real event).
   */
  startFakeProgress(
    taskId: string,
    intervalMs: number,
    onUpdate: (progress: number) => void,
  ): void {
    const id = String(taskId)
    this.stopFakeProgress(id)

    let p = 0
    const iv = setInterval(() => {
      if (p >= 85) {
        clearInterval(iv)
        this.fakeProgressTimers.delete(id)
        return
      }
      if (p < 30) p += 2
      else if (p < 60) p += 1
      else p += 0.5
      p = Math.min(p, 85)
      onUpdate(Math.round(p))
    }, intervalMs)

    this.fakeProgressTimers.set(id, iv)
  }

  /** Stop fake progress for a task. */
  stopFakeProgress(taskId: string): void {
    const id = String(taskId)
    const iv = this.fakeProgressTimers.get(id)
    if (iv) {
      clearInterval(iv)
      this.fakeProgressTimers.delete(id)
    }
  }

  // ----------------------------------------------------------------
  // Lifecycle
  // ----------------------------------------------------------------

  /** Full cleanup — unsubscribe IPC + clear all state. */
  destroy(): void {
    // Unsubscribe from IPC
    if (this.unsubscribe) {
      try { this.unsubscribe() } catch {}
      this.unsubscribe = null
    }

    // Reject all pending phase promises
    for (const [id, ps] of this.phaseState) {
      const destroyErr = new Error('destroyed')
      if (!ps.download.settled) {
        ps.download.reject(destroyErr)
        ps.download.promise.catch(() => {})
      }
      if (!ps.operation.settled) {
        ps.operation.reject(destroyErr)
        ps.operation.promise.catch(() => {})
      }
    }

    // Clear fake progress timers
    for (const iv of this.fakeProgressTimers.values()) {
      clearInterval(iv)
    }

    this.listeners.clear()
    this.phaseState.clear()
    this.unboundAt.clear()
    this.fakeProgressTimers.clear()
  }
}

export default TaskStreamService
