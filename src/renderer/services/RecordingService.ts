/**
 * RecordingService — stream-event subscription router for adb_auto
 * recording sessions (Todo 3 of .omo/plans/adb-auto-test.md).
 *
 * TaskStreamService silently drops unknown event types (default: break),
 * so `record_event` / `record_stopped` events from the automation plugin
 * are routed here instead, keyed by the recording task_id.
 *
 * Envelope contract (the main process forwards `{ stream_id, data: result }`
 * where result = { type, payload, task_id }):
 *   { stream_id, data: { type, payload, task_id } }
 *
 * NOTE: `automation.record_start` is a streaming init — the renderer-side
 * unwrap returns `undefined` for a result without a `type` field, so a
 * resolved call means the backend accepted the session. A stream_id is
 * never read here (runScript's init.stream_id check is a known defect —
 * do not imitate).
 */

import { log } from '@utils/logger'
import unifiedApi from '../api/unifiedApi'

// ------------------------------------------------------------------
// Interfaces
// ------------------------------------------------------------------

interface RecordingCallbacks {
  onStep?: (step: any) => void
  onError?: (message: string) => void
  onStopped?: (payload: any) => void
}

// ------------------------------------------------------------------
// Service
// ------------------------------------------------------------------

class RecordingService {
  private unsubscribe: (() => void) | null = null
  private handlers: Map<string, RecordingCallbacks> = new Map()

  /** Subscribe to stream-event IPC (idempotent). */
  async initialize(): Promise<void> {
    if (this.unsubscribe) return // already subscribed
    const api = window.electronAPI
    if (!api || typeof api.onStreamEvent !== 'function') {
      log.warn('[RecordingService] onStreamEvent not available — record events will not be received')
      this.unsubscribe = () => {} // no-op to mark as initialized
      return
    }
    this.unsubscribe = api.onStreamEvent((raw: any) => this.handleStream(raw))
  }

  /**
   * Start a recording session on a device and return its task id.
   * Optional callbacks are written into the recId slot BEFORE the backend
   * call is issued, so events emitted while the call is in flight stay
   * routable (subscription precedes launch).
   */
  async startRecording(deviceId: string, callbacks?: RecordingCallbacks): Promise<string> {
    const recId = 'rec-' + crypto.randomUUID()
    const slot = this.getSlot(recId)
    if (callbacks?.onStep) slot.onStep = callbacks.onStep
    if (callbacks?.onError) slot.onError = callbacks.onError
    if (callbacks?.onStopped) slot.onStopped = callbacks.onStopped
    try {
      await unifiedApi.call('automation.record_start', { device_id: deviceId, task_id: recId })
    } catch (err) {
      // Do not leak the slot (and its callback closures) for a failed start.
      this.handlers.delete(recId)
      throw err
    }
    return recId
  }

  /**
   * Stop the recording session on a device. Non-streaming: the envelope
   * unwraps normally to `{ steps, record_device }`.
   */
  async stopRecording(deviceId: string): Promise<any> {
    return unifiedApi.call('automation.record_stop', { device_id: deviceId })
  }

  /** Register a per-step callback for a recording. */
  onStep(taskId: string, cb: (step: any) => void): void {
    this.getSlot(String(taskId)).onStep = cb
  }

  /** Register an error callback for a recording. */
  onError(taskId: string, cb: (message: string) => void): void {
    this.getSlot(String(taskId)).onError = cb
  }

  /** Register a stopped callback for a recording. */
  onStopped(taskId: string, cb: (payload: any) => void): void {
    this.getSlot(String(taskId)).onStopped = cb
  }

  /** Clear all callbacks for a recording. */
  finish(taskId: string): void {
    this.handlers.delete(String(taskId))
  }

  // ----------------------------------------------------------------
  // Internals
  // ----------------------------------------------------------------

  private getSlot(taskId: string): RecordingCallbacks {
    let slot = this.handlers.get(taskId)
    if (!slot) {
      slot = {}
      this.handlers.set(taskId, slot)
    }
    return slot
  }

  private handleStream(raw: any): void {
    if (!raw) return

    try {
      const data = raw.data
      const tid: string | undefined =
        typeof data?.task_id === 'string' || typeof data?.task_id === 'number'
          ? String(data.task_id)
          : undefined

      if (!tid || !this.handlers.has(tid)) return

      const slot = this.handlers.get(tid)!
      const payload = data.payload
      if (payload == null) return

      switch (data.type) {
        case 'record_event': {
          if (payload.step !== undefined) {
            slot.onStep?.(payload.step)
          }
          break
        }

        case 'error': {
          slot.onError?.(payload.message ?? String(payload))
          break
        }

        case 'record_stopped': {
          slot.onStopped?.(payload)
          break
        }

        // Unknown types are ignored — TaskStreamService already drops them;
        // this service exists precisely to catch the record_* ones.
        default:
          break
      }
    } catch (err) {
      // Callback errors should never break event routing
      log.error('[RecordingService] handleStream error:', err)
    }
  }
}

export default RecordingService
