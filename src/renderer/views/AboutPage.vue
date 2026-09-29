<template>
  <div class="screen about-page">
    <PageHeader :title="t('about.title')" :description="t('about.subtitle')" />

    <div class="about-content">

      <!-- Build Info -->
      <n-card :bordered="false" class="about-card">
        <div class="section-header">
          <AppIcon name="layers" size="lg" style="color: var(--success-text)" />
          <span class="section-title">{{ t('settings.buildInfo') }}</span>
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

      <!-- Bundled Tools -->
      <n-card :bordered="false" class="about-card">
        <div class="section-header">
          <AppIcon name="tool" size="lg" style="color: var(--text-muted)" />
          <span class="section-title">{{ t('settings.tools') }}</span>
        </div>
        <div class="info-grid">
          <div v-for="tool in tools" :key="tool.name" class="info-row">
            <span class="info-label">{{ tool.name }}</span>
            <span class="info-val">{{ tool.version || t('common.unknown') }}</span>
            <span class="info-path" :title="tool.path">{{ tool.path || t('common.unknown') }}</span>
          </div>
          <div v-if="tools.length === 0" class="info-empty">{{ t('settings.loading') }}</div>
        </div>
      </n-card>

      <!-- System Info -->
      <n-card :bordered="false" class="about-card">
        <div class="section-header">
          <AppIcon name="cpu" size="lg" style="color: var(--text-muted)" />
          <span class="section-title">{{ t('settings.systemInfo') }}</span>
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
import { useMessage } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'
import PageHeader from '@components/ui/PageHeader.vue'
import { useSystemStore, useToolStore } from '@stores/index'
import { useUpdateStore } from '@stores/updateStore'
import serviceManager from '@services/ServiceManager'
import type UpdateService from '@services/UpdateService'

const { t } = useI18n()
const systemStore = useSystemStore()
const toolStore = useToolStore()
const tools = toolStore.tools
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
/* 页面宽度交给外壳（满宽）；mock 遗留的 max-width:740px 会导致页面之间宽窄不一。
 * 满宽后卡片改栅格：构建信息 / 系统信息 并排，「随包工具」因路径长而整行。
 * DOM 顺序是 构建/工具/系统 → 用 order 把「系统」提到第 2 位。 */
.about-content {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}
.about-content > .about-card:nth-child(1) { order: 1; }
.about-content > .about-card:nth-child(3) { order: 2; }
.about-content > .about-card:nth-child(2) { order: 3; grid-column: 1 / -1; }
/* 极简：静止态只留 1px 描边，hover 才升起 */
.about-card {
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-card);
  text-align: left;
  transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}
.about-card:hover { box-shadow: var(--shadow-lift); border-color: var(--primary-soft-border); transform: translateY(-1px); }
.section-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; justify-content: flex-start; }
.section-title { font-family: var(--font-family-base); font-size: 15px; font-weight: 600; color: var(--app-text-primary); }
.info-grid { display: flex; flex-direction: column; gap: 6px; }
.info-row { display: flex; align-items: baseline; justify-content: flex-start; gap: 12px; padding: 5px 0; text-align: left; }
.info-row:last-child { border-bottom: none; }
.info-label { font-size: 13px; color: var(--app-text-muted); min-width: 110px; text-align: left; }
.info-val { font-size: 13px; color: var(--app-text-secondary); font-family: var(--font-family-monospace); min-width: 80px; }
.info-path { font-size: 12px; color: var(--app-text-dim); font-family: var(--font-family-monospace); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; text-align: right; }
.info-empty { font-size: 13px; color: var(--app-text-dim); padding: 8px 0; }
.update-status-inline { font-size: 12px; color: var(--success-text); white-space: nowrap; }
</style>
