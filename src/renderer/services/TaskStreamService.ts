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

export interface TaskCallbacks {
  onDownloadProgress?: (progress: number, downloaded: number, total: number, speed: number) => void
  onComplete?: (payload: any, phase: 'download' | 'operation') => void
  onError?: (message: string, phase: 'download' | 'operation') => void
  onCancelled?: () => void
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
  private fakeProgressTimers: Map<string, ReturnType<typeof setInterval>> = new Map()

  /** Subscribe to stream-event IPC (idempotent). */
  async initialize(): Promise<void> {
    if (this.unsubscribe) return // already subscribed
    const api = (window as any).electronAPI
    if (!api || typeof api.onStreamEvent !== 'function') {
      console.warn('[TaskStreamService] onStreamEvent not available — stream events will not be received')
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
    }
    // Keep phaseState entry — settled slots are the latch
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
          this.unbindTask(tid)
          break
        }

        case 'error': {
          const msg =
            data.payload?.message ||
            data.message ||
            'Unknown error'
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

        // 'log', 'started', 'process_finished' are routed to different
        // IPC channels (logcat-output, logcat-started, logcat-finished)
        // by the main process.  Ignore them here.
        default:
          break
      }
    } catch (err) {
      // Callback errors should never break event routing
      console.error('[TaskStreamService] handleStream error:', err)
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
    this.fakeProgressTimers.clear()
  }
}

export default TaskStreamService
