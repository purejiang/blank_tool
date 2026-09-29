<template>
  <!-- S4 运行记录（docs/08 §3-S4）：全部运行记录（history.list 终态 + run.list
       在跑合并），筛选、回看、取消、重跑、清理。 -->
  <div class="run-list">
    <!-- 筛选栏 -->
    <div class="rl-filters">
      <n-input
        v-model:value="query"
        size="small"
        clearable
        class="rl-search"
        :placeholder="t('tasks.runs.search')"
      />
      <n-select
        v-model:value="taskFilter"
        size="small"
        clearable
        class="rl-task-filter"
        :placeholder="t('tasks.runs.taskFilter')"
        :options="taskOptions"
      />
      <n-select
        v-model:value="statusFilter"
        size="small"
        class="rl-status-filter"
        :options="statusOptions"
      />
      <span class="rl-grow" />
      <n-button size="small" quaternary type="error" :disabled="rows.length === 0" @click="clearAll">
        {{ t('tasks.runs.clearAll') }}
      </n-button>
    </div>

    <div class="rl-hint">{{ t('tasks.runs.retentionHint') }}</div>

    <div v-if="loading && merged.length === 0" class="rl-status">{{ t('tasks.runs.loading') }}</div>
    <n-alert v-else-if="loadError" type="error" :show-icon="true" class="rl-status">
      <div class="rl-status-row">
        <span>{{ t('tasks.loadFailed', { error: loadError }) }}</span>
        <n-button size="tiny" @click="reload">{{ t('workflows.retry') }}</n-button>
      </div>
    </n-alert>
    <div v-else-if="filtered.length === 0" class="rl-empty">
      <div class="rl-empty-title">{{ t('tasks.runs.empty') }}</div>
      <n-button size="small" type="primary" @click="emit('new-task')">
        {{ t('tasks.new') }}
      </n-button>
    </div>

    <div v-else class="rl-rows">
      <div v-for="item in filtered" :key="item.key" class="rl-row" :class="{ 'rl-row--running': item.running }">
        <StatusBadge :status="item.status" />
        <span class="rl-workflow">{{ item.workflow || '—' }}</span>
        <span class="rl-task">{{ item.taskName || t('tasks.runs.oneShot') }}</span>
        <span class="rl-source">{{ item.source || '—' }}</span>
        <span class="rl-time">{{ formatTime(item.startedAt) }}</span>
        <span class="rl-duration">{{ item.running ? t('tasks.status.running') : formatMs(item.durationMs) }}</span>
        <span class="rl-actions">
          <n-button v-if="item.running" size="tiny" @click="cancel(item)">
            {{ t('tasks.runs.cancel') }}
          </n-button>
          <n-button v-else size="tiny" quaternary :loading="busyKey === item.key" @click="rerun(item)">
            {{ t('tasks.runs.rerun') }}
          </n-button>
          <n-button
            v-if="!item.running"
            size="tiny"
            quaternary
            :disabled="!item.runDir"
            @click="openPath(item.runDir)"
          >
            {{ t('tasks.runs.openRunDir') }}
          </n-button>
          <n-button v-if="!item.running" size="tiny" quaternary type="error" @click="remove(item)">
            {{ t('tasks.actions.delete') }}
          </n-button>
          <n-button
            v-if="!item.running"
            size="tiny"
            quaternary
            :title="t('tasks.runs.detailHint')"
            @click="openDetail(item)"
          >
            <template #icon><AppIcon name="down" /></template>
          </n-button>
        </span>
      </div>
    </div>

    <div v-if="hasMore" class="rl-more">
      <n-button size="small" :loading="loading" @click="loadMore">
        {{ t('tasks.runs.loadMore') }}
      </n-button>
    </div>

    <!-- S5 运行详情抽屉 -->
    <RunDetailDrawer
      v-model:show="detail.show"
      :run-id="detail.runId"
      :rerunning="busyKey === `detail-${detail.runId}`"
      @rerun="onRerunRecord"
      @delete="onDeleteRecord"
      @save-as-task="emit('save-as-task', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAlert, NButton, NInput, NSelect, useDialog } from 'naive-ui'
import AppIcon from '@components/ui/AppIcon.vue'

import StatusBadge from '@components/ui/StatusBadge.vue'
import RunDetailDrawer from './RunDetailDrawer.vue'
import { formatMs, runStatusOf, type RunStatusKey } from './runFormat'
import type { RunListItem, RunRecord, RunSummary } from '../../../shared/ipc/protocol'
import unifiedApi from '@/api/unifiedApi'
import serviceManager from '@services/ServiceManager'
import { useNotification } from '@composables/useNotification'
import { log } from '@utils/logger'

/**
 * S4: merged run records.
 *
 * `history.list` holds terminal runs; `run.list` holds the in-flight ones. The
 * table shows both, keyed by run id, so "运行中" can sit next to finished rows
 * without pretending the history has an in-progress state.
 */
const props = defineProps<{
  /** Preset from a task row's 「查看运行记录」 (`/tasks?tab=runs&task=<name>`). */
  initialTask?: string
}>()

const emit = defineEmits<{
  (e: 'new-task'): void
  (e: 'save-as-task', run: RunRecord): void
}>()

const { t } = useI18n()
const dialog = useDialog()
const { showSuccess, showError, showWarning } = useNotification()

const PAGE_SIZE = 50

const rows = ref<RunSummary[]>([])
const inflight = ref<RunListItem[]>([])
const loading = ref(false)
const loadError = ref('')
const offset = ref(0)
const hasMore = ref(false)
const busyKey = ref<string | null>(null)

const query = ref('')
const taskFilter = ref<string | null>(props.initialTask ?? null)
const statusFilter = ref<'all' | RunStatusKey>('all')

const detail = ref({ show: false, runId: '' })

watch(
  () => props.initialTask,
  (value) => {
    taskFilter.value = value ?? null
  },
)

function errMsg(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

// ---- 数据加载 ---------------------------------------------------------------

async function loadRuns(append = false) {
  loading.value = true
  loadError.value = ''
  try {
    const [historyResult, runResult] = await Promise.all([
      unifiedApi.call<{ runs?: RunSummary[] }>('history.list', {
        limit: PAGE_SIZE,
        offset: append ? offset.value : 0,
      }),
      unifiedApi.call<{ runs?: RunListItem[] }>('run.list'),
    ])
    const page = Array.isArray(historyResult?.runs) ? historyResult.runs : []
    rows.value = append ? [...rows.value, ...page] : page
    offset.value = rows.value.length
    hasMore.value = page.length === PAGE_SIZE
    inflight.value = Array.isArray(runResult?.runs) ? runResult.runs : []
  } catch (error) {
    log.error('[RunListView] loading runs failed:', error)
    loadError.value = errMsg(error)
    if (!append) {
      rows.value = []
      inflight.value = []
    }
  } finally {
    loading.value = false
  }
}

function reload() {
  offset.value = 0
  return loadRuns(false)
}

function loadMore() {
  return loadRuns(true)
}

onMounted(() => {
  void reload()
})

// ---- 投影（历史终态 + 在跑合并） --------------------------------------------

interface RunRow {
  key: string
  runId: string
  running: boolean
  status: RunStatusKey
  workflow: string
  taskName: string | null
  source: string
  startedAt: string | null
  durationMs: number | null
  /** Cancellation key (`task_id` / run identity) — only for in-flight rows. */
  cancelKey: string
  runDir: string
  record: RunSummary | null
}

const merged = computed<RunRow[]>(() => {
  const list: RunRow[] = []
  const seen = new Set<string>()

  for (const item of inflight.value) {
    const key = `inflight-${item.run_id}`
    seen.add(item.run_id)
    list.push({
      key,
      runId: item.run_id,
      running: !item.cancelled,
      status: item.cancelled ? 'cancelled' : 'running',
      workflow: '',
      taskName: null,
      source: '',
      startedAt: item.started_at ? new Date(item.started_at * 1000).toISOString() : null,
      durationMs: null,
      cancelKey: item.task_id || item.run_id,
      runDir: '',
      record: null,
    })
  }

  for (const record of rows.value) {
    if (seen.has(record.run_id)) continue
    list.push({
      key: `history-${record.run_id}`,
      runId: record.run_id,
      running: false,
      status: runStatusOf(record),
      workflow: record.workflow_name ?? '',
      taskName: record.task_name ?? null,
      source: record.source ?? '',
      startedAt: record.started_at ?? null,
      durationMs: typeof record.duration_ms === 'number' ? record.duration_ms : null,
      cancelKey: record.task_id || '',
      runDir: record.run_dir ?? '',
      record,
    })
  }

  // 在跑排前面，其余按开始时间倒序
  return list.sort((a, b) => {
    if (a.running !== b.running) return a.running ? -1 : 1
    return String(b.startedAt ?? '').localeCompare(String(a.startedAt ?? ''))
  })
})

const taskOptions = computed(() => {
  const names = new Set<string>()
  for (const row of merged.value) {
    if (row.taskName) names.add(row.taskName)
  }
  return [...names].sort().map((name) => ({ label: name, value: name }))
})

const statusOptions = computed(() => [
  { label: t('tasks.runs.statusAll'), value: 'all' },
  { label: t('tasks.status.running'), value: 'running' },
  { label: t('tasks.status.succeeded'), value: 'succeeded' },
  { label: t('tasks.status.failed'), value: 'failed' },
  { label: t('tasks.status.cancelled'), value: 'cancelled' },
])

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return merged.value.filter((row) => {
    if (taskFilter.value && row.taskName !== taskFilter.value) return false
    if (statusFilter.value !== 'all' && row.status !== statusFilter.value) return false
    if (!needle) return true
    return [row.workflow, row.source, row.taskName ?? '', row.runId]
      .some((field) => String(field).toLowerCase().includes(needle))
  })
})

// ---- 行操作 -----------------------------------------------------------------

async function cancel(row: RunRow) {
  try {
    // `request.cancel` accepts request_id or task_id; the page only knows the
    // task_id alias it passed when starting the run (TaskManager resolves it
    // to the run identity internally).
    await unifiedApi.call('request.cancel', { task_id: row.cancelKey })
    showSuccess(t('tasks.runs.cancelRequested'))
    await reload()
  } catch (error) {
    showError(t('tasks.runs.cancelFailed', { error: errMsg(error) }))
  }
}

/** 有 task_name → 用任务当前保存的入参复跑；否则用记录快照复跑。 */
async function rerun(row: RunRow) {
  busyKey.value = row.key
  try {
    if (row.taskName) {
      await unifiedApi.call('task.execute', { name: row.taskName, task_id: `rerun-${Date.now().toString(36)}` })
    } else if (row.record) {
      const full = await unifiedApi.call<{ run: RunRecord }>('history.get', { run_id: row.runId })
      const record = full?.run
      if (!record) throw new Error(t('tasks.detail.notFound'))
      if (!record.workflow_name) throw new Error(t('tasks.runs.cannotRerun'))
      await unifiedApi.call('template.execute', {
        name: record.workflow_name,
        inputs: record.inputs ?? {},
        task_id: `rerun-${Date.now().toString(36)}`,
      })
    }
    showSuccess(t('tasks.runs.rerunStarted'))
    await reload()
  } catch (error) {
    showError(t('tasks.runs.rerunFailed', { error: errMsg(error) }))
  } finally {
    busyKey.value = null
  }
}

function onRerunRecord(record: RunRecord) {
  const row = merged.value.find((entry) => entry.runId === record.run_id)
  if (row) void rerun(row)
}

function remove(row: RunRow) {
  dialog.warning({
    title: t('tasks.runs.deleteTitle'),
    content: t('tasks.runs.deleteContent', { workflow: row.workflow || row.runId }),
    positiveText: t('tasks.actions.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await unifiedApi.call('history.delete', { run_id: row.runId })
        await reload()
      } catch (error) {
        showError(t('tasks.runs.deleteFailed', { error: errMsg(error) }))
      }
    },
  })
}

function onDeleteRecord(record: RunRecord) {
  const row = merged.value.find((entry) => entry.runId === record.run_id)
  if (row) remove(row)
}

function clearAll() {
  dialog.error({
    title: t('tasks.runs.clearTitle'),
    content: t('tasks.runs.clearContent'),
    positiveText: t('tasks.runs.clearAll'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await unifiedApi.call('history.clear', {})
        showWarning(t('tasks.runs.cleared'))
        await reload()
      } catch (error) {
        showError(t('tasks.runs.deleteFailed', { error: errMsg(error) }))
      }
    },
  })
}

function openDetail(row: RunRow) {
  detail.value = { show: true, runId: row.runId }
}

async function openPath(target: string) {
  if (!target) return
  try {
    const svc = (await serviceManager.getService('system')) as any
    await svc.openPath(target)
  } catch (error) {
    log.error('[RunListView] openPath failed:', error)
  }
}

defineExpose({ reload })
</script>

<style scoped>
.run-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rl-filters {
  display: flex;
  gap: 8px;
  align-items: center;
}

.rl-search {
  width: 220px;
}

.rl-task-filter {
  width: 180px;
}

.rl-status-filter {
  width: 140px;
}

.rl-grow {
  flex: 1;
}

.rl-hint {
  font-size: 11px;
  color: var(--app-text-dim);
}

.rl-status {
  font-size: 12px;
  color: var(--app-text-muted);
}

.rl-status-row {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.rl-empty {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  padding: 40px 20px;
  border: 1px dashed var(--app-card-border);
  border-radius: var(--radius-control);
}

.rl-empty-title {
  font-size: 14px;
  color: var(--app-text-secondary);
}

.rl-rows {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rl-row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 12px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: var(--radius-control);
}

.rl-row--running {
  border-color: var(--app-blue);
}

.rl-workflow {
  flex: none;
  min-width: 140px;
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rl-task {
  flex: none;
  min-width: 110px;
  overflow: hidden;
  font-size: 12px;
  color: var(--app-text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rl-source {
  flex: none;
  font-size: 11px;
  color: var(--app-text-dim);
}

.rl-time,
.rl-duration {
  flex: none;
  font-size: 11px;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
}

.rl-time {
  margin-left: auto;
}

.rl-actions {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-shrink: 0;
}

.rl-more {
  display: flex;
  justify-content: center;
  padding: 6px 0;
}
</style>
