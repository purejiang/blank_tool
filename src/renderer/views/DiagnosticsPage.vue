<template>
  <div class="diagnostics-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('diagnostics.title') }}</h1>
        <p class="page-subtitle">{{ t('diagnostics.subtitle') }}</p>
      </div>
    </div>

    <div class="diagnostics-content">

      <!-- Card 1: Backend Health -->
      <n-card :bordered="false" class="diag-card">
        <div class="section-header">
          <n-icon size="18" :color="healthColor"><HeartPulse /></n-icon>
          <span class="section-title">{{ t('diagnostics.backendHealth') }}</span>
          <n-button size="tiny" quaternary class="header-action" @click="refreshHealth">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
            {{ t('diagnostics.refresh') }}
          </n-button>
        </div>
        <div class="health-row">
          <span class="health-dot" :class="healthClass"></span>
          <span class="health-label">{{ healthLabel }}</span>
          <span class="muted">{{ t('diagnostics.lastChecked') }}: {{ formattedLastChecked }}</span>
          <span class="muted">{{ t('diagnostics.uptime') }}: {{ formattedUptime }}</span>
        </div>
      </n-card>

      <!-- Card 2: Running Tasks -->
      <n-card :bordered="false" class="diag-card">
        <div class="section-header">
          <n-icon size="18" color="#64748B"><ListChecks /></n-icon>
          <span class="section-title">{{ t('diagnostics.runningTasks') }}</span>
          <n-button size="tiny" quaternary class="header-action" @click="refreshTasks">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
            {{ t('diagnostics.refresh') }}
          </n-button>
        </div>
        <div v-if="tasks.length === 0" class="empty-hint">{{ t('diagnostics.noTasks') }}</div>
        <n-data-table v-else :columns="taskColumns" :data="tasks" :bordered="false" size="small" :row-key="taskRowKey" />
      </n-card>

      <!-- Card 3: Log Tail (3 tabs) -->
      <n-card :bordered="false" class="diag-card">
        <div class="section-header">
          <n-icon size="18" color="#64748B"><ScrollText /></n-icon>
          <span class="section-title">{{ t('diagnostics.logTail') }}</span>
          <n-button size="tiny" quaternary class="header-action" @click="refreshLogTail()">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
            {{ t('diagnostics.refresh') }}
          </n-button>
        </div>
        <n-tabs type="line" v-model:value="activeLogTab" @update:value="onTabChange">
          <n-tab-pane name="backend" :tab="t('diagnostics.logTailBackend')">
            <pre ref="logViewRef" class="log-view">{{ backendLog.lines.join('\n') }}</pre>
            <div v-if="backendLog.lines.length === 0" class="empty-hint">{{ t('diagnostics.noLogs') }}</div>
            <div class="log-meta muted">
              {{ backendLog.lines.length }} {{ t('diagnostics.lines') }}
              <n-tag v-if="backendLog.truncated" size="tiny" :bordered="false" type="warning" class="log-meta-tag">{{ t('diagnostics.truncated') }}</n-tag>
            </div>
          </n-tab-pane>
          <n-tab-pane name="main" :tab="t('diagnostics.logTailMain')">
            <pre ref="logViewRef" class="log-view">{{ mainLog.lines.join('\n') }}</pre>
            <div v-if="mainLog.lines.length === 0" class="empty-hint">{{ t('diagnostics.noLogs') }}</div>
            <div class="log-meta muted">
              {{ mainLog.lines.length }} {{ t('diagnostics.lines') }}
              <n-tag v-if="mainLog.truncated" size="tiny" :bordered="false" type="warning" class="log-meta-tag">{{ t('diagnostics.truncated') }}</n-tag>
            </div>
          </n-tab-pane>
          <n-tab-pane name="renderer" :tab="t('diagnostics.logTailRenderer')">
            <pre ref="logViewRef" class="log-view">{{ rendererLogLines.join('\n') }}</pre>
            <div v-if="rendererLogLines.length === 0" class="empty-hint">{{ t('diagnostics.noLogs') }}</div>
            <div class="log-meta muted">{{ rendererLogLines.length }} {{ t('diagnostics.lines') }}</div>
          </n-tab-pane>
        </n-tabs>
      </n-card>

      <!-- Card 4: Resolved Paths -->
      <n-card :bordered="false" class="diag-card">
        <div class="section-header">
          <n-icon size="18" color="#64748B"><FolderTree /></n-icon>
          <span class="section-title">{{ t('diagnostics.resolvedPaths') }}</span>
          <n-button size="tiny" quaternary class="header-action" @click="refreshPaths">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
            {{ t('diagnostics.refresh') }}
          </n-button>
        </div>
        <div class="path-grid">
          <div class="path-row">
            <span class="path-label">{{ t('diagnostics.runtime') }}</span>
            <span class="path-val" :title="resolvedPaths.runtime">{{ resolvedPaths.runtime || '—' }}</span>
          </div>
          <div class="path-row">
            <span class="path-label">{{ t('diagnostics.server') }}</span>
            <span class="path-val" :title="resolvedPaths.server">{{ resolvedPaths.server || '—' }}</span>
          </div>
        </div>
      </n-card>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NTag, useDialog, useMessage } from 'naive-ui'
import { HeartPulse, ListChecks, ScrollText, FolderTree, RefreshCw } from 'lucide-vue-next'
import { useBackendHealthStore } from '@stores/backendHealthStore'
import { useRendererLogStore } from '@stores/rendererLogStore'
import unifiedApi from '../api/unifiedApi'
import { log } from '@utils/logger'
import type { TaskListItem, TaskListResult, CancelRequestResult, LogTailResult } from '../../shared/ipc/protocol'

const { t } = useI18n()
const dialog = useDialog()
const message = useMessage()
const healthStore = useBackendHealthStore()
const rendererLogStore = useRendererLogStore()

const LOG_TAIL_LINES = 200
const TASK_POLL_MS = 5000

// ---- Card 1: Backend health -------------------------------------------------
const uptimeS = ref<number | null>(null)

const healthClass = computed(() =>
  healthStore.isHealthy === null ? 'dot-unknown' :
  healthStore.isHealthy ? 'dot-healthy' : 'dot-unhealthy'
)
const healthColor = computed(() =>
  healthStore.isHealthy === null ? '#64748B' :
  healthStore.isHealthy ? 'var(--app-green)' : 'var(--app-red)'
)
const healthLabel = computed(() =>
  healthStore.isHealthy === null ? t('diagnostics.unknown') :
  healthStore.isHealthy ? t('diagnostics.healthy') : t('diagnostics.unhealthy')
)
const formattedLastChecked = computed(() =>
  healthStore.lastCheckedAt ? new Date(healthStore.lastCheckedAt).toLocaleTimeString() : '—'
)
const formattedUptime = computed(() => {
  const s = uptimeS.value
  if (s === null || s === undefined) return '—'
  const hh = Math.floor(s / 3600)
  const mm = Math.floor((s % 3600) / 60)
  const ss = Math.floor(s % 60)
  if (hh > 0) return `${hh}h ${mm}m ${ss}s`
  if (mm > 0) return `${mm}m ${ss}s`
  return `${ss}s`
})

async function refreshHealth(): Promise<void> {
  healthStore.check()
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = await window.electronAPI?.getBackendHealth?.()
    uptimeS.value = typeof result?.uptime_s === 'number' ? result.uptime_s : null
  } catch {
    uptimeS.value = null
  }
}

// ---- Card 2: Running tasks --------------------------------------------------
const tasks = ref<TaskListItem[]>([])
let taskPoll: ReturnType<typeof setInterval> | null = null
const taskRowKey = (row: TaskListItem) => row.task_id

async function refreshTasks(): Promise<void> {
  try {
    const result = await unifiedApi.call<TaskListResult>('task.list')
    tasks.value = result?.tasks || []
  } catch (e) {
    log.error('Diagnostics: failed to fetch task list', e)
  }
}

function cancelTask(taskId: string): void {
  dialog.warning({
    title: t('diagnostics.cancelAction'),
    content: t('diagnostics.cancelConfirm'),
    positiveText: t('diagnostics.cancelAction'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await unifiedApi.call<CancelRequestResult>('request.cancel', { request_id: taskId })
        message.success(t('diagnostics.cancelSuccess'))
        await refreshTasks()
      } catch (e) {
        log.error('Diagnostics: cancel failed', e)
        message.error(t('diagnostics.cancelFailed'))
      }
    },
  })
}

const taskColumns = computed(() => [
  { title: 'ID', key: 'task_id', ellipsis: { tooltip: true } },
  {
    title: t('diagnostics.taskType'),
    key: 'type',
    width: 110,
    render: (row: TaskListItem) => h(
      NTag,
      { size: 'tiny', bordered: false, type: row.type === 'streaming' ? 'info' : 'default' },
      { default: () => row.type }
    ),
  },
  {
    title: t('diagnostics.startedAt'),
    key: 'started_at',
    width: 120,
    render: (row: TaskListItem) => row.started_at ? new Date(row.started_at * 1000).toLocaleTimeString() : '—',
  },
  {
    title: t('diagnostics.cancelled'),
    key: 'cancelled',
    width: 100,
    render: (row: TaskListItem) => row.cancelled
      ? h(NTag, { size: 'tiny', bordered: false, type: 'warning' }, { default: () => t('diagnostics.cancelled') })
      : '—',
  },
  {
    title: '',
    key: 'actions',
    width: 90,
    render: (row: TaskListItem) => !row.cancelled
      ? h(
          NButton,
          { size: 'tiny', type: 'error', ghost: true, onClick: () => cancelTask(row.task_id) },
          { default: () => t('diagnostics.cancelAction') }
        )
      : null,
  },
])

// ---- Card 3: Log tail -------------------------------------------------------
type LogTab = 'backend' | 'main' | 'renderer'
const activeLogTab = ref<LogTab>('backend')
const backendLog = ref<{ lines: string[]; truncated: boolean }>({ lines: [], truncated: false })
const mainLog = ref<{ lines: string[]; truncated: boolean }>({ lines: [], truncated: false })
const rendererLogLines = ref<string[]>([])
const logViewRef = ref<HTMLElement | null>(null)

function scrollLogToBottom(): void {
  nextTick(() => {
    const el = logViewRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function refreshLogTail(tab?: LogTab): Promise<void> {
  const target = tab || activeLogTab.value
  try {
    if (target === 'backend') {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const logsTail = window.electronAPI?.logsTail
      if (typeof logsTail === 'function') {
        const r = (await logsTail(LOG_TAIL_LINES)) as LogTailResult | undefined
        backendLog.value = { lines: r?.lines || [], truncated: !!r?.truncated }
      }
    } else if (target === 'main') {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const readElectronLogTail = window.electronAPI?.readElectronLogTail
      if (typeof readElectronLogTail === 'function') {
        const r = (await readElectronLogTail(LOG_TAIL_LINES)) as LogTailResult | undefined
        mainLog.value = { lines: r?.lines || [], truncated: !!r?.truncated }
      }
    } else {
      rendererLogLines.value = rendererLogStore.getTail(LOG_TAIL_LINES).map(
        e => `${new Date(e.ts).toISOString()} [${e.level}] ${e.message}`
      )
    }
    scrollLogToBottom()
  } catch (e) {
    log.error('Diagnostics: log tail failed', e)
  }
}

function onTabChange(name: string): void {
  refreshLogTail(name as LogTab)
}

// ---- Card 4: Resolved paths -------------------------------------------------
const resolvedPaths = ref<{ runtime?: string; server?: string }>({})

async function refreshPaths(): Promise<void> {
  try {
    const api = unifiedApi.getAPI()
    if (api?.settings?.resolvePaths) {
      resolvedPaths.value = (await api.settings.resolvePaths({})) || {}
    }
  } catch (e) {
    log.error('Diagnostics: path resolve failed', e)
  }
}

// ---- Lifecycle --------------------------------------------------------------
onMounted(() => {
  refreshHealth()
  refreshTasks()
  refreshLogTail()
  refreshPaths()
  taskPoll = setInterval(refreshTasks, TASK_POLL_MS)
})

onUnmounted(() => {
  if (taskPoll) clearInterval(taskPoll)
})
</script>

<style scoped>
.diagnostics-page { max-width: 900px; margin: 0 auto; }
.page-header { margin-bottom: 20px; text-align: left; display: block; }
.page-title { font-family: Inter, sans-serif; font-size: 22px; font-weight: 700; color: var(--app-text-primary); margin: 0; letter-spacing: -0.02em; }
.page-subtitle { font-size: 13px; color: var(--app-text-muted); margin: 4px 0 0; }
.diagnostics-content { display: flex; flex-direction: column; gap: 16px; }
.diag-card { background: var(--app-card-bg); border-radius: 10px; text-align: left; transition: box-shadow 0.2s ease; }
.diag-card:hover { box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08); }
.section-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; justify-content: flex-start; }
.section-title { font-family: Inter, sans-serif; font-size: 15px; font-weight: 600; color: var(--app-text-primary); }
.header-action { margin-left: auto; }

/* Health */
.health-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.health-label { font-size: 14px; font-weight: 600; color: var(--app-text-primary); }
.health-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.health-dot.dot-healthy { background: var(--app-green); }
.health-dot.dot-unhealthy { background: var(--app-red); animation: diag-pulse 1.5s infinite; }
.health-dot.dot-unknown { background: var(--app-text-dim); }
@keyframes diag-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* Tasks / logs shared */
.muted { color: var(--app-text-muted); font-size: 12px; }
.empty-hint { font-size: 13px; color: var(--app-text-dim); padding: 8px 0; }

/* Log viewer */
.log-view {
  max-height: 400px;
  min-height: 120px;
  overflow-y: auto;
  margin: 8px 0 6px;
  background: var(--app-code-bg);
  border: 1px solid var(--app-card-border);
  padding: 12px;
  border-radius: 6px;
  font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}
.log-meta { display: flex; align-items: center; gap: 8px; }
.log-meta-tag { margin-left: 4px; }

/* Resolved paths */
.path-grid { display: flex; flex-direction: column; gap: 6px; }
.path-row { display: flex; align-items: baseline; gap: 12px; padding: 5px 0; }
.path-label { font-size: 13px; color: var(--app-text-muted); min-width: 110px; }
.path-val { font-size: 13px; color: var(--app-text-secondary); font-family: 'Fira Code', monospace; word-break: break-all; flex: 1; }
</style>
