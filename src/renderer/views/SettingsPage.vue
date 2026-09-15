<template>
  <div class="app-page">
    <div class="app-page-header">
      <div>
        <h1 class="app-page-title">{{ t('settings.title') }}</h1>
        <p class="app-page-sub">{{ t('settings.subtitle') }}</p>
      </div>
      <n-tag v-if="showSaved" type="success" size="small" :bordered="false" class="saved-tag">
        <template #icon><n-icon><CheckCircle /></n-icon></template>
        {{ t('settings.savedIndicator') }}
      </n-tag>
    </div>

    <div class="settings-body">
      <!-- 左侧导航：组级切换，组内所有设置卡一起展示 -->
      <aside class="settings-nav">
        <div
          v-for="item in navItems"
          :key="item.key"
          class="app-nav-item"
          :class="{ active: activePanel === item.key }"
          @click="activePanel = item.key"
        >
          <n-icon size="15"><component :is="item.icon" /></n-icon>
          <span>{{ item.label }}</span>
        </div>
      </aside>

      <div class="settings-panel">
      <div class="panel-title">{{ panelTitle }}</div>
      <!-- Appearance -->
      <section v-show="activePanel === 'general'">
      <div class="panel-sec">
        <n-icon size="14"><Monitor /></n-icon>
        <span>{{ t('settings.appearance') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">
      <div class="set-rows">
          <div class="set-row">
            <div class="set-info">
              <div class="set-label">{{ t('settings.language') }}</div>
              <div class="set-desc">{{ t('settings.languageDesc') }}</div>
            </div>
            <n-select v-model:value="general.language" @update:value="saveGeneral"
              :options="langOptions" class="set-control set-w200" />
          </div>
          <div class="set-row">
            <div class="set-info">
              <div class="set-label">{{ t('settings.theme') }}</div>
              <div class="set-desc">{{ t('settings.themeDesc') }}</div>
            </div>
            <n-select v-model:value="general.theme" @update:value="saveGeneral"
              :options="themeOptions" class="set-control set-w200" />
          </div>
        </div>
      </n-card>
      </section>

      <!-- Behavior -->
      <section v-show="activePanel === 'general'">
      <div class="panel-sec">
        <n-icon size="14"><Settings2 /></n-icon>
        <span>{{ t('settings.behavior') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">
      <div class="set-rows">
          <div class="set-row">
            <div class="set-info">
              <div class="set-label">{{ t('settings.notifications') }}</div>
              <div class="set-desc">{{ t('settings.notificationsDesc') }}</div>
            </div>
            <n-switch v-model:value="general.enableNotifications" @update:value="saveGeneral" />
          </div>
          <div class="set-row">
            <div class="set-info">
              <div class="set-label">{{ t('settings.autoDeleteOutput') }}</div>
              <div class="set-desc">{{ t('settings.autoDeleteOutputDesc') }}</div>
            </div>
            <n-switch v-model:value="general.autoDeleteOutputOnTaskRemove" @update:value="saveGeneral" />
          </div>
          <div class="set-row">
            <div class="set-info">
              <div class="set-label">{{ t('settings.useProxyForDownload') }}</div>
              <div class="set-desc">{{ t('settings.useProxyForDownloadDesc') }}</div>
            </div>
            <n-switch v-model:value="general.useProxyForDownload" @update:value="saveGeneral" />
          </div>
          <div class="set-row">
            <div class="set-info">
              <div class="set-label">{{ t('settings.timeout') }}</div>
              <div class="set-desc">{{ t('settings.timeoutDesc') }}</div>
            </div>
            <n-input-number v-model:value="general.timeout" :min="10" :max="600" :step="10" @update:value="saveGeneral" class="set-control set-w140">
              <template #suffix>{{ t('settings.seconds') }}</template>
            </n-input-number>
          </div>
          <div class="set-row">
            <div class="set-info">
              <div class="set-label">{{ t('settings.maxConcurrentTasks') }}</div>
              <div class="set-desc">{{ t('settings.maxConcurrentTasksDesc') }}</div>
            </div>
            <n-input-number v-model:value="general.maxConcurrentTasks" :min="1" :max="16" :step="1" @update:value="saveGeneral" class="set-control set-w140">
              <template #suffix>{{ t('settings.tasksUnit') }}</template>
            </n-input-number>
          </div>
        </div>
      </n-card>
      </section>

      <!-- Logging -->
      <section v-show="activePanel === 'general'">
      <div class="panel-sec">
        <n-icon size="14"><FileText /></n-icon>
        <span>{{ t('settings.logging') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">
      <div class="set-rows">
          <div class="set-row">
            <div class="set-info">
              <div class="set-label">{{ t('settings.loggingLevel') }}</div>
              <div class="set-desc">{{ t('settings.loggingLevelDesc') }}</div>
            </div>
            <n-select v-model:value="logLevel" @update:value="saveLogLevel"
              :options="logLevelOptions" class="set-control set-w200" />
          </div>
        </div>
      </n-card>
      </section>

      <!-- Local runtimes: Java / Python / Node (version + path, path editable) -->
      <section v-show="activePanel === 'runtime'">
      <div class="panel-sec">
        <n-icon size="14"><Cpu /></n-icon>
        <span>{{ t('settings.localRuntimes') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">
        <div class="runtime-list">
          <div v-for="row in runtimeRows" :key="row.key" class="runtime-row">
            <div class="runtime-info">
              <div class="runtime-label">
                {{ row.label }}
                <span class="runtime-version" :class="{ 'is-missing': !row.version }">
                  {{ row.version || t('settings.runtimeUnknown') }}
                </span>
              </div>
              <div class="runtime-path" :title="row.path">{{ row.path || t('settings.runtimeUnknown') }}</div>
              <!-- Node has no consumer in the backend today — say so instead of
                   implying an override would change anything. -->
              <div v-if="row.hint" class="runtime-hint">{{ row.hint }}</div>
            </div>
            <n-button size="tiny" @click="handleBrowseRuntime(row)">
              <template #icon><n-icon><FolderOpen /></n-icon></template>
              {{ t('settings.browse') }}
            </n-button>
            <n-button
              v-if="row.overridden"
              size="tiny"
              quaternary
              type="warning"
              @click="handleResetRuntime(row)"
            >
              {{ t('settings.runtimeReset') }}
            </n-button>
          </div>
        </div>
      </n-card>
      </section>

      <!-- Local service (the spawned Python backend) -->
      <section v-show="activePanel === 'runtime'">
      <div class="panel-sec">
        <n-icon size="14"><Server /></n-icon>
        <span>{{ t('settings.localService') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">
        <div class="svc-row">
          <span class="svc-label">{{ t('settings.serviceVersion') }}</span>
          <span class="svc-value">{{ serviceVersion || t('settings.runtimeUnknown') }}</span>
        </div>
        <div class="svc-row">
          <span class="svc-label">{{ t('settings.serviceStatus') }}</span>
          <span class="svc-value">
            <n-icon size="14" :style="{ color: serviceHealthy ? 'var(--app-green)' : 'var(--app-yellow)' }" class="svc-dot">
              <CheckCircle v-if="serviceHealthy" /><AlertCircle v-else />
            </n-icon>
            {{ serviceStatusText }}
          </span>
        </div>
        <div class="svc-row">
          <span class="svc-label">{{ t('settings.serviceDir') }}</span>
          <div class="svc-path-wrap">
            <n-input :value="displayPaths.server" readonly size="small" style="width: 320px" placeholder=".\backend" />
            <n-button size="small" @click="handleBrowseDirectory('server')">
              <template #icon><n-icon><FolderOpen /></n-icon></template>
              {{ t('settings.browse') }}
            </n-button>
          </div>
        </div>
      </n-card>
      </section>

      <!-- Tools & dependencies: built-in tools + automation components -->
      <section v-show="activePanel === 'runtime'">
      <div class="panel-sec">
        <n-icon size="14"><Wrench /></n-icon>
        <span>{{ t('settings.dependencies') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">

        <div class="dep-sub-head">{{ t('settings.builtinTools') }}</div>
        <div class="tool-path-list">
          <div v-for="tool in toolList" :key="tool.name" class="tool-path-row">
            <span class="tool-path-name">
              {{ tool.name }}
              <!-- version comes from the tool check (tool.version); the About
                   page used to be the only place it was shown -->
              <span class="tool-version" :class="{ 'is-missing': !tool.version }">
                {{ tool.version || t('common.unknown') }}
              </span>
            </span>
            <div class="tool-path-input-wrap">
              <n-input
                size="small"
                :value="toolPaths[tool.name] || tool.defaultPath"
                readonly
                :placeholder="tool.defaultPath || ''"
                style="width: 320px"
              />
              <n-button size="small" @click="handleBrowseToolPath(tool.name)">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                {{ t('settings.browse') }}
              </n-button>
            </div>
            <n-button
              v-if="customPathOverrides[tool.name]"
              size="tiny"
              quaternary
              type="warning"
              @click="handleResetToolPath(tool.name)"
              :loading="resettingTool === tool.name"
            >
              {{ t('settings.reset') }}
            </n-button>
            <n-icon v-if="validatingTool === tool.name" size="16"><Loader2 class="spin" /></n-icon>
            <n-icon v-else-if="tool.status === 'available'" size="16" color="var(--app-green)"><CheckCircle /></n-icon>
            <n-icon v-else size="16" color="var(--app-yellow)"><AlertCircle /></n-icon>
          </div>
        </div>

        <!-- Automation components: tools the automation feature reaches for
             (mitmproxy on the PC, ADBKeyBoard on the device) -->
        <div class="dep-sub-head dep-sub-head-with-action">
          {{ t('settings.automationComponents') }}
          <n-button size="tiny" quaternary @click="refreshCapabilities" :loading="isLoadingCapabilities">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
          </n-button>
        </div>

        <!-- Traffic capture (PC side: mitmproxy) -->
        <div class="cap-row">
          <div class="cap-status-icon" :style="{ color: trafficReady ? 'var(--app-green)' : 'var(--app-yellow)' }">
            <n-icon size="16"><CheckCircle v-if="trafficReady" /><AlertCircle v-else /></n-icon>
          </div>
          <div class="cap-info">
            <div class="cap-label">{{ t('settings.trafficCaptureRow') }}</div>
            <div class="cap-sub">{{ trafficStateText }}</div>
            <div class="cap-sub cap-mono" v-if="trafficStatus?.lib_path">{{ trafficStatus.lib_path }}</div>
            <div class="cap-hint" v-if="trafficStatus && !trafficStatus.ready">{{ trafficHintText }}</div>
          </div>
        </div>

        <!-- Chinese input (device side: ADBKeyBoard) -->
        <div class="cap-row">
          <div class="cap-status-icon" :style="{ color: imeAllReady ? 'var(--app-green)' : 'var(--app-yellow)' }">
            <n-icon size="16"><CheckCircle v-if="imeAllReady" /><AlertCircle v-else /></n-icon>
          </div>
          <div class="cap-info">
            <div class="cap-label">{{ t('settings.imeRow') }}</div>
            <template v-if="!deviceStore.sortedDevices.length">
              <div class="cap-sub">{{ t('settings.imeNoDevice') }}</div>
            </template>
            <template v-else>
              <div v-for="st in imeStatuses" :key="st.device_id" class="cap-sub">
                <n-icon size="12" :style="{ color: st.installed ? 'var(--app-green)' : 'var(--app-yellow)' }">
                  <CheckCircle v-if="st.installed" /><AlertCircle v-else />
                </n-icon>
                {{ st.device_id }} · {{ st.installed ? t('settings.imeInstalled') : t('settings.imeNotInstalled') }}
                <span v-if="st.active"> · {{ t('settings.imeActive') }}</span>
              </div>
              <div class="cap-hint" v-if="imeStatuses.some(s => !s.installed)">{{ t('settings.imeInstallHint') }}</div>
            </template>
          </div>
        </div>
      </n-card>
      </section>

      <!-- Signature Configs -->
      <section v-show="activePanel === 'general'">
      <div class="panel-sec">
        <n-icon size="14"><Key /></n-icon>
        <span>{{ t('signature.title') }}</span>
        <n-button size="tiny" type="primary" secondary class="panel-sec-action" @click="openAddSignature">
          <template #icon><n-icon size="14"><Plus /></n-icon></template>
        </n-button>
      </div>
      <n-card :bordered="false" class="settings-card">
        <div v-if="sigConfigs.length === 0" class="info-empty">{{ t('signature.empty') }}</div>
        <div v-else class="sig-list">
          <div v-for="cfg in sigConfigs" :key="cfg.id" class="sig-item">
            <div class="sig-info">
              <span class="sig-name">{{ cfg.name }}</span>
              <span class="sig-detail">{{ cfg.alias }}</span>
              <span class="sig-path" :title="String(cfg.path ?? '')">{{ cfg.path }}</span>
            </div>
            <n-space :size="4">
              <n-button size="tiny" quaternary @click="openEditSignature(cfg)">
                <template #icon><n-icon size="14"><Edit /></n-icon></template>
              </n-button>
              <n-button size="tiny" quaternary type="error" @click="deleteSignature(cfg.id)">
                <template #icon><n-icon size="14"><Trash2 /></n-icon></template>
              </n-button>
            </n-space>
          </div>
        </div>
      </n-card>
      </section>

      <!-- Storage -->
      <section v-show="activePanel === 'runtime'">
      <div class="panel-sec">
        <n-icon size="14"><HardDrive /></n-icon>
        <span>{{ t('settings.storage') }}</span>
        <span class="storage-total-text">{{ formatBytes(cacheInfo.total.size) }}</span>
        <div class="hdr-actions">
          <n-button
            size="tiny"
            quaternary
            type="error"
            :title="t('settings.clearAllStorage')"
            :loading="clearingTarget === 'all'"
            :disabled="cacheInfo.total.size === 0"
            @click="confirmClear('all')"
          >
            <template #icon><n-icon><Trash2 /></n-icon></template>
          </n-button>
          <n-button size="tiny" quaternary @click="refreshCache" :loading="isLoadingCacheInfo">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
          </n-button>
        </div>
      </div>
      <n-card :bordered="false" class="settings-card">

        <!-- Proportional bar -->
        <div class="storage-bar" v-if="cacheInfo.total.size > 0">
          <div
            v-for="cat in storageCategories"
            :key="cat.key"
            class="storage-bar-seg"
            :style="{ width: barWidth(cat.key), background: cat.color }"
            :title="t(cat.label) + ' ' + formatBytes(getCatSize(cat.key))"
          />
        </div>

        <!-- Category rows -->
        <div class="storage-rows">
          <div v-for="cat in storageCategories" :key="cat.key" class="storage-row">
            <div class="storage-row-icon" :style="{ color: cat.color }">
              <n-icon size="16"><component :is="cat.icon" /></n-icon>
            </div>
            <div class="storage-row-info">
              <div class="storage-row-label">{{ t(cat.label) }}</div>
              <div class="storage-row-sub">{{ formatBytes(getCatSize(cat.key)) }} · {{ getCatFiles(cat.key) }} {{ t('settings.filesUnit') }}</div>
            </div>
            <n-button
              size="tiny"
              quaternary
              type="error"
              :loading="clearingTarget === cat.key"
              :disabled="getCatSize(cat.key) === 0"
              @click="confirmClear(cat.key)"
            >
              <template #icon><n-icon size="13"><Trash2 /></n-icon></template>
            </n-button>
          </div>
        </div>
      </n-card>
      </section>

      <!-- About（原独立关于页并入） -->
      <section v-show="activePanel === 'about'">
      <div class="panel-sec">
        <n-icon size="14"><Layers /></n-icon>
        <span>{{ t('settings.buildInfo') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">
        <div class="info-grid">
          <div class="info-row">
            <span class="info-label">{{ t('settings.appVersion') }}</span>
            <span class="info-val">{{ buildInfo.appVersion || t('common.unknown') }}</span>
            <n-button
              size="tiny"
              :disabled="updateButtonDisabled"
              :loading="updateStore.status === 'checking'"
              @click="checkForUpdate"
            >
              {{ updateButtonText }}
            </n-button>
            <span v-if="updateStatusText" class="update-status-inline">{{ updateStatusText }}</span>
          </div>
          <div class="info-row"><span class="info-label">{{ t('settings.electron') }}</span><span class="info-val">{{ buildInfo.electronVersion || t('common.unknown') }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.nodeJs') }}</span><span class="info-val">{{ buildInfo.nodeVersion || t('common.unknown') }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.python') }}</span><span class="info-val">{{ buildInfo.pythonVersion || t('common.unknown') }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.chrome') }}</span><span class="info-val">{{ buildInfo.chromeVersion || t('common.unknown') }}</span></div>
        </div>
      </n-card>

      <div class="panel-sec">
        <n-icon size="14"><Cpu /></n-icon>
        <span>{{ t('settings.systemInfo') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">
        <div class="info-grid">
          <div class="info-row"><span class="info-label">{{ t('settings.os') }}</span><span class="info-val">{{ systemInfo.platform || t('common.unknown') }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.architecture') }}</span><span class="info-val">{{ systemInfo.architecture || t('common.unknown') }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.hostname') }}</span><span class="info-val">{{ systemInfo.hostname || t('common.unknown') }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.cpu') }}</span><span class="info-val">{{ cpuText }}</span></div>
        </div>
      </n-card>
      </section>

      </div>
    </div>

    <SignatureEditModal :visible="sigModalVisible" :data="sigEditing" @update:visible="(v: boolean) => sigModalVisible = v" @save="handleSignatureSave" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, inject, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon, NButton, useDialog } from 'naive-ui'
import { FolderOpen, Trash2, RefreshCw, Cpu, Monitor, Layers, Settings2, HardDrive, CheckCircle, Wrench, Key, Plus, Edit, Loader2, AlertCircle, Archive, FileText, FolderArchive, History, Server, Palette, Info } from 'lucide-vue-next'
import serviceManager from '@services/ServiceManager'
import { log, setLogLevel } from '@utils/logger'
import { formatBytes } from '@utils/format'
import { useNotification } from '@composables/useNotification'
import { useSystemStore, useToolStore, useUpdateStore } from '@stores/index'
import { useDeviceStore } from '@stores/deviceStore'
import { useBackendHealthStore } from '@stores/backendHealthStore'
import { storeToRefs } from 'pinia'
import { useSignatureStore } from '@stores/signatureStore'
import SignatureEditModal from '@components/package/SignatureEditModal.vue'
import { setMaxConcurrent } from '@services/TaskExecutionService'
import type { TrafficStatus, ImeStatus } from '@services/AutomationService'
import type UpdateService from '@services/UpdateService'

const { t } = useI18n()
const { showSuccess, showError, showWarning } = useNotification()
const dialog = useDialog()
const setLocale = inject<(lang: string) => void>('setLocale', () => {})
const setTheme = inject<(mode: string) => Promise<void>>('setTheme', async () => {})
const systemStore = useSystemStore()
const toolStore = useToolStore()
const tools = toolStore.tools
const sigStore = useSignatureStore()
const { configs: sigConfigs } = storeToRefs(sigStore)
const sigModalVisible = ref(false)
const sigEditing = ref<any>(null)

const validatingTool = ref<string | null>(null)
const resettingTool = ref<string | null>(null)
const customPathOverrides = reactive<Record<string, string>>({})
const toolPaths = reactive<Record<string, string>>({})

const toolList = computed(() => {
  const names = ['adb', 'aapt', 'apktool', 'bundletool', 'zipalign', 'apksigner', 'jarsigner']
  const toolsArr = tools
  return names.map(name => {
    const tool = Array.isArray(toolsArr) ? toolsArr.find((t: any) => t.name === name || t.key === name) : toolsArr[name]
    return {
      name,
      status: tool?.status || 'unavailable',
      version: tool?.version || '',
      defaultPath: tool?.path || '',
    }
  })
})

const openAddSignature = () => { sigEditing.value = null; sigModalVisible.value = true }
const openEditSignature = (cfg: any) => { sigEditing.value = cfg; sigModalVisible.value = true }

const handleSignatureSave = async (data: any) => {
  try {
    if (data.id) {
      await sigStore.updateConfig(data)
    } else {
      await sigStore.addConfig({ ...data, id: Date.now().toString() })
    }
    showSuccess(t('signature.saved'))
  } catch (e: any) { showError(t('signature.saveFailed'), e.message) }
}

const deleteSignature = async (id: string) => {
  try {
    await sigStore.removeConfig(id)
    showSuccess(t('signature.deleted'))
  } catch (e: any) { showError(t('signature.deleteFailed'), e.message) }
}

const showSaved = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | null = null
const triggerSaved = () => {
  showSaved.value = true
  if (savedTimer) clearTimeout(savedTimer)
  savedTimer = setTimeout(() => { showSaved.value = false }, 2000)
}

const general = reactive({ language: 'zh-CN', theme: 'auto', enableNotifications: true, autoDeleteOutputOnTaskRemove: false, useProxyForDownload: false, timeout: 300, maxConcurrentTasks: 3 })
const logLevel = ref('info')
const logLevelOptions = [
  { label: 'Debug', value: 'debug' },
  { label: 'Info', value: 'info' },
  { label: 'Warn', value: 'warn' },
  { label: 'Error', value: 'error' },
]
const pathSettings = reactive({ server: '.\\backend' })
const displayPaths = reactive({ server: '', runtimeExecutable: '' })
const cacheInfo = ref({
  tasks: { size: 0, files: 0 },
  output: { size: 0, files: 0 },
  logs: { size: 0, files: 0 },
  total: { size: 0, files: 0 }
})
const isLoadingCacheInfo = ref(false)
const clearingTarget = ref<string | null>(null)
const systemInfo = systemStore.systemInfo
const buildInfo = systemStore.buildInfo

// ---------------- settings nav（左侧导航，组级面板切换，选择持久化） ----------------
// 旧版存的是细粒度 key（appearance/behavior/…），不匹配新组级 key 时回退 general
const _PANEL_KEYS = ['general', 'runtime', 'about']
const _storedPanel = localStorage.getItem('bt:settingsPanel')
const activePanel = ref(_storedPanel && _PANEL_KEYS.includes(_storedPanel) ? _storedPanel : 'general')
watch(activePanel, (v) => { try { localStorage.setItem('bt:settingsPanel', v) } catch {} })
const navItems = computed(() => [
  { key: 'general', label: t('settings.navGeneral'), icon: Palette },
  { key: 'runtime', label: t('settings.navRuntime'), icon: Wrench },
  { key: 'about', label: t('about.title'), icon: Info },
])
const panelTitle = computed(() =>
  navItems.value.find(i => i.key === activePanel.value)?.label || ''
)

// ---------------- about（原独立关于页并入；构建信息 + 检查更新） ----------------
const updateStore = useUpdateStore()
let updateService: UpdateService | null = null

onMounted(async () => {
  try {
    updateService = await serviceManager.getService('update') as UpdateService
  } catch {
    updateService = null
  }
})

const updateButtonText = computed(() => {
  if (updateStore.status === 'checking') return t('update.checking')
  if (updateStore.status === 'available') return t('update.download')
  if (updateStore.status === 'downloaded') return t('update.restartNow')
  return t('update.checkUpdate')
})
const updateButtonDisabled = computed(() =>
  updateStore.status === 'checking' || updateStore.status === 'downloading'
)
const updateStatusText = computed(() => {
  if (updateStore.status === 'not-available') return t('update.upToDate')
  if (updateStore.status === 'error') return updateStore.error || t('update.error')
  if (updateStore.status === 'downloaded') return `${t('update.downloaded')} (v${updateStore.latestVersion})`
  if (updateStore.status === 'available') return `${t('update.newVersion')}: v${updateStore.latestVersion}`
  return ''
})

async function checkForUpdate(): Promise<void> {
  if (!updateService) return
  const status = updateStore.status
  if (status === 'available') {
    await updateService.downloadUpdate()
    return
  }
  if (status === 'downloaded') {
    await updateService.quitAndInstall()
    return
  }
  try {
    const result = await updateService.checkForUpdates()
    if (result && !result.updateAvailable) {
      showSuccess(t('update.upToDate'))
    }
  } catch (err: any) {
    showError(t('update.error'), err.message || String(err))
  }
}

// ---------------- automation capabilities ----------------
const deviceStore = useDeviceStore()
const trafficStatus = ref<TrafficStatus | null>(null)
const imeStatuses = ref<ImeStatus[]>([])
const isLoadingCapabilities = ref(false)

const trafficReady = computed(() => trafficStatus.value?.ready === true)
const trafficStateText = computed(() => {
  const s = trafficStatus.value
  if (!s) return t('settings.trafficFetchFailed')
  if (s.ready) return t('settings.trafficReady')
  if (s.python_mismatch) return t('settings.trafficPythonMismatch')
  return t('settings.trafficNotInstalled')
})
const trafficHintText = computed(() => {
  const s = trafficStatus.value
  if (s?.python_mismatch) return s.python_mismatch
  return t('settings.trafficInstallHint')
})
const imeAllReady = computed(() =>
  deviceStore.sortedDevices.length > 0 &&
  imeStatuses.value.length > 0 &&
  imeStatuses.value.every(s => s.installed)
)

// ---------------- local runtimes (Java / Python / Node) ----------------
// A path counts as "overridden" only when the user picked one; otherwise the
// backend (java) / Electron (node) discovery chain decides and we just report
// what it actually found.
const runtimeOverrides = reactive<Record<string, string>>({
  javaPath: '',
  runtimeExecutable: '',
  nodePath: ''
})

// ---------------- local service (the spawned Python backend) ----------------
const healthStore = useBackendHealthStore()
const serviceVersion = ref('')
const serviceHealthy = computed(() => healthStore.isHealthy === true)
const serviceStatusText = computed(() => {
  if (healthStore.isHealthy === null) return t('settings.serviceUnknown')
  return healthStore.isHealthy ? t('settings.serviceRunning') : t('settings.serviceStopped')
})

interface RuntimeRow {
  key: string
  label: string
  version: string
  path: string
  configKey: string
  overridden: boolean
  hint: string
}

const runtimeRows = computed<RuntimeRow[]>(() => [
  {
    key: 'java',
    label: t('settings.runtimeJava'),
    version: buildInfo.javaVersion,
    path: buildInfo.javaPath,
    configKey: 'javaPath',
    overridden: !!runtimeOverrides.javaPath,
    hint: ''
  },
  {
    // Python: the editable key is `runtimeExecutable` — that IS the
    // interpreter we spawn, so changing it really swaps the runtime.
    key: 'python',
    label: t('settings.runtimePython'),
    version: buildInfo.pythonVersion,
    path: displayPaths.runtimeExecutable || buildInfo.pythonPath,
    configKey: 'runtimeExecutable',
    overridden: !!runtimeOverrides.runtimeExecutable,
    hint: ''
  },
  {
    // Node is displayed honestly: the backend has no Node consumer today
    // (env.get_node_bin has zero callers), so an override is recorded but
    // changes nothing yet.
    key: 'node',
    label: t('settings.runtimeNode'),
    version: buildInfo.nodeVersion,
    path: runtimeOverrides.nodePath || buildInfo.nodePath,
    configKey: 'nodePath',
    overridden: !!runtimeOverrides.nodePath,
    hint: t('settings.runtimeRecordOnly')
  }
])

async function handleBrowseRuntime(row: RuntimeRow) {
  try {
    const svc = await serviceManager.getService('system')
    const result = await svc.selectFile({ title: `${t('settings.runtimePath')} - ${row.label}` })
    const file = result?.filePaths?.[0]
    if (!file) return
    await saveRuntimeOverride(row, file)
  } catch { /* user cancelled */ }
}

function handleResetRuntime(row: RuntimeRow) {
  return saveRuntimeOverride(row, '')
}

async function saveRuntimeOverride(row: RuntimeRow, value: string) {
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ [row.configKey]: value })
    runtimeOverrides[row.configKey] = value
    // Runtime overrides ride in the env the backend is spawned with, so a new
    // path only takes effect after an app restart.
    showWarning(t('settings.pathRestartHint'))
  } catch (e: any) {
    showError(t('settings.saveFailed'), e?.message || String(e))
  }
}

async function loadServiceInfo() {
  try {
    void healthStore.check(true)
    const svc = await serviceManager.getService('system')
    const info = await svc.getBackendInfo()
    if (info?.version) serviceVersion.value = String(info.version)
  } catch { /* best-effort: the card renders an unknown state instead */ }
}

const refreshCapabilities = async () => {
  isLoadingCapabilities.value = true
  try {
    const svc = await serviceManager.getService('automation')
    trafficStatus.value = await svc.getTrafficStatus(true)
    const devices = deviceStore.sortedDevices
    if (!devices.length) {
      imeStatuses.value = []
      return
    }
    const probed = await Promise.all(devices.map(d => svc.getImeStatus(d.id)))
    imeStatuses.value = probed.filter((s): s is ImeStatus => s !== null)
  } catch (e) { log.error('Failed to refresh automation capabilities:', e) }
  finally { isLoadingCapabilities.value = false }
}

const langOptions = computed(() => [
  { label: t('settings.simplifiedChinese'), value: 'zh-CN' },
  { label: t('settings.english'), value: 'en-US' },
])
const themeOptions = computed(() => [
  { label: t('settings.themeAuto'), value: 'auto' },
  { label: t('settings.themeLight'), value: 'light' },
  { label: t('settings.themeDark'), value: 'dark' },
])
// Storage categories: key → label, icon, color
const storageCategories = [
  { key: 'tasks',      label: 'settings.tasks',      icon: Archive,       color: 'var(--app-yellow)' },
  { key: 'auto_tasks', label: 'settings.auto_tasks', icon: History,       color: 'var(--app-purple)' },
  { key: 'output',     label: 'settings.output',     icon: FolderArchive, color: 'var(--app-blue)' },
  { key: 'logs',       label: 'settings.logs',       icon: FileText,      color: 'var(--app-green)' },
] as const

const getCatSize = (key: string) => (cacheInfo.value as any)[key]?.size || 0
const getCatFiles = (key: string) => (cacheInfo.value as any)[key]?.files || 0
const barWidth = (key: string) => {
  const total = cacheInfo.value.total.size
  if (!total) return '0%'
  return Math.max(0, (getCatSize(key) / total) * 100) + '%'
}
const cpuText = computed(() => {
  const count = systemInfo.cpuCount || '0'
  return `${count} ${t('device.cores', { count: Number(count) || 0 })}`
})

// 文件大小格式化统一走 @utils/format（原先这里 toFixed(2) 会输出 "1.50 MB"，
// 与 ApkService / systemStore 的 "1.5 MB" 不一致）

const loadSettings = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    const model = await svc.loadSettingsModel()
    if (model?.settings) {
      const s = model.settings as Record<string, unknown>
      for (const key of Object.keys(general)) {
        if (Object.prototype.hasOwnProperty.call(s, key)) (general as any)[key] = s[key]
      }
      if (s.server) pathSettings.server = s.server as string
      // Runtime overrides: empty means "let the discovery chain decide".
      for (const key of Object.keys(runtimeOverrides)) {
        runtimeOverrides[key] = typeof s[key] === 'string' ? s[key] as string : ''
      }
    }
    if (model?.displayPaths) {
      displayPaths.server = model.displayPaths.server || ''
      displayPaths.runtimeExecutable = model.displayPaths.runtimeExecutable || ''
    }
    // Load log level from appConfig (logs.level)
    try {
      const logsConfig = await window.electronAPI.appConfig.get('logs')
      if (logsConfig && typeof logsConfig === 'object' && 'level' in logsConfig) {
        const level = (logsConfig as Record<string, unknown>).level
        if (typeof level === 'string' && ['debug', 'info', 'warn', 'error'].includes(level)) {
          logLevel.value = level
        }
      }
    } catch {}
  } catch (e) { log.error('Failed to load settings:', e) }
}

const saveGeneral = async () => {
  setLocale(general.language)
  await setTheme(general.theme)
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ ...general })
    // Apply the concurrency cap immediately (frontend queue). The backend
    // pool picks it up on the next app start via the BT_MAX_WORKERS env var.
    setMaxConcurrent(general.maxConcurrentTasks)
    triggerSaved()
    } catch (e) { showError(t('settings.saveFailed'), (e as Error).message) }
}

const saveLogLevel = async (value: string) => {
  setLogLevel(value as 'debug' | 'info' | 'warn' | 'error')
  try {
    await window.electronAPI.appConfig.set('logs.level', value)
    triggerSaved()
  } catch (e) { log.error('Failed to save log level:', e) }
}

const savePaths = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ server: pathSettings.server })
    triggerSaved()
  } catch (e: any) { showError(t('settings.pathsFailed'), e.message) }
}

const handleBrowseDirectory = async (target: 'server') => {
  try {
    const svc = await serviceManager.getService('system')
    const result = await svc.selectDirectory({ title: t('settings.selectDir') })
    // dialog.showOpenDialog returns { canceled, filePaths }. Some builds also
    // surface the picked folder as `directoryPath`, so accept both shapes.
    const dir = result?.filePaths?.[0] || result?.directoryPath
    if (!dir) return
    pathSettings[target] = dir
    const settingsSvc = await serviceManager.getService('settings')
    const paths = await settingsSvc.resolveDisplayPaths(pathSettings)
    displayPaths.server = paths.server || ''
    await savePaths()
    // BT_SERVER_DIR is injected when the Python backend is spawned, so a new
    // path only takes effect after restarting the app.
    showWarning(t('settings.pathRestartHint'))
  } catch (e) { showError(t('settings.selectDirFailed')) }
}

const refreshCache = async () => {
  isLoadingCacheInfo.value = true
  try {
    const svc = await serviceManager.getService('cache')
    const info = await svc.getCacheInfo(true)
    if (info) cacheInfo.value = info
  } catch (e) { log.error('Failed to refresh cache:', e) }
  finally { isLoadingCacheInfo.value = false }
}

const confirmClear = (target: string) => {
  const label = target === 'all'
    ? t('settings.clearAllStorage')
    : t(`settings.${target}`)
  dialog.warning({
    title: t('settings.clearConfirmTitle'),
    content: t('settings.clearConfirmContent', { target: label }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      clearingTarget.value = target
      try {
        const svc = await serviceManager.getService('cache')
        const result = await svc.clearStorage(target)
        if (result.success) {
          showSuccess(t('settings.storageCleared'))
          await refreshCache()
        } else {
          showError(t('settings.clearFailed'), result.error)
        }
      } catch (e: any) {
        showError(t('settings.clearFailed'), e.message)
      } finally {
        clearingTarget.value = null
      }
    }
  })
}

const handleToolPathChange = async (toolName: string, path: string) => {
  if (!path.trim()) return
  validatingTool.value = toolName
  try {
    const result = await toolStore.setCustomPath(toolName, path.trim())
    if (result) {
      toolPaths[toolName] = path.trim()
      customPathOverrides[toolName] = path.trim()
    }
  } catch (e: any) {
    showError(t('settings.toolPathFailed'), e.message)
  } finally {
    validatingTool.value = null
  }
}

const handleBrowseToolPath = async (toolName: string) => {
  try {
    const svc = await serviceManager.getService('system')
    const result = await svc.selectFile({ title: `${t('settings.selectToolPath')} - ${toolName}` })
    if (result?.filePaths?.length) {
      const filePath = result.filePaths[0]
      toolPaths[toolName] = filePath
      await handleToolPathChange(toolName, filePath)
    }
  } catch (e) { /* user cancelled */ }
}

const handleResetToolPath = async (toolName: string) => {
  resettingTool.value = toolName
  try {
    await toolStore.resetCustomPath(toolName)
    delete customPathOverrides[toolName]
    toolPaths[toolName] = ''
  } catch (e: any) {
    showError(t('settings.toolPathFailed'), e.message)
  } finally {
    resettingTool.value = null
  }
}

onMounted(() => {
  log.debug('设置页面已挂载')
  loadSettings()
  refreshCache()
  refreshCapabilities()
  // Runtime versions/paths and the service version are cached in the system
  // store, but a direct landing on this page can race the bootstrap — refetch.
  void systemStore.fetchBuildInfo()
  void loadServiceInfo()
  sigStore.loadConfigs()
  toolStore.fetchCustomPaths().then(() => {
    Object.assign(customPathOverrides, toolStore.customPaths)
    Object.assign(toolPaths, toolStore.customPaths)
  })
})
</script>

<style scoped>
.saved-tag { margin-top: 4px; transition: opacity 0.3s; }
.settings-body { display: flex; gap: 16px; align-items: flex-start; }
.settings-nav { width: 148px; flex: none; display: flex; flex-direction: column; gap: 2px; position: sticky; top: 0; }
.settings-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.panel-title { font-size: 16px; font-weight: 600; color: var(--app-text-primary); margin-bottom: 2px; }
.panel-sec { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: var(--app-text-dim); margin-bottom: -6px; }
.panel-sec .storage-total-text { margin-left: 0; margin-right: auto; }
.panel-sec-action { margin-left: auto; }
.settings-card { background: var(--app-card-bg); border-radius: 10px; }
.set-rows { display: flex; flex-direction: column; margin-top: 6px; }
.set-row { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 11px 0; }
.set-row + .set-row { border-top: 1px solid var(--app-card-border); }
.set-info { min-width: 0; }
.set-label { font-size: 13px; font-weight: 500; color: var(--app-text-primary); }
.set-desc { font-size: 12px; color: var(--app-text-muted); margin-top: 2px; }
.set-control { flex: none; }
.set-w200 { width: 200px; }
.set-w140 { width: 140px; }
.hdr-actions { display: flex; align-items: center; gap: 4px; margin-left: auto; }
.info-grid { display: flex; flex-direction: column; gap: 6px; }
.info-row { display: flex; align-items: baseline; gap: 12px; padding: 5px 0; }
.info-label { font-size: 13px; color: var(--app-text-muted); min-width: 110px; }
.info-val { font-size: 13px; color: var(--app-text-secondary); font-family: var(--app-font-mono); min-width: 80px; word-break: break-all; }
.update-status-inline { font-size: 12px; color: var(--app-green); white-space: nowrap; }
.storage-total-text { font-size: 16px; font-weight: 600; color: var(--app-green); font-variant-numeric: tabular-nums; margin-left: auto; margin-right: 12px; }
.storage-bar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: var(--app-storage-bg); margin-bottom: 12px; }
.storage-bar-seg { height: 100%; transition: width 0.3s ease; }
.storage-rows { display: flex; flex-direction: column; gap: 2px; }
.storage-row { display: flex; align-items: center; gap: 10px; padding: 8px 4px; border-radius: 6px; }
.storage-row:hover { background: var(--app-storage-bg); }
.storage-row-icon { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 6px; background: var(--app-storage-bg); flex-shrink: 0; }
.storage-row-info { flex: 1; min-width: 0; }
.cap-row { display: flex; align-items: flex-start; gap: 10px; padding: 8px 4px; border-radius: 6px; }
.cap-row:hover { background: var(--app-storage-bg); }
.cap-status-icon { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 6px; background: var(--app-storage-bg); flex-shrink: 0; }
.cap-info { flex: 1; min-width: 0; }
.cap-label { font-size: 13px; font-weight: 500; color: var(--app-text-primary); }
.cap-sub { font-size: 12px; color: var(--app-text-muted); margin-top: 2px; }
.cap-mono { font-family: var(--app-font-mono); font-size: 11px; word-break: break-all; }
.cap-hint { font-size: 12px; color: var(--app-text-muted); margin-top: 4px; }
/* local runtimes (Java / Python / Node) */
.runtime-list { display: flex; flex-direction: column; gap: 2px; }
.runtime-row { display: flex; align-items: center; gap: 10px; padding: 8px 4px; border-radius: 6px; }
.runtime-row:hover { background: var(--app-storage-bg); }
.runtime-info { flex: 1; min-width: 0; }
.runtime-label { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--app-text-primary); }
.runtime-version { font-size: 11px; font-weight: 500; color: var(--app-green); }
.runtime-version.is-missing { color: var(--app-yellow); }
.runtime-path { font-size: 11px; color: var(--app-text-muted); font-family: var(--app-font-mono); word-break: break-all; margin-top: 2px; }
.runtime-hint { font-size: var(--app-font-size-sm); color: var(--app-text-muted); margin-top: 4px; }
/* local service (version / status / directory) */
.svc-row { display: flex; align-items: center; gap: 12px; padding: 6px 4px; }
.svc-label { font-size: 13px; color: var(--app-text-muted); min-width: 88px; }
.svc-value { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--app-text-secondary); }
.svc-dot { display: flex; align-items: center; }
.svc-path-wrap { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
/* tools & dependencies: sub-group headings */
.dep-sub-head { display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; color: var(--app-text-secondary); margin: 10px 0 4px; }
.dep-sub-head-with-action { justify-content: space-between; }
.storage-row-label { font-size: 13px; font-weight: 600; color: var(--app-text-primary); }
.storage-row-sub { font-size: 11px; color: var(--app-text-muted); margin-top: 1px; }
.info-empty { font-size: 13px; color: var(--app-text-dim); padding: 8px 0; }

.sig-list { display: flex; flex-direction: column; gap: 6px; }
.sig-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; background: var(--app-storage-bg); border-radius: 8px; gap: 8px; }
.sig-info { display: flex; align-items: center; gap: 12px; min-width: 0; flex: 1; }
.sig-name { font-size: 13px; font-weight: 600; color: var(--app-text-primary); white-space: nowrap; }
.sig-detail { font-size: 12px; color: var(--app-text-dim); white-space: nowrap; }
.sig-path { font-size: 11px; color: var(--app-text-dim); font-family: var(--app-font-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }

.tool-path-list { display: flex; flex-direction: column; gap: 8px; }
.tool-path-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
.tool-path-name { display: inline-flex; align-items: baseline; gap: 6px; font-size: 13px; font-weight: 600; color: var(--app-text-primary); min-width: 110px; font-family: var(--app-font-mono); padding-left: 4px; }
.tool-version { font-size: 11px; font-weight: 400; color: var(--app-text-muted); }
.tool-version.is-missing { color: var(--app-yellow); }
.tool-path-input-wrap { display: flex; align-items: center; gap: 4px; flex: 1; }
.tool-path-input-wrap :deep(.n-input .n-input__input-el) { color: var(--app-text-muted); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
