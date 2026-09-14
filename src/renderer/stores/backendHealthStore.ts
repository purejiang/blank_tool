import { defineStore } from 'pinia'
import { ref } from 'vue'

// 健康检查是主进程内的一次本地判断（看 python 子进程还活着没，不走 stdin、
// 没有 JSON-RPC 往返，<1ms）。所以「多久查一次」纯粹是「响应速度 vs 界面刷新
// 观感」的取舍，不是性能问题：
//   · 正常 30s：诊断页的「最后检查 / 运行时间」不再每 10 秒跳一次
//   · 异常 5s ：服务掉线后能很快自己好起来、点也尽快变绿
// 窗口不可见时不做检查，回到前台立刻补一次。
const HEALTHY_INTERVAL_MS = 30000
const UNHEALTHY_INTERVAL_MS = 5000

export const useBackendHealthStore = defineStore('backendHealth', () => {
  const isHealthy = ref<boolean | null>(null) // null = unknown (initial)
  const lastCheckedAt = ref<number | null>(null)
  // 后端服务已运行秒数（主进程按 spawn 时刻算）；进程不健康时为 null。
  const uptimeS = ref<number | null>(null)

  let timer: ReturnType<typeof setTimeout> | null = null
  let visibilityBound = false

  const isHidden = () => typeof document !== 'undefined' && document.hidden
  const nextDelay = () => (isHealthy.value === false ? UNHEALTHY_INTERVAL_MS : HEALTHY_INTERVAL_MS)

  function schedule(): void {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { void check() }, nextDelay())
  }

  /** 查一次健康状态（含运行时间）。页面/设置页的手动刷新传 force=true。 */
  async function check(force = false): Promise<void> {
    if (!timer && !force) return // 没在轮询时的裸调用（不该发生）不做无谓 IPC
    if (!force && isHidden()) {
      schedule()
      return
    }
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result = await window.electronAPI?.getBackendHealth?.()
      isHealthy.value = result?.healthy ?? false
      uptimeS.value = typeof result?.uptime_s === 'number' ? result.uptime_s : null
    } catch {
      isHealthy.value = false
      uptimeS.value = null
    }
    lastCheckedAt.value = Date.now()
    schedule()
  }

  function onVisibilityChange(): void {
    if (!isHidden()) void check(true)
  }

  function startPolling(): void {
    if (timer) return
    if (!visibilityBound && typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange)
      visibilityBound = true
    }
    schedule()
    void check()
  }

  function stopPolling(): void {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    if (visibilityBound && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange)
      visibilityBound = false
    }
  }

  return { isHealthy, lastCheckedAt, uptimeS, check, startPolling, stopPolling }
})
