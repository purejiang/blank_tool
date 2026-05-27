<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-notification-provider>
      <n-message-provider>
        <div id="app">
          <!-- Loading Screen -->
          <div v-if="isLoading" class="loading-screen">
            <div class="loading-container">
              <div class="loading-brand">
                <n-icon size="48" color="#22C55E">
                  <Terminal />
                </n-icon>
                <h1 class="loading-title">Blank Tool</h1>
                <p class="loading-subtitle">Android Development Toolkit</p>
              </div>
              <n-progress
                type="line"
                :percentage="loadingProgress"
                :indicator-placement="'inside'"
                :height="4"
                :border-radius="2"
                color="#22C55E"
                rail-color="rgba(255,255,255,0.1)"
              />
              <div class="loading-info">
                <p class="loading-step">{{ loadingStep }}</p>
                <p class="loading-timer">{{ loadingTime }}s</p>
              </div>
              <div v-if="initError" class="loading-error-card">
                <n-alert type="error" :title="initError">
                  <template v-if="showRetryButton" #footer>
                    <n-button @click="retryInitialization" type="error" size="small">
                      Retry ({{ retryCount }}/{{ maxRetries }})
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
              <!-- App Brand -->
              <div class="sider-brand" :class="{ collapsed: sidebarCollapsed }">
                <n-icon size="28" color="#22C55E">
                  <Terminal />
                </n-icon>
                <span v-if="!sidebarCollapsed" class="brand-text">Blank Tool</span>
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
              />

              <!-- Bottom Actions -->
              <div class="sider-footer" :class="{ collapsed: sidebarCollapsed }">
                <n-button
                  quaternary
                  circle
                  size="small"
                  @click="sidebarCollapsed = !sidebarCollapsed"
                >
                  <template #icon>
                    <n-icon><ChevronsLeft v-if="!sidebarCollapsed" /><ChevronsRight v-else /></n-icon>
                  </template>
                </n-button>
              </div>
            </n-layout-sider>

            <!-- Main Content -->
            <n-layout>
              <n-layout-content class="main-content">
                <router-view />
              </n-layout-content>
              <StatusBar />
            </n-layout>
          </n-layout>
        </div>
      </n-message-provider>
    </n-notification-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { ref, h, onMounted, onUnmounted, getCurrentInstance, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { darkTheme, NIcon } from 'naive-ui'
import {
  Smartphone, Package, Settings, Wrench, Terminal,
  ChevronsLeft, ChevronsRight
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
import { useToolStore, useAppConfigStore, useSystemStore } from '@stores/index'

const router = useRouter()
const route = useRoute()

// Theme overrides for OLED dark mode
const themeOverrides = {
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
    hoverColor: 'rgba(34,197,94,0.1)',
  },
}

// Sidebar
const sidebarCollapsed = ref(false)
const activeMenuKey = ref(route.path || '/device')

const renderMenuLabel = (option: MenuOption) => {
  return option.label as string
}

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions: MenuOption[] = [
  { label: 'Device', key: '/device', icon: renderIcon(Smartphone) },
  { label: 'Package', key: '/package', icon: renderIcon(Package) },
  { label: 'Tools', key: '/tools', icon: renderIcon(Wrench) },
  { label: 'Settings', key: '/settings', icon: renderIcon(Settings) },
]

function handleMenuSelect(key: string) {
  activeMenuKey.value = key
  router.push(key)
}

// Loading state
const isLoading = ref(true)
const loadingProgress = ref(0)
const loadingStep = ref('Initializing...')
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
      { name: 'Loading services...', task: initializeServices, weight: 40, critical: true },
      { name: 'Loading configuration...', task: loadApplicationData, weight: 30, critical: true },
      { name: 'Checking tools...', task: checkToolsStatus, weight: 20, critical: false },
      { name: 'Preparing UI...', task: prepareUI, weight: 10, critical: true },
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
    initError.value = error.message || 'Initialization failed'
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

async function prepareUI() {
  await new Promise(resolve => setTimeout(resolve, 100))
  const themeService = await serviceManager.getService('theme')
  if (themeService) { await themeService.applyTheme() }
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
  background: #0F172A;
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
  color: #F8FAFC;
  margin: 12px 0 0;
}
.loading-subtitle {
  font-family: Inter, sans-serif;
  font-size: 13px;
  color: #94A3B8;
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
  color: #94A3B8;
  margin: 0;
}
.loading-timer {
  font-size: 12px;
  color: #64748B;
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
  background: #0C1322;
}
.sider-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 18px 16px;
  border-bottom: 1px solid #1E293B;
}
.sider-brand.collapsed {
  justify-content: center;
  padding: 20px 0 16px;
}
.brand-text {
  font-family: Inter, sans-serif;
  font-size: 16px;
  font-weight: 700;
  color: #F8FAFC;
  letter-spacing: -0.02em;
}
.sider-footer {
  position: absolute;
  bottom: 12px;
  left: 12px;
  right: 12px;
  display: flex;
  justify-content: flex-end;
}
.sider-footer.collapsed {
  justify-content: center;
}
.main-content {
  padding: 24px;
  background: #0F172A;
  min-height: 100vh;
}
</style>

<style>
/* Global Naive UI menu overrides */
.n-menu .n-menu-item-content {
  margin: 2px 8px;
  border-radius: 8px;
}
.n-menu .n-menu-item-content--selected {
  background: rgba(34,197,94,0.12) !important;
}
.n-menu .n-menu-item-content:hover {
  background: rgba(255,255,255,0.04) !important;
}
/* Scrollbar */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #334155;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: #475569;
}
</style>
