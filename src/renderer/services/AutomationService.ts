
/**
 * 自动化能力探测 + 工具安装服务
 *
 * Two halves:
 *  - Read-only probes for the two optional dependencies of the automation
 *    feature — mitmproxy (PC side, traffic capture) and ADBKeyBoard (device
 *    side, non-ASCII text input). Probes never mutate anything: the settings
 *    page renders the result and the automation page turns it into
 *    non-blocking run hints.
 *  - One-shot streaming installs of the same two tools
 *    (automation.install_mitmproxy / automation.install_ime), routed like
 *    RecordingService: a per-call task_id slot is registered BEFORE the
 *    backend call, stream events are matched by task_id, and the returned
 *    Promise settles on the stream's terminal event — the resolved
 *    `{ stream_id }` of callBackendAPI itself is never a business result.
 *
 * Envelope contract (the main process forwards `{ stream_id, data: result }`
 * where result = { type, payload, task_id }):
 *   { stream_id, data: { type, payload, task_id } }
 * with type ∈ 'log' | 'progress' | 'complete' | 'error'.
 */
import { log } from '@utils/logger'
import { genId } from '@utils/id'
import { requireApiMethod } from '../api/apiAccess';

export interface TrafficStatus {
    installed: boolean
    ready: boolean
    lib_path: string
    python_mismatch: string | null
    /** CA 证书是否已生成（首次抓包运行时自动生成）。 */
    ca_cert_exists: boolean
}

export interface ImeStatus {
    device_id: string
    package: string
    installed: boolean
    active: boolean
}

/**
 * Terminal payload of a streaming install — the `complete` event's payload.
 * Success shape: `{ success: true, ...traffic_status }`.
 * Degraded shape (any pip/install failure on the PC side): the promise still
 * RESOLVES with `{ success: false, degraded: true, manual_command, ... }` so
 * the UI can offer the exact copy-paste command instead of a bare error.
 */
export interface TerminalPayload {
    success?: boolean
    degraded?: boolean
    manual_command?: string
    lib_path?: string
    python_bin?: string
    error?: string
    message?: string
    [key: string]: any
}

interface InstallSlot {
    onLog?: (line: string) => void
    onProgress?: (progress: any) => void
    resolve: (payload: TerminalPayload) => void
    reject: (reason: Error) => void
}

class AutomationService {
    /**
     * mitmproxy availability. `null` means the probe itself failed — the UI
     * shows an "unknown" state instead of pretending it is missing.
     */
    async getTrafficStatus(force = false): Promise<TrafficStatus | null> {
        if (!force && this.trafficStatus) {
            return this.trafficStatus;
        }
        try {
            this.trafficStatus = await requireApiMethod('callBackendAPI')(
                'automation.traffic_status', {}
            ) as TrafficStatus;
            return this.trafficStatus;
        } catch (error) {
            log.error('获取流量抓取组件状态失败:', error);
            return null;
        }
    }

    /**
     * ADBKeyBoard availability on ONE device. Device side, hence the id.
     */
    async getImeStatus(deviceId: string): Promise<ImeStatus | null> {
        if (!deviceId) {
            return null;
        }
        try {
            return await requireApiMethod('callBackendAPI')(
                'automation.ime_status', { device_id: deviceId }
            ) as ImeStatus;
        } catch (error) {
            log.error('获取输入法状态失败:', error);
            return null;
        }
    }

    /**
     * Subscribe to stream-event IPC (idempotent). ServiceManager calls this
     * automatically on first getService() — no manual wiring elsewhere.
     */
    async initialize(): Promise<void> {
        if (this.unsubscribe) return // already subscribed
        const api = window.electronAPI
        if (!api || typeof api.onStreamEvent !== 'function') {
            log.warn('[AutomationService] onStreamEvent not available — install stream events will not be received')
            this.unsubscribe = () => {} // no-op to mark as initialized
            return
        }
        this.unsubscribe = api.onStreamEvent((raw: any) => this.handleStream(raw))
    }

    /**
     * Streaming install of mitmproxy into `runtime/mitmproxy/lib`. Resolves
     * with the `complete` payload — INCLUDING the degraded
     * `{ success: false, degraded: true, manual_command, ... }` form — and
     * rejects only on the `error` event or a failed backend call.
     */
    async installMitmproxy(callbacks?: { onLog?: (line: string) => void }): Promise<TerminalPayload> {
        const taskId = genId('toolinstall')
        const promise = new Promise<TerminalPayload>((resolve, reject) => {
            // Slot registered synchronously BEFORE the backend call is issued
            // (subscription precedes launch — events emitted while the call is
            // in flight stay routable).
            this.handlers.set(taskId, {
                onLog: callbacks?.onLog,
                resolve,
                reject,
            })
        })
        try {
            await requireApiMethod('callBackendAPI')('automation.install_mitmproxy', { task_id: taskId })
        } catch (err) {
            // Do not leak the slot (and its callback closures) for a failed start.
            this.handlers.delete(taskId)
            throw err
        }
        return promise
    }

    /**
     * Streaming ADBKeyBoard install on one device: download → `adb install -r`
     * → verify. `apkPath` switches to the offline local-APK path (skips the
     * download); progress events only flow in the download phase.
     */
    async installIme(
        deviceId: string,
        callbacks?: { onLog?: (line: string) => void; onProgress?: (progress: any) => void },
        apkPath?: string,
    ): Promise<TerminalPayload> {
        const taskId = genId('toolinstall')
        const params: Record<string, unknown> = { device_id: deviceId, task_id: taskId }
        if (apkPath) {
            params.apk_path = apkPath
        }
        const promise = new Promise<TerminalPayload>((resolve, reject) => {
            this.handlers.set(taskId, {
                onLog: callbacks?.onLog,
                onProgress: callbacks?.onProgress,
                resolve,
                reject,
            })
        })
        try {
            await requireApiMethod('callBackendAPI')('automation.install_ime', params)
        } catch (err) {
            this.handlers.delete(taskId)
            throw err
        }
        return promise
    }

    /**
     * Install the already-generated CA certificate onto one device.
     * Non-streaming: the envelope unwraps normally to the backend result
     * (`{ success, already_installed, error }`), rejections propagate.
     */
    async installCa(deviceId: string): Promise<any> {
        return requireApiMethod('callBackendAPI')('automation.install_ca', { device_id: deviceId })
    }

    /** Drop the cached traffic probe so the next getTrafficStatus() re-fetches. */
    clearTrafficCache(): void {
        this.trafficStatus = null
    }

    // ----------------------------------------------------------------
    // Internals
    // ----------------------------------------------------------------

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
                case 'log': {
                    slot.onLog?.(payload?.line ?? String(payload))
                    break
                }

                case 'progress': {
                    slot.onProgress?.(payload)
                    break
                }

                case 'complete': {
                    // Degraded installs also arrive here — resolve, never reject.
                    this.handlers.delete(tid)
                    slot.resolve(payload)
                    break
                }

                case 'error': {
                    this.handlers.delete(tid)
                    slot.reject(new Error(payload?.message ?? String(payload)))
                    break
                }

                // Unknown types are ignored — the backend may grow new event
                // kinds without a renderer update.
                default:
                    break
            }
        } catch (err) {
            // Callback errors should never break event routing
            log.error('[AutomationService] handleStream error:', err)
        }
    }

    private unsubscribe: (() => void) | null = null;
    private handlers: Map<string, InstallSlot> = new Map();
    private trafficStatus: TrafficStatus | null = null;
}

export default AutomationService;
