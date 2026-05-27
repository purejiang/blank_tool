<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { useToolStore, useSystemStore } from '@stores/index'

const { showSuccess, showError } = useNotification()
const toolStore = useToolStore()
const systemStore = useSystemStore()

const isLoadingTools = ref(false)
const isLoadingBuildInfo = ref(false)
const isLoadingSystemInfo = ref(false)
const systemSearchEnabled = ref(false)

const systemInfo = systemStore.systemInfo
const buildInfo = systemStore.buildInfo

const recommendedVersions: Record<string, string> = {
  java: '11', adb: '1.0.41', aapt: '30.0.3', apktool: '2.7.0', bundletool: '1.15.5',
}

const checkNeedsUpdate = (key: string, version: string) => {
  if (!version) return false
  const min = recommendedVersions[key]
  if (!min) return false
  const normalize = (v: string) => v.replace(/[^0-9.]/g, '')
  const cmp = (a: string, b: string) => {
    const pa = normalize(a).split('.').map(n => parseInt(n || '0', 10))
    const pb = normalize(b).split('.').map(n => parseInt(n || '0', 10))
    const len = Math.max(pa.length, pb.length)
    for (let i = 0; i < len; i++) {
      const da = pa[i] || 0
      const db = pb[i] || 0
      if (da < db) return -1
      if (da > db) return 1
    }
    return 0
  }
  return cmp(version, min) < 0
}

const tools = computed(() => {
  const fullNameMap: Record<string, string> = {
    adb: 'Android Debug Bridge', aapt: 'Android Asset Packaging Tool',
    apktool: 'APKTool', java: 'Java', bundletool: 'BundleTool',
    apksigner: 'Apk Signer', zipalign: 'Zipalign', jarsigner: 'JAR Signer',
  }
  return toolStore.tools.map((item: any) => {
    const key = item.name || item.key
    const fullName = fullNameMap[key] || key
    const version = item.version || ''
    const needsUpdate = checkNeedsUpdate(key, version)
    return { key, fullName, status: item.status || (item.available ? 'available' : 'unavailable'), version, path: item.path || item.tool_path || '', source: item.source || 'unknown', needsUpdate }
  })
})

const refreshTools = async () => {
  try {
    isLoadingTools.value = true
    await toolStore.fetchTools(true)
    showSuccess('Tool status refreshed')
  } catch (e) {
    showError('Failed to refresh tool status')
  } finally {
    isLoadingTools.value = false
  }
}

const toggleSystemSearch = async () => {
  try {
    const next = !systemSearchEnabled.value
    const toolService = await serviceManager.getService('tools')
    const payload = await toolService.setSystemSearchMode(next)
    if (payload) {
      systemSearchEnabled.value = !!payload.system_search
      showSuccess(`System search ${next ? 'enabled' : 'disabled'}`)
      await toolStore.fetchTools(true)
    }
  } catch (e) {
    showError('Failed to toggle system search')
  }
}

const checkVersion = async (key: string) => {
  try {
    const toolService = await serviceManager.getService('tools')
    const info = await toolService.checkTool(key, true)
    if (info) {
      toolStore.updateTool({ ...info, key: info.name })
      showSuccess(`${info.name} status updated`)
    } else {
      showError('Version check failed')
    }
  } catch (e) {
    showError('Version check failed')
  }
}

const browseToolExecutable = async (key: string) => {
  try {
    const svc = await serviceManager.getService('system')
    const result = await svc.selectFile({
      title: 'Select tool file',
      filters: [{ name: 'Executable', extensions: ['exe', 'jar'] }, { name: 'All Files', extensions: ['*'] }],
    })
    if (result && result.filePath) {
      const dotKey = `tools.${key}`
      const settingsSvc = await serviceManager.getService('settings')
      await settingsSvc.saveSettings({ [dotKey]: result.filePath })
      showSuccess('Tool path saved')
      await refreshTools()
    }
  } catch (e) {
    showError('Failed to select tool file')
  }
}

const refreshBuildInfo = async () => {
  try {
    isLoadingBuildInfo.value = true
    await systemStore.fetchBuildInfo()
    showSuccess('Build info refreshed')
  } catch (error: unknown) {
    showError('Failed to refresh build info', error instanceof Error ? error.message : '')
  } finally {
    isLoadingBuildInfo.value = false
  }
}

const refreshSystemInfo = async () => {
  try {
    isLoadingSystemInfo.value = true
    await systemStore.fetchSystemInfo()
    showSuccess('System info refreshed')
  } catch (error: unknown) {
    showError('Failed to refresh system info', error instanceof Error ? error.message : '')
  } finally {
    isLoadingSystemInfo.value = false
  }
}

const exportSystemInfo = async () => {
  try {
    const exportData = { timestamp: new Date().toISOString(), systemInfo, buildInfo }
    const dataStr = JSON.stringify(exportData, null, 2)
    const blob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `system-info-${new Date().toISOString().split('T')[0]}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    showSuccess('System info exported')
  } catch (error) {
    showError('Failed to export')
  }
}

const formatFileSize = (bytes: number) => {
  if (!bytes) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`
}

onMounted(async () => {
  await toolStore.fetchTools(false)
  if (!systemStore.systemInfo.platform) await systemStore.fetchSystemInfo()
  if (!systemStore.buildInfo.appName) await systemStore.fetchBuildInfo()
})
</script>

<template>
  <div>
    <!-- Tools -->
    <div class="section">
      <div class="section-header">
        <h2><span class="section-icon">&#x1F6E0;&#xFE0F;</span>Development Tools</h2>
        <div class="section-actions">
          <span class="toggle-desc">System Search</span>
          <div class="toggle-switch-container" :title="systemSearchEnabled ? 'Disable system search' : 'Enable system search'">
            <label class="toggle-switch">
              <input type="checkbox" :checked="systemSearchEnabled" @change="toggleSystemSearch">
              <span class="toggle-slider"></span>
            </label>
          </div>
          <button class="btn btn-sm btn-secondary" @click="refreshTools" :disabled="isLoadingTools" title="Re-detect tools">
            <span>&#x1F504;</span>
          </button>
        </div>
      </div>
      <div class="tool-grid">
        <div class="tool-card" v-for="tool in tools as any[]" :key="tool.key">
          <div class="tool-card-header">
            <div class="tool-header-left">
              <div class="tool-name">{{ tool.fullName }}</div>
              <div class="tool-status">
                <span :class="['status-badge', tool.status === 'available' ? 'status-ok' : 'status-bad']">
                  {{ tool.status === 'available' ? 'Available' : 'Unavailable' }}
                </span>
                <span v-if="tool.needsUpdate" class="update-badge">Needs Update</span>
              </div>
            </div>
            <div class="tool-header-right">
              <span class="version-text" v-if="tool.version">{{ tool.version }}</span>
              <span class="version-text text-muted" v-else>Unknown</span>
            </div>
          </div>
          <div class="tool-card-body">
            <div class="tool-field path-field">
              <div class="path-input-wrapper">
                <span class="path-label">Path:</span>
                <input type="text" class="form-control path-input" :value="tool.path || 'Not configured'" readonly :title="tool.path || 'Not configured'">
                <div class="action-buttons">
                  <button class="btn btn-sm btn-secondary btn-icon" @click="browseToolExecutable(tool.key)" title="Change path">
                    <span>&#x270F;&#xFE0F;</span>
                  </button>
                  <button class="btn btn-sm btn-secondary btn-icon" @click="checkVersion(tool.key)" title="Refresh status">
                    <span>&#x1F50D;</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Build Info -->
    <div class="section">
      <div class="section-header">
        <h2><span class="section-icon">&#x1F527;</span>Build Information</h2>
        <div class="section-actions">
          <button class="btn btn-sm btn-secondary" @click="refreshBuildInfo" :disabled="isLoadingBuildInfo" title="Refresh build info">
            <span v-if="!isLoadingBuildInfo">&#x1F504;</span>
            <span v-else class="btn-spinner"></span>
          </button>
        </div>
      </div>
      <div class="settings-group">
        <div class="info-category">
          <h3>Application</h3>
          <div class="info-grid">
            <div class="info-item">
              <p class="info-label">App Name</p>
              <span class="info-value">{{ (buildInfo as any).appName || 'Loading...' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label">App Version</p>
              <span class="info-value">{{ (buildInfo as any).appVersion || 'Loading...' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label">Description</p>
              <span class="info-value">{{ (buildInfo as any).appDescription || 'Loading...' }}</span>
            </div>
          </div>
        </div>
        <div class="info-category">
          <h3>Runtime</h3>
          <div class="info-grid">
            <div class="info-item">
              <p class="info-label">Electron</p>
              <span class="info-value">{{ (buildInfo as any).electronVersion || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label">Node.js</p>
              <span class="info-value">{{ (buildInfo as any).nodeVersion || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label">Chrome</p>
              <span class="info-value">{{ (buildInfo as any).chromeVersion || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label">Java</p>
              <span class="info-value">{{ (buildInfo as any).javaVersion || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label">Python</p>
              <span class="info-value">{{ (buildInfo as any).pythonVersion || 'Unknown' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- System Info -->
    <div class="section">
      <div class="section-header">
        <h2><span class="section-icon">&#x1F4BB;</span>System Information</h2>
        <div class="section-actions">
          <button class="btn btn-sm btn-secondary" @click="refreshSystemInfo" :disabled="isLoadingSystemInfo" title="Refresh system info">
            <span>&#x1F504;</span>
          </button>
          <button class="btn btn-sm btn-secondary" @click="exportSystemInfo" title="Export system info">
            <span>&#x1F4E4;</span>
          </button>
        </div>
      </div>
      <div class="settings-group">
        <div class="info-category">
          <h3>Operating System</h3>
          <div class="info-grid">
            <div class="info-item">
              <p class="info-label"><span class="info-icon">&#x1F5A5;&#xFE0F;</span>Platform</p>
              <span class="info-value">{{ (systemInfo as any).platform || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label"><span class="info-icon">&#x1F4CB;</span>Version</p>
              <span class="info-value">{{ (systemInfo as any).platform_version || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label"><span class="info-icon">&#x1F3F7;&#xFE0F;</span>Release</p>
              <span class="info-value">{{ (systemInfo as any).platform_release || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label"><span class="info-icon">&#x1F3D7;&#xFE0F;</span>Architecture</p>
              <span class="info-value">{{ (systemInfo as any).architecture || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label"><span class="info-icon">&#x1F3E0;</span>Hostname</p>
              <span class="info-value">{{ (systemInfo as any).hostname || 'Unknown' }}</span>
            </div>
          </div>
        </div>
        <div class="info-category">
          <h3>Hardware</h3>
          <div class="info-grid">
            <div class="info-item">
              <p class="info-label"><span class="info-icon">&#x1F527;</span>Processor</p>
              <span class="info-value">{{ (systemInfo as any).processor || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label"><span class="info-icon">&#x2699;&#xFE0F;</span>CPU Cores</p>
              <span class="info-value">{{ (systemInfo as any).cpuCount || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label"><span class="info-icon">&#x1F9E0;</span>Memory Total</p>
              <span class="info-value">{{ (systemInfo as any).memoryTotal || 'Unknown' }}</span>
            </div>
            <div class="info-item">
              <p class="info-label"><span class="info-icon">&#x1F4C8;</span>Memory Used</p>
              <span class="info-value">
                {{ (systemInfo as any).memoryUsed || 'Unknown' }}
                <span v-if="(systemInfo as any).memoryPercent">({{ (systemInfo as any).memoryPercent }})</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-group { padding: var(--space-sm) 0; }
.info-category { margin-bottom: var(--space-lg); }
.info-category:last-child { margin-bottom: 0; }
.info-category h3 { font-size: 14px; font-weight: 600; color: var(--color-text); margin-bottom: var(--space-sm); padding-bottom: var(--space-xs); border-bottom: 1px solid var(--color-border); }
.info-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-md); }
.info-item { display: flex; flex-direction: column; gap: var(--space-xs); padding: var(--space-sm); background: var(--color-bg); border-radius: var(--radius-sm); border: 1px solid var(--color-border); transition: all 0.2s ease; }
.info-item:hover { border-color: var(--color-primary); }
.info-label { font-size: var(--font-size-sm); color: var(--color-text-secondary); display: flex; align-items: center; gap: 6px; }
.info-icon { font-size: 14px; opacity: 0.8; }
.info-value { font-size: var(--font-size-base); font-weight: 500; color: var(--color-text); word-break: break-all; line-height: 1.4; }

.tool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--space-md); margin-top: var(--space-md); }
.tool-card { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius-md); overflow: hidden; transition: all 0.2s ease; }
.tool-card:hover { box-shadow: var(--shadow-md); border-color: var(--color-primary); }
.tool-card-header { padding: var(--space-sm) var(--space-md); background: var(--color-bg); border-bottom: 1px solid var(--color-border); display: flex; justify-content: space-between; align-items: center; }
.tool-header-left { display: flex; flex-direction: column; gap: var(--space-xs); }
.tool-name { font-weight: 600; color: var(--color-text); font-size: var(--font-size-base); }
.tool-status { display: flex; align-items: center; gap: var(--space-sm); }
.status-badge { font-size: 11px; padding: 2px 6px; border-radius: var(--radius-sm); font-weight: 500; }
.status-ok { background: rgba(34, 197, 94, 0.1); color: var(--color-success); }
.status-bad { background: rgba(239, 68, 68, 0.1); color: var(--color-error); }
.update-badge { font-size: 10px; padding: 2px 6px; background: var(--color-warning); color: white; border-radius: 10px; }
.tool-header-right { text-align: right; }
.version-text { font-family: monospace; font-size: var(--font-size-sm); color: var(--color-text-secondary); background: var(--color-bg); padding: 2px 6px; border-radius: var(--radius-sm); }
.tool-card-body { padding: var(--space-md); }
.path-input-wrapper { display: flex; align-items: center; gap: var(--space-sm); background: var(--color-bg); padding: var(--space-xs); border-radius: var(--radius-sm); border: 1px solid var(--color-border); }
.path-label { font-size: var(--font-size-sm); color: var(--color-text-secondary); white-space: nowrap; padding-left: var(--space-sm); }
.path-input { flex: 1; border: none; background: transparent; font-size: var(--font-size-sm); color: var(--color-text); padding: var(--space-xs); min-width: 0; }
.path-input:focus { outline: none; }
.action-buttons { display: flex; gap: var(--space-xs); }
.btn-icon { width: 28px; height: 28px; padding: 0; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-sm); }

.toggle-desc { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-right: var(--space-xs); }
.toggle-switch { position: relative; display: inline-block; width: 36px; height: 20px; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .3s; border-radius: 20px; }
.toggle-slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; }
input:checked + .toggle-slider { background-color: var(--color-primary); }
input:checked + .toggle-slider:before { transform: translateX(16px); }
</style>
