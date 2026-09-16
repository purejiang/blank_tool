
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
 * with type ∈ 'log' | 'progress' | 'complete' | 'error' | 'cancelled'.
 */
import { log } from '@utils/logger'
import { genId } from '@utils/id'
import { requireApiMethod } from '../api/apiAccess';

/** Message a cancelled install rejects with — the modal maps it to 已取消. */
export const INSTALL_CANCELLED = 'cancelled'

export interface TrafficStatus {
    installed: boolean
    ready: boolean
    lib_path: string
    python_mismatch: string | null
    /** CA 证书是否已生成（首次抓包运行时自动生成）。 */
    ca_cert_exists: boolean
    /** 以下字段只在按设备探测时返回（见 getTrafficStatus 的 deviceId 参数）。 */
    device_id?: string
    /** `adb get-state`：device / offline / unauthorized / unknown … */
    device_state?: string
    /** 设备系统证书区是否已有该 CA；`null` = 证书还没生成/无法判断。 */
    ca_on_device?: boolean | null
    /** 设备是否可用 root（安装 CA 的前提）；`null` = 无法判断。 */
    root_available?: boolean | null
}

/**
 * Sentinel message the install watchdog rejects with when a stream has been
 * totally silent for INSTALL_IDLE_TIMEOUT_MS. The main process now emits a
 * synthetic terminal `error` when it drops a stream — timeout `-32003` or
 * backend exit `-32002` — carrying `stream_id` + `task_id`, so a dead
 * transport normally settles the returned Promise. The renderer-side
 * watchdog stays as DEFENSE-IN-DEPTH: it still covers the edges the
 * synthetic cannot — the sender WebContents was destroyed, or the stream
 * goes silent without its entry ever being reaped — where the Promise would
 * otherwise never settle and the install modal's buttons would stay wedged
 * until app reload.
 */
export const INSTALL_IDLE_TIMEOUT = 'install-idle-timeout'
/** Total silence (no stream event for the task_id) before the watchdog fires. */
export const INSTALL_IDLE_TIMEOUT_MS = 180_000

export interface ImeStatus {
    device_id: string
    package: string
    installed: boolean
    active: boolean
}

/** One device repaired by ``resetTraffic`` (see ``automation.traffic_reset``). */
export interface TrafficRecovery {
    device_id: string
    proxy_restored: boolean
    reverse_removed: boolean
    /** `null` = nothing was listening on the port; `false` = it could not be freed. */
    port_freed: boolean | null
    error?: string
}

export interface TrafficResetResult {
    success: boolean
    restored: TrafficRecovery[]
    error?: string
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
    /** Inactivity watchdog — cleared and re-armed on every stream event. */
    idleTimer?: ReturnType<typeof setTimeout>
}

class AutomationService {
    /**
     * mitmproxy availability. `null` means the probe itself failed — the UI
     * shows an "unknown" state instead of pretending it is missing.
     *
     * Pass `deviceId` to additionally probe THAT device's capture readiness
     * (reachable / rooted / CA installed). The cache is PER device, so a
     * PC-only probe never masks a device-scoped one.
     */
    async getTrafficStatus(force = false, deviceId = ''): Promise<TrafficStatus | null> {
        const key = deviceId || ''
        if (!force && this.trafficStatus.has(key)) {
            return this.trafficStatus.get(key)!
        }
        try {
            const status = await requireApiMethod('callBackendAPI')(
                'automation.traffic_status', key ? { device_id: key } : {}
            ) as TrafficStatus;
            this.trafficStatus.set(key, status)
            return status;
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
     * Repair device-side traffic-capture wiring left by a killed backend.
     *
     * A capture in flight when the app is force-closed leaves the device's
     * `global http_proxy` pointing at a dead local proxy — the device is then
     * offline until this is undone. The backend also runs the same recovery
     * automatically at startup; this is the manual escape hatch. Idempotent:
     * `restored` is empty when nothing was stale. Never throws — failures are
     * reported so the settings page can show them instead of a dead button.
     */
    async resetTraffic(deviceId?: string): Promise<TrafficResetResult> {
        try {
            return await requireApiMethod('callBackendAPI')(
                'automation.traffic_reset',
                deviceId ? { device_id: deviceId } : {},
            ) as TrafficResetResult;
        } catch (error: any) {
            log.error('修复设备代理失败:', error);
            return { success: false, restored: [], error: error?.message || String(error) };
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
            // in flight stay routable). The inactivity watchdog is armed at the
            // same moment: 180s of total silence for this task_id rejects.
            const slot: InstallSlot = {
                onLog: callbacks?.onLog,
                resolve,
                reject,
            }
            this.handlers.set(taskId, slot)
            this.armIdleWatchdog(taskId, slot)
        })
        // Fast-refusal paths (backend rejects before the stream starts) can
        // settle the promise before the caller awaits — swallow that first
        // settlement so it never surfaces as "Uncaught (in promise)". The
        // caller still observes the rejection through the returned promise.
        promise.catch(() => {})
        this.trackInstall(taskId, promise)
        try {
            await requireApiMethod('callBackendAPI')('automation.install_mitmproxy', { task_id: taskId })
        } catch (err) {
            // Do not leak the slot (and its callback closures) for a failed start.
            this.clearIdleWatchdog(taskId)
            this.handlers.delete(taskId)
            this.installing.delete(taskId)
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
        /** Force a fresh APK download even when the cache is populated. */
        redownload = false,
    ): Promise<TerminalPayload> {
        const taskId = genId('toolinstall')
        const params: Record<string, unknown> = { device_id: deviceId, task_id: taskId }
        if (apkPath) {
            params.apk_path = apkPath
        }
        if (redownload) {
            params.redownload = true
        }
        const promise = new Promise<TerminalPayload>((resolve, reject) => {
            const slot: InstallSlot = {
                onLog: callbacks?.onLog,
                onProgress: callbacks?.onProgress,
                resolve,
                reject,
            }
            this.handlers.set(taskId, slot)
            this.armIdleWatchdog(taskId, slot)
        })
        promise.catch(() => {})
        this.trackInstall(taskId, promise)
        try {
            await requireApiMethod('callBackendAPI')('automation.install_ime', params)
        } catch (err) {
            this.clearIdleWatchdog(taskId)
            this.handlers.delete(taskId)
            this.installing.delete(taskId)
            throw err
        }
        return promise
    }

    /**
     * Cancel every in-flight streaming tool install (IME / mitmproxy).
     *
     * Installs can spend minutes downloading an APK or running pip, and the
     * modal used to offer no way out at all. `request.cancel` is the only path
     * that reaches the backend's stop_event / process holder, and the backend
     * answers with a terminal `cancelled` event which rejects these promises.
     *
     * Returns the number of tasks signalled (0 = nothing was running).
     */
    async cancelInstalls(): Promise<number> {
        const ids = [...this.installing]
        if (!ids.length) return 0
        const api = window.electronAPI as any
        if (!api || typeof api.cancelRequest !== 'function') return 0
        let signalled = 0
        for (const id of ids) {
            try {
                await api.cancelRequest(id)
                signalled++
            } catch (error) {
                log.warn('[AutomationService] cancel install failed:', error)
            }
        }
        return signalled
    }

    /** True while at least one install stream is live (drives the modal's
     *  cancel affordance without the caller tracking task ids). */
    hasRunningInstall(): boolean {
        return this.installing.size > 0
    }

    /**
     * Remember a live install task id and drop it as soon as its promise
     * settles — either way, so a failed install never stays cancelable.
     */
    private trackInstall(taskId: string, promise: Promise<unknown>): void {
        this.installing.add(taskId)
        const drop = () => this.installing.delete(taskId)
        promise.then(drop, drop)
    }

    /**
     * Install the already-generated CA certificate onto one device.
     * Non-streaming: the envelope unwraps normally to the backend result
     * (`{ success, already_installed, error }`), rejections propagate.
     */
    async installCa(deviceId: string): Promise<any> {
        return requireApiMethod('callBackendAPI')('automation.install_ca', { device_id: deviceId })
    }

    /** Drop the cached traffic probes (every device) so the next call re-fetches. */
    clearTrafficCache(): void {
        this.trafficStatus.clear()
    }

    // ----------------------------------------------------------------
    // Internals
    // ----------------------------------------------------------------

    /**
     * Arm the per-slot inactivity watchdog. Fires only after
     * INSTALL_IDLE_TIMEOUT_MS of TOTAL silence for the task_id (every routed
     * stream event re-arms it): the terminal `complete` may have been dropped
     * by the main process, so silence is the only detectable symptom.
     */
    private armIdleWatchdog(taskId: string, slot: InstallSlot): void {
        slot.idleTimer = setTimeout(() => {
            if (this.handlers.get(taskId) !== slot) return // already settled elsewhere
            this.handlers.delete(taskId)
            slot.reject(new Error(INSTALL_IDLE_TIMEOUT))
        }, INSTALL_IDLE_TIMEOUT_MS)
    }

    /** Re-arm the watchdog on activity (log / progress / complete / error). */
    private resetIdleWatchdog(taskId: string, slot: InstallSlot): void {
        if (slot.idleTimer) clearTimeout(slot.idleTimer)
        this.armIdleWatchdog(taskId, slot)
    }

    /** Drop the watchdog handle — every exit path must leave no live timer. */
    private clearIdleWatchdog(taskId: string): void {
        const slot = this.handlers.get(taskId)
        if (slot?.idleTimer) {
            clearTimeout(slot.idleTimer)
            slot.idleTimer = undefined
        }
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
                case 'log': {
                    this.resetIdleWatchdog(tid, slot)
                    slot.onLog?.(payload?.line ?? String(payload))
                    break
                }

                case 'progress': {
                    this.resetIdleWatchdog(tid, slot)
                    slot.onProgress?.(payload)
                    break
                }

                case 'complete': {
                    // Degraded installs also arrive here — resolve, never reject.
                    this.clearIdleWatchdog(tid)
                    this.handlers.delete(tid)
                    slot.resolve(payload)
                    break
                }

                case 'error': {
                    this.clearIdleWatchdog(tid)
                    this.handlers.delete(tid)
                    slot.reject(new Error(payload?.message ?? String(payload)))
                    break
                }

                case 'cancelled': {
                    // The user stopped the install. Terminal — never resolve
                    // with a result, or the UI would report the half-finished
                    // install as done (which is exactly what the idle-timeout
                    // watchdog used to mask, 180s later).
                    this.clearIdleWatchdog(tid)
                    this.handlers.delete(tid)
                    slot.reject(new Error(INSTALL_CANCELLED))
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
    /** task ids of live streaming installs — the cancel button's targets. */
    private installing: Set<string> = new Set();
    private trafficStatus: Map<string, TrafficStatus> = new Map();
}

export default AutomationService;
