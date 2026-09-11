<template>
  <div class="run-history">
    <div class="rh-head">
      <span class="rh-title">{{ t('automation.runHistory') }}</span>
      <span class="rh-count" v-if="runs.length">{{ runs.length }}</span>
      <n-button size="tiny" text :title="t('automation.refresh')" :loading="loading" @click="emit('refresh')">
        <template #icon><n-icon><RefreshCw /></n-icon></template>
      </n-button>
    </div>

    <div v-if="!runs.length" class="rh-empty">{{ t('automation.noRuns') }}</div>

    <n-scrollbar v-else class="rh-list">
      <div
        v-for="r in runs"
        :key="r.task_id"
        class="run-row"
        :class="{ active: r.task_id === selectedTaskId }"
        @click="emit('select', r.task_id)"
      >
        <n-tag
          size="tiny"
          :bordered="false"
          :type="r.cancelled ? 'warning' : (r.success ? 'success' : 'error')"
          class="run-badge"
        >
          {{ r.cancelled ? t('automation.cancelled') : (r.success ? t('automation.success') : t('automation.failed')) }}
        </n-tag>
        <span class="run-time" :title="r.package_name">{{ shortTime(r.started_at) }}</span>
        <span class="run-counts">
          <span class="ok">{{ r.passed }}/{{ r.total }}</span>
        </span>
        <span class="run-dur">{{ fmtDur(r.duration_ms) }}</span>
        <n-button
          size="tiny" text type="error"
          :title="t('automation.deleteRun')"
          @click.stop="emit('remove', r.task_id)"
        >
          <template #icon><n-icon size="13"><Trash2 /></n-icon></template>
        </n-button>
      </div>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NScrollbar, NTag } from 'naive-ui'
import { RefreshCw, Trash2 } from 'lucide-vue-next'

defineProps<{
  runs: any[]
  loading?: boolean
  /** 当前在页面里查看的那条记录（高亮） */
  selectedTaskId?: string
}>()

const emit = defineEmits<{
  (e: 'select', task_id: string): void
  (e: 'remove', task_id: string): void
  (e: 'refresh'): void
}>()

const { t } = useI18n()

function shortTime(iso: string): string {
  // "2026-09-10T20:31:02" → "09-10 20:31"
  const m = /(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || '')
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}` : (iso || '-')
}

function fmtDur(ms: number): string {
  const n = Number(ms) || 0
  return n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${n}ms`
}
</script>

<style scoped>
.run-history {
  border: 1px solid var(--app-card-border);
  border-radius: 8px;
  padding: 6px 8px;
  flex: none;
}
.rh-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.rh-title { font-size: 12px; font-weight: 600; color: var(--app-text-primary); }
.rh-count {
  font-size: 11px; color: var(--app-text-muted); background: var(--app-blue-bg);
  border-radius: 8px; padding: 0 6px; line-height: 16px;
}
.rh-head :deep(.n-button) { margin-left: auto; }
.rh-empty { padding: 8px 0; font-size: 12px; color: var(--app-text-muted); text-align: center; }
.rh-list { max-height: 148px; }
.run-row {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 4px; border-radius: 6px; cursor: pointer; font-size: 12px;
  border: 1px solid transparent;
}
.run-row:hover { background: var(--app-blue-bg); }
.run-row.active { background: var(--app-blue-bg); border-color: #2080f0; }
.run-badge { flex: none; }
.run-time { color: var(--app-text-primary); flex: none; font-variant-numeric: tabular-nums; }
.run-counts { flex: 1; text-align: right; }
.run-counts .ok { color: #18a058; }
.run-dur { color: var(--app-text-muted); flex: none; font-variant-numeric: tabular-nums; }
</style>
