<template>
  <n-modal
    :show="visible"
    :mask-closable="false"
    preset="card"
    :title="dialogTitle"
    style="max-width: 440px"
    @close="handleClose"
  >
    <template #header>
      <div style="text-align: center; width: 100%">
        <div style="font-size: 32px; margin-bottom: 4px">{{ statusIcon }}</div>
        <div style="font-size: 16px; font-weight: 700">{{ dialogTitle }}</div>
      </div>
    </template>

    <!-- Available state -->
    <div v-if="store.status === 'available'" class="update-body">
      <div class="version-compare">
        <span class="ver-old">{{ store.currentVersion || $t('common.unknown') }}</span>
        <n-icon size="16"><ArrowRight /></n-icon>
        <span class="ver-new">{{ store.latestVersion }}</span>
        <n-tag type="success" size="small" round>Latest</n-tag>
      </div>
      <div v-if="store.releaseNotes" class="release-notes">
        <div class="rn-title">{{ $t('update.releaseNotes') }}</div>
        <div class="rn-body">{{ store.releaseNotes }}</div>
      </div>
      <div class="update-actions">
        <n-button quaternary @click="handleClose">{{ $t('update.later') }}</n-button>
        <n-button type="primary" @click="handleDownload">{{ $t('update.download') }}</n-button>
      </div>
    </div>

    <!-- Downloading state -->
    <div v-else-if="store.status === 'downloading'" class="update-body">
      <div class="download-info">
        <span>{{ store.downloadPercent.toFixed(2) }}%</span>
        <span v-if="store.downloadSpeed">{{ formatSpeed(store.downloadSpeed) }}</span>
      </div>
      <n-progress
        type="line"
        :percentage="store.downloadPercent"
        :height="6"
        :border-radius="3"
        color="#22C55E"
        rail-color="rgba(0,0,0,0.06)"
      />
    </div>

    <!-- Downloaded state -->
    <div v-else-if="store.status === 'downloaded'" class="update-body">
      <p style="text-align: center; color: var(--app-text-secondary); font-size: 14px">
        {{ $t('update.restartToInstall') }}
      </p>
      <div class="update-actions">
        <n-button quaternary @click="handleClose">{{ $t('update.later') }}</n-button>
        <n-button type="primary" @click="handleRestart">{{ $t('update.restartNow') }}</n-button>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="store.status === 'error'" class="update-body">
      <n-alert type="error" :title="store.error || $t('update.error')" />
      <div class="update-actions" style="margin-top: 16px">
        <n-button quaternary @click="handleClose">{{ $t('update.later') }}</n-button>
        <n-button type="primary" @click="handleRetry">{{ $t('app.retry') }}</n-button>
      </div>
    </div>

    <!-- Checking state -->
    <div v-else class="update-body" style="text-align: center; padding: 32px 0">
      <n-spin size="medium" />
      <p style="margin-top: 12px; color: var(--app-text-muted); font-size: 13px">{{ $t('update.checking') }}</p>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal, NButton, NProgress, NTag, NIcon, NAlert, NSpin } from 'naive-ui'
import { ArrowRight } from 'lucide-vue-next'
import { useUpdateStore } from '@stores/updateStore'

const { t } = useI18n()
const store = useUpdateStore()

const emit = defineEmits<{
  close: []
  download: []
  restart: []
  retry: []
}>()

// 下载进度在顶部进度条显示，弹窗只处理需要用户操作的阶段
const visible = computed(() =>
  ['checking', 'available', 'error'].includes(store.status)
)

const statusIcon = computed(() => {
  switch (store.status) {
    case 'checking': return '🔍'
    case 'available': return '🎉'
    case 'downloading': return '⬇️'
    case 'downloaded': return '✅'
    case 'error': return '❌'
    default: return ''
  }
})

const dialogTitle = computed(() => {
  switch (store.status) {
    case 'checking': return t('update.checking')
    case 'available': return t('update.newVersion')
    case 'downloading': return t('update.downloading', { version: store.latestVersion || '' })
    case 'downloaded': return t('update.downloaded')
    case 'error': return t('update.error')
    default: return ''
  }
})

function formatSpeed(bytesPerSecond: number): string {
  if (bytesPerSecond < 1024) return `${bytesPerSecond} B/s`
  if (bytesPerSecond < 1048576) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`
  return `${(bytesPerSecond / 1048576).toFixed(1)} MB/s`
}

function handleClose(): void {
  emit('close')
}

function handleDownload(): void {
  emit('download')
}

function handleRestart(): void {
  emit('restart')
}

function handleRetry(): void {
  emit('retry')
}
</script>

<style scoped>
.update-body { padding: 8px 0; }
.version-compare {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 16px;
}
.ver-old { font-size: 13px; color: var(--app-text-muted); font-family: monospace; }
.ver-new { font-size: 15px; font-weight: 700; color: #22C55E; font-family: monospace; }
.release-notes {
  background: var(--app-hover);
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 16px;
}
.rn-title { font-size: 12px; font-weight: 600; color: var(--app-text-muted); margin-bottom: 8px; }
.rn-body { font-size: 13px; color: var(--app-text-secondary); white-space: pre-wrap; line-height: 1.6; }
.update-actions { display: flex; gap: 10px; justify-content: flex-end; }
.download-info { display: flex; justify-content: space-between; font-size: 13px; color: var(--app-text-secondary); margin-bottom: 8px; }
</style>
