<template>
  <n-config-provider :theme="currentTheme" :theme-overrides="themeOverrides" :locale="locale">
    <n-notification-provider placement="bottom-right">
      <n-message-provider>
        <div id="app">
          <!-- Loading Screen -->
          <div v-if="isLoading" class="loading-screen">
            <div class="loading-container">
              <div class="loading-brand">
                <n-icon size="48" color="#22C55E">
                  <Terminal />
                </n-icon>
                <h1 class="loading-title">{{ $t('app.title') }}</h1>
                <p class="loading-subtitle">{{ $t('app.subtitle') }}</p>
              </div>
              <n-progress
                type="line"
                :percentage="loadingProgress"
                :height="6"
                :border-radius="3"
                color="#22C55E"
                rail-color="rgba(255,255,255,0.1)"
              />
              <div class="loading-info">
                <p class="loading-step">{{ loadingStep }}</p>
                <p class="loading-timer">{{ loadingTime }}s</p>
              </div>
              <div v-if="initError" class="loading-error-card">
                <n-alert type="error" :title="initError">
                  <template #footer>
                    <n-button v-if="showRetryButton" @click="retryInitialization" type="error" size="small">
                      {{ $t('app.retry') }} ({{ retryCount }}/{{ maxRetries }})
                    </n-button>
                  </template>
                </n-alert>
              </div>
            </div>
          </div>

          <!-- Main App Layout -->
          <n-layout v-else has-sider class="app-layout">
            <!-- Sidebar -->
            <n-layout-sider
              bordered
              collapse-mode="width"
              :collapsed-width="64"
              :width="220"
              :collapsed="sidebarCollapsed"
              :native-scrollbar="false"
              class="app-sider"
            >
              <div class="sider-inner">
                <!-- App Brand -->
                <div class="sider-brand" :class="{ collapsed: sidebarCollapsed }">
                  <n-icon size="28" color="#22C55E">
                    <Terminal />
                  </n-icon>
                  <span v-if="!sidebarCollapsed" class="brand-text">{{ $t('app.title') }}</span>
                  <div class="brand-collapse">
                    <n-button
                      quaternary
                      circle
                      size="tiny"
                      @click="sidebarCollapsed = !sidebarCollapsed"
                    >
                      <template #icon>
                        <n-icon size="16"><ChevronsLeft v-if="!sidebarCollapsed" /><ChevronsRight v-else /></n-icon>
                      </template>
                    </n-button>
                  </div>
                </div>

                <!-- Navigation Menu -->
                <n-menu
                  :value="activeMenuKey"
                  :collapsed="sidebarCollapsed"
                  :collapsed-width="64"
                  :collapsed-icon-size="22"
                  :options="menuOptions"
                  :render-label="renderMenuLabel"
                  @update:value="handleMenuSelect"
                  class="sider-menu"
                />

                <!-- Status Bar (bottom of sidebar) -->
                <StatusBar :collapsed="sidebarCollapsed" />
              </div>
            </n-layout-sider>

            <!-- Main Content -->
            <n-layout>
              <n-layout-content class="main-content">
                <router-view />
              </n-layout-content>
            </n-layout>
          </n-layout>
        </div>
      </n-message-provider>
    </n-notification-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { ref, h, onMounted, onUnmounted, getCurrentInstance, computed, provide, watch } from 'vue'
import type { GlobalTheme } from 'naive-ui'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { darkTheme, NIcon, zhCN, enUS } from 'naive-ui'
import {
  Smartphone, Package, Settings, Wrench, Terminal,
  ChevronsLeft, ChevronsRight, Info
} from 'lucide-vue-next'
import type { MenuOption } from 'naive-ui'
import StatusBar from '@components/common/StatusBar.vue'
import serviceManager from '@services/ServiceManager'
import { ThemeService } from '@services/ThemeService'
import ToolService from '@services/ToolService'
import NotificationService from '@services/NotificationService'
import unifiedApi from './api/unifiedApi'
import ErrorService from '@services/ErrorService'
import { ConfigService } from '@services/ConfigService'
import ApkService from '@services/ApkService'
import CacheService from '@services/CacheService'
import DeviceService from '@services/DeviceService'
import SystemService from '@services/SystemService'
import StoreService from '@services/StoreService'
import SettingsService from '@services/SettingsService'
import { useToolStore, useAppConfigStore, useSystemStore } from '@stores/index'

const router = useRouter()
const route = useRoute()
const { t, locale: i18nLocale } = useI18n()

// Theme overrides for OLED dark mode
const themeOverridesDark = {
  common: {
    bodyColor: '#0F172A',
    cardColor: '#1E293B',
    modalColor: '#1E293B',
    popoverColor: '#1E293B',
    borderColor: '#334155',
    borderRadius: '8px',
    primaryColor: '#22C55E',
    primaryColorHover: '#16A34A',
    primaryColorPressed: '#15803D',
    infoColor: '#3B82F6',
    successColor: '#22C55E',
    warningColor: '#F59E0B',
    errorColor: '#EF4444',
    textColor1: '#F8FAFC',
    textColor2: '#CBD5E1',
    textColor3: '#94A3B8',
    scrollbarColor: '#334155',
    inputColor: '#1E293B',
    actionColor: '#334155',
    hoverColor: 'rgba(34,197,94,0.12)',
  },
  Input: {
    border: '1px solid #475569',
    borderHover: '1px solid #22C55E',
    borderFocus: '1px solid #22C55E',
    borderRadius: '8px',
  },
  InternalSelection: {
    border: '1px solid #475569',
    borderHover: '1px solid #22C55E',
    borderFocus: '1px solid #22C55E',
    borderRadius: '8px',
  },
}

const themeOverridesLight = {
  common: {
    bodyColor: '#F1F5F9',
    cardColor: '#FFFFFF',
    modalColor: '#FFFFFF',
    popoverColor: '#FFFFFF',
    borderColor: '#E2E8F0',
    borderRadius: '8px',
    primaryColor: '#16A34A',
    primaryColorHover: '#15803D',
    primaryColorPressed: '#166534',
    infoColor: '#2563EB',
    successColor: '#16A34A',
    warningColor: '#D97706',
    errorColor: '#DC2626',
    textColor1: '#0F172A',
    textColor2: '#475569',
    textColor3: '#94A3B8',
    scrollbarColor: '#CBD5E1',
    inputColor: '#FFFFFF',
    actionColor: '#E2E8F0',
    hoverColor: 'rgba(22,163,74,0.08)',
  },
  Input: {
    border: '1px solid #CBD5E1',
    borderHover: '1px solid #16A34A',
    borderFocus: '1px solid #16A34A',
    borderRadius: '8px',
  },
  InternalSelection: {
    border: '1px solid #CBD5E1',
    borderHover: '1px solid #16A34A',
    borderFocus: '1px solid #16A34A',
    borderRadius: '8px',
  },
}

const themeOverrides = computed(() =>
  currentTheme.value ? themeOverridesDark : themeOverridesLight
)

// Sidebar
const sidebarCollapsed = ref(false)
const activeMenuKey = ref(route.path || '/package')
const currentTheme = ref<GlobalTheme | null>(darkTheme)

// Locale for Naive UI i18n
const locale = computed(() => i18nLocale.value === 'zh-CN' ? zhCN : enUS)
const setLocale = (lang: string) => {
  i18nLocale.value = lang
}
const setTheme = async (mode: string) => {
  const themeService = await serviceManager.getService('theme')
  if (themeService) {
    currentTheme.value = await themeService.setTheme(mode)
  }
}
const getCurrentTheme = () => currentTheme.value
provide('setLocale', setLocale)
provide('setTheme', setTheme)
provide('getCurrentTheme', getCurrentTheme)

const renderMenuLabel = (option: MenuOption) => {
  return option.label as string
}

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions = computed<MenuOption[]>(() => [
  { label: t('nav.package'), key: '/package', icon: renderIcon(Package) },
  { label: t('nav.tools'), key: '/plugins', icon: renderIcon(Wrench) },
  { label: t('nav.settings'), key: '/settings', icon: renderIcon(Settings) },
  { label: t('nav.about'), key: '/about', icon: renderIcon(Info) },
])

function handleMenuSelect(key: string) {
  activeMenuKey.value = key
  router.push(key)
}

// Sync active menu key with current route (e.g., after redirect / -> /package)
watch(() => route.path, (p) => {
  if (p !== '/') activeMenuKey.value = p
}, { immediate: true })

// Loading state
const isLoading = ref(true)
const loadingProgress = ref(0)
const loadingStep = ref(t('app.loadingInit'))
const initError = ref('')
const showRetryButton = ref(false)
const retryCount = ref(0)
const maxRetries = 3
const loadingTime = ref('0.0')
let timerInterval: ReturnType<typeof setInterval> | null = null
let startTime = 0

function registerServices() {
  serviceManager.register('config', ConfigService)
  serviceManager.register('notification', NotificationService)
  serviceManager.register('device', DeviceService)
  serviceManager.register('theme', ThemeService)
  serviceManager.register('tools', ToolService, ['config'])
  serviceManager.register('error', ErrorService, ['notification'])
  serviceManager.register('system', SystemService)
  serviceManager.register('apk', ApkService, ['config'])
  serviceManager.register('cache', CacheService, ['config'])
  serviceManager.register('store', StoreService)
  serviceManager.register('settings', SettingsService, ['store'])
}

function createErrorHandler() {
  return (error: Error, _instance: any, info: string) => {
    console.error('Global error:', error, info)
    serviceManager.getService('error').then((errorService) => {
      if (errorService && typeof errorService.reportError === 'function') {
        errorService.reportError(error, { context: 'Vue global error handler', info })
      }
    }).catch(() => {})
  }
}

function startTimer() {
  startTime = Date.now()
  if (timerInterval) clearInterval(timerInterval)
  timerInterval = setInterval(() => {
    loadingTime.value = ((Date.now() - startTime) / 1000).toFixed(1)
  }, 100)
}

function stopTimer() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null }
}

async function initializeApplication() {
  startTimer()
  try {
    initError.value = ''

    const initTasks = [
      { name: t('app.loadingServices'), task: initializeServices, weight: 40, critical: true },
      { name: t('app.loadingConfig'), task: loadApplicationData, weight: 30, critical: true },
      { name: t('app.loadingTools'), task: checkToolsStatus, weight: 20, critical: false },
      { name: t('app.loadingUI'), task: prepareUI, weight: 10, critical: true },
    ]

    let completedWeight = 0
    for (const taskInfo of initTasks) {
      try {
        loadingStep.value = taskInfo.name
        loadingProgress.value = completedWeight
        await taskInfo.task()
        completedWeight += taskInfo.weight
        loadingProgress.value = completedWeight
      } catch (error: any) {
        console.error(`${taskInfo.name} failed:`, error)
        if (taskInfo.critical) {
          throw new Error(`Critical task "${taskInfo.name}" failed: ${error.message}`)
        } else {
          completedWeight += taskInfo.weight
          loadingProgress.value = completedWeight
        }
      }
    }

    loadingProgress.value = 100
    await new Promise(resolve => setTimeout(resolve, 300))
    isLoading.value = false
    stopTimer()
  } catch (error: any) {
    console.error('Init failed:', error)
    stopTimer()
    initError.value = error.message || t('app.initFailed')
    showRetryButton.value = true
    throw error
  }
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
  const themeService = await serviceManager.getService('theme')
  if (themeService) {
    const savedTheme = await loadThemePreference()
    if (savedTheme && typeof themeService.setTheme === 'function') {
      currentTheme.value = await themeService.setTheme(savedTheme)
    } else if (typeof themeService.applyTheme === 'function') {
      currentTheme.value = await themeService.applyTheme()
    }
    if (typeof themeService.onChange === 'function') {
      themeService.onChange((theme: GlobalTheme | null) => {
        currentTheme.value = theme
      })
    }
  }
  const cacheService = await serviceManager.getService('cache')
  if (cacheService) { await cacheService.getCacheInfo().catch(() => {}) }
}

function retryInitialization() {
  if (retryCount.value >= maxRetries) {
    showRetryButton.value = false
    return
  }
  retryCount.value++
  initError.value = ''
  showRetryButton.value = false
  isLoading.value = true
  setTimeout(() => initializeApplication(), 1000)
}

onMounted(() => {
  console.log('App mounted, starting initialization')
  initializeApplication()
})

onUnmounted(() => {
  stopTimer()
})
</script>

<style scoped>
/* Loading Screen */
.loading-screen {
  position: fixed;
  inset: 0;
  background: var(--app-body-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.loading-container {
  width: 360px;
  text-align: center;
}
.loading-brand {
  margin-bottom: 32px;
}
.loading-title {
  font-family: Inter, sans-serif;
  font-size: 24px;
  font-weight: 700;
  color: var(--app-text-primary);
  margin: 12px 0 0;
}
.loading-subtitle {
  font-family: Inter, sans-serif;
  font-size: 13px;
  color: var(--app-text-muted);
  margin: 4px 0 0;
}
.loading-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}
.loading-step {
  font-size: 13px;
  color: var(--app-text-muted);
  margin: 0;
}
.loading-timer {
  font-size: 12px;
  color: var(--app-text-muted);
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.loading-error-card {
  margin-top: 24px;
}

/* App Layout */
.app-layout {
  height: 100vh;
}
.app-sider {
  background: var(--app-sidebar-bg);
}
.sider-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.sider-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 18px 16px;
  border-bottom: 1px solid var(--app-sidebar-border);
  flex-shrink: 0;
}
.brand-collapse {
  margin-left: auto;
}
.sider-brand.collapsed {
  justify-content: center;
  padding: 20px 0 16px;
}
.sider-brand.collapsed {
  flex-direction: column;
  gap: 8px;
  padding: 16px 0 12px;
}
.sider-brand.collapsed .brand-collapse {
  margin-left: 0;
}
.brand-text {
  font-family: Inter, sans-serif;
  font-size: 16px;
  font-weight: 700;
  color: var(--app-text-primary);
  letter-spacing: -0.02em;
}
.sider-menu {
  flex: 1;
  overflow-y: auto;
}
.main-content {
  padding: 24px;
  background: var(--app-body-bg);
  height: 100vh;
  overflow-y: auto;
}
</style>

<style>
/* Global Naive UI menu overrides */
.n-menu .n-menu-item-content {
  margin: 2px 8px;
  border-radius: 8px;
  transition: all 0.15s ease;
}
.n-menu .n-menu-item-content--selected {
  background: var(--app-hover-strong) !important;
}

/* Card header backgrounds - transparent everywhere */
.n-card-header,
.n-card-header__main,
.n-card-header__close,
.n-card__header,
.n-card .n-card-header,
.n-card > .n-card-header {
  background: transparent !important;
}
/* Card content area also transparent, matching cardColor */
.n-card > .n-card__content {
  background: transparent !important;
}
.n-menu .n-menu-item-content:hover {
  background: var(--app-hover) !important;
}
.n-menu .n-menu-item-content:active {
  background: var(--app-hover-strong) !important;
}
/* Center icons when sidebar is collapsed */
.n-menu--collapsed .n-menu-item-content {
  margin-left: auto !important;
  margin-right: auto !important;
  justify-content: center !important;
}
.n-menu--collapsed .n-menu-item-content .n-menu-item-content__icon {
  margin-right: 0 !important;
}
/* Sidebar scroll container fill sider height */
.n-layout-sider .n-scrollbar-container,
.n-layout-sider .n-scrollbar-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.n-layout-sider .n-scrollbar {
  height: 100%;
}

/* Notification toasts — smaller font */
.n-notification .n-notification__main {
  font-size: 12px;
}
.n-notification .n-notification__main__title {
  font-size: 13px;
  font-weight: 600;
}

</style>
