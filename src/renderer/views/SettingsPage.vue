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
      <!-- Section: Appearance -->
      <n-card :bordered="false" class="settings-card">
        <template #header>
          <div class="section-header">
            <n-icon size="18" color="#22C55E"><Monitor /></n-icon>
            <span class="section-title">{{ t('settings.appearance') }}</span>
          </div>
        </template>
        <n-form label-placement="left" label-width="140" size="small">
          <n-form-item :label="t('settings.language')">
            <n-select v-model:value="general.language" @update:value="saveGeneral" :options="[
              { label: t('settings.simplifiedChinese'), value: 'zh-CN' },
              { label: t('settings.english'), value: 'en-US' },
            ]" style="width: 220px" />
          </n-form-item>
          <n-form-item :label="t('settings.theme')">
            <n-select v-model:value="general.theme" @update:value="saveGeneral" :options="[
              { label: t('settings.themeAuto'), value: 'auto' },
              { label: t('settings.themeLight'), value: 'light' },
              { label: t('settings.themeDark'), value: 'dark' },
            ]" style="width: 220px" />
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Section: Behavior -->
      <n-card :bordered="false" class="settings-card">
        <template #header>
          <div class="section-header">
            <n-icon size="18" color="#3B82F6"><Settings2 /></n-icon>
            <span class="section-title">{{ t('settings.behavior') }}</span>
          </div>
        </template>
        <n-form label-placement="left" label-width="140" size="small">
          <n-form-item :label="t('settings.autoSave')">
            <n-switch v-model:value="general.autoSave" @update:value="saveGeneral" />
          </n-form-item>
          <n-form-item :label="t('settings.notifications')">
            <n-switch v-model:value="general.enableNotifications" @update:value="saveGeneral" />
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Section: Paths -->
      <n-card :bordered="false" class="settings-card">
        <template #header>
          <div class="section-header">
            <n-icon size="18" color="#F59E0B"><FolderOpen /></n-icon>
            <span class="section-title">{{ t('settings.environmentPaths') }}</span>
          </div>
        </template>
        <n-form label-placement="left" label-width="140" size="small">
          <n-form-item :label="t('settings.runtime')">
            <n-space>
              <n-input :value="displayPaths.runtime" readonly style="width: 320px" placeholder=".\runtime" />
              <n-button size="small" @click="handleBrowseDirectory('runtime')">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                {{ t('settings.browse') }}
              </n-button>
            </n-space>
          </n-form-item>
          <n-form-item :label="t('settings.backend')">
            <n-space>
              <n-input :value="displayPaths.server" readonly style="width: 320px" placeholder=".\backend" />
              <n-button size="small" @click="handleBrowseDirectory('server')">
                <template #icon><n-icon><FolderOpen /></n-icon></template>
                {{ t('settings.browse') }}
              </n-button>
            </n-space>
          </n-form-item>
        </n-form>
      </n-card>

      <!-- Section: Storage -->
      <n-card :bordered="false" class="settings-card">
        <template #header>
          <div class="section-header">
            <n-icon size="18" color="#8B5CF6"><Database /></n-icon>
            <span class="section-title">{{ t('settings.storage') }}</span>
          </div>
          <template #header-extra>
            <n-button size="tiny" quaternary @click="refreshCache" :loading="isLoadingCacheInfo">
              <template #icon><n-icon><RefreshCw /></n-icon></template>
            </n-button>
          </template>
        </template>
        <n-grid :cols="3" :x-gap="12">
          <n-grid-item>
            <n-statistic :label="t('settings.cache')" :value="formatFileSize(cacheInfo.cache.size)">
              <template #suffix>{{ cacheFilesText }}</template>
            </n-statistic>
          </n-grid-item>
          <n-grid-item>
            <n-statistic :label="t('settings.output')" :value="formatFileSize(cacheInfo.output.size)">
              <template #suffix>{{ outputFilesText }}</template>
            </n-statistic>
          </n-grid-item>
          <n-grid-item>
            <n-statistic :label="t('settings.total')" :value="formatFileSize(cacheInfo.total.size)" />
          </n-grid-item>
        </n-grid>
        <n-space style="margin-top: 16px">
          <n-button type="warning" size="small" @click="clearStorage('cache')" :loading="isClearingCache">
            <template #icon><n-icon><Trash2 /></n-icon></template>
            {{ t('settings.clearCache') }}
          </n-button>
          <n-button type="warning" size="small" @click="clearStorage('output')" :loading="isClearingOutput">
            <template #icon><n-icon><Download /></n-icon></template>
            {{ t('settings.clearOutput') }}
          </n-button>
        </n-space>
      </n-card>

      <!-- Section: System Info -->
      <n-card :bordered="false" class="settings-card">
        <template #header>
          <div class="section-header">
            <n-icon size="18" color="#64748B"><Cpu /></n-icon>
            <span class="section-title">{{ t('settings.systemInfo') }}</span>
          </div>
          <template #header-extra>
            <n-button size="tiny" quaternary @click="systemStore.fetchSystemInfo()">
              <template #icon><n-icon><RefreshCw /></n-icon></template>
            </n-button>
          </template>
        </template>
        <n-descriptions label-placement="left" :column="2" size="small">
          <n-descriptions-item :label="t('settings.os')">{{ systemInfo.platform || '-' }}</n-descriptions-item>
          <n-descriptions-item :label="t('settings.architecture')">{{ systemInfo.architecture || '-' }}</n-descriptions-item>
          <n-descriptions-item :label="t('settings.hostname')">{{ systemInfo.hostname || '-' }}</n-descriptions-item>
          <n-descriptions-item :label="t('settings.cpu')">{{ cpuText }}</n-descriptions-item>
        </n-descriptions>
      </n-card>

      <!-- Section: Build Info -->
      <n-card :bordered="false" class="settings-card">
        <template #header>
          <div class="section-header">
            <n-icon size="18" color="#64748B"><Layers /></n-icon>
            <span class="section-title">{{ t('settings.buildInfo') }}</span>
          </div>
          <template #header-extra>
            <n-button size="tiny" quaternary @click="systemStore.fetchBuildInfo()">
              <template #icon><n-icon><RefreshCw /></n-icon></template>
            </n-button>
          </template>
        </template>
        <n-descriptions label-placement="left" :column="2" size="small">
          <n-descriptions-item :label="t('settings.appVersion')">{{ buildInfo.appVersion || '-' }}</n-descriptions-item>
          <n-descriptions-item :label="t('settings.electron')">{{ buildInfo.electronVersion || '-' }}</n-descriptions-item>
          <n-descriptions-item :label="t('settings.nodeJs')">{{ buildInfo.nodeVersion || '-' }}</n-descriptions-item>
          <n-descriptions-item :label="t('settings.python')">{{ buildInfo.pythonVersion || '-' }}</n-descriptions-item>
          <n-descriptions-item :label="t('settings.chrome')">{{ buildInfo.chromeVersion || '-' }}</n-descriptions-item>
        </n-descriptions>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import {
  Save, RotateCcw, FolderOpen, Trash2, Download, RefreshCw,
  Cpu, Monitor, Layers, Settings2, Database, CheckCircle
} from 'lucide-vue-next'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { useToolStore, useSystemStore } from '@stores/index'

const { t } = useI18n()
const { showSuccess, showError } = useNotification()

// Computed texts to avoid complex template expressions in slots
const cacheFilesText = computed(() => t('settings.files', { count: cacheInfo.value.cache.files }))
const outputFilesText = computed(() => t('settings.files', { count: cacheInfo.value.output.files }))
const cpuText = computed(() => {
  const count = systemInfo.cpuCount || '0'
  return `${count} ${t('device.cores', { count: Number(count) || 0 })}`
})
const setLocale = inject<(lang: string) => void>('setLocale', () => {})
const toolStore = useToolStore()
const systemStore = useSystemStore()

// --- Auto-save indicator ---
const showSaved = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | null = null

const triggerSaved = () => {
  showSaved.value = true
  if (savedTimer) clearTimeout(savedTimer)
  savedTimer = setTimeout(() => { showSaved.value = false }, 2000)
}

// --- General Settings ---
const general = reactive({
  language: 'zh-CN',
  theme: 'auto',
  autoSave: true,
  enableNotifications: true,
})

// --- Path Settings ---
const pathSettings = reactive({ runtime: '.\\runtime', server: '.\\backend' })
const displayPaths = reactive({ runtime: '', server: '' })

// --- Cache ---
const cacheInfo = ref({ cache: { size: 0, files: 0 }, output: { size: 0, files: 0 }, total: { size: 0, files: 0 } })
const isClearingCache = ref(false)
const isClearingOutput = ref(false)
const isLoadingCacheInfo = ref(false)

// --- System Info ---
const systemInfo = systemStore.systemInfo
const buildInfo = systemStore.buildInfo

const formatFileSize = (bytes: number) => {
  if (!bytes) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`
}

// --- Load settings ---
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

// --- Auto-save methods ---
const saveGeneral = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ ...general })
    setLocale(general.language)
    triggerSaved()
  } catch (e: any) {
    showError(t('settings.saveFailed'), e.message)
  }
}

const savePaths = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ runtime: pathSettings.runtime, server: pathSettings.server })
    triggerSaved()
  } catch (e: any) {
    showError(t('settings.pathsFailed'), e.message)
  }
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
  } catch (e) {
    showError(t('settings.selectDirFailed'))
  }
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
    if (result.success) {
      showSuccess(t('settings.storageCleared'))
      await refreshCache()
    } else {
      showError(t('settings.clearFailed'), result.error)
    }
  } catch (e: any) {
    showError(t('settings.clearFailed'), e.message)
  }
  finally {
    if (target === 'cache') isClearingCache.value = false
    else isClearingOutput.value = false
  }
}

onMounted(() => {
  loadSettings()
  refreshCache()
})
</script>

<style scoped>
.settings-page {
  max-width: 740px;
  margin: 0 auto;
}
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
  color: #F8FAFC;
  margin: 0;
  letter-spacing: -0.02em;
}
.page-subtitle {
  font-size: 13px;
  color: #94A3B8;
  margin: 4px 0 0;
}
.saved-tag {
  margin-top: 4px;
  transition: opacity 0.3s;
}
.settings-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.settings-card {
  background: #1E293B;
  border-radius: 10px;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.section-title {
  font-family: Inter, sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: #F8FAFC;
}
</style>
