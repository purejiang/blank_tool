<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'

const { showSuccess, showError } = useNotification()
const systemServiceRef = ref<any>(null)

const settings = reactive({
  runtime: '.\\runtime',
  server: '.\\backend',
})

const displayPaths = reactive({
  runtime: '',
  server: '',
})

const isClearingCache = ref(false)
const isClearingOutput = ref(false)
const isLoadingCacheInfo = ref(false)
const cacheInfo = ref({
  cache: { size: 0, files: 0 },
  output: { size: 0, files: 0 },
  total: { size: 0, files: 0 },
})

const formatFileSize = (bytes: number) => {
  if (!bytes) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`
}

const updateDisplayPaths = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    const nextDisplayPaths = await svc.resolveDisplayPaths(settings)
    displayPaths.runtime = nextDisplayPaths.runtime || ''
    displayPaths.server = nextDisplayPaths.server || ''
  } catch (e) {
    console.error('Failed to resolve paths:', e)
  }
}

const browseDirectory = async (target: 'runtime' | 'server') => {
  try {
    if (!systemServiceRef.value) {
      systemServiceRef.value = await serviceManager.getService('system')
    }
    const result = await systemServiceRef.value.selectDirectory({ title: 'Select directory' })
    if (result && result.directoryPath) {
      settings[target] = result.directoryPath
      await updateDisplayPaths()
    }
  } catch (error: unknown) {
    showError('Failed to select directory')
  }
}

const saveEnvironmentSettings = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    await svc.saveSettings({ runtime: settings.runtime, server: settings.server })
    showSuccess('Path settings saved')
  } catch (error: unknown) {
    showError('Failed to save path settings', error instanceof Error ? error.message : '')
  }
}

const resetEnvironmentSettings = async () => {
  if (!confirm('Reset path settings to defaults?')) return
  settings.runtime = '.\\runtime'
  settings.server = '.\\backend'
  await saveEnvironmentSettings()
  showSuccess('Path settings reset')
}

const refreshCacheInfo = async () => {
  isLoadingCacheInfo.value = true
  try {
    const svc = await serviceManager.getService('cache')
    const info = await svc.getCacheInfo(true)
    if (info) {
      cacheInfo.value = info
    }
  } catch (error: unknown) {
    console.error('Failed to refresh cache info:', error)
  } finally {
    isLoadingCacheInfo.value = false
  }
}

const clearStorage = async (target: 'cache' | 'output') => {
  if (target === 'cache') isClearingCache.value = true
  if (target === 'output') isClearingOutput.value = true
  try {
    const svc = await serviceManager.getService('cache')
    const result = await svc.clearStorage(target)
    if (result.success) {
      showSuccess('Storage cleared')
      await refreshCacheInfo()
    } else {
      showError('Failed to clear storage', result.error)
    }
  } catch (error: unknown) {
    showError('Failed to clear storage', error instanceof Error ? error.message : '')
  } finally {
    if (target === 'cache') isClearingCache.value = false
    if (target === 'output') isClearingOutput.value = false
  }
}

const loadSettings = async () => {
  try {
    const svc = await serviceManager.getService('settings')
    const model = await svc.loadSettingsModel()
    if (model && model.settings) {
      if (model.settings.runtime) settings.runtime = model.settings.runtime as string
      if (model.settings.server) settings.server = model.settings.server as string
    }
    if (model && model.displayPaths) {
      displayPaths.runtime = model.displayPaths.runtime || ''
      displayPaths.server = model.displayPaths.server || ''
    }
  } catch (error) {
    console.error('Failed to load settings:', error)
  }
}

onMounted(() => {
  loadSettings()
  refreshCacheInfo()
})
</script>

<template>
  <div>
    <!-- Environment Settings -->
    <div class="section responsive-section">
      <div class="section-header">
        <h2><span class="section-icon">&#x1F527;</span>Environment Paths</h2>
        <div class="section-actions">
          <button class="btn btn-sm btn-primary" @click="saveEnvironmentSettings" title="Save paths">
            <span>&#x1F4BE;</span>
          </button>
          <button class="btn btn-sm btn-secondary" @click="resetEnvironmentSettings" title="Reset to defaults">
            <span>&#x1F504;</span>
          </button>
        </div>
      </div>
      <div class="settings-group">
        <div class="form-group">
          <label class="form-label" for="runtime">Runtime Path</label>
          <div class="input-group">
            <input type="text" id="runtime" class="form-control" :value="displayPaths.runtime" readonly
              placeholder="Default: .\runtime" :title="settings.runtime">
            <button class="btn btn-secondary path-browse-btn" @click="browseDirectory('runtime')">Browse</button>
          </div>
          <p class="form-text">Current config: {{ settings.runtime }}</p>
        </div>
        <div class="form-group">
          <label class="form-label" for="server">Backend Path</label>
          <div class="input-group">
            <input type="text" id="server" class="form-control" :value="displayPaths.server" readonly
              placeholder="Default: .\backend" :title="settings.server">
            <button class="btn btn-secondary path-browse-btn" @click="browseDirectory('server')">Browse</button>
          </div>
          <p class="form-text">Current config: {{ settings.server }}</p>
        </div>
      </div>
    </div>

    <!-- Storage Management -->
    <div class="section">
      <div class="section-header">
        <h2><span class="section-icon">&#x1F9F9;</span>Storage Management</h2>
        <div class="section-actions">
          <button class="btn btn-sm btn-secondary" @click="refreshCacheInfo" :disabled="isLoadingCacheInfo" title="Refresh storage info">
            <span v-if="!isLoadingCacheInfo">&#x1F504;</span>
            <span v-else class="btn-spinner"></span>
          </button>
        </div>
      </div>
      <div class="settings-group">
        <div class="info-grid info-grid-spaced">
          <div class="info-item">
            <p class="info-label">Cache Size</p>
            <span class="info-value">{{ formatFileSize(cacheInfo.cache.size) }} ({{ cacheInfo.cache.files }} files)</span>
          </div>
          <div class="info-item">
            <p class="info-label">Output Size</p>
            <span class="info-value">{{ formatFileSize(cacheInfo.output.size) }} ({{ cacheInfo.output.files }} files)</span>
          </div>
          <div class="info-item">
            <p class="info-label">Total</p>
            <span class="info-value">{{ formatFileSize(cacheInfo.total.size) }}</span>
          </div>
        </div>
        <div class="form-group">
          <p class="form-text">Manage temporary cache and output files.</p>
          <div class="btn-group">
            <button class="btn btn-warning" :class="{ 'loading': isClearingCache }" @click="clearStorage('cache')"
              :disabled="isClearingCache || isLoadingCacheInfo">
              <span v-if="!isClearingCache">&#x1F5D1;&#xFE0F;</span>
              <span v-if="isClearingCache" class="btn-spinner"></span>
              {{ isClearingCache ? 'Clearing...' : 'Clear Cache' }}
            </button>
            <button class="btn btn-warning" :class="{ 'loading': isClearingOutput }" @click="clearStorage('output')"
              :disabled="isClearingOutput || isLoadingCacheInfo">
              <span v-if="!isClearingOutput">&#x1F4E4;</span>
              <span v-if="isClearingOutput" class="btn-spinner"></span>
              {{ isClearingOutput ? 'Clearing...' : 'Clear Output' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-group { padding: var(--space-sm) 0; }
.form-group { margin-bottom: var(--space-md); }
.form-label { display: block; font-weight: 600; margin-bottom: var(--space-xs); font-size: var(--font-size-sm); color: var(--color-text-secondary); }
.form-text { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-top: var(--space-xs); }
.input-group { display: flex; gap: var(--space-sm); align-items: center; }
.path-browse-btn { white-space: nowrap; flex-shrink: 0; }
.btn-group { display: flex; gap: var(--space-sm); }
.info-grid-spaced { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-md); margin-bottom: var(--space-lg); }
.info-item { text-align: center; padding: var(--space-md); background: var(--color-bg-card); border-radius: var(--radius-sm); border: 1px solid var(--color-border); }
.info-label { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-bottom: var(--space-sm); }
.info-value { font-size: var(--font-size-lg); font-weight: 600; color: var(--color-primary); }
</style>
