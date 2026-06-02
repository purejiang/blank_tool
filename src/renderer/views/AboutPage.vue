<template>
  <div class="about-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('about.title') }}</h1>
        <p class="page-subtitle">{{ t('about.subtitle') }}</p>
      </div>
    </div>

    <div class="about-content">

      <!-- Bundled Tools -->
      <n-card :bordered="false" class="about-card">
        <div class="section-header">
          <n-icon size="18" color="#22C55E"><Wrench /></n-icon>
          <span class="section-title">{{ t('settings.tools') }}</span>
        </div>
        <div class="info-grid">
          <div v-for="tool in tools" :key="tool.name" class="info-row">
            <span class="info-label">{{ tool.name }}</span>
            <span class="info-val">{{ tool.version || '-' }}</span>
            <span class="info-path" :title="tool.path">{{ tool.path || '-' }}</span>
          </div>
          <div v-if="tools.length === 0" class="info-empty">{{ t('settings.loading') }}</div>
        </div>
      </n-card>

      <!-- System Info -->
      <n-card :bordered="false" class="about-card">
        <div class="section-header">
          <n-icon size="18" color="#64748B"><Cpu /></n-icon>
          <span class="section-title">{{ t('settings.systemInfo') }}</span>
        </div>
        <div class="info-grid">
          <div class="info-row"><span class="info-label">{{ t('settings.os') }}</span><span class="info-val">{{ systemInfo.platform || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.architecture') }}</span><span class="info-val">{{ systemInfo.architecture || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.hostname') }}</span><span class="info-val">{{ systemInfo.hostname || '-' }}</span></div>
          <div class="info-row"><span class="info-label">{{ t('settings.cpu') }}</span><span class="info-val">{{ cpuText }}</span></div>
        </div>
      </n-card>

      <!-- Build Info -->
      <n-card :bordered="false" class="about-card">
        <div class="section-header">
          <n-icon size="18" color="#64748B"><Layers /></n-icon>
          <span class="section-title">{{ t('settings.buildInfo') }}</span>
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
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { Wrench, Cpu, Layers } from 'lucide-vue-next'
import { useSystemStore, useToolStore } from '@stores/index'

const { t } = useI18n()
const systemStore = useSystemStore()
const toolStore = useToolStore()
const tools = toolStore.tools
const systemInfo = systemStore.systemInfo
const buildInfo = systemStore.buildInfo

const cpuText = computed(() => {
  const count = systemInfo.cpuCount || '0'
  return `${count} ${t('device.cores', { count: Number(count) || 0 })}`
})
</script>

<style scoped>
.about-page { max-width: 740px; margin: 0 auto; }
.page-header { margin-bottom: 20px; text-align: left; display: block; }
.page-title { font-family: Inter, sans-serif; font-size: 22px; font-weight: 700; color: var(--app-text-primary); margin: 0; letter-spacing: -0.02em; }
.page-subtitle { font-size: 13px; color: var(--app-text-muted); margin: 4px 0 0; }
.about-content { display: flex; flex-direction: column; gap: 16px; }
.about-card { background: var(--app-card-bg); border-radius: 10px; text-align: left; }
.section-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; justify-content: flex-start; }
.section-title { font-family: Inter, sans-serif; font-size: 15px; font-weight: 600; color: var(--app-text-primary); }
.info-grid { display: flex; flex-direction: column; gap: 6px; }
.info-row { display: flex; align-items: baseline; justify-content: flex-start; gap: 12px; padding: 5px 0; text-align: left; }
.info-row:last-child { border-bottom: none; }
.info-label { font-size: 13px; color: var(--app-text-muted); min-width: 110px; text-align: left; }
.info-val { font-size: 13px; color: var(--app-text-secondary); font-family: 'Fira Code', monospace; min-width: 80px; }
.info-path { font-size: 12px; color: var(--app-text-dim); font-family: 'Fira Code', monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; text-align: right; }
.info-empty { font-size: 13px; color: var(--app-text-dim); padding: 8px 0; }
</style>
