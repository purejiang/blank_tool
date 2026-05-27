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
        <n-form label-placement="left" label-width="140" size="small" style="margin-top:12px">
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
        <n-form label-placement="left" label-width="140" size="small" style="margin-top:12px">
          <n-form-item :label="t('settings.autoSave')">
            <n-switch v-model:value="general.autoSave" @update:value="saveGeneral" />
          </n-form-item>
          <n-form-item :label="t('settings.notifications')">
            <n-switch v-model:value="general.enableNotifications" @update:value="saveGeneral" />
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Paths -->
      <n-card :bordered="false" class="settings-card">
        <div class="section-header">
          <n-icon size="18" color="#F59E0B"><FolderOpen /></n-icon>
          <span class="section-title">{{ t('settings.environmentPaths') }}</span>
        </div>
        <n-form label-placement="left" label-width="140" size="small" style="margin-top:12px">
          <n-form-item :label="t('settings.runtime')">
            <div style="display:flex;align-items:center;gap:8px">
              <n-input :value="displayPaths.runtime" readonly style="width: 320px" placeholder=".\runtime" />
              <n-button size="small" @click="handleBrowseDirectory('runtime')">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                {{ t('settings.browse') }}
              </n-button>
            </div>
          </n-form-item>
          <n-form-item :label="t('settings.backend')">
            <div style="display:flex;align-items:center;gap:8px">
              <n-input :value="displayPaths.server" readonly style="width: 320px" placeholder=".\backend" />
              <n-button size="small" @click="handleBrowseDirectory('server')">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                {{ t('settings.browse') }}
              </n-button>
            </div>
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Storage -->
      <n-card :bordered="false" class="settings-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <div class="section-header">
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

      <!-- System Info -->
      <n-card :bordered="false" class="settings-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <div class="section-header">
            <n-icon size="18" color="#64748B"><Cpu /></n-icon>
            <span class="section-title">{{ t('settings.systemInfo') }}</span>
          </div>
          <n-button size="tiny" quaternary @click="systemStore.fetchSystemInfo()">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
          </n-button>
        </div>
        <div class="info-grid">
          <div class="info-row"><span class="info-label">{{ t('settings.os') }}</span><span class="info-val">{{ systemInfo.platform || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.architecture') }}</span><span class="info-val">{{ systemInfo.architecture || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.hostname') }}</span><span class="info-val">{{ systemInfo.hostname || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.cpu') }}</span><span class="info-val">{{ cpuText }}</span></div>
        </div>
      </n-card>

      <!-- Build Info -->
      <n-card :bordered="false" class="settings-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <div class="section-header">
            <n-icon size="18" color="#64748B"><Layers /></n-icon>
            <span class="section-title">{{ t('settings.buildInfo') }}</span>
          </div>
          <n-button size="tiny" quaternary @click="systemStore.fetchBuildInfo()">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
          </n-button>
        </div>
        <div class="info-grid">
          <div class="info-row"><span class="info-label">{{ t('settings.appVersion') }}</span><span class="info-val">{{ buildInfo.appVersion || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.electron') }}</span><span class="info-val">{{ buildInfo.electronVersion || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.nodeJs') }}</span><span class="info-val">{{ buildInfo.nodeVersion || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.python') }}</span><span class="info-val">{{ buildInfo.pythonVersion || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.chrome') }}</span><span class="info-val">{{ buildInfo.chromeVersion || '-' }}</span></div>
        </div>
      </n-card>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { FolderOpen, Trash2, Download, RefreshCw, Cpu, Monitor, Layers, Settings2, Database, CheckCircle } from 'lucide-vue-next'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { useSystemStore } from '@stores/index'

const { t } = useI18n()
const { showSuccess, showError } = useNotification()
const setLocale = inject<(lang: string) => void>('setLocale', () => {})
const systemStore = useSystemStore()

const showSaved = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | null = null
const triggerSaved = () => {
  showSaved.value = true
  if (savedTimer) clearTimeout(savedTimer)
  savedTimer = setTimeout(() => { showSaved.value = false }, 2000)
}

const general = reactive({ language: 'zh-CN', theme: 'auto', autoSave: true, enableNotifications: true })
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
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ ...general })
    setLocale(general.language)
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

onMounted(() => { loadSettings(); refreshCache() })
</script>

<style scoped>
.settings-page { max-width: 740px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-family: Inter, sans-serif; font-size: 22px; font-weight: 700; color: #F8FAFC; margin: 0; letter-spacing: -0.02em; }
.page-subtitle { font-size: 13px; color: #94A3B8; margin: 4px 0 0; }
.saved-tag { margin-top: 4px; transition: opacity 0.3s; }
.settings-content { display: flex; flex-direction: column; gap: 16px; }
.settings-card { background: #1E293B; border-radius: 10px; }
.section-header { display: flex; align-items: center; gap: 10px; }
.section-title { font-family: Inter, sans-serif; font-size: 15px; font-weight: 600; color: #F8FAFC; }
.storage-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.storage-item { text-align: center; padding: 12px; background: rgba(15,23,42,0.5); border-radius: 8px; }
.storage-label { font-size: 12px; color: #94A3B8; margin-bottom: 4px; }
.storage-value { font-size: 18px; font-weight: 600; color: #22C55E; font-variant-numeric: tabular-nums; }
.storage-sub { font-size: 11px; color: #64748B; margin-top: 2px; }
.info-grid { display: flex; flex-direction: column; gap: 10px; }
.info-row { display: flex; align-items: baseline; gap: 12px; padding: 6px 0; border-bottom: 1px solid rgba(51,65,85,0.3); }
.info-row:last-child { border-bottom: none; }
.info-label { font-size: 13px; color: #94A3B8; min-width: 100px; }
.info-val { font-size: 13px; color: #E2E8F0; font-family: 'Fira Code', monospace; }
</style>
