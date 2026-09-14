<template>
  <div class="app-page">
    <div class="app-page-header">
      <div>
        <h1 class="app-page-title">{{ t('about.title') }}</h1>
        <p class="app-page-sub">{{ t('about.subtitle') }}</p>
      </div>
    </div>

    <div class="about-content">

      <!-- Build Info -->
      <n-card :bordered="false" class="about-card">
        <div class="app-section-header">
          <n-icon size="18" color="var(--app-green)"><Layers /></n-icon>
          <span class="app-section-title">{{ t('settings.buildInfo') }}</span>
        </div>
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

      <!-- System Info -->
      <n-card :bordered="false" class="about-card">
        <div class="app-section-header">
          <n-icon size="18" color="var(--app-text-dim)"><Cpu /></n-icon>
          <span class="app-section-title">{{ t('settings.systemInfo') }}</span>
        </div>
        <div class="info-grid">
          <div class="info-row"><span class="info-label">{{ t('settings.os') }}</span><span class="info-val">{{ systemInfo.platform || t('common.unknown') }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.architecture') }}</span><span class="info-val">{{ systemInfo.architecture || t('common.unknown') }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.hostname') }}</span><span class="info-val">{{ systemInfo.hostname || t('common.unknown') }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.cpu') }}</span><span class="info-val">{{ cpuText }}</span></div>
        </div>
      </n-card>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon, useMessage } from 'naive-ui'
import { Cpu, Layers } from 'lucide-vue-next'
import { useSystemStore } from '@stores/index'
import { useUpdateStore } from '@stores/updateStore'
import serviceManager from '@services/ServiceManager'
import type UpdateService from '@services/UpdateService'

const { t } = useI18n()
const systemStore = useSystemStore()
const systemInfo = systemStore.systemInfo
const buildInfo = systemStore.buildInfo

const updateStore = useUpdateStore()
const message = useMessage()

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
      message.success(t('update.upToDate'))
    }
  } catch (err: any) {
    message.error(err.message || t('update.error'))
  }
}

const cpuText = computed(() => {
  const count = parseInt(systemInfo.cpuCount) || 0
  return count ? t('device.cores', { count }) : t('common.unknown')
})
</script>

<style scoped>
.about-content { display: flex; flex-direction: column; gap: 16px; }
.about-card { background: var(--app-card-bg); border-radius: 10px; text-align: left; }
.info-grid { display: flex; flex-direction: column; gap: 6px; }
.info-row { display: flex; align-items: baseline; justify-content: flex-start; gap: 12px; padding: 5px 0; text-align: left; }
.info-row:last-child { border-bottom: none; }
.info-label { font-size: 13px; color: var(--app-text-muted); min-width: 110px; text-align: left; }
.info-val { font-size: 13px; color: var(--app-text-secondary); font-family: var(--app-font-mono); min-width: 80px; }
.update-status-inline { font-size: 12px; color: var(--app-green); white-space: nowrap; }
</style>
