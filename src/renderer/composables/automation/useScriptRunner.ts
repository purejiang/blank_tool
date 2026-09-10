/**
 * Run lifecycle for the adb_auto plugin task: streaming callbacks, logs,
 * result payload, and cancel. All UI feedback (messages) stays in the
 * caller — validation of device/steps happens there too. Presentation
 * (step rows/summary) lives in ResultPanel.
 */
import { reactive, ref } from 'vue'
import serviceManager from '@services/ServiceManager'

export interface RunPayload {
  device_id: string
  package_name: string
  steps: unknown[]
  capture_traffic: boolean
}

export function useScriptRunner() {
  const running = ref(false)
  const taskId = ref('')
  const logs = ref<string[]>([])
  const runResult = ref<any>(null)
  const screenshots = ref<string[]>([])
  /** 运行中的实时步骤行（逐步推送，pending=true 表示正在执行） */
  const liveSteps = ref<any[]>([])

  function genId(): string {
    try {
      return (crypto as any).randomUUID()
    } catch {
      return 'id-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8)
    }
  }

  /**
   * Kick off a plugin.run stream. Throws on IPC failure; stream failures
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

    const id = genId()
    taskId.value = id

    const taskStream = (await serviceManager.getService('taskStream')) as any
    taskStream.bindTask(id)
    taskStream.setCallbacks(id, {
      onLog: (line: string) => {
        logs.value.push(String(line))
      },
      onError: (msg: string) => {
        logs.value.push('[ERROR] ' + msg)
        running.value = false
      },
      onCancelled: () => {
        logs.value.push('[CANCELLED]')
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
      // plugin.run is @streaming: the init response resolves to undefined after
      // unwrapBackendResponse (no `type` field) — NEVER test it for stream_id.
      // Real failures arrive as stream error events / the waitForPhase latch.
      // Deep-clone before IPC: steps come straight from reactive state and
      // Vue proxies are not structured-cloneable (preload also normalizes,
      // but this keeps the page safe even on a stale preload).
      const plainSteps = JSON.parse(JSON.stringify(payload.steps))
      await api.callBackendAPI('plugin.run', {
        name: 'adb_auto',
        params: {
          device_id: payload.device_id,
          package_name: payload.package_name,
          steps: plainSteps,
          continue_on_error: false,
          capture_traffic: payload.capture_traffic,
        },
        task_id: id,
      })
      await taskStream.waitForPhase(id, 'operation')
    } catch (e: any) {
      const m = e?.message
      if (m !== 'cancelled' && m !== 'unbound') {
        logs.value.push('[ERROR] ' + (m || String(e)))
        throw e
      }
      running.value = false
    }
  }

  async function stopRun() {
    if (!taskId.value) return
    const api = window.electronAPI as any
    // Streams (adb_auto / plugin.run) register their stop_event in TaskManager
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
    runScript,
    stopRun,
  })
}

export type ScriptRunner = ReturnType<typeof useScriptRunner>
