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
        :class="[rowState(r), { active: r.task_id === selectedTaskId }]"
        :title="r.package_name"
        @click="emit('select', r.task_id)"
      >
        <span class="run-dot" />
        <span class="run-time">{{ shortTime(r.started_at) }}</span>
        <span class="run-counts">{{ r.passed ?? 0 }}/{{ r.total ?? 0 }}</span>
        <span class="run-dur">{{ fmtDur(r.duration_ms) }}</span>
        <n-button
          size="tiny" text type="error"
          class="run-del"
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
import { NButton, NIcon, NScrollbar } from 'naive-ui'
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

/** 失败 / 取消 的行使计数标红，扫一眼就能找到出问题的那次 */
function rowState(r: any): string {
  if (r?.cancelled) return 'warn'
  return r?.success ? 'ok' : 'bad'
}

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
  /* shrinkable, and clipped: when the window is short this list gives up
     height before the run panel does (the panel is the working area) */
  display: flex; flex-direction: column;
  flex: 0 1 auto; min-height: 0; overflow: hidden;
}
.rh-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; flex: none; }
.rh-title { font-size: 12px; font-weight: 600; color: var(--app-text-primary); }
.rh-count {
  font-size: 11px; color: var(--app-text-muted); background: var(--app-blue-bg);
  border-radius: 8px; padding: 0 6px; line-height: 16px;
}
.rh-head :deep(.n-button) { margin-left: auto; }
.rh-empty { padding: 8px 0; font-size: 12px; color: var(--app-text-muted); text-align: center; }
.rh-list { flex: 1 1 auto; min-height: 0; max-height: 140px; }
.run-row {
  display: flex; align-items: center; gap: 8px;
  padding: 2px 4px; border-radius: 6px; cursor: pointer; font-size: 12px;
  border: 1px solid transparent;
}
.run-row:hover { background: var(--app-blue-bg); }
.run-row.active { background: var(--app-blue-bg); border-color: #2080f0; }
.run-dot { width: 7px; height: 7px; border-radius: 50%; flex: none; background: var(--app-text-muted); }
.run-row.ok .run-dot { background: #18a058; }
.run-row.bad .run-dot { background: #d03050; }
.run-row.warn .run-dot { background: #f0a020; }
.run-time { color: var(--app-text-primary); flex: none; font-variant-numeric: tabular-nums; font-size: 11.5px; }
.run-counts { flex: 1; text-align: right; font-variant-numeric: tabular-nums; font-size: 11.5px; }
.run-row.ok .run-counts { color: #18a058; }
.run-row.bad .run-counts { color: #d03050; }
.run-row.warn .run-counts { color: #f0a020; }
.run-dur { color: var(--app-text-muted); flex: none; font-variant-numeric: tabular-nums; font-size: 11px; }
/* the delete affordance only appears on hover — it was crowding the row */
.run-del { flex: none; opacity: 0; transition: opacity 0.12s; }
.run-row:hover .run-del, .run-row.active .run-del { opacity: 1; }
</style>
