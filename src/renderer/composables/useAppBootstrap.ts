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
    await Promise.all([
      appConfigStore.initialize(),
      systemStore.fetchSystemInfo(),
      systemStore.fetchBuildInfo(),
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

  async function checkToolsStatus() {
    const toolStore = useToolStore()
    await toolStore.fetchTools(true)
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
    const cacheService = await serviceManager.getService('cache')
    if (cacheService) { await cacheService.getCacheInfo().catch(() => {}) }

    // Initialize update service (set up event listeners)
    try {
      await serviceManager.getService('update')
    } catch {}

    // Initialize TaskStreamService (subscribes to stream-event IPC globally)
    try {
      await serviceManager.getService('taskStream')
    } catch {}
  }

  async function initializeApplication() {
    log.debug('应用初始化开始')
    startTimer()
    try {
      error.value = ''

      const initTasks = [
        { name: t('app.loadingServices'), task: initializeServices, weight: 40, critical: true },
        { name: t('app.loadingConfig'), task: loadApplicationData, weight: 30, critical: true },
        { name: t('app.loadingTools'), task: checkToolsStatus, weight: 20, critical: false },
        { name: t('app.loadingUI'), task: prepareUI, weight: 10, critical: true },
      ]

      let completedWeight = 0
      for (const taskInfo of initTasks) {
        try {
          step.value = taskInfo.name
          progress.value = completedWeight
          await taskInfo.task()
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
      await new Promise(resolve => setTimeout(resolve, 300))
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
    setTimeout(() => initializeApplication(), 1000)
  }

  onMounted(() => {
    initializeApplication()
  })

  onUnmounted(() => {
    stopTimer()
  })

  return { isLoading, progress, step, time, error, retryCount, maxRetries, retry }
}
