<template>
  <div class="tools-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('tools.title') }}</h1>
        <p class="page-subtitle">{{ t('tools.subtitle') }}</p>
      </div>
    </div>

    <n-empty :description="t('task.pluginDevDesc')" size="large">
      <template #icon>
        <n-icon size="64" color="var(--app-text-dim)"><Puzzle /></n-icon>
      </template>
      <template #extra>
        <p class="plugin-dev-title">{{ t('task.pluginDev') }}</p>
      </template>
    </n-empty>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NIcon, NEmpty } from 'naive-ui'
import { Puzzle } from 'lucide-vue-next'

const { t } = useI18n()
</script>

<style scoped>
.tools-page { max-width: 1000px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title {
  font-family: Inter, sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text-primary);
  margin: 0;
  letter-spacing: -0.02em;
}
.page-subtitle { font-size: 13px; color: var(--app-text-muted); margin: 4px 0 0; }
.plugin-dev-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text-muted);
  margin-top: 16px;
}
</style>
