/**
 * Run lifecycle for an automation.run task: streaming callbacks, logs,
 * result payload, and cancel. All UI feedback (messages) stays in the
 * caller — validation of device/steps happens there too. Presentation
 * (status bar / step rows / log feed) lives in RunPanel.
 */
import { reactive, ref } from 'vue'
import serviceManager from '@services/ServiceManager'
import { genId } from '@utils/id'

export interface RunPayload {
  device_id: string
  package_name: string
  steps: unknown[]
  capture_traffic: boolean
  /** Comma-separated host substrings; empty string = record everything. */
  traffic_host_filter?: string
  /** 步骤失败后继续执行（默认 false：首个失败即中止）。 */
  continue_on_error?: boolean
  /** 目标应用进程消失/重启时中止（默认 true）。 */
  abort_on_crash?: boolean
  /** 允许切换设备输入法输入非 ASCII（默认 true：不传即开启）。 */
  use_ime?: boolean
  /** 从脚本的第几步开始执行（0 基，缺省 0 = 从头跑）。 */
  start_index?: number
  /** 步骤之间的默认等待（ms，0 = 不等待）。单步可用 `delay_ms` 覆盖。 */
  step_interval_ms?: number
}

/** One console line. `ts` is epoch **seconds** (renderer clock on receipt,
 *  backend clock when replayed from report.json) so the log tab can show a
 *  timestamp without the backend having to stamp the streamed string. */
export interface LogLine {
  ts: number
  text: string
}

/**
 * Ring-buffer bound on the live console. A long run (element polling, a
 * verbosity-heavy script, shell probes) can emit tens of thousands of lines;
 * without a cap the array grows for the whole run and every push re-renders a
 * virtual list over all of it. The FULL feed stays available in the run's
 * `report.json` (backend side), so dropping the oldest lines here loses
 * nothing permanent. Mirrors the backend's `DEFAULT_LOG_LIMIT`.
 */
export const LOG_LIMIT = 5000

export function useScriptRunner() {
  const running = ref(false)
  const taskId = ref('')
  const logs = ref<LogLine[]>([])
  const runResult = ref<any>(null)
  const screenshots = ref<string[]>([])
  /** 运行中的实时步骤行（逐步推送，pending=true 表示正在执行） */
  const liveSteps = ref<any[]>([])
  /** 本次运行的起点（渲染进程时钟，epoch 秒）——实时日志算相对时间的基准 */
  const runStartedTs = ref(0)
  /** 日志已超过 {@link LOG_LIMIT}，最早的行被丢弃（控制台提示用） */
  const droppedLogs = ref(false)

  function pushLog(text: string) {
    logs.value.push({ ts: Date.now() / 1000, text: String(text) })
    // Ring buffer: keep the newest LOG_LIMIT lines (drop from the front, so
    // the console still ends on the line that just arrived).
    if (logs.value.length > LOG_LIMIT) {
      logs.value.splice(0, logs.value.length - LOG_LIMIT)
      droppedLogs.value = true
    }
  }

  /**
   * Kick off an automation.run stream. Throws on IPC failure; stream failures
   * arrive via callbacks / logs. Caller is responsible for validating the
   * payload BEFORE calling (device picked, steps non-empty, editor committed).
   */
  async function runScript(payload: RunPayload) {
    if (running.value) return
    running.value = true
    logs.value = []
    runResult.value = null
    screenshots.value = []
    liveSteps.value = []
    runStartedTs.value = Date.now() / 1000
    droppedLogs.value = false

    const id = genId()
    taskId.value = id

    const taskStream = (await serviceManager.getService('taskStream')) as any
    taskStream.bindTask(id)
    taskStream.setCallbacks(id, {
      onLog: (line: string) => {
        pushLog(line)
      },
      onError: (msg: string) => {
        pushLog('[ERROR] ' + msg)
        running.value = false
      },
      onCancelled: () => {
        pushLog('[CANCELLED]')
        running.value = false
      },
      onStepStart: (st: any) => {
        liveSteps.value = [...liveSteps.value.filter((x: any) => x.index !== st.index), st].sort(
          (a: any, b: any) => a.index - b.index,
        )
      },
      onStep: (st: any) => {
        const rest = liveSteps.value.filter((x: any) => x.index !== st?.index)
        liveSteps.value = [...rest, { ...st }].sort((a: any, b: any) => a.index - b.index)
      },
      onComplete: (result: any) => {
        runResult.value = result || {}
        screenshots.value = (result?.screenshots || []).slice()
        // complete 是权威结果：有步骤数据就覆盖实时行
        if (Array.isArray(result?.steps) && result.steps.length) {
          liveSteps.value = result.steps.slice()
        }
        running.value = false
      },
    })
    taskStream.setPhase(id, 'operation')

    const api = window.electronAPI as any
    try {
      // automation.run is @streaming: the init response resolves to undefined
      // after unwrapBackendResponse (no `type` field) — NEVER test it for
      // stream_id. Real failures arrive as stream error events / the
      // waitForPhase latch.
      // Deep-clone before IPC: steps come straight from reactive state and
      // Vue proxies are not structured-cloneable (preload also normalizes,
      // but this keeps the page safe even on a stale preload).
      const plainSteps = JSON.parse(JSON.stringify(payload.steps))
      await api.callBackendAPI('automation.run', {
        device_id: payload.device_id,
        package_name: payload.package_name,
        steps: plainSteps,
        // Defaults match both the backend signature and the pre-existing
        // behaviour (abort on first failure / abort on crash); the run
        // settings dialog is what turns them off.
        continue_on_error: payload.continue_on_error === true,
        abort_on_crash: payload.abort_on_crash !== false,
        // 不传即开启（与后端默认 true 对齐）：只有显式 false 才禁用中文输入
        use_ime: payload.use_ime !== false,
        // 运行起点 / 步骤间隔：夹到合法值再上行（后端也会再夹一次并打日志）
        start_index: Math.max(0, Math.floor(Number(payload.start_index) || 0)),
        step_interval_ms: Math.max(0, Math.round(Number(payload.step_interval_ms) || 0)),
        capture_traffic: payload.capture_traffic,
        traffic_host_filter: payload.traffic_host_filter || '',
        task_id: id,
      })
      await taskStream.waitForPhase(id, 'operation')
    } catch (e: any) {
      const m = e?.message
      if (m !== 'cancelled' && m !== 'unbound') {
        // IPC-level failure (backend down / request timed out / error
        // envelope). No `onError` stream callback fires on this path, so the
        // error line must be added here — and the rethrow is what lets the
        // page surface a toast. Skip when the identical line was already
        // pushed by the onError callback (waitForPhase rejects on the same
        // error event that fired the callback — that used to log twice).
        const line = '[ERROR] ' + (m || String(e))
        if (logs.value[logs.value.length - 1]?.text !== line) pushLog(line)
        // The stream will never report this task again (the backend never
        // started it, or the response was lost): drop the listener + latch now
        // instead of leaving the task registered for the whole session.
        // `unbindTask` is idempotent, so the already-unbound paths are safe.
        taskStream.unbindTask(id)
        throw e
      }
    } finally {
      // ALWAYS clear the busy flag: on the IPC-failure path above neither
      // `onComplete` nor `onError` ever runs, which previously left
      // `running === true` forever — the run console stayed "运行中" (stop
      // button, inputs disabled) while showing no logs and no steps.
      running.value = false
    }
  }

  async function stopRun() {
    if (!taskId.value) return
    const api = window.electronAPI as any
    // automation.run registers its stop_event in TaskManager
    // under task_id — only `request.cancel` signals it. `apk.cancelTask` only
    // touches APK jobs, so using it here left the run unstoppable.
    if (api && typeof api.cancelRequest === 'function') {
      try {
        await api.cancelRequest(taskId.value)
      } catch {
        /* ignore */
      }
    }
  }

  return reactive({
    running,
    taskId,
    logs,
    runResult,
    screenshots,
    liveSteps,
    runStartedTs,
    droppedLogs,
    runScript,
    stopRun,
  })
}

export type ScriptRunner = ReturnType<typeof useScriptRunner>
