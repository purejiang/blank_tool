<template>
  <div class="settings-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('settings.title') }}</h1>
        <p class="page-subtitle">{{ t('settings.subtitle') }}</p>
      </div>
      <n-tag v-if="showSaved" type="success" size="small" :bordered="false" class="saved-tag">
        <template #icon><n-icon><CheckCircle /></n-icon></template>
        {{ t('settings.savedIndicator') }}
      </n-tag>
    </div>

    <div class="settings-content">

      <!-- Appearance -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <n-icon size="18" color="#22C55E"><Monitor /></n-icon>
          <span class="section-title">{{ t('settings.appearance') }}</span>
        </div>
        <n-form label-placement="left" label-width="100" size="small" style="margin-top:12px;max-width:420px">
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
          <n-icon size="18" color="#3B82F6"><Settings2 /></n-icon>
          <span class="section-title">{{ t('settings.behavior') }}</span>
        </div>
        <n-form label-placement="left" label-width="100" size="small" style="margin-top:12px;max-width:420px">
          <n-form-item :label="t('settings.autoSave')">
            <n-switch v-model:value="general.autoSave" @update:value="saveGeneral" />
          </n-form-item>
          <n-form-item :label="t('settings.notifications')">
            <n-switch v-model:value="general.enableNotifications" @update:value="saveGeneral" />
          </n-form-item>
          <n-form-item :label="t('settings.timeout')">
            <n-input-number v-model:value="general.timeout" :min="10" :max="600" :step="10" @update:value="saveGeneral" style="width: 120px">
              <template #suffix>{{ t('settings.seconds') }}</template>
            </n-input-number>
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Paths -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <n-icon size="18" color="#F59E0B"><FolderOpen /></n-icon>
          <span class="section-title">{{ t('settings.environmentPaths') }}</span>
        </div>
        <n-form label-placement="left" label-width="100" size="small" style="margin-top:12px;max-width:420px">
          <n-form-item :label="t('settings.runtime')">
            <div class="environ-path-input" style="display:flex;align-items:center;gap:8px">
              <n-input :value="displayPaths.runtime" readonly style="width: 320px" placeholder=".\runtime" />
              <n-button size="small" @click="handleBrowseDirectory('runtime')">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                {{ t('settings.browse') }}
              </n-button>
            </div>
          </n-form-item>
          <n-form-item :label="t('settings.backend')">
            <div class="environ-path-input" style="display:flex;align-items:center;gap:8px">
              <n-input :value="displayPaths.server" readonly style="width: 320px" placeholder=".\backend" />
              <n-button size="small" @click="handleBrowseDirectory('server')">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                {{ t('settings.browse') }}
              </n-button>
            </div>
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Tool Paths -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <n-icon size="18" color="#22C55E"><Wrench /></n-icon>
          <span class="section-title">{{ t('settings.toolPaths') }}</span>
        </div>
        <div class="tool-path-list">
          <div v-for="tool in toolList" :key="tool.name" class="tool-path-row">
            <span class="tool-path-name">{{ tool.name }}</span>
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
            <n-icon v-else-if="tool.status === 'available'" size="16" color="#22C55E"><CheckCircle /></n-icon>
            <n-icon v-else size="16" color="#F59E0B"><AlertCircle /></n-icon>
          </div>
        </div>
      </n-card>

      <!-- Signature Configs -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header" style="margin-bottom:12px">
          <n-icon size="18" color="#F59E0B"><Key /></n-icon>
          <span class="section-title">{{ t('signature.title') }}</span>
          <n-button size="tiny" type="primary" secondary style="margin-left:auto" @click="openAddSignature">
            <template #icon><n-icon size="14"><Plus /></n-icon></template>
          </n-button>
        </div>
        <div v-if="sigConfigs.length === 0" class="info-empty">{{ t('signature.empty') }}</div>
        <div v-else class="sig-list">
          <div v-for="cfg in sigConfigs" :key="cfg.id" class="sig-item">
            <div class="sig-info">
              <span class="sig-name">{{ cfg.name }}</span>
              <span class="sig-detail">{{ cfg.alias }}</span>
              <span class="sig-path" :title="cfg.path">{{ cfg.path }}</span>
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

      <!-- Storage -->
      <n-card :bordered="false" class="settings-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <div class="section-header" style="margin-bottom:0">
            <n-icon size="18" color="#8B5CF6"><Database /></n-icon>
            <span class="section-title">{{ t('settings.storage') }}</span>
          </div>
          <n-button size="tiny" quaternary @click="refreshCache" :loading="isLoadingCacheInfo">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
          </n-button>
        </div>
        <div class="storage-grid">
          <div class="storage-item">
            <div class="storage-label">{{ t('settings.cache') }}</div>
            <div class="storage-value">{{ formatFileSize(cacheInfo.cache.size) }}</div>
            <div class="storage-sub">{{ cacheFilesText }}</div>
          </div>
          <div class="storage-item">
            <div class="storage-label">{{ t('settings.output') }}</div>
            <div class="storage-value">{{ formatFileSize(cacheInfo.output.size) }}</div>
            <div class="storage-sub">{{ outputFilesText }}</div>
          </div>
          <div class="storage-item">
            <div class="storage-label">{{ t('settings.total') }}</div>
            <div class="storage-value">{{ formatFileSize(cacheInfo.total.size) }}</div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:16px">
          <n-button type="warning" size="small" @click="clearStorage('cache')" :loading="isClearingCache">
            <template #icon><n-icon><Trash2 /></n-icon></template>
            {{ t('settings.clearCache') }}
          </n-button>
          <n-button type="warning" size="small" @click="clearStorage('output')" :loading="isClearingOutput">
            <template #icon><n-icon><Download /></n-icon></template>
            {{ t('settings.clearOutput') }}
          </n-button>
        </div>
      </n-card>

    </div>

    <SignatureEditModal :visible="sigModalVisible" :data="sigEditing" @update:visible="(v: boolean) => sigModalVisible = v" @save="handleSignatureSave" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { FolderOpen, Trash2, Download, RefreshCw, Cpu, Monitor, Layers, Settings2, Database, CheckCircle, Wrench, Key, Plus, Edit, Loader2, AlertCircle } from 'lucide-vue-next'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { useSystemStore, useToolStore } from '@stores/index'
import { storeToRefs } from 'pinia'
import { useSignatureStore } from '@stores/signatureStore'
import SignatureEditModal from '@components/package/SignatureEditModal.vue'

const { t } = useI18n()
const { showSuccess, showError } = useNotification()
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
  const toolsArr = tools.value || tools
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

const general = reactive({ language: 'zh-CN', theme: 'auto', autoSave: true, enableNotifications: true, timeout: 300 })
const pathSettings = reactive({ runtime: '.\\runtime', server: '.\\backend' })
const displayPaths = reactive({ runtime: '', server: '' })
const cacheInfo = ref({ cache: { size: 0, files: 0 }, output: { size: 0, files: 0 }, total: { size: 0, files: 0 } })
const isClearingCache = ref(false)
const isClearingOutput = ref(false)
const isLoadingCacheInfo = ref(false)
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
const cacheFilesText = computed(() => t('settings.files', { count: cacheInfo.value.cache.files }))
const outputFilesText = computed(() => t('settings.files', { count: cacheInfo.value.output.files }))
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
  } catch (e) { console.error('Failed to load settings:', e) }
}

const saveGeneral = async () => {
  setLocale(general.language)
  await setTheme(general.theme)
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ ...general })
    triggerSaved()
  } catch (e: any) { showError(t('settings.saveFailed'), e.message) }
}

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
  isLoadingCacheInfo.value = true
  try {
    const svc = await serviceManager.getService('cache')
    const info = await svc.getCacheInfo(true)
    if (info) cacheInfo.value = info
  } catch (e) { console.error('Failed to refresh cache:', e) }
  finally { isLoadingCacheInfo.value = false }
}

const clearStorage = async (target: 'cache' | 'output') => {
  if (target === 'cache') isClearingCache.value = true
  else isClearingOutput.value = true
  try {
    const svc = await serviceManager.getService('cache')
    const result = await svc.clearStorage(target)
    if (result.success) { showSuccess(t('settings.storageCleared')); await refreshCache() }
    else showError(t('settings.clearFailed'), result.error)
  } catch (e: any) { showError(t('settings.clearFailed'), e.message) }
  finally {
    if (target === 'cache') isClearingCache.value = false
    else isClearingOutput.value = false
  }
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
  loadSettings()
  refreshCache()
  sigStore.loadConfigs()
  toolStore.fetchCustomPaths().then(() => {
    Object.assign(customPathOverrides, toolStore.customPaths)
    Object.assign(toolPaths, toolStore.customPaths)
  })
})
</script>

<style scoped>
.settings-page { max-width: 740px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-family: Inter, sans-serif; font-size: 22px; font-weight: 700; color: var(--app-text-primary); margin: 0; letter-spacing: -0.02em; }
.page-subtitle { font-size: 13px; color: var(--app-text-muted); margin: 4px 0 0; }
.saved-tag { margin-top: 4px; transition: opacity 0.3s; }
.settings-content { display: flex; flex-direction: column; gap: 16px; }
.settings-card { background: var(--app-card-bg); border-radius: 10px; }
.section-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; justify-content: flex-start; }
.section-title { font-family: Inter, sans-serif; font-size: 15px; font-weight: 600; color: var(--app-text-primary); }
.storage-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.storage-item { text-align: center; padding: 12px; background: var(--app-storage-bg); border-radius: 8px; }
.storage-label { font-size: 12px; color: var(--app-text-muted); margin-bottom: 4px; }
.storage-value { font-size: 18px; font-weight: 600; color: var(--app-green); font-variant-numeric: tabular-nums; }
.storage-sub { font-size: 11px; color: var(--app-text-dim); margin-top: 2px; }
.info-grid { display: flex; flex-direction: column; gap: 10px; }
.info-row { display: flex; align-items: baseline; gap: 12px; padding: 6px 0; border-bottom: 1px solid rgba(51,65,85,0.3); }
.info-row:last-child { border-bottom: none; }
.info-label { font-size: 13px; color: var(--app-text-muted); min-width: 100px; }
.info-val { font-size: 13px; color: var(--app-text-secondary); font-family: 'Fira Code', monospace; min-width: 80px; }
.info-path { font-size: 12px; color: var(--app-text-dim); font-family: 'Fira Code', monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; text-align: right; }
.info-empty { font-size: 13px; color: var(--app-text-dim); padding: 8px 0; }

.sig-list { display: flex; flex-direction: column; gap: 6px; }
.sig-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; background: var(--app-storage-bg); border-radius: 8px; gap: 8px; }
.sig-info { display: flex; align-items: center; gap: 12px; min-width: 0; flex: 1; }
.sig-name { font-size: 13px; font-weight: 600; color: var(--app-text-primary); white-space: nowrap; }
.sig-detail { font-size: 12px; color: var(--app-text-dim); white-space: nowrap; }
.sig-path { font-size: 11px; color: var(--app-text-dim); font-family: 'Fira Code', monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }

.tool-path-list { display: flex; flex-direction: column; gap: 8px; }
.tool-path-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
.tool-path-name { font-size: 13px; font-weight: 600; color: var(--app-text-primary); min-width: 90px; font-family: 'Fira Code', monospace; padding-left: 4px; }
.tool-path-input-wrap { display: flex; align-items: center; gap: 4px; flex: 1; }
.tool-path-input-wrap :deep(.n-input .n-input__input-el) { color: var(--app-text-muted); }
.environ-path-input :deep(.n-input .n-input__input-el) { color: var(--app-text-muted); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
