<script setup lang="ts">
import { ref, reactive, onMounted, computed, inject } from 'vue'
import { NIcon } from 'naive-ui'
import { Save, RotateCcw, FolderOpen, Trash2, Download, RefreshCw, Cpu, Monitor, Layers } from 'lucide-vue-next'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { useToolStore, useSystemStore } from '@stores/index'

const { showSuccess, showError } = useNotification()
const setLocale = inject<(lang: string) => void>('setLocale', () => {})
const toolStore = useToolStore()
const systemStore = useSystemStore()

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
const cacheInfo = ref({ cache: { size: 0, files: 0 }, output: { size: 0, files: 0 }, total: { size: 0, files: 0 } })
const isClearingCache = ref(false)
const isClearingOutput = ref(false)
const isLoadingCacheInfo = ref(false)

// --- Advanced Settings ---
const isLoadingTools = ref(false)
const systemSearchEnabled = ref(false)
const recommendedVersions: Record<string, string> = {
  java: '11', adb: '1.0.41', aapt: '30.0.3', apktool: '2.7.0', bundletool: '1.15.5',
}

const systemInfo = systemStore.systemInfo
const buildInfo = systemStore.buildInfo

const formatFileSize = (bytes: number) => {
  if (!bytes) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`
}

// --- Load/Save methods ---
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
    showSuccess('Settings saved')
  } catch (e: any) { showError('Failed to save', e.message) }
}

const savePaths = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ runtime: pathSettings.runtime, server: pathSettings.server })
    showSuccess('Paths saved')
  } catch (e: any) { showError('Failed to save paths', e.message) }
}

const browseDirectory = async (target: 'runtime' | 'server') => {
  try {
    const svc = await serviceManager.getService('system')
    const result = await svc.selectDirectory({ title: 'Select directory' })
    if (result?.directoryPath) {
      pathSettings[target] = result.directoryPath
      const settingsSvc = await serviceManager.getService('settings')
      const paths = await settingsSvc.resolveDisplayPaths(pathSettings)
      displayPaths.runtime = paths.runtime || ''
      displayPaths.server = paths.server || ''
    }
  } catch (e) { showError('Failed to select directory') }
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
    if (result.success) { showSuccess('Storage cleared'); await refreshCache() }
    else showError('Failed to clear', result.error)
  } catch (e: any) { showError('Failed to clear', e.message) }
  finally {
    if (target === 'cache') isClearingCache.value = false
    else isClearingOutput.value = false
  }
}

const refreshTools = async () => {
  isLoadingTools.value = true
  try { await toolStore.fetchTools(true) }
  catch (e: any) { showError('Failed to refresh tools', e.message) }
  finally { isLoadingTools.value = false }
}

onMounted(() => { loadSettings(); refreshCache() })
</script>

<template>
  <div class="settings-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">Settings</h1>
        <p class="page-subtitle">Configure application preferences and paths</p>
      </div>
    </div>

    <n-tabs type="line" animated :default-value="'general'" class="settings-tabs">
      <!-- General Tab -->
      <n-tab-pane name="general" tab="General">
        <n-card :bordered="false" class="settings-card">
          <n-form label-placement="left" label-width="160" size="small">
            <n-form-item label="Language">
              <n-select v-model:value="general.language" :options="[
                { label: 'Simplified Chinese', value: 'zh-CN' },
                { label: 'English', value: 'en-US' },
              ]" style="width: 200px" />
            </n-form-item>
            <n-form-item label="Theme">
              <n-select v-model:value="general.theme" :options="[
                { label: 'Follow System', value: 'auto' },
                { label: 'Light', value: 'light' },
                { label: 'Dark', value: 'dark' },
              ]" style="width: 200px" />
            </n-form-item>
            <n-form-item label="Auto Save">
              <n-switch v-model:value="general.autoSave" />
            </n-form-item>
            <n-form-item label="Notifications">
              <n-switch v-model:value="general.enableNotifications" />
            </n-form-item>
          </n-form>
          <n-space style="margin-top: 16px">
            <n-button type="success" size="small" @click="saveGeneral">
              <template #icon><n-icon><Save /></n-icon></template>
              Save
            </n-button>
          </n-space>
        </n-card>
      </n-tab-pane>

      <!-- Paths Tab -->
      <n-tab-pane name="paths" tab="Paths">
        <n-card :bordered="false" class="settings-card" title="Environment Paths">
          <n-form label-placement="left" label-width="120" size="small">
            <n-form-item label="Runtime">
              <n-space>
                <n-input :value="displayPaths.runtime" readonly style="width: 300px" placeholder=".\\runtime" />
                <n-button size="small" @click="browseDirectory('runtime')">
                  <template #icon><n-icon><FolderOpen /></n-icon></template>
                  Browse
                </n-button>
              </n-space>
            </n-form-item>
            <n-form-item label="Backend">
              <n-space>
                <n-input :value="displayPaths.server" readonly style="width: 300px" placeholder=".\\backend" />
                <n-button size="small" @click="browseDirectory('server')">
                  <template #icon><n-icon><FolderOpen /></n-icon></template>
                  Browse
                </n-button>
              </n-space>
            </n-form-item>
          </n-form>
          <n-space style="margin-top: 12px">
            <n-button type="success" size="small" @click="savePaths">
              <template #icon><n-icon><Save /></n-icon></template>
              Save
            </n-button>
          </n-space>
        </n-card>

        <n-card :bordered="false" class="settings-card" title="Storage" style="margin-top: 16px">
          <template #header-extra>
            <n-button size="tiny" quaternary @click="refreshCache" :loading="isLoadingCacheInfo">
              <template #icon><n-icon><RefreshCw /></n-icon></template>
            </n-button>
          </template>
          <n-grid :cols="3" :x-gap="12">
            <n-grid-item>
              <n-statistic label="Cache" :value="formatFileSize(cacheInfo.cache.size)">
                <template #suffix>{{ cacheInfo.cache.files }} files</template>
              </n-statistic>
            </n-grid-item>
            <n-grid-item>
              <n-statistic label="Output" :value="formatFileSize(cacheInfo.output.size)">
                <template #suffix>{{ cacheInfo.output.files }} files</template>
              </n-statistic>
            </n-grid-item>
            <n-grid-item>
              <n-statistic label="Total" :value="formatFileSize(cacheInfo.total.size)" />
            </n-grid-item>
          </n-grid>
          <n-space style="margin-top: 16px">
            <n-button type="warning" size="small" @click="clearStorage('cache')" :loading="isClearingCache">
              <template #icon><n-icon><Trash2 /></n-icon></template>
              Clear Cache
            </n-button>
            <n-button type="warning" size="small" @click="clearStorage('output')" :loading="isClearingOutput">
              <template #icon><n-icon><Download /></n-icon></template>
              Clear Output
            </n-button>
          </n-space>
        </n-card>
      </n-tab-pane>

      <!-- Advanced Tab -->
      <n-tab-pane name="advanced" tab="Advanced">
        <n-card :bordered="false" class="settings-card" title="System Info">
          <template #header-extra>
            <n-button size="tiny" quaternary @click="systemStore.fetchSystemInfo()">
              <template #icon><n-icon><RefreshCw /></n-icon></template>
            </n-button>
          </template>
          <n-descriptions label-placement="left" :column="2" size="small">
            <n-descriptions-item label="OS">{{ systemInfo.platform || '-' }}</n-descriptions-item>
            <n-descriptions-item label="Architecture">{{ systemInfo.architecture || '-' }}</n-descriptions-item>
            <n-descriptions-item label="Hostname">{{ systemInfo.hostname || '-' }}</n-descriptions-item>
            <n-descriptions-item label="CPU">{{ systemInfo.cpuCount || '-' }} cores</n-descriptions-item>
          </n-descriptions>
        </n-card>

        <n-card :bordered="false" class="settings-card" title="Build Info" style="margin-top: 16px">
          <template #header-extra>
            <n-button size="tiny" quaternary @click="systemStore.fetchBuildInfo()">
              <template #icon><n-icon><RefreshCw /></n-icon></template>
            </n-button>
          </template>
          <n-descriptions label-placement="left" :column="2" size="small">
            <n-descriptions-item label="App Version">{{ buildInfo.appVersion || '-' }}</n-descriptions-item>
            <n-descriptions-item label="Electron">{{ buildInfo.electronVersion || '-' }}</n-descriptions-item>
            <n-descriptions-item label="Node.js">{{ buildInfo.nodeVersion || '-' }}</n-descriptions-item>
            <n-descriptions-item label="Python">{{ buildInfo.pythonVersion || '-' }}</n-descriptions-item>
            <n-descriptions-item label="Chrome">{{ buildInfo.chromeVersion || '-' }}</n-descriptions-item>
          </n-descriptions>
        </n-card>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 800px;
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
.settings-card {
  background: #1E293B;
  border-radius: 10px;
}
</style>
