<template>
  <div class="app-page">
    <!-- 页头只留标题：保存反馈走应用统一通知，不再往标题行塞状态标签 -->
    <div class="app-page-header" ref="headerRef">
      <div>
        <h1 class="app-page-title">{{ t('settings.title') }}</h1>
        <p class="app-page-sub">{{ t('settings.subtitle') }}</p>
      </div>
    </div>

    <div class="settings-body">
      <!-- 左侧导航：组级切换，组内所有设置卡一起展示 -->
      <aside class="settings-nav" :style="{ top: navTop + 'px' }">
        <div
          v-for="item in navItems"
          :key="item.key"
          class="app-nav-item"
          :class="{ active: activePanel === item.key }"
          @click="activePanel = item.key"
        >
          <n-icon size="14"><component :is="item.icon" /></n-icon>
          <span>{{ item.label }}</span>
        </div>
      </aside>

      <div class="settings-panel">
      <div class="panel-title">{{ panelTitle }}</div>
      <!-- Appearance -->
      <section v-show="activePanel === 'general'">
      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
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
      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
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
      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
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
      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
        <n-icon size="14"><Cpu /></n-icon>
        <span>{{ t('settings.localRuntimes') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">
        <div class="path-list">
          <PathRow
            v-for="row in runtimeRows"
            :key="row.key"
            :label="row.label"
            :path="row.path"
            :placeholder="t('settings.runtimeUnknown')"
            :hint="row.hint"
            editable
            :overridden="row.overridden"
            @edit="handleBrowseRuntime(row)"
            @reset="handleResetRuntime(row)"
          >
            <template #badge>
              <span class="path-badge" :class="row.version ? 'is-ok' : 'is-missing'">
                {{ row.version || t('settings.runtimeUnknown') }}
              </span>
            </template>
          </PathRow>
        </div>
      </n-card>
      </section>

      <!-- Local service (the spawned Python backend) -->
      <section v-show="activePanel === 'runtime'">
      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
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
        <div class="path-list">
          <PathRow
            :label="t('settings.serviceDir')"
            :path="displayPaths.server"
            placeholder=".\backend"
            editable
            :edit-title="t('settings.selectDir')"
            @edit="handleBrowseDirectory('server')"
          />
        </div>
      </n-card>
      </section>

      <!-- Tools & dependencies: built-in tools + automation components -->
      <section v-show="activePanel === 'runtime'">
      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
        <n-icon size="14"><Wrench /></n-icon>
        <span>{{ t('settings.dependencies') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">

        <div class="dep-sub-head app-subhead app-subhead--sm app-subhead--muted">{{ t('settings.builtinTools') }}</div>
        <div class="path-list">
          <PathRow
            v-for="tool in toolList"
            :key="tool.name"
            :label="tool.name"
            label-mono
            :path="toolPaths[tool.name] || tool.defaultPath"
            :placeholder="t('settings.runtimeUnknown')"
            editable
            :editing="validatingTool === tool.name"
            :overridden="!!customPathOverrides[tool.name]"
            :reset-loading="resettingTool === tool.name"
            :edit-title="t('settings.selectToolPath')"
            @edit="handleBrowseToolPath(tool.name)"
            @reset="handleResetToolPath(tool.name)"
          >
            <!-- 版本来自工具探测（tool.version）；原先只有关于页展示过 -->
            <template #badge>
              <span class="path-badge" :class="{ 'is-missing': !tool.version }">
                {{ tool.version || t('common.unknown') }}
              </span>
            </template>
            <template #actions>
              <n-icon v-if="tool.status === 'available'" size="14" color="var(--app-green)"><CheckCircle /></n-icon>
              <n-icon v-else size="14" color="var(--app-yellow)"><AlertCircle /></n-icon>
            </template>
          </PathRow>
        </div>

        <!-- Automation components: tools the automation feature reaches for
             (mitmproxy on the PC, ADBKeyBoard on the device) -->
        <div class="dep-sub-head app-subhead app-subhead--sm app-subhead--muted">{{ t('settings.automationComponents') }}</div>
        <div class="card-toolbar">
          <div class="card-toolbar-actions">
            <n-button size="tiny" quaternary :loading="isResettingTraffic" @click="resetTrafficProxy">
              <template #icon><n-icon size="14"><Wrench /></n-icon></template>
              {{ t('settings.trafficReset') }}
            </n-button>
            <n-button size="tiny" quaternary :loading="isLoadingCapabilities" @click="refreshCapabilities">
              <template #icon><n-icon size="14"><RefreshCw /></n-icon></template>
              {{ t('settings.refreshStatus') }}
            </n-button>
          </div>
        </div>

        <div class="path-list">
          <!-- Traffic capture (PC side: mitmproxy) — 只读路径：不提供修改入口 -->
          <PathRow
            :label="t('settings.trafficCaptureRow')"
            :path="trafficStatus?.lib_path || ''"
            :placeholder="t('settings.runtimeUnknown')"
            :hint="trafficStatus && !trafficStatus.ready ? trafficHintText : ''"
          >
            <template #badge>
              <span class="path-badge" :class="trafficReady ? 'is-ok' : 'is-missing'">{{ trafficStateText }}</span>
            </template>
            <template #actions>
              <n-icon size="14" :style="{ color: trafficReady ? 'var(--app-green)' : 'var(--app-yellow)' }">
                <CheckCircle v-if="trafficReady" /><AlertCircle v-else />
              </n-icon>
            </template>
          </PathRow>

          <!-- Chinese input (device side: ADBKeyBoard) — 设备状态列表，无路径 -->
          <PathRow
            :label="t('settings.imeRow')"
            :hint="imeStatuses.some(s => !s.installed) ? t('settings.imeInstallHint') : ''"
          >
            <template #value>
              <div v-if="!deviceStore.sortedDevices.length" class="ime-lines">
                <div class="ime-line">{{ t('settings.imeNoDevice') }}</div>
              </div>
              <div v-else class="ime-lines">
                <div v-for="st in imeStatuses" :key="st.device_id" class="ime-line">
                  <n-icon size="12" :style="{ color: st.installed ? 'var(--app-green)' : 'var(--app-yellow)' }">
                    <CheckCircle v-if="st.installed" /><AlertCircle v-else />
                  </n-icon>
                  <span>{{ st.device_id }} · {{ st.installed ? t('settings.imeInstalled') : t('settings.imeNotInstalled') }}</span>
                  <span v-if="st.active"> · {{ t('settings.imeActive') }}</span>
                </div>
              </div>
            </template>
            <template #actions>
              <n-icon size="14" :style="{ color: imeAllReady ? 'var(--app-green)' : 'var(--app-yellow)' }">
                <CheckCircle v-if="imeAllReady" /><AlertCircle v-else />
              </n-icon>
            </template>
          </PathRow>
        </div>
      </n-card>
      </section>

      <!-- Signature Configs -->
      <section v-show="activePanel === 'signing'">
      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
        <n-icon size="14"><Key /></n-icon>
        <span>{{ t('signature.title') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">
        <div class="card-toolbar">
          <div class="card-toolbar-actions">
            <n-button size="tiny" type="primary" secondary @click="openAddSignature">
              <template #icon><n-icon size="14"><Plus /></n-icon></template>
              {{ t('signature.add') }}
            </n-button>
          </div>
        </div>
        <div v-if="sigConfigs.length === 0" class="app-empty-hint">{{ t('signature.empty') }}</div>
        <div v-else class="path-list">
          <PathRow
            v-for="cfg in sigConfigs"
            :key="cfg.id"
            :label="String(cfg.name ?? '')"
            :path="String(cfg.path ?? '')"
            :placeholder="t('common.unknown')"
          >
            <template #badge>
              <span class="path-badge">{{ cfg.alias }}</span>
            </template>
            <template #actions>
              <IconButton
                :icon="Edit"
                :label="t('signature.editTitle')"
                size="tiny"
                quaternary
                @click="openEditSignature(cfg)"
              />
              <IconButton
                :icon="Trash2"
                :label="t('signature.delete')"
                size="tiny"
                quaternary
                type="error"
                @click="deleteSignature(cfg.id)"
              />
            </template>
          </PathRow>
        </div>
      </n-card>
      </section>

      <!-- Storage -->
      <section v-show="activePanel === 'storage'">
      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
        <n-icon size="14"><HardDrive /></n-icon>
        <span>{{ t('settings.storage') }}</span>
      </div>
      <n-card :bordered="false" class="settings-card">

        <!-- 合计与整体操作都收进卡片：标题行只留标题 -->
        <div class="card-toolbar">
          <span class="storage-total-text">{{ t('settings.total') }} · {{ formatBytes(cacheInfo.total.size) }}</span>
          <div class="card-toolbar-actions">
            <IconButton
              :icon="Trash2"
              :label="t('settings.clearAllStorage')"
              :loading="clearingTarget === 'all'"
              :disabled="cacheInfo.total.size === 0"
              size="tiny"
              quaternary
              type="error"
              @click="confirmClear('all')"
            />
            <IconButton
              :icon="RefreshCw"
              :label="t('settings.refresh')"
              :loading="isLoadingCacheInfo"
              size="tiny"
              quaternary
              @click="refreshCache"
            />
          </div>
        </div>

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
            <IconButton
              :icon="Trash2"
              :label="t('settings.clearCategory')"
              :loading="clearingTarget === cat.key"
              :disabled="getCatSize(cat.key) === 0"
              size="tiny"
              quaternary
              type="error"
              @click="confirmClear(cat.key)"
            />
          </div>
        </div>

        <!-- Run-history retention: rule-based cleanup of auto_tasks/.
             `storage.clear auto_tasks` throws away EVERY run; these rules let
             the user keep the recent ones and drop the rest. The backend
             refuses a rule-less request and never touches a run that is
             executing right now. -->
        <div class="prune-block">
          <div class="prune-head">
            <span class="app-subhead app-subhead--sm app-subhead--muted">{{ t('settings.pruneTitle') }}</span>
            <span v-if="orphanCount > 0" class="prune-orphans">{{ t('settings.orphanRuns', { count: orphanCount }) }}</span>
          </div>
          <div class="prune-hint">{{ t('settings.pruneHint') }}</div>
          <div class="prune-controls">
            <span class="prune-label">{{ t('settings.pruneKeepLast') }}</span>
            <n-input-number
              v-model:value="pruneKeepLast"
              size="tiny"
              :min="0"
              :max="1000"
              :show-button="false"
              class="prune-num"
              :placeholder="t('settings.pruneOff')"
            />
            <span class="prune-label">{{ t('settings.pruneKeepLastUnit') }}</span>
            <span class="prune-sep" />
            <span class="prune-label">{{ t('settings.pruneOlderDays') }}</span>
            <n-input-number
              v-model:value="pruneOlderDays"
              size="tiny"
              :min="0"
              :max="3650"
              :show-button="false"
              class="prune-num"
              :placeholder="t('settings.pruneOff')"
            />
            <span class="prune-label">{{ t('settings.pruneOlderUnit') }}</span>
            <span class="prune-sep" />
            <n-checkbox v-model:checked="pruneOrphansOnly" size="small">
              {{ t('settings.pruneOrphansOnly') }}
            </n-checkbox>
          </div>
          <div class="prune-actions">
            <n-button
              size="tiny"
              secondary
              :loading="pruning === 'dry'"
              :disabled="!pruneRuleSet"
              @click="runPrune(true)"
            >
              {{ t('settings.prunePreview') }}
            </n-button>
            <n-button
              size="tiny"
              type="error"
              secondary
              :loading="pruning === 'run'"
              :disabled="!pruneRuleSet"
              @click="confirmPrune"
            >
              {{ t('settings.pruneApply') }}
            </n-button>
          </div>
        </div>
      </n-card>
      </section>

      <!-- About（原独立关于页并入） -->
      <section v-show="activePanel === 'about'">
      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
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

      <div class="panel-sec app-subhead app-subhead--sm app-subhead--dim">
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
import { ref, reactive, computed, onMounted, onBeforeUnmount, inject, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon, NButton, useDialog } from 'naive-ui'
import { Trash2, RefreshCw, Cpu, Monitor, Layers, Settings2, HardDrive, CheckCircle, Wrench, Key, Plus, Edit, AlertCircle, Archive, FileText, FolderArchive, History, Server, Palette, Info } from 'lucide-vue-next'
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
import PathRow from '@components/common/PathRow.vue'
import IconButton from '@components/common/IconButton.vue'
import { setMaxConcurrent } from '@services/TaskExecutionService'
import type { TrafficStatus, ImeStatus } from '@services/AutomationService'
import type UpdateService from '@services/UpdateService'

const { t } = useI18n()
const { showSuccess, showError, showWarning, showInfo } = useNotification()
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

// 保存反馈统一走应用通知：原先在页头标题行挂一个「已保存」标签，
// 标题行不再承载任何状态显示。
const notifySaved = () => { showSuccess(t('settings.saved')) }

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
// 签名不并进「通用」：它既不是外观也不是行为，而是一类独立的凭据配置
const _PANEL_KEYS = ['general', 'signing', 'runtime', 'storage', 'about']
const _storedPanel = localStorage.getItem('bt:settingsPanel')
const activePanel = ref(_storedPanel && _PANEL_KEYS.includes(_storedPanel) ? _storedPanel : 'general')
watch(activePanel, (v) => { try { localStorage.setItem('bt:settingsPanel', v) } catch {} })
const navItems = computed(() => [
  { key: 'general', label: t('settings.navGeneral'), icon: Palette },
  { key: 'signing', label: t('settings.navSigning'), icon: Key },
  { key: 'runtime', label: t('settings.navRuntime'), icon: Wrench },
  { key: 'storage', label: t('settings.navStorage'), icon: HardDrive },
  { key: 'about', label: t('about.title'), icon: Info },
])
const panelTitle = computed(() =>
  navItems.value.find(i => i.key === activePanel.value)?.label || ''
)

// 左栏 sticky 的吸附位必须让开页头：页头自己也是 sticky top:0 + z-index:10，
// 左栏若也贴 top:0 会钻到页头底下被盖住（表现为「列表跟着滚、小标题消失」）。
// 页头高度随字号/是否换行变化，这里实测而非写死像素。
const headerRef = ref<HTMLElement | null>(null)
const navTop = ref(0)
let headerRO: ResizeObserver | null = null
onMounted(() => {
  const el = headerRef.value
  if (!el) return
  const measure = () => { navTop.value = Math.ceil(el.getBoundingClientRect().height) }
  measure()
  headerRO = new ResizeObserver(measure)
  headerRO.observe(el)
})
onBeforeUnmount(() => {
  headerRO?.disconnect()
  headerRO = null
})

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

/**
 * Manual repair for a device left pointing at a dead capture proxy.
 *
 * The backend already self-heals at startup; this covers the case where the
 * proxy is stuck while the app keeps running (mitmdump killed externally).
 * Idempotent — `restored: []` means there was nothing stale.
 */
const isResettingTraffic = ref(false)
const resetTrafficProxy = async () => {
  if (isResettingTraffic.value) return
  isResettingTraffic.value = true
  try {
    const svc = await serviceManager.getService('automation')
    const res = await svc.resetTraffic()
    if (!res?.success) {
      showError(res?.error || t('settings.trafficResetFailed'))
      return
    }
    const restored = res.restored || []
    if (!restored.length) {
      showInfo(t('settings.trafficResetNothing'))
      return
    }
    showSuccess(t('settings.trafficResetDone', { count: restored.length }))
    await refreshCapabilities()
  } catch (e: any) {
    showError(e?.message || String(e))
  } finally {
    isResettingTraffic.value = false
  }
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
    notifySaved()
    } catch (e) { showError(t('settings.saveFailed'), (e as Error).message) }
}

const saveLogLevel = async (value: string) => {
  setLogLevel(value as 'debug' | 'info' | 'warn' | 'error')
  try {
    await window.electronAPI.appConfig.set('logs.level', value)
    notifySaved()
  } catch (e) { log.error('Failed to save log level:', e) }
}

const savePaths = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ server: pathSettings.server })
    notifySaved()
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

// ---------------- run-history retention (prune) ----------------
// `storage.clear auto_tasks` throws away EVERY run. These rules keep the
// recent ones and drop the rest; the backend refuses a rule-less request and
// never deletes a run that is executing right now.
const pruneKeepLast = ref<number | null>(null)
const pruneOlderDays = ref<number | null>(null)
const pruneOrphansOnly = ref(false)
const pruning = ref<'' | 'dry' | 'run'>('')
const orphanCount = ref(0)

const pruneRuleSet = computed(() =>
  pruneKeepLast.value !== null || pruneOlderDays.value !== null || pruneOrphansOnly.value
)

const pruneParams = (dryRun: boolean) => ({
  dry_run: dryRun,
  keep_last: pruneKeepLast.value === null ? undefined : pruneKeepLast.value,
  older_than_days: pruneOlderDays.value === null ? undefined : pruneOlderDays.value,
  orphans_only: pruneOrphansOnly.value || undefined,
})

/** 残留条数（被中断的运行）：只在存储面板里做一个提示 */
const loadRunStats = async () => {
  try {
    const api = window.electronAPI as any
    const res = await api.callBackendAPI('automation.list_runs', {})
    orphanCount.value = Number(res?.orphans) || 0
  } catch { /* 计数只是提示，失败就当作 0 */ }
}

/** 返回 `{ count, size }`（预览与实际执行同一套规则）；失败返回 null */
const runPrune = async (dryRun: boolean) => {
  pruning.value = dryRun ? 'dry' : 'run'
  try {
    const api = window.electronAPI as any
    const res = await api.callBackendAPI('automation.prune_runs', pruneParams(dryRun))
    if (!res?.success) {
      showError(t('settings.pruneFailed'), res?.error || '')
      return null
    }
    const info = {
      count: Number(res.deleted_count) || 0,
      size: formatBytes(Number(res.freed_bytes) || 0),
    }
    if (!dryRun) {
      if (info.count) showSuccess(t('settings.pruneDone', info))
      else showInfo(t('settings.pruneNothing'))
      await Promise.all([refreshCache(), loadRunStats()])
    }
    return info
  } catch (e: any) {
    showError(t('settings.pruneFailed'), e?.message || String(e))
    return null
  } finally {
    pruning.value = ''
  }
}

/** 先干跑一次拿到准确条数/体积，再让用户确认 —— 删除不可恢复 */
const confirmPrune = async () => {
  const preview = await runPrune(true)
  if (!preview) return
  if (!preview.count) {
    showInfo(t('settings.pruneNothing'))
    return
  }
  dialog.warning({
    title: t('settings.pruneConfirmTitle'),
    content: t('settings.pruneConfirmContent', preview),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => { await runPrune(false) },
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
  void loadRunStats()
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
.settings-body { display: flex; gap: 16px; align-items: flex-start; }
.settings-nav { width: 148px; flex: none; display: flex; flex-direction: column; gap: 2px; position: sticky; z-index: 5; background: var(--app-body-bg); }
  /* top 由 script 实测页头高度后注入（见 navTop）：不能与页头抢 top:0 */
.settings-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.panel-title { font-size: var(--app-font-size-xl); font-weight: 600; color: var(--app-text-primary); margin-bottom: 2px; }
/* 区块标题行只承载标题（图标 + 文案）：按钮 / 状态 / 统计统统进卡片 */
.panel-sec { gap: 6px; margin-bottom: 0; }
.settings-card { background: var(--app-card-bg); border-radius: 10px; }
/* 卡片内的工具栏行：左侧统计文案，右侧操作按钮 */
.card-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.card-toolbar-actions { display: flex; align-items: center; gap: 4px; margin-left: auto; }

/* ---- 统一路径行（PathRow 的容器与插槽内容配套样式） ---- */
.path-list { display: flex; flex-direction: column; gap: 2px; }
.path-badge { font-size: var(--app-font-size-xs); font-weight: 500; color: var(--app-text-muted); white-space: nowrap; }
.path-badge.is-ok { color: var(--app-green); }
.path-badge.is-missing { color: var(--app-yellow); }
/* 自动化中文输入（ADBKeyBoard）：按设备逐行列出，没有单一路径 */
.ime-lines { display: flex; flex-direction: column; gap: 2px; }
.ime-line { display: flex; align-items: center; gap: 6px; font-size: var(--app-font-size-sm); color: var(--app-text-muted); font-family: var(--app-font-mono); }

.set-rows { display: flex; flex-direction: column; margin-top: 6px; }
.set-row { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 11px 0; }
.set-row + .set-row { border-top: 1px solid var(--app-card-border); }
.set-info { min-width: 0; }
.set-label { font-size: var(--app-font-size-md); font-weight: 500; color: var(--app-text-primary); }
.set-desc { font-size: var(--app-font-size-sm); color: var(--app-text-muted); margin-top: 2px; }
.set-control { flex: none; }
.set-w200 { width: 200px; }
.set-w140 { width: 140px; }
.info-grid { display: flex; flex-direction: column; gap: 6px; }
.info-row { display: flex; align-items: baseline; gap: 12px; padding: 5px 0; }
.info-label { font-size: var(--app-font-size-md); color: var(--app-text-muted); min-width: 110px; }
.info-val { font-size: var(--app-font-size-md); color: var(--app-text-secondary); font-family: var(--app-font-mono); min-width: 80px; word-break: break-all; }
.update-status-inline { font-size: var(--app-font-size-sm); color: var(--app-green); white-space: nowrap; }
.storage-total-text { font-size: var(--app-font-size-xl); font-weight: 600; color: var(--app-green); font-variant-numeric: tabular-nums; }
.storage-bar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: var(--app-storage-bg); margin-bottom: 12px; }
.storage-bar-seg { height: 100%; transition: width 0.3s ease; }
.storage-rows { display: flex; flex-direction: column; gap: 2px; }
.storage-row { display: flex; align-items: center; gap: 10px; padding: 8px 4px; border-radius: 6px; }
.storage-row:hover { background: var(--app-storage-bg); }
.storage-row-icon { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 6px; background: var(--app-storage-bg); flex-shrink: 0; }
.storage-row-info { flex: 1; min-width: 0; }
.storage-row-label { font-size: var(--app-font-size-md); font-weight: 600; color: var(--app-text-primary); }
.storage-row-sub { font-size: var(--app-font-size-xs); color: var(--app-text-muted); margin-top: 1px; }
/* local service (version / status / directory) —— 路径行由 PathRow 渲染，前两行对齐同一内距 */
.svc-row { display: flex; align-items: center; gap: 12px; padding: 9px 6px; }
.svc-label { font-size: var(--app-font-size-md); color: var(--app-text-muted); min-width: 88px; }
.svc-value { display: flex; align-items: center; gap: 6px; font-size: var(--app-font-size-md); color: var(--app-text-secondary); }
.svc-dot { display: flex; align-items: center; }
/* tools & dependencies: sub-group headings（只放标题，动作进卡片内容区） */
.dep-sub-head { margin: 10px 0 4px; }
/* ---- run-history retention（按规则清理 auto_tasks） ---- */
.prune-block { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--app-card-border); }
.prune-head { display: flex; align-items: center; gap: 8px; }
.prune-orphans { font-size: var(--app-font-size-xs); color: var(--app-yellow); }
.prune-hint { font-size: var(--app-font-size-sm); color: var(--app-text-muted); margin-top: 2px; }
.prune-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.prune-label { font-size: var(--app-font-size-sm); color: var(--app-text-secondary); }
.prune-num { width: 92px; }
.prune-sep { width: 1px; height: 14px; background: var(--app-card-border); margin: 0 4px; }
.prune-actions { display: flex; align-items: center; gap: 6px; margin-top: 8px; }
</style>
