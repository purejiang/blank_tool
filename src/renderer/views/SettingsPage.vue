<template>
  <div class="screen settings-page">
    <PageHeader :title="t('settings.title')" :description="t('settings.subtitle')">
      <template #actions>
        <AppBadge v-if="showSaved" tone="success" :bordered="false" class="saved-tag">
          <template #icon><AppIcon name="check" /></template>
          {{ t('settings.savedIndicator') }}
        </AppBadge>
      </template>
    </PageHeader>

    <div class="settings-content">

      <!-- Appearance -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <AppIcon name="monitor" size="lg" style="color: var(--success-text)" />
          <span class="section-title">{{ t('settings.appearance') }}</span>
        </div>
        <n-form label-placement="left" label-width="120" size="small" style="margin-top:12px">
          <n-form-item :label="t('settings.language')">
            <n-select v-model:value="general.language" @update:value="saveGeneral"
              :options="langOptions" style="width: 220px" />
          </n-form-item>
          <n-form-item :label="t('settings.theme')">
            <n-select v-model:value="general.theme" @update:value="saveGeneral"
              :options="themeOptions" style="width: 220px" />
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Behavior -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <AppIcon name="set" size="lg" style="color: var(--primary)" />
          <span class="section-title">{{ t('settings.behavior') }}</span>
        </div>
        <n-form label-placement="left" label-width="120" size="small" style="margin-top:12px">
          <n-form-item :label="t('settings.notifications')">
            <n-switch v-model:value="general.enableNotifications" @update:value="saveGeneral" />
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Nodes：节点级默认设置。删除任务时清理输出文件已是默认行为（不再可配），
           节点超时等默认值后续落在这里。 -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <AppIcon name="layers" size="lg" style="color: var(--primary)" />
          <span class="section-title">{{ t('settings.nodes') }}</span>
        </div>
        <div class="form-hint" style="margin-top:12px">{{ t('settings.nodesEmpty') }}</div>
      </n-card>

      <!-- Logging -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <AppIcon name="file" size="lg" style="color: var(--success-text)" />
          <span class="section-title">{{ t('settings.logging') }}</span>
        </div>
        <n-form label-placement="left" label-width="120" size="small" style="margin-top:12px">
          <n-form-item :label="t('settings.loggingLevel')">
            <n-select v-model:value="logLevel" @update:value="saveLogLevel"
              :options="logLevelOptions" style="width: 220px" />
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Paths -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <AppIcon name="folder" size="lg" style="color: var(--warning-text)" />
          <span class="section-title">{{ t('settings.environmentPaths') }}</span>
        </div>
        <n-form label-placement="left" label-width="120" size="small" style="margin-top:12px">
          <n-form-item :label="t('settings.runtime')">
            <div class="environ-path-input">
              <n-input :value="displayPaths.runtime" readonly class="environ-path-field" placeholder=".\runtime" />
              <n-button size="small" @click="handleBrowseDirectory('runtime')">
                <template #icon><AppIcon name="folder" /></template>
                {{ t('settings.browse') }}
              </n-button>
            </div>
          </n-form-item>
          <n-form-item :label="t('settings.backend')">
            <div class="environ-path-input">
              <n-input :value="displayPaths.server" readonly class="environ-path-field" placeholder=".\cli" />
              <n-button size="small" @click="handleBrowseDirectory('server')">
                <template #icon><AppIcon name="folder" /></template>
                {{ t('settings.browse') }}
              </n-button>
            </div>
          </n-form-item>
          <div class="form-hint" style="margin-bottom:8px">{{ t('settings.pathsRestartHint') }}</div>
        </n-form>
      </n-card>

      <!-- 工具路径已收敛到 /tools（docs/07 §2-7 / docs/08 缺口 #19）：这里只留跳转入口 -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <AppIcon name="tool" size="lg" style="color: var(--success-text)" />
          <span class="section-title">{{ t('settings.toolPaths') }}</span>
        </div>
        <div class="more-links">
          <n-button size="small" @click="router.push('/tools')">
            <template #icon><AppIcon name="tool" /></template>
            {{ t('settings.toolPathsGo') }}
          </n-button>
          <span class="more-hint">{{ t('settings.toolPathsMoved') }}</span>
        </div>
      </n-card>

      <!-- Storage -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header" style="margin-bottom:12px">
          <AppIcon name="drive" size="lg" style="color: var(--primary)" />
          <span class="section-title">{{ t('settings.storage') }}</span>
          <span class="storage-total-text">{{ formatFileSize(cacheInfo.total.size) }}</span>
        </div>

        <!-- Proportional bar -->
        <div class="storage-bar" v-if="cacheInfo.total.size > 0">
          <div
            v-for="cat in storageCategories"
            :key="cat.key"
            class="storage-bar-seg"
            :style="{ width: barWidth(cat.key), background: cat.color }"
            :title="t(cat.label) + ' ' + formatFileSize(getCatSize(cat.key))"
          />
        </div>

        <!-- Category rows -->
        <div class="storage-rows">
          <div v-for="cat in storageCategories" :key="cat.key" class="storage-row">
            <div class="storage-row-icon" :style="{ color: cat.color }">
              <AppIcon :name="cat.icon" />
            </div>
            <div class="storage-row-info">
              <div class="storage-row-label">{{ t(cat.label) }}</div>
              <div class="storage-row-sub">{{ formatFileSize(getCatSize(cat.key)) }} · {{ getCatFiles(cat.key) }} {{ t('settings.filesUnit') }}</div>
            </div>
            <AppButton
              variant="danger-ghost"
              size="tiny"
              icon-only
              :aria-label="t('settings.clearCategory')"
              :title="t('settings.clearCategory')"
              :loading="clearingTarget === cat.key"
              :disabled="getCatSize(cat.key) === 0"
              @click="confirmClear(cat.key)"
            >
              <template #icon><AppIcon name="trash" size="sm" /></template>
            </AppButton>
          </div>
        </div>

        <!-- Clear all -->
        <div style="margin-top:12px">
          <AppButton
            variant="danger-ghost"
            block
            :loading="clearingTarget === 'all'"
            :disabled="cacheInfo.total.size === 0"
            @click="confirmClear('all')"
          >
            <template #icon><AppIcon name="trash" /></template>
            {{ t('settings.clearAllStorage') }}
          </AppButton>
        </div>
      </n-card>

      <!-- 二级页入口（docs/08 §2.1/§3-S7）：诊断与关于不进侧边栏，从这里进入 -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <AppIcon name="archive" size="lg" style="color: var(--text-muted)" />
          <span class="section-title">{{ t('settings.more') }}</span>
        </div>
        <div class="more-links">
          <n-button size="small" @click="router.push('/diagnostics')">
            <template #icon><AppIcon name="activity" /></template>
            {{ t('diagnostics.title') }}
          </n-button>
          <n-button size="small" @click="router.push('/about')">
            <template #icon><AppIcon name="info" /></template>
            {{ t('nav.about') }}
          </n-button>
          <span class="more-hint">{{ t('settings.moreHint') }}</span>
        </div>
      </n-card>

    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, useDialog } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'
import AppBadge from '@components/ui/AppBadge.vue'
import AppButton from '@components/ui/AppButton.vue'
import PageHeader from '@components/ui/PageHeader.vue'
import serviceManager from '@services/ServiceManager'
import { log, setLogLevel } from '@utils/logger'
import { useNotification } from '@composables/useNotification'
import { useSystemStore, useToolStore } from '@stores/index'
import { storeToRefs } from 'pinia'

const { t } = useI18n()
const router = useRouter()
const { showSuccess, showError } = useNotification()
const dialog = useDialog()
const setLocale = inject<(lang: string) => void>('setLocale', () => {})
const setTheme = inject<(mode: string) => Promise<void>>('setTheme', async () => {})
const systemStore = useSystemStore()
const toolStore = useToolStore()

const validatingTool = ref<string | null>(null)
const resettingTool = ref<string | null>(null)
const customPathOverrides = reactive<Record<string, string>>({})
const toolPaths = reactive<Record<string, string>>({})

const toolList = computed(() => {
  const toolsArr = toolStore.tools
  return []
})

const openAddSignature = () => {}

const handleSignatureSave = async (data: any) => {}

const deleteSignature = async (id: string) => {}

const showSaved = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | null = null
const triggerSaved = () => {
  showSaved.value = true
  if (savedTimer) clearTimeout(savedTimer)
  savedTimer = setTimeout(() => { showSaved.value = false }, 2000)
}

const general = reactive({ language: 'zh-CN', theme: 'auto', enableNotifications: false })
const logLevel = ref('info')
const logLevelOptions = [
  { label: 'Debug', value: 'debug' },
  { label: 'Info', value: 'info' },
  { label: 'Warn', value: 'warn' },
  { label: 'Error', value: 'error' },
]
const pathSettings = reactive({ runtime: '.\\runtime', server: '.\\cli' })
const displayPaths = reactive({ runtime: '', server: '' })
const cacheInfo = ref({
  tasks: { size: 0, files: 0 },
  output: { size: 0, files: 0 },
  logs: { size: 0, files: 0 },
  total: { size: 0, files: 0 }
})
const clearingTarget = ref<string | null>(null)
const systemInfo = systemStore.systemInfo
const buildInfo = systemStore.buildInfo

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
  { key: 'tasks',   label: 'settings.tasks',   icon: 'archive',      color: 'var(--warning-text)' },
  { key: 'output',  label: 'settings.output',  icon: 'archive',      color: 'var(--primary)' },
  { key: 'logs',    label: 'settings.logs',    icon: 'file',         color: 'var(--success-text)' },
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

const formatFileSize = (bytes: number) => {
  if (!bytes) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`
}

const loadSettings = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    const model = await svc.loadSettingsModel()
    if (model?.settings) {
      const s = model.settings as Record<string, unknown>
      for (const key of Object.keys(general)) {
        if (Object.prototype.hasOwnProperty.call(s, key)) (general as any)[key] = s[key]
      }
      if (s.runtime) pathSettings.runtime = s.runtime as string
      if (s.server) pathSettings.server = s.server as string
    }
    if (model?.displayPaths) {
      displayPaths.runtime = model.displayPaths.runtime || ''
      displayPaths.server = model.displayPaths.server || ''
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

// 写 `commands.timeout`（毫秒）的界面入口已移除：请求超时是内部实现细节
// （主进程启动时读一次），设置页不再暴露；节点级超时后续挪到「节点」卡片。
const savePaths = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ runtime: pathSettings.runtime, server: pathSettings.server })
    triggerSaved()
  } catch (e: any) { showError(t('settings.pathsFailed'), e.message) }
}

const handleBrowseDirectory = async (target: 'runtime' | 'server') => {
  try {
    const svc = await serviceManager.getService('system')
    const result = await svc.selectDirectory({ title: t('settings.selectDir') })
    if (result?.directoryPath) {
      pathSettings[target] = result.directoryPath
      const settingsSvc = await serviceManager.getService('settings')
      const paths = await settingsSvc.resolveDisplayPaths(pathSettings)
      displayPaths.runtime = paths.runtime || ''
      displayPaths.server = paths.server || ''
      await savePaths()
    }
  } catch (e) { showError(t('settings.selectDirFailed')) }
}

const refreshCache = async () => {
  try {
    const svc = await serviceManager.getService('cache')
    const info = await svc.getCacheInfo(true)
    if (info) cacheInfo.value = info
  } catch (e) { log.error('Failed to refresh cache:', e) }
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
  toolStore.fetchCustomPaths().then(() => {
    Object.assign(customPathOverrides, toolStore.customPaths)
    Object.assign(toolPaths, toolStore.customPaths)
  })
})
</script>

<style scoped>
/* 页面宽度交给外壳（满宽）；mock 遗留的 max-width:740px 会导致页面之间宽窄不一。 */
.saved-tag { margin-top: 4px; transition: opacity 0.3s; }
/* 满宽后卡片改栅格（窄屏自动回落单列），避免长条卡片右侧空一大截。
 * 下限 460px 让 1600 视口下是舒服的两列；太窄的列会让 label-width:100 的表单挤爆。 */
.settings-content {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
  gap: 16px;
  align-items: start;
}
/* naive 的 .n-form-item-blank 默认不带 min-width:0，列变窄时输入框会把同行按钮挤出去 */
.settings-card :deep(.n-form-item-blank) { min-width: 0; }
/* 极简：静止态只留 1px 描边，hover 才升起 */
.settings-card {
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-card);
  transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}
.settings-card:hover { box-shadow: var(--shadow-lift); border-color: var(--primary-soft-border); transform: translateY(-1px); }
.section-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; justify-content: flex-start; }
.section-title { font-family: var(--font-family-base); font-size: 15px; font-weight: 600; color: var(--app-text-primary); }
.form-hint { font-size: 11px; color: var(--app-text-dim); margin-top: 4px; }
.storage-total-text { font-size: 16px; font-weight: 600; color: var(--app-green); font-variant-numeric: tabular-nums; margin-left: auto; margin-right: 12px; }
.storage-bar { display: flex; height: 6px; border-radius: var(--radius-chip); overflow: hidden; background: var(--app-storage-bg); margin-bottom: 12px; }
.storage-bar-seg { height: 100%; transition: width 0.3s ease; }
.storage-rows { display: flex; flex-direction: column; gap: 2px; }
.storage-row { display: flex; align-items: center; gap: 10px; padding: 8px 4px; border-radius: var(--radius-chip); }
.storage-row:hover { background: var(--app-storage-bg); }
.storage-row-icon { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: var(--radius-chip); background: var(--app-storage-bg); flex-shrink: 0; }
.storage-row-info { flex: 1; min-width: 0; }
.storage-row-label { font-size: 13px; font-weight: 600; color: var(--app-text-primary); }
.storage-row-sub { font-size: 11px; color: var(--app-text-muted); margin-top: 1px; }
.more-links { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.more-hint { font-size: 11px; color: var(--app-text-dim); }

/* 工具路径已收敛到 /tools，这里只剩跳转入口 */
.environ-path-input { display: flex; align-items: center; gap: 8px; }
.environ-path-field { flex: 1 1 auto; min-width: 0; max-width: 420px; }
.environ-path-input :deep(.n-input .n-input__input-el) { color: var(--app-text-muted); }
</style>
