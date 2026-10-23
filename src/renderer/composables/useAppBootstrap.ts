import { ref, onMounted, onUnmounted, getCurrentInstance } from 'vue'
import type { Ref } from 'vue'
import type { GlobalTheme } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import serviceManager from '@services/ServiceManager'
import { registerServices } from '../services/registry'
import { useAppConfigStore, useSystemStore, useToolStore } from '@stores/index'
import unifiedApi from '../api/unifiedApi'
import { log, setLogLevel, _setRingPusher } from '@utils/logger'
import { useRendererLogStore } from '@stores/rendererLogStore'
import { setMaxConcurrent } from '@services/TaskExecutionService'

// Tool probing is worth waiting for — every page needs it — but it is not
// worth hanging the splash on. Past this point the app opens with whatever the
// probe has produced so far (the store keeps filling in behind the UI).
const TOOL_PROBE_MAX_WAIT_MS = 5000

export function useAppBootstrap(currentTheme: Ref<GlobalTheme | null>) {
  const { t, locale: i18nLocale } = useI18n()

  // Loading state
  const isLoading = ref(true)
  const progress = ref(0)
  const step = ref(t('app.loadingInit'))
  const error = ref('')
  const retryCount = ref(0)
  const maxRetries = 3
  const time = ref('0.0')

  let timerInterval: ReturnType<typeof setInterval> | null = null
  let startTime = 0

  function createErrorHandler() {
    return (err: Error, _instance: unknown, info: string) => {
      log.error('Global error:', err, info)
      serviceManager.getService('error').then((errorService) => {
        if (errorService && typeof errorService.reportError === 'function') {
          errorService.reportError(err, { context: 'Vue global error handler', info })
        }
      }).catch(() => {})
    }
  }

  function startTimer() {
    startTime = Date.now()
    if (timerInterval) clearInterval(timerInterval)
    timerInterval = setInterval(() => {
      time.value = ((Date.now() - startTime) / 1000).toFixed(1)
    }, 100)
  }

  function stopTimer() {
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null }
  }

  async function initializeServices() {
    registerServices()
    const instance = getCurrentInstance()
    if (instance && instance.appContext.app) {
      instance.appContext.app.config.errorHandler = createErrorHandler()
    }
  }

  async function loadApplicationData() {
    const appConfigStore = useAppConfigStore()
    const systemStore = useSystemStore()
    // `build.info` shells out to `java -version` (a cold JVM, up to ~0.8s) for
    // the Settings/About card, which refetches it on mount anyway — it has no
    // business holding up the first paint.
    await Promise.all([
      appConfigStore.initialize(),
      systemStore.fetchSystemInfo(),
    ])
    // Wire renderer log ring buffer — logger.ts pushes entries here
    // so the Diagnostics panel can show them later.
    const ringStore = useRendererLogStore()
    _setRingPusher((level: string, msg: string) => {
      ringStore.push(level as 'debug' | 'info' | 'warn' | 'error', msg)
    })
    // Apply saved log level before any further logging
    const logsConfig = appConfigStore.get('logs') as { level?: string } | undefined
    const level = logsConfig?.level
    if (level) {
      setLogLevel(level as 'debug' | 'info' | 'warn' | 'error')
    }
    // Apply saved task concurrency cap (Settings → "Max concurrent tasks").
    const mct = appConfigStore.get('maxConcurrentTasks')
    if (typeof mct === 'number' && mct >= 1) {
      setMaxConcurrent(mct)
    }
  }

  /**
   * Kick off the tool probe and never reject.
   *
   * Deliberately NOT forced: a forced fetch re-probes every tool, which used to
   * mean fourteen subprocess launches (eight JVM cold starts) on every single
   * launch. The backend caches verdicts keyed by the binary's mtime/size, so
   * the unforced path is both correct and free on warm starts.
   */
  function startToolProbe(): Promise<void> {
    return useToolStore()
      .fetchTools(false)
      .then(() => undefined)
      .catch((e) => {
        log.error('Tool probe failed:', e)
      })
  }

  /** Join the probe, but never wait longer than the guard. */
  async function awaitToolProbe(probe: Promise<void> | null): Promise<void> {
    if (!probe) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const guard = new Promise<void>((resolve) => {
      timer = setTimeout(() => {
        log.warn(
          `Tool probe still running after ${TOOL_PROBE_MAX_WAIT_MS}ms — opening with partial results`
        )
        resolve()
      }, TOOL_PROBE_MAX_WAIT_MS)
    })
    try {
      await Promise.race([probe, guard])
    } finally {
      if (timer) clearTimeout(timer)
    }
  }

  /** Run one splash stage, recording its duration for the startup timeline. */
  async function runStage(key: string, task: () => unknown): Promise<void> {
    const startedAt = performance.now()
    try {
      await task()
    } finally {
      log.debug(`[startup] ${key} ${Math.round(performance.now() - startedAt)}ms`)
    }
  }

  async function loadThemePreference(): Promise<string | null> {
    try {
      const settingsSvc = await serviceManager.getService('settings')
      const model = await settingsSvc.loadSettingsModel()
      if (model?.settings) {
        const s = model.settings as Record<string, unknown>
        return typeof s.theme === 'string' ? s.theme : null
      }
    } catch {}
    return null
  }

  async function prepareUI() {
    await new Promise(resolve => setTimeout(resolve, 100))
    // Restore saved language preference
    try {
      const savedLang = await unifiedApi.getAPI()?.appConfig?.get('language')
      if (typeof savedLang === 'string') i18nLocale.value = savedLang
    } catch {}
    const themeService = await serviceManager.getService('theme')
    if (themeService) {
      const savedTheme = await loadThemePreference()
      if (savedTheme && typeof themeService.setTheme === 'function') {
        currentTheme.value = await themeService.setTheme(savedTheme)
      } else if (typeof themeService.applyTheme === 'function') {
        currentTheme.value = await themeService.applyTheme()
      }
      try {
        localStorage.setItem('bt:theme', themeService.getActualTheme())
      } catch {}
      if (typeof themeService.onChange === 'function') {
        themeService.onChange((theme: GlobalTheme | null) => {
          currentTheme.value = theme
          try {
            localStorage.setItem('bt:theme', themeService.getActualTheme())
          } catch {}
        })
      }
    }
    // The storage card's sizes are fetched by SettingsPage itself on mount,
    // so walking four directory trees does not belong on the splash path.

    // Initialize update service (set up event listeners)
    try {
      await serviceManager.getService('update')
    } catch {}

    // Initialize TaskStreamService (subscribes to stream-event IPC globally)
    try {
      await serviceManager.getService('taskStream')
    } catch {}

    // Global device monitoring: refresh the device list (and re-poll every
    // 5s) for ALL pages, not just while the Device page is mounted — other
    // pages (automation/install) read deviceStore.devices and used to show
    // stale disconnected devices until the user visited the Device page.
    try {
      const deviceSvc = await serviceManager.getService('device')
      await deviceSvc.refreshDevices()
      void deviceSvc.startMonitoring()
    } catch {}
  }

  async function initializeApplication() {
    log.debug('应用初始化开始')
    startTimer()
    try {
      error.value = ''

      // The tool probe starts once services are registered (config stage) and
      // is joined at the tools stage. Overlapping it with the remaining stages
      // costs the splash `max(config, probe)` instead of `config + probe`.
      let probePromise: Promise<void> | null = null

      const initTasks = [
        {
          key: 'services', name: t('app.loadingServices'),
          task: initializeServices, weight: 40, critical: true,
        },
        {
          key: 'config', name: t('app.loadingConfig'), weight: 30, critical: true,
          task: async () => {
            probePromise = startToolProbe()
            await loadApplicationData()
          },
        },
        {
          key: 'tools', name: t('app.loadingTools'), weight: 20, critical: false,
          task: () => awaitToolProbe(probePromise),
        },
        {
          key: 'ui', name: t('app.loadingUI'),
          task: prepareUI, weight: 10, critical: true,
        },
      ]

      let completedWeight = 0
      for (const taskInfo of initTasks) {
        try {
          step.value = taskInfo.name
          progress.value = completedWeight
          await runStage(taskInfo.key, taskInfo.task)
          completedWeight += taskInfo.weight
          progress.value = completedWeight
        } catch (e) {
          log.error(`${taskInfo.name} failed:`, e)
          if (taskInfo.critical) {
            throw new Error(`Critical task "${taskInfo.name}" failed: ${(e as Error).message}`)
          } else {
            completedWeight += taskInfo.weight
            progress.value = completedWeight
          }
        }
      }

      progress.value = 100
      isLoading.value = false
      stopTimer()
      log.debug('应用初始化完成')
    } catch (e) {
      log.error('Init failed:', e)
      stopTimer()
      error.value = (e as Error).message || t('app.initFailed')
      throw e
    }
  }

  function retry() {
    if (retryCount.value >= maxRetries) return
    retryCount.value++
    error.value = ''
    isLoading.value = true
    setTimeout(() => {
      // `initializeApplication` records the failure in `error` for the splash;
      // nobody awaits it here, so swallow the rejection rather than leaving an
      // unhandled one behind.
      initializeApplication().catch(() => {})
    }, 1000)
  }

  onMounted(() => {
    initializeApplication().catch(() => {})
  })

  onUnmounted(() => {
    stopTimer()
  })

  return { isLoading, progress, step, time, error, retryCount, maxRetries, retry }
}
