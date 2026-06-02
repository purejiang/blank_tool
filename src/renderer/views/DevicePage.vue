<template>
  <div class="device-page">
    <!-- Page Header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('device.title') }}</h1>
        <p class="page-subtitle">{{ t('device.subtitle') }}</p>
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
            <n-icon size="48" color="#475569"><Smartphone /></n-icon>
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
            <n-tab-pane name="apps" :tab="t('device.appsTab')">
              <div class="tab-content">
                <!-- Filters -->
                <div class="filter-row">
                  <n-select
                    v-model:value="appType"
                    :options="appTypeOptions"
                    size="small"
                    :placeholder="t('appManager.appType')"
                    @update:value="refreshAppList"
                    style="width: 140px"
                  />
                  <n-input
                    v-model:value="appSearchQuery"
                    :placeholder="t('appManager.searchPlaceholder')"
                    size="small"
                    clearable
                  >
                    <template #prefix>
                      <n-icon size="14"><Search /></n-icon>
                    </template>
                  </n-input>
                  <n-button size="tiny" secondary @click="refreshAppList">
                    <template #icon><n-icon><RefreshCw /></n-icon></template>
                  </n-button>
                  <n-button
                    size="tiny"
                    secondary
                    :disabled="apps.length === 0"
                    @click="exportAppList"
                  >
                    <template #icon><n-icon><FileDown /></n-icon></template>
                  </n-button>
                </div>

                <!-- App List -->
                <n-spin :show="appsLoading">
                  <div v-if="apps.length === 0" class="empty-state small">
                    <n-icon size="24" color="#475569"><Inbox /></n-icon>
                    <p class="empty-title">{{ t('appManager.noApps') }}</p>
                    <p class="empty-desc">{{ t('appManager.noAppsDesc') }}</p>
                  </div>
                  <div v-else-if="filteredApps.length === 0" class="empty-state small">
                    <n-icon size="24" color="#475569"><Search /></n-icon>
                    <p class="empty-title">{{ t('appManager.noMatches') }}</p>
                    <p class="empty-desc">{{ t('appManager.noMatchesDesc') }}</p>
                  </div>
                  <n-scrollbar v-else style="max-height: 280px">
                    <n-list hoverable clickable class="app-list">
                      <n-list-item v-for="app in filteredApps" :key="app.packageName">
                        <template #prefix>
                          <n-icon size="16" color="#64748B"><Box /></n-icon>
                        </template>
                        <span class="app-package-name" :title="app.packageName">
                          {{ app.packageName }}
                        </span>
                        <template #suffix>
                          <n-space :size="4">
                            <n-button
                              size="tiny"
                              secondary
                              type="success"
                              :loading="isExportingPkg(app.packageName)"
                              @click="exportApp(app.packageName)"
                            >
                              <template #icon><n-icon><Download /></n-icon></template>
                            </n-button>
                            <n-button
                              size="tiny"
                              secondary
                              type="error"
                              @click="uninstallApp(app.packageName)"
                            >
                              <template #icon><n-icon><Trash2 /></n-icon></template>
                            </n-button>
                          </n-space>
                        </template>
                      </n-list-item>
                    </n-list>
                  </n-scrollbar>
                </n-spin>
              </div>
            </n-tab-pane>

            <!-- Tab 4: Logcat -->
            <n-tab-pane name="logcat" :tab="t('device.logcat')">
              <div class="tab-content">
                <div class="logcat-toolbar">
                  <n-space align="center" :size="8">
                    <n-tag v-if="isLogcatRunning" type="success" size="tiny" :bordered="false">
                      <template #icon><n-icon size="10"><Circle /></n-icon></template>
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
                  <n-icon size="32" color="#475569"><Terminal /></n-icon>
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
import { NIcon } from 'naive-ui'
import {
  Smartphone, RefreshCw, Activity, Link, Link2Off, Circle,
  Terminal, RotateCw, Wrench, Zap,
  Play, PauseCircle, Trash2, FileDown, Eye, Search, Inbox,
  Box, Download, Settings2
} from 'lucide-vue-next'
import { useDeviceStore } from '@stores/deviceStore'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { storeToRefs } from 'pinia'
import DeviceManager from '@components/DeviceManager.vue'

const { t } = useI18n()
const { showSuccess, showError, showLoading, completeLoading, failLoading } = useNotification()

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
  try {
    deviceSvcRef.value = await serviceManager.getService('device')
  } catch {}
})

onUnmounted(() => {
  if (isLogcatRunning.value) {
    serviceManager.getService('device').then(svc => svc.toggleLogcat()).catch(() => {})
  }
})

// --- Logcat ---
function getLogLevel(line: string): string {
  if (line.includes(' E/') || line.includes('ERROR')) return 'level-error'
  if (line.includes(' W/') || line.includes('WARN')) return 'level-warn'
  if (line.includes(' I/') || line.includes('INFO')) return 'level-info'
  if (line.includes(' D/') || line.includes('DEBUG')) return 'level-debug'
  return ''
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
const refreshAppList = async () => {
  appsLoading.value = true
  try {
    const svc = deviceSvcRef.value || await serviceManager.getService('device')
    deviceSvcRef.value = svc
    await svc.refreshAppList()
  } finally {
    appsLoading.value = false
  }
}

const exportAppList = async () => {
  const svc = deviceSvcRef.value || await serviceManager.getService('device')
  deviceSvcRef.value = svc
  await svc.exportAppList()
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
</script>

<style scoped>
.device-page {
  max-width: 1300px;
  margin: 0 auto;
}

/* Page Header */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.page-title {
  font-family: Inter, sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text-primary);
  margin: 0;
  letter-spacing: -0.02em;
}
.page-subtitle {
  font-size: 13px;
  color: var(--app-text-muted);
  margin: 4px 0 0;
}

/* Layout */
.page-content {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 16px;
  align-items: start;
}
.left-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.right-panel {
  min-height: 400px;
}

@media (max-width: 1100px) {
  .page-content {
    grid-template-columns: 1fr;
  }
}

/* Cards */
.card-title {
  font-family: Inter, sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
}

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
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-muted);
  margin: 8px 0 0;
}
.placeholder-desc {
  font-size: 13px;
  color: var(--app-text-dim);
  margin: 0;
  max-width: 280px;
}

/* Tab Panel Card */
.panel-card {
  background: var(--app-card-bg);
  border-radius: 10px;
  min-height: 400px;
}
.panel-tabs {
  margin: -8px 0 0;
}
.tab-content {
  padding-top: 4px;
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
  font-family: 'Fira Code', monospace;
  font-size: 12px;
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
  font-size: 11px;
  color: var(--app-text-muted);
  background: rgba(34,197,94,0.06);
  border-bottom: 1px solid var(--app-card-bg);
}
.shell-output-text {
  margin: 0;
  padding: 10px 12px;
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  color: var(--app-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 180px;
  overflow-y: auto;
}

/* Apps */
.filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.app-list {
  margin: -4px 0;
}
.app-package-name {
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  color: var(--app-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.app-list .n-list-item) {
  border-radius: 8px;
  margin: 2px 0;
}

/* Logcat tab */
.logcat-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}
.logcat-waiting { font-size: 12px; color: var(--app-text-dim); padding: 24px 0; text-align: center; }
.logcat-output-full {
  background: var(--app-code-bg);
  border-radius: 8px;
  padding: 10px 12px;
  max-height: 480px;
  overflow-y: auto;
  font-family: 'Fira Code', monospace;
  font-size: 11px;
  line-height: 1.5;
}
.logcat-line { display: flex; gap: 10px; white-space: pre-wrap; word-break: break-all; color: var(--app-text-secondary); }
.log-line-num { color: var(--app-text-dim); min-width: 36px; text-align: right; user-select: none; flex-shrink: 0; }
.level-error { color: var(--app-red); }
.level-warn { color: var(--app-yellow); }
.level-info { color: var(--app-blue); }
.level-debug { color: var(--app-text-dim); }

/* Empty States (small variant) */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 16px;
  color: var(--app-text-dim);
  font-size: 14px;
}
.empty-state p { margin: 0; }
.empty-state.small {
  padding: 20px 16px;
}
.empty-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-muted);
}
.empty-desc {
  font-size: 12px;
  color: var(--app-text-dim);
}
</style>
