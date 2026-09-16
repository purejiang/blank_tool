<template>
  <div class="run-history">
    <div class="rh-head app-subhead app-subhead--sm">
      <span>{{ t('automation.runHistory') }}</span>
      <span class="rh-count" v-if="runs.length">{{ runs.length }}</span>
      <IconButton
        :icon="RefreshCw"
        :label="t('automation.refresh')"
        :loading="loading"
        size="tiny"
        text
        @click="emit('refresh')"
      />
    </div>

    <div v-if="!runs.length" class="rh-empty app-empty-note">{{ t('automation.noRuns') }}</div>

    <n-scrollbar v-else class="rh-list">
      <div
        v-for="r in runs"
        :key="r.task_id"
        class="run-row"
        :class="[rowState(r), { active: r.task_id === selectedTaskId, inert: isInert(r) }]"
        :title="rowTitle(r)"
        @click="onSelect(r)"
      >
        <span class="run-dot" />
        <span class="run-time">{{ shortTime(r.started_at) }}</span>
        <span v-if="r.orphan" class="run-tag orphan">{{ t('automation.runOrphan') }}</span>
        <span v-else-if="r.running" class="run-tag running">{{ t('automation.runRunning') }}</span>
        <span class="run-counts">{{ r.passed ?? 0 }}/{{ r.total ?? 0 }}</span>
        <span class="run-dur">{{ r.orphan ? fmtSize(r.size) : fmtDur(r.duration_ms) }}</span>
        <IconButton
          :icon="Trash2"
          :label="t('automation.deleteRun')"
          size="tiny"
          text
          type="error"
          class="run-del"
          @click.stop="emit('remove', r.task_id)"
        />
      </div>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NScrollbar } from 'naive-ui'
import { RefreshCw, Trash2 } from 'lucide-vue-next'
import IconButton from '@components/common/IconButton.vue'

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
  if (r?.orphan) return 'orphan'
  if (r?.running) return 'running'
  if (r?.cancelled) return 'warn'
  return r?.success ? 'ok' : 'bad'
}

/** Orphan / running rows have no readable report.json — selecting them only
 *  produces "报告读取失败", so the row is not clickable. */
function isInert(r: any): boolean {
  return !!r?.orphan || !!r?.running
}

function onSelect(r: any) {
  if (isInert(r)) return
  emit('select', r.task_id)
}

function rowTitle(r: any): string {
  if (r?.orphan) return t('automation.runOrphanHint')
  return r?.running ? t('automation.runRunning') : (r?.package_name || '')
}

function fmtSize(bytes: any): string {
  const n = Number(bytes) || 0
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)}MB`
  if (n >= 1024) return `${(n / 1024).toFixed(0)}KB`
  return `${n}B`
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
.rh-head { gap: 6px; margin-bottom: 4px; flex: none; }
.rh-count {
  font-size: var(--app-font-size-xs); color: var(--app-text-muted); background: var(--app-blue-bg);
  border-radius: 8px; padding: 0 6px; line-height: 16px;
}
.rh-head :deep(.app-icon-btn) { margin-left: auto; }
.rh-empty { padding: 8px 0; }
.rh-list { flex: 1 1 auto; min-height: 0; max-height: 140px; }
.run-row {
  display: flex; align-items: center; gap: 8px;
  padding: 2px 4px; border-radius: 6px; cursor: pointer; font-size: var(--app-font-size-sm);
  border: 1px solid transparent;
}
.run-row:hover { background: var(--app-blue-bg); }
.run-row.active { background: var(--app-blue-bg); border-color: var(--app-blue); }
.run-dot { width: 7px; height: 7px; border-radius: 50%; flex: none; background: var(--app-text-muted); }
.run-row.ok .run-dot { background: var(--app-green); }
.run-row.bad .run-dot { background: var(--app-red); }
.run-row.warn .run-dot { background: var(--app-yellow); }
.run-row.orphan .run-dot { background: var(--app-text-muted); }
.run-row.running .run-dot { background: var(--app-blue); }
.run-row.inert { cursor: default; }
.run-row.inert:hover { background: transparent; }
.run-row.inert.active { background: transparent; border-color: transparent; }
.run-tag {
  flex: none; font-size: var(--app-font-size-xs); line-height: 15px;
  padding: 0 5px; border-radius: 6px; background: var(--app-blue-bg);
  color: var(--app-text-muted);
}
.run-tag.orphan { color: var(--app-yellow); }
.run-time { color: var(--app-text-primary); flex: none; font-variant-numeric: tabular-nums; font-size: var(--app-font-size-sm); }
.run-counts { flex: 1; text-align: right; font-variant-numeric: tabular-nums; font-size: var(--app-font-size-sm); }
.run-row.ok .run-counts { color: var(--app-green); }
.run-row.bad .run-counts { color: var(--app-red); }
.run-row.warn .run-counts { color: var(--app-yellow); }
.run-dur { color: var(--app-text-muted); flex: none; font-variant-numeric: tabular-nums; font-size: var(--app-font-size-xs); }
/* the delete affordance only appears on hover — it was crowding the row */
.run-del { flex: none; opacity: 0; transition: opacity 0.12s; }
.run-row:hover .run-del, .run-row.active .run-del { opacity: 1; }
</style>
