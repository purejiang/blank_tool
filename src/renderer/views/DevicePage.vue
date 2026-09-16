<template>
  <div class="app-page">
    <!-- Page Header -->
    <div class="app-page-header">
      <div>
        <h1 class="app-page-title">{{ t('device.title') }}</h1>
        <p class="app-page-sub">{{ t('device.subtitle') }}</p>
      </div>
    </div>

    <div class="page-content">
      <!-- Left Panel: Device List -->
      <div class="left-panel">
        <DeviceManager @refresh-devices="refreshDevices" />
      </div>

      <!-- Right Panel: Context-aware Tabs -->
      <div class="right-panel">
        <!-- No device selected -->
        <n-card v-if="!selectedDevice" :bordered="false" class="placeholder-card" size="small">
          <div class="placeholder-state">
            <n-icon size="48" color="var(--app-text-muted)"><Smartphone /></n-icon>
            <p class="placeholder-title">{{ t('device.noDeviceSelected') }}</p>
            <p class="placeholder-desc">{{ t('device.noDeviceSelectedDesc') }}</p>
          </div>
        </n-card>

        <!-- Device selected: Tabbed info panel -->
        <n-card v-else :bordered="false" class="panel-card" size="small">
          <n-tabs type="line" animated :default-value="'info'" class="panel-tabs">
            <!-- Tab 1: Device Info + Logcat -->
            <n-tab-pane name="info" :tab="t('device.infoTab')">
              <div class="tab-content">
                <n-descriptions label-placement="left" :column="1" size="small" class="device-descriptions">
                  <n-descriptions-item :label="t('device.model')">
                    <span class="info-value highlight">{{ selectedDevice.name || '-' }}</span>
                  </n-descriptions-item>
                  <n-descriptions-item :label="t('device.serial')">
                    <span class="info-value mono">{{ selectedDevice.id }}</span>
                  </n-descriptions-item>
                  <n-descriptions-item :label="t('device.status')">
                    <n-tag :type="selectedDevice.status === 'device' ? 'success' : 'warning'" size="small" :bordered="false">
                      {{ selectedDevice.status }}
                    </n-tag>
                  </n-descriptions-item>
                  <n-descriptions-item :label="t('device.product')">
                    {{ deviceInfo.product || '-' }}
                  </n-descriptions-item>
                  <template v-if="deviceInfo.androidVersion || deviceInfo.apiLevel || deviceInfo.architecture">
                    <n-descriptions-item :label="t('device.android')">
                      {{ deviceInfo.androidVersion || '-' }}
                    </n-descriptions-item>
                    <n-descriptions-item :label="t('device.sdk')">
                      {{ deviceInfo.apiLevel || '-' }}
                    </n-descriptions-item>
                    <n-descriptions-item :label="t('device.cpu')">
                      {{ deviceInfo.architecture || '-' }}
                    </n-descriptions-item>
                  </template>
                </n-descriptions>

              </div>
            </n-tab-pane>

            <!-- Tab 2: Device Actions -->
            <n-tab-pane name="actions" :tab="t('device.actionsTab')">
              <div class="tab-content">
                <!-- Reboot Actions -->
                <div class="actions-section">
                  <n-tag :bordered="false" type="info" size="small" class="section-label">
                    {{ t('actions.reboot') }}
                  </n-tag>
                  <n-space :size="8">
                    <n-button size="small" secondary @click="rebootDevice('normal')">
                      <template #icon><n-icon><RotateCw /></n-icon></template>
                      {{ t('actions.system') }}
                    </n-button>
                    <n-button size="small" secondary type="warning" @click="rebootDevice('recovery')">
                      <template #icon><n-icon><Wrench /></n-icon></template>
                      {{ t('actions.recovery') }}
                    </n-button>
                    <n-button size="small" secondary type="error" @click="rebootDevice('bootloader')">
                      <template #icon><n-icon><Zap /></n-icon></template>
                      {{ t('actions.bootloader') }}
                    </n-button>
                  </n-space>
                </div>

                <n-divider style="margin: 14px 0" />

                <!-- Screenshot -->
                <div class="actions-section">
                  <n-tag :bordered="false" type="info" size="small" class="section-label">
                    {{ t('device.screenshot') }}
                  </n-tag>
                  <n-space :size="8">
                    <n-button size="small" secondary type="success" @click="takeScreenshot">
                      <template #icon><n-icon><Camera /></n-icon></template>
                      {{ t('device.screenshot') }}
                    </n-button>
                  </n-space>
                </div>

                <n-divider style="margin: 14px 0" />

                <!-- Shell Command -->
                <div class="actions-section">
                  <n-tag :bordered="false" type="info" size="small" class="section-label">
                    {{ t('actions.shell') }}
                  </n-tag>
                  <n-space :size="8" style="flex: 1">
                    <n-input
                      v-model:value="shellCommand"
                      :placeholder="t('actions.shellPlaceholder')"
                      size="small"
                      clearable
                      @keyup.enter="executeShellCommand"
                    />
                    <n-button
                      size="small"
                      type="success"
                      secondary
                      :disabled="!shellCommand.trim()"
                      @click="executeShellCommand"
                    >
                      <template #icon><n-icon><Play /></n-icon></template>
                      {{ t('actions.run') }}
                    </n-button>
                  </n-space>
                </div>

                <!-- Shell Output -->
                <div v-if="shellOutput" class="shell-output">
                  <div class="shell-output-header">
                    <n-icon size="14"><Terminal /></n-icon>
                    <span>{{ t('actions.output') }}</span>
                  </div>
                  <pre class="shell-output-text">{{ shellOutput }}</pre>
                </div>
              </div>
            </n-tab-pane>

            <!-- Tab 3: Apps -->
            <!-- 列表只在点「刷新」时才拉取：不做自动加载，也不回显上次的缓存
                 （deviceStore 已把 apps / appsLoaded 排除出持久化）。 -->
            <n-tab-pane name="apps" :tab="t('device.appsTab')">
              <div class="tab-content">
                <!-- Toolbar: type + search + actions
                     分成「可自由收缩的筛选组」+「不收缩的按钮组」并允许换行：
                     容器变窄时由筛选组让位，按钮组要么留在同一行右端、要么整体
                     掉到第二行，绝不会被挤出容器右缘裁掉。 -->
                <div class="apps-toolbar">
                  <div class="apps-filters">
                    <n-select
                      v-model:value="appType"
                      :options="appTypeOptions"
                      size="small"
                      :placeholder="t('appManager.appType')"
                      class="apps-type"
                    />
                    <n-input
                      v-model:value="appSearchQuery"
                      :placeholder="t('appManager.searchPlaceholder')"
                      size="small"
                      clearable
                      class="apps-search"
                    >
                      <template #prefix>
                        <n-icon size="14"><Search /></n-icon>
                      </template>
                    </n-input>
                  </div>
                  <div class="apps-buttons">
                    <n-button
                      class="apps-action"
                      size="small"
                      secondary
                      type="primary"
                      :loading="appsLoading"
                      @click="refreshAppList"
                    >
                      <template #icon><n-icon><RefreshCw /></n-icon></template>
                      {{ t('appManager.refresh') }}
                    </n-button>
                  </div>
                </div>

                <!-- Result counter -->
                <div v-if="appsLoaded" class="apps-meta">
                  <span>{{ t('appManager.totalApps', { count: apps.length }) }}</span>
                  <template v-if="appSearchQuery.trim()">
                    <span class="apps-meta-dot">·</span>
                    <span>{{ t('appManager.matchedApps', { count: filteredApps.length }) }}</span>
                  </template>
                </div>

                <!-- App List -->
                <n-spin :show="appsLoading">
                  <div v-if="!appsLoaded" class="empty-state small">
                    <n-icon size="28" color="var(--app-text-muted)"><PackageSearch /></n-icon>
                    <p class="empty-title">{{ t('appManager.notLoaded') }}</p>
                    <p class="empty-desc">{{ t('appManager.notLoadedDesc') }}</p>
                  </div>
                  <div v-else-if="apps.length === 0" class="empty-state small">
                    <n-icon size="28" color="var(--app-text-muted)"><Inbox /></n-icon>
                    <p class="empty-title">{{ t('appManager.noApps') }}</p>
                    <p class="empty-desc">{{ t('appManager.noAppsDesc') }}</p>
                  </div>
                  <div v-else-if="filteredApps.length === 0" class="empty-state small">
                    <n-icon size="28" color="var(--app-text-muted)"><Search /></n-icon>
                    <p class="empty-title">{{ t('appManager.noMatches') }}</p>
                    <p class="empty-desc">{{ t('appManager.noMatchesDesc') }}</p>
                  </div>
                  <!-- 虚拟滚动：几百个包名若整表渲染会阻塞主线程 ~1.5s -->
                  <n-virtual-list
                    v-else
                    class="app-vlist"
                    :items="filteredApps"
                    :item-size="38"
                    :item-resizable="true"
                    key-field="packageName"
                    :style="{ maxHeight: 'min(54vh, 400px)' }"
                  >
                    <template #default="{ item }">
                      <div class="app-row">
                        <n-icon size="16" class="app-row-icon"><Box /></n-icon>
                        <span class="app-package-name" :title="item.packageName">
                          {{ item.packageName }}
                        </span>
                        <div class="app-row-actions">
                          <IconButton
                            :icon="Play"
                            :label="t('device.launchApp')"
                            size="tiny"
                            secondary
                            type="info"
                            @click="launchApp(item.packageName)"
                          />
                          <IconButton
                            :icon="Download"
                            :label="t('appManager.export')"
                            :loading="isExportingPkg(item.packageName)"
                            size="tiny"
                            secondary
                            type="success"
                            @click="exportApp(item.packageName)"
                          />
                          <IconButton
                            :icon="Eraser"
                            :label="t('device.clearData')"
                            size="tiny"
                            secondary
                            type="warning"
                            @click="clearAppData(item.packageName)"
                          />
                          <IconButton
                            :icon="Trash2"
                            :label="t('device.uninstall')"
                            size="tiny"
                            secondary
                            type="error"
                            @click="uninstallApp(item.packageName)"
                          />
                        </div>
                      </div>
                    </template>
                  </n-virtual-list>
                </n-spin>
              </div>
            </n-tab-pane>

            <!-- Tab 4: Logcat -->
            <n-tab-pane name="logcat" :tab="t('device.logcat')">
              <div class="tab-content">
                <div class="logcat-toolbar">
                  <n-space align="center" :size="8">
                    <n-tag v-if="isLogcatRunning" type="success" size="tiny" :bordered="false">
                      <template #icon><n-icon size="12"><Circle /></n-icon></template>
                      {{ t('device.live') }}
                    </n-tag>
                    <n-button
                      :type="isLogcatRunning ? 'error' : 'success'"
                      size="small"
                      secondary
                      @click="toggleLogcat"
                    >
                      <template #icon><n-icon size="14"><Activity /></n-icon></template>
                      {{ isLogcatRunning ? t('device.stopLogcat') : t('device.startLogcat') }}
                    </n-button>
                    <n-button
                      size="small"
                      secondary
                      :disabled="logcatOutput.length === 0"
                      @click="clearLogcatOutput"
                    >
                      <template #icon><n-icon><Trash2 /></n-icon></template>
                      {{ t('device.clearLogcat') }}
                    </n-button>
                    <n-button
                      size="small"
                      secondary
                      :disabled="logcatOutput.length === 0"
                      @click="exportLogcatOutput"
                    >
                      <template #icon><n-icon><FileDown /></n-icon></template>
                      {{ t('device.exportLogcat') }}
                    </n-button>
                  </n-space>
                </div>

                <div v-if="!isLogcatRunning && logcatOutput.length === 0" class="empty-state small">
                  <n-icon size="32" color="var(--app-text-muted)"><Terminal /></n-icon>
                  <p class="empty-title">{{ t('device.logcatNotRunning') }}</p>
                  <p class="empty-desc">{{ t('device.logcatNotRunningHint') }}</p>
                </div>

                <div v-else-if="logcatOutput.length === 0 && isLogcatRunning" class="logcat-waiting">
                  {{ t('device.waitingForOutput') }}
                </div>

                <div v-else class="logcat-output-full" ref="logcatContainer">
                  <div v-for="(line, i) in logcatOutput" :key="i" class="logcat-line" :class="getLogLevel(line)">
                    <span class="log-line-num">{{ i + 1 }}</span>
                    <span>{{ line }}</span>
                  </div>
                </div>
              </div>
            </n-tab-pane>
          </n-tabs>
        </n-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon, useDialog } from 'naive-ui'
import {
  Smartphone, RefreshCw, Activity, Link, Link2Off, Circle,
  Terminal, RotateCw, Wrench, Zap,
  Play, PauseCircle, Trash2, FileDown, Eye, Search, Inbox,
  Box, Download, Settings2, Eraser, Camera, PackageSearch
} from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { storeToRefs } from 'pinia'
import { log } from '@utils/logger'
import DeviceManager from '@components/DeviceManager.vue'
import IconButton from '@components/common/IconButton.vue'

const { t } = useI18n()
const { showSuccess, showError, showLoading, completeLoading, failLoading } = useNotification()
const dialog = useDialog()

const deviceStore = useDeviceStore()
const {
  devices,
  selectedDeviceId,
  selectedDevice,
  deviceInfo,
  isLogcatRunning,
  connectionStatus,
  logcatOutput,
  apps,
  appsLoaded,
  appType,
  shellOutput
} = storeToRefs(deviceStore)

// --- Page-level state ---
const loading = ref(false)
const logcatContainer = ref<HTMLElement | null>(null)

// --- Actions tab state ---
const shellCommand = ref('')

// --- Apps tab state ---
const appSearchQuery = ref('')
const appsLoading = ref(false)
const deviceSvcRef = ref<any>(null)
const exportingPackages = ref(new Set<string>())

// 改了应用类型，现有列表就不再对应这个筛选了：作废并回到「未加载」空态，
// 由用户点「获取」重新拉。这里刻意不自动拉取。
watch(appType, () => {
  apps.value = []
  appsLoaded.value = false
})

const appTypeOptions = computed(() => [
  { label: t('appManager.allApps'), value: 'all' },
  { label: t('appManager.systemApps'), value: 'system' },
  { label: t('appManager.userApps'), value: 'user' },
  { label: t('appManager.enabled'), value: 'enabled' },
  { label: t('appManager.disabled'), value: 'disabled' },
])

const filteredApps = computed(() => {
  const q = String(appSearchQuery.value || '').trim().toLowerCase()
  if (!q) return apps.value
  return apps.value.filter(a => String(a.packageName || '').toLowerCase().includes(q))
})

const isExportingPkg = (packageName: string) => exportingPackages.value.has(packageName)

// --- Auto-scroll logcat ---
watch(() => logcatOutput.value.length, () => {
  nextTick(() => {
    if (logcatContainer.value) {
      const threshold = 100
      const isNearBottom = logcatContainer.value.scrollHeight - logcatContainer.value.scrollTop - logcatContainer.value.clientHeight < threshold
      if (isNearBottom || logcatOutput.value.length < 100) {
        logcatContainer.value.scrollTop = logcatContainer.value.scrollHeight
      }
    }
  })
})

onMounted(async () => {
  log.debug('设备管理页面已挂载')
  try {
    const svc = await serviceManager.getService('device')
    deviceSvcRef.value = svc
    // The list itself is polled globally (useAppBootstrap starts the
    // monitor at app startup, refresh only). This page additionally asks
    // for the selected device's info refresh, which is dumpsys-heavy and
    // only needed while the details panel is visible.
    await svc.refreshDevices()
    void svc.startMonitoring(5000, true)
  } catch {}
})

onUnmounted(() => {
  if (isLogcatRunning.value) {
    serviceManager.getService('device').then(svc => svc.toggleLogcat()).catch(() => {})
  }
  // NOTE: do NOT stopMonitoring here — the monitor is global now and keeps
  // device lists fresh on every page.
})

// --- Logcat ---
// Level detection for the two formats adb actually emits:
//  - threadtime (our startLogcat uses -v threadtime): "... PID TID E Tag: msg"
//    → the level is a single letter surrounded by spaces right before "TAG:"
//  - brief (plain logcat / old exports): "E/Tag(pid): msg" → level letter before '/'
// The old code only looked for " E/" which never matches threadtime lines,
// so almost every line rendered with the default color.
const THREADTIME_LEVEL_RE = /\s([VDIWEF])\s[A-Za-z0-9_.$-]+:/
const BRIEF_LEVEL_RE = /(?:^|\s)([VDIWEF])\//

function getLogLevel(line: string): string {
  const m = THREADTIME_LEVEL_RE.exec(line) || BRIEF_LEVEL_RE.exec(line)
  if (!m) return ''
  switch (m[1]) {
    case 'E':
    case 'F': return 'level-error'
    case 'W': return 'level-warn'
    case 'I': return 'level-info'
    case 'D': return 'level-debug'
    case 'V': return 'level-verbose'
    default: return ''
  }
}

const refreshDevices = async () => {
  loading.value = true
  try {
    const svc = deviceSvcRef.value || await serviceManager.getService('device')
    deviceSvcRef.value = svc
    await svc.refreshDevices()
  } finally {
    loading.value = false
  }
}

const toggleLogcat = async () => {
  const svc = deviceSvcRef.value || await serviceManager.getService('device')
  deviceSvcRef.value = svc
  try {
    const ok = await svc.toggleLogcat()
    if (!ok) showError(t('device.logcatFailed'), t('device.logcatStartError'))
  } catch (e: any) {
    showError(t('device.logcatFailed'), e.message || t('device.logcatStartError'))
  }
}

const clearLogcatOutput = async () => {
  const svc = deviceSvcRef.value || await serviceManager.getService('device')
  deviceSvcRef.value = svc
  await svc.clearLogcat()
}

const exportLogcatOutput = async () => {
  const svc = deviceSvcRef.value || await serviceManager.getService('device')
  deviceSvcRef.value = svc
  await svc.exportLogcat()
}

// --- Device Actions ---
const rebootDevice = async (mode: string) => {
  const loadingId = showLoading(t('actions.rebooting'), t('actions.rebootingTo', { mode }))
  try {
    const svc = deviceSvcRef.value || await serviceManager.getService('device')
    deviceSvcRef.value = svc
    await svc.rebootDevice(mode)
    completeLoading(loadingId, t('actions.rebootSent'), t('actions.rebootDesc', { mode }))
  } catch (error: any) {
    failLoading(loadingId, t('actions.rebootFailed'), error.message || t('actions.unknownError'))
  }
}

const executeShellCommand = async () => {
  if (!shellCommand.value.trim()) return
  const loadingId = showLoading(t('actions.executing'), t('actions.executingCmd', { cmd: shellCommand.value }))
  try {
    const svc = deviceSvcRef.value || await serviceManager.getService('device')
    deviceSvcRef.value = svc
    await svc.executeShell(shellCommand.value)
    shellCommand.value = ''
    completeLoading(loadingId, t('actions.executionComplete'), t('actions.executionSuccess'))
  } catch (error: any) {
    failLoading(loadingId, t('actions.executionFailed'), error.message || t('actions.unknownError'))
  }
}

// --- App Manager ---
// 「刷新」是唯一入口：首次加载和重新拉取都走它，所以不做未加载即禁用的处理。
// 不自动拉取（切页签、切设备、改类型都不会触发），避免几百个包名一次性渲染卡住界面。
const refreshAppList = async () => {
  if (appsLoading.value) return
  appsLoading.value = true
  try {
    const svc = deviceSvcRef.value || await serviceManager.getService('device')
    deviceSvcRef.value = svc
    await svc.refreshAppList()
  } finally {
    appsLoading.value = false
  }
}

const exportApp = async (packageName: string) => {
  if (exportingPackages.value.has(packageName)) return
  exportingPackages.value.add(packageName)
  try {
    const svc = deviceSvcRef.value || await serviceManager.getService('device')
    deviceSvcRef.value = svc
    await svc.exportApp(packageName)
  } finally {
    exportingPackages.value.delete(packageName)
  }
}

const uninstallApp = async (packageName: string) => {
  const svc = deviceSvcRef.value || await serviceManager.getService('device')
  deviceSvcRef.value = svc
  await svc.uninstallApp(packageName)
}

const launchApp = async (packageName: string) => {
  const svc = deviceSvcRef.value || await serviceManager.getService('device')
  deviceSvcRef.value = svc
  try {
    await svc.launchApp(packageName)
    showSuccess(t('device.launchApp'), packageName)
  } catch (error: any) {
    showError(t('device.launchApp'), error.message || t('actions.unknownError'))
  }
}

const clearAppData = (packageName: string) => {
  dialog.warning({
    title: t('device.clearData'),
    content: t('device.clearDataConfirm', { pkg: packageName }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      const svc = deviceSvcRef.value || await serviceManager.getService('device')
      deviceSvcRef.value = svc
      try {
        await svc.clearAppData(packageName)
        showSuccess(t('device.clearData'), packageName)
      } catch (error: any) {
        showError(t('device.clearData'), error.message || t('actions.unknownError'))
      }
    },
  })
}

const takeScreenshot = async () => {
  const svc = deviceSvcRef.value || await serviceManager.getService('device')
  deviceSvcRef.value = svc
  const loadingId = showLoading(t('device.screenshot'), t('device.screenshotting'))
  try {
    const savedPath = await svc.screenshotDevice()
    if (savedPath) {
      completeLoading(loadingId, t('device.screenshotSuccess'), savedPath)
    } else {
      // User canceled the save dialog — close the loading toast quietly.
      completeLoading(loadingId, t('device.screenshot'), t('device.screenshotCancelled'))
    }
  } catch (error: any) {
    failLoading(loadingId, t('device.screenshotFailed'), error.message || t('actions.unknownError'))
  }
}
</script>

<style scoped>
/* Layout */
.page-content {
  display: grid;
  /* 第二列写 minmax(0, 1fr) 而不是 1fr：1fr 的最小值是 auto，列内任何
     有最小宽度的内容（工具栏那一行就是）都能把整列撑破页面右缘。 */
  grid-template-columns: 380px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.left-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.right-panel {
  min-height: 400px;
  min-width: 0;
}

@media (max-width: 1100px) {
  .page-content {
    grid-template-columns: 1fr;
  }
}

/* Cards */
/* Placeholder */
.placeholder-card {
  background: var(--app-card-bg);
  border-radius: 10px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.placeholder-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 64px 16px;
  color: var(--app-text-dim);
  text-align: center;
}
.placeholder-title {
  font-size: var(--app-font-size-xl);
  font-weight: 600;
  color: var(--app-text-muted);
  margin: 8px 0 0;
}
.placeholder-desc {
  font-size: var(--app-font-size-md);
  color: var(--app-text-dim);
  margin: 0;
  max-width: 280px;
}

/* Tab Panel Card */
.panel-card {
  background: var(--app-card-bg);
  border-radius: 10px;
  min-height: 400px;
  min-width: 0;
}
.panel-tabs {
  margin: -8px 0 0;
  min-width: 0;
}
.tab-content {
  padding-top: 4px;
  min-width: 0;
}

/* Device Info */
.device-descriptions {
  margin: -4px 0;
}
.info-value {
  color: var(--app-text-secondary);
}
.info-value.highlight {
  font-weight: 600;
  color: var(--app-text-primary);
}
.info-value.mono {
  font-family: var(--app-font-mono);
  font-size: var(--app-font-size-sm);
  color: var(--app-blue);
}

/* Actions */
.actions-section {
  display: flex;
  align-items: center;
  gap: 12px;
}
.section-label {
  flex-shrink: 0;
  min-width: 56px;
  text-align: center;
}
.shell-output {
  margin-top: 12px;
  background: var(--app-code-bg);
  border-radius: 8px;
  overflow: hidden;
}
.shell-output-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: var(--app-font-size-xs);
  color: var(--app-text-muted);
  background: var(--app-green-bg-hover);
  border-bottom: 1px solid var(--app-card-bg);
}
.shell-output-text {
  margin: 0;
  padding: 10px 12px;
  font-family: var(--app-font-mono);
  font-size: var(--app-font-size-sm);
  color: var(--app-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 180px;
  overflow-y: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
}

/* Apps */
.apps-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  min-width: 0;
}
/* 筛选组：吸收所有收缩量（min-width:0 让它能一直退到 0）。
   基准 320 而非 auto：小于 320+8+按钮宽 时整组独占一行、按钮换行，
   不会把搜索框压成一条缝。 */
.apps-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 320px;
  min-width: 0;
}
/* 类型选择固定宽（shrink 0），「全部应用」标签永远不会被压掉 */
.apps-type {
  flex: 0 0 132px;
}
/* 搜索框独自承担收缩，基准给小值以免组内提前触发收缩 */
.apps-search {
  flex: 1 1 140px;
  min-width: 0;
}
/* 按钮组：不收缩，靠 margin-left:auto 贴右；放不下时整组换到下一行 */
.apps-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  margin-left: auto;
}
.apps-action {
  flex: none;
}
.apps-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: -2px 0 8px;
  font-size: var(--app-font-size-sm);
  color: var(--app-text-dim);
}
.apps-meta-dot {
  color: var(--app-text-muted);
}

/* 虚拟列表：行高必须与 item-size(=38) 一致，否则滚动位置会漂。
   （旧版是 n-list + n-list-item__suffix，naive-ui 给后缀设了 flex:0，
   里面的 n-space 默认 wrap 会把 4 个按钮竖排成 4 行、每行 134px。） */
.app-vlist {
  overflow-x: hidden;
}
.app-row {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 38px;
  padding: 0 8px;
  border-radius: 8px;
  transition: background-color 0.16s ease;
}
.app-row:hover {
  background: var(--app-hover);
}
.app-row-icon {
  flex: none;
  color: var(--app-text-dim);
}
.app-package-name {
  flex: 1 1 auto;
  min-width: 0;
  font-family: var(--app-font-mono);
  font-size: var(--app-font-size-sm);
  line-height: 1.4;
  color: var(--app-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-row-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Logcat tab */
.logcat-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}
.logcat-waiting { font-size: var(--app-font-size-sm); color: var(--app-text-dim); padding: 24px 0; text-align: center; }
.logcat-output-full {
  background: var(--app-code-bg);
  border-radius: 8px;
  padding: 10px 12px;
  max-height: 480px;
  overflow-y: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
  font-family: var(--app-font-mono);
  font-size: var(--app-font-size-xs);
  line-height: 1.5;
}
.logcat-line { display: flex; gap: 10px; white-space: pre-wrap; word-break: break-all; color: var(--app-text-secondary); padding: 0 6px; border-radius: 3px; }
.log-line-num { color: var(--app-text-dim); min-width: 36px; text-align: right; user-select: none; flex-shrink: 0; }
.level-error { color: var(--app-red); background: color-mix(in srgb, var(--app-red) 10%, transparent); }
.level-error .log-line-num { color: var(--app-red); opacity: 0.7; }
.level-warn { color: var(--app-yellow); background: color-mix(in srgb, var(--app-yellow) 8%, transparent); }
.level-info { color: var(--app-blue); }
.level-debug { color: var(--app-text-dim); }
.level-verbose { color: var(--app-text-dim); opacity: 0.65; }

/* Empty States (small variant) */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 16px;
  color: var(--app-text-dim);
  font-size: var(--app-font-size-lg);
}
.empty-state p { margin: 0; }
.empty-state.small {
  padding: 20px 16px;
}
.empty-title {
  font-size: var(--app-font-size-md);
  font-weight: 600;
  color: var(--app-text-muted);
}
.empty-desc {
  font-size: var(--app-font-size-sm);
  color: var(--app-text-dim);
}
</style>
