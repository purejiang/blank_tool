<template>
  <div class="app-page">
    <div class="app-page-header">
      <div>
        <h1 class="app-page-title">{{ t('diagnostics.title') }}</h1>
        <p class="app-page-sub">{{ t('diagnostics.subtitle') }}</p>
      </div>
    </div>

    <div class="diagnostics-content">

      <!-- Card 1: Backend Health -->
      <n-card :bordered="false" class="diag-card">
        <div class="app-section-header">
          <n-icon size="18" :color="healthColor"><HeartPulse /></n-icon>
          <span class="app-section-title">{{ t('diagnostics.backendHealth') }}</span>
          <n-button size="tiny" quaternary class="header-action" @click="refreshHealth">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
            {{ t('diagnostics.refresh') }}
          </n-button>
        </div>
        <div class="health-row">
          <span class="health-dot" :class="healthClass"></span>
          <span class="health-label">{{ healthLabel }}</span>
          <span class="app-muted">{{ t('diagnostics.lastChecked') }}: {{ formattedLastChecked }}</span>
          <span class="app-muted">{{ t('diagnostics.uptime') }}: {{ formattedUptime }}</span>
        </div>
      </n-card>

      <!-- Card 2: Running Tasks -->
      <n-card :bordered="false" class="diag-card">
        <div class="app-section-header">
          <n-icon size="18" color="var(--app-text-dim)"><ListChecks /></n-icon>
          <span class="app-section-title">{{ t('diagnostics.runningTasks') }}</span>
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
        <div class="app-section-header">
          <n-icon size="18" color="var(--app-text-dim)"><ScrollText /></n-icon>
          <span class="app-section-title">{{ t('diagnostics.logTail') }}</span>
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

      <!-- Card 4: System self-check -->
      <n-card :bordered="false" class="diag-card">
        <div class="app-section-header">
          <n-icon size="18" :color="selfCheckColor"><ShieldCheck /></n-icon>
          <span class="app-section-title">{{ t('diagnostics.selfCheck') }}</span>
          <n-button size="tiny" quaternary class="header-action" :loading="selfChecking" @click="runSelfCheck">
            <template #icon><n-icon><RefreshCw /></n-icon></template>
            {{ t('diagnostics.selfCheckRun') }}
          </n-button>
        </div>

        <div v-if="selfChecking && selfCheckItems.length === 0" class="empty-hint">
          {{ t('diagnostics.selfCheckRunning') }}
        </div>

        <template v-else>
          <div class="sc-summary">
            <span class="sc-count"><span class="sc-dot sc-dot-ok"></span>{{ t('diagnostics.scPass') }} {{ selfCheckCounts.ok }}</span>
            <span class="sc-count"><span class="sc-dot sc-dot-warn"></span>{{ t('diagnostics.scWarn') }} {{ selfCheckCounts.warn }}</span>
            <span class="sc-count"><span class="sc-dot sc-dot-fail"></span>{{ t('diagnostics.scFail') }} {{ selfCheckCounts.fail }}</span>
            <span class="app-muted sc-stamp">{{ t('diagnostics.lastChecked') }}: {{ selfCheckTimeText }}</span>
          </div>

          <!-- Risk items float to the top: the whole point of a self-check -->
          <div class="sc-section">
            <div class="sc-section-title">{{ t('diagnostics.scRisks') }}</div>
            <div v-if="riskItems.length === 0" class="sc-clean">
              <n-icon size="14" color="var(--app-green)"><CheckCircle2 /></n-icon>
              {{ t('diagnostics.scNoRisk') }}
            </div>
            <div v-else class="sc-list">
              <div v-for="item in riskItems" :key="item.id" class="sc-row">
                <n-icon class="sc-icon" size="14" :color="statusColor(item.status)">
                  <component :is="statusIcon(item.status)" />
                </n-icon>
                <span class="sc-label" :title="checkLabel(item)">{{ checkLabel(item) }}</span>
                <span class="sc-value">{{ checkValue(item) }}</span>
                <span v-if="checkHint(item)" class="sc-hint">{{ checkHint(item) }}</span>
              </div>
            </div>
          </div>

          <!-- Full inventory, grouped -->
          <div v-for="group in selfCheckGroups" :key="group.key" class="sc-section">
            <div class="sc-section-title">{{ t(group.titleKey) }}</div>
            <div class="sc-list">
              <div v-for="item in group.items" :key="item.id" class="sc-row">
                <n-icon class="sc-icon" size="14" :color="statusColor(item.status)">
                  <component :is="statusIcon(item.status)" />
                </n-icon>
                <span class="sc-label" :title="checkLabel(item)">{{ checkLabel(item) }}</span>
                <span class="sc-value">{{ checkValue(item) }}</span>
                <span v-if="checkHint(item)" class="sc-hint">{{ checkHint(item) }}</span>
              </div>
            </div>
          </div>
        </template>
      </n-card>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NTag, useDialog, useMessage } from 'naive-ui'
import {
  HeartPulse, ListChecks, ScrollText, RefreshCw, ShieldCheck,
  CheckCircle2, AlertTriangle, XCircle,
} from 'lucide-vue-next'
import { useBackendHealthStore } from '@stores/backendHealthStore'
import { useRendererLogStore } from '@stores/rendererLogStore'
import type { TrafficStatus } from '@services/AutomationService'
import unifiedApi from '../api/unifiedApi'
import { log } from '@utils/logger'
import type {
  TaskListItem, TaskListResult, CancelRequestResult, LogTailResult,
  SelfCheckItem, SelfCheckResult, SelfCheckStatus, ToolDetail,
} from '../../shared/ipc/protocol'

const { t } = useI18n()
const dialog = useDialog()
const message = useMessage()
const healthStore = useBackendHealthStore()
const rendererLogStore = useRendererLogStore()

const LOG_TAIL_LINES = 200
// 任务列表轮询：有存活任务时快，空闲时慢——空闲时 `task.list` 只是遍历一个空/小
// 字典，但没人希望后台每 5 秒戳一次后端。健康检查的节奏由 backendHealthStore 管，
// 与本轮询相互独立。
const TASK_POLL_ACTIVE_MS = 5000
const TASK_POLL_IDLE_MS = 15000

// ---- Card 1: Backend health -------------------------------------------------
// 运行时间直接读全局健康 store（StatusBar 也在用它轮询），这里不再单独打 IPC。

const healthClass = computed(() =>
  healthStore.isHealthy === null ? 'dot-unknown' :
  healthStore.isHealthy ? 'dot-healthy' : 'dot-unhealthy'
)
const healthColor = computed(() =>
  healthStore.isHealthy === null ? 'var(--app-text-dim)' :
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
  const s = healthStore.uptimeS
  if (s === null || s === undefined) return '—'
  const hh = Math.floor(s / 3600)
  const mm = Math.floor((s % 3600) / 60)
  const ss = Math.floor(s % 60)
  if (hh > 0) return `${hh}h ${mm}m ${ss}s`
  if (mm > 0) return `${mm}m ${ss}s`
  return `${ss}s`
})

function refreshHealth(): void {
  // force=true：手动点刷新时立即补一次，不等自适应定时器。运行时间随同回包更新。
  void healthStore.check(true)
}

// ---- Card 2: Running tasks --------------------------------------------------
const tasks = ref<TaskListItem[]>([])
let taskPoll: ReturnType<typeof setTimeout> | null = null
let taskPollStopped = false
const taskRowKey = (row: TaskListItem) => row.task_id

function scheduleTaskPoll(): void {
  if (taskPollStopped) return
  if (taskPoll) clearTimeout(taskPoll)
  taskPoll = setTimeout(() => { void refreshTasks() }, tasks.value.length > 0 ? TASK_POLL_ACTIVE_MS : TASK_POLL_IDLE_MS)
}

async function refreshTasks(): Promise<void> {
  try {
    const result = await unifiedApi.call<TaskListResult>('task.list')
    tasks.value = result?.tasks || []
  } catch (e) {
    log.error('Diagnostics: failed to fetch task list', e)
  }
  scheduleTaskPoll()
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

// ---- Card 4: System self-check ---------------------------------------------
// The backend answers only for the world *it* can see: are the directories
// usable, where did java/python resolve to, what proxy would a download use.
// Facts that live on the Electron side (app version, local-service health) or
// in the tool registry (built-in tool resolution) are composed here. Every
// probe carries a stable id and raw values — all wording stays in i18n, so no
// sentence ever crosses the wire.

const SELF_CHECK_ORDER = [
  'env.selfcheck', 'env.os', 'env.python', 'env.java', 'env.proxy', 'env.app',
  'tool.adb', 'tool.aapt', 'tool.apktool', 'tool.bundletool',
  'tool.zipalign', 'tool.apksigner', 'tool.jarsigner', 'tool.mitmproxy',
  'config.dir.runtime', 'config.dir.backend', 'config.dir.cache',
  'config.dir.tasks', 'config.dir.auto_tasks', 'config.dir.output',
  'config.tool_search', 'config.tool_overrides', 'config.proxy_download',
]

const CHECK_LABELS: Record<string, string> = {
  'env.selfcheck': 'diagnostics.ckSelfCheck',
  'env.os': 'diagnostics.ckOs',
  'env.python': 'diagnostics.ckPython',
  'env.java': 'diagnostics.ckJava',
  'env.proxy': 'diagnostics.ckProxy',
  'env.app': 'diagnostics.ckApp',
  'config.dir.runtime': 'diagnostics.ckDirRuntime',
  'config.dir.backend': 'diagnostics.ckDirBackend',
  'config.dir.cache': 'diagnostics.ckDirCache',
  'config.dir.tasks': 'diagnostics.ckDirTasks',
  'config.dir.auto_tasks': 'diagnostics.ckDirAutoTasks',
  'config.dir.output': 'diagnostics.ckDirOutput',
  'config.tool_search': 'diagnostics.ckToolSearch',
  'config.tool_overrides': 'diagnostics.ckToolOverrides',
  'config.proxy_download': 'diagnostics.ckProxyDownload',
  'tool.mitmproxy': 'diagnostics.ckMitmproxy',
  'run.backend': 'diagnostics.ckBackend',
}

const BUILTIN_TOOLS = ['adb', 'aapt', 'apktool', 'bundletool', 'zipalign', 'apksigner', 'jarsigner']

const GROUP_DEFS = [
  { key: 'env', titleKey: 'diagnostics.catEnv', cat: 'env' },
  { key: 'tool', titleKey: 'diagnostics.catTool', cat: 'tool' },
  { key: 'config', titleKey: 'diagnostics.catConfig', cat: 'config' },
  { key: 'runtime', titleKey: 'diagnostics.catRuntime', cat: 'runtime' },
] as const

const selfChecking = ref(false)
const selfCheckBase = ref<SelfCheckItem[]>([])
const selfCheckAt = ref<number | null>(null)

async function safeAsync<T>(fn: () => Promise<T> | undefined): Promise<T | null> {
  try {
    return (await fn()) ?? null
  } catch {
    return null
  }
}

/** Local-service health is polled globally, so it follows the store instead of
 *  freezing into the self-check snapshot. */
const backendSelfCheckItem = computed<SelfCheckItem>(() => {
  const healthy = healthStore.isHealthy
  return {
    id: 'run.backend',
    category: 'runtime',
    status: healthy === false ? 'fail' : healthy ? 'ok' : 'warn',
    value: healthy ? formattedUptime.value : '',
    facts: { healthy },
  }
})

const selfCheckItems = computed<SelfCheckItem[]>(() => [
  ...selfCheckBase.value,
  backendSelfCheckItem.value,
])

const selfCheckCounts = computed(() => {
  const counts = { ok: 0, warn: 0, fail: 0 }
  for (const item of selfCheckItems.value) counts[item.status] += 1
  return counts
})

const riskItems = computed(() => selfCheckItems.value.filter(i => i.status !== 'ok'))

const selfCheckGroups = computed(() =>
  GROUP_DEFS
    .map(g => ({ ...g, items: selfCheckItems.value.filter(i => i.category === g.cat) }))
    .filter(g => g.items.length > 0)
)

const selfCheckColor = computed(() =>
  selfCheckCounts.value.fail > 0 ? 'var(--app-red)'
  : selfCheckCounts.value.warn > 0 ? 'var(--app-yellow)'
  : 'var(--app-green)'
)

const selfCheckTimeText = computed(() =>
  selfCheckAt.value ? new Date(selfCheckAt.value).toLocaleTimeString() : '—'
)

function statusIcon(status: SelfCheckStatus) {
  if (status === 'fail') return XCircle
  if (status === 'warn') return AlertTriangle
  return CheckCircle2
}

function statusColor(status: SelfCheckStatus): string {
  if (status === 'fail') return 'var(--app-red)'
  if (status === 'warn') return 'var(--app-yellow)'
  return 'var(--app-green)'
}

function checkLabel(item: SelfCheckItem): string {
  const key = CHECK_LABELS[item.id]
  if (key) return t(key)
  // A tool probe's id *is* the tool name (adb / aapt / ...) — never translated.
  if (item.id.startsWith('tool.')) return item.id.slice(5)
  return item.id
}

function checkValue(item: SelfCheckItem): string {
  if (item.value) return item.value
  const facts = item.facts || {}
  if (facts.configured === false) return t('diagnostics.stateDirect')
  if (typeof facts.enabled === 'boolean') {
    return facts.enabled ? t('diagnostics.stateOn') : t('diagnostics.stateOff')
  }
  if (facts.count === 0 || facts.state === 'none') return t('diagnostics.stateNone')
  if (facts.source === 'none') return t('diagnostics.stateNotFound')
  switch (facts.reason) {
    case 'unresolved': return t('diagnostics.stateUnresolved')
    case 'missing': return t('diagnostics.stateMissing')
    case 'readonly': return t('diagnostics.stateReadonly')
    case 'not_runnable': return t('diagnostics.stateNotRunnable')
    case 'unavailable': return t('diagnostics.stateUnavailable')
    default: return '—'
  }
}

function checkHint(item: SelfCheckItem): string {
  if (item.status === 'ok') return ''
  const facts = item.facts || {}

  // A built-in tool's two failure modes read differently: "not usable at all"
  // versus "usable but the version is whatever happens to be on PATH".
  if (item.id.startsWith('tool.') && item.id !== 'tool.mitmproxy') {
    return item.status === 'fail' ? t('diagnostics.hintToolMissing') : t('diagnostics.hintToolSystem')
  }

  switch (item.id) {
    case 'env.selfcheck':
      return t('diagnostics.hintSelfCheck')
    case 'env.java':
      if (facts.source === 'none') return t('diagnostics.hintJavaMissing')
      if (facts.reason === 'not_runnable') return t('diagnostics.hintJavaNotRunnable')
      return t('diagnostics.hintJavaSystem')
    case 'env.proxy':
      return t('diagnostics.hintProxy')
    case 'config.proxy_download':
      return t('diagnostics.hintProxyDownload')
    case 'config.dir.output':
      return t('diagnostics.hintDirOutput')
    case 'config.tool_search':
      return t('diagnostics.hintToolSearch')
    case 'config.tool_overrides':
      return t('diagnostics.hintToolOverrides')
    case 'tool.mitmproxy':
      return t('diagnostics.hintMitmproxy')
    case 'run.backend':
      return facts.healthy === false ? t('diagnostics.hintBackend') : t('diagnostics.hintBackendUnknown')
    default:
      return ''
  }
}

async function runSelfCheck(): Promise<void> {
  selfChecking.value = true
  try {
    // Each probe stands alone: one failing source must not blank the whole card.
    const [backend, tools, traffic, overrides, viewModel, build] = await Promise.all([
      safeAsync(() => unifiedApi.call<SelfCheckResult>('system.selfcheck')),
      safeAsync(() => unifiedApi.call<Record<string, ToolDetail>>('tool.get_tools')),
      safeAsync(() => unifiedApi.call<TrafficStatus>('automation.traffic_status')),
      safeAsync(() => unifiedApi.call<Record<string, string>>('tool.get_custom_paths')),
      safeAsync(() => window.electronAPI?.settings?.getViewModel?.()),
      safeAsync(() => window.electronAPI?.getFontendBuildInfo?.()),
    ])

    const pool = new Map<string, SelfCheckItem>()
    if (backend) {
      for (const item of backend.checks || []) pool.set(item.id, item)
    } else {
      // Without the backend's own probes the card would silently lose half its
      // sections — say so explicitly instead.
      pool.set('env.selfcheck', {
        id: 'env.selfcheck',
        category: 'env',
        status: 'fail',
        value: '',
        facts: { reason: 'unavailable' },
      })
    }

    for (const name of BUILTIN_TOOLS) {
      const info = tools?.[name]
      const source = String(info?.source || 'none')
      pool.set(`tool.${name}`, {
        id: `tool.${name}`,
        category: 'tool',
        status: !info?.is_valid ? 'fail' : source === 'system' ? 'warn' : 'ok',
        value: [info?.version, info?.path].filter(Boolean).join(' · '),
        facts: { source },
      })
    }

    if (traffic) {
      const facts: Record<string, unknown> = {
        installed: traffic.installed,
        ready: traffic.ready,
        mismatch: traffic.python_mismatch,
      }
      if (!traffic.installed) facts.reason = 'missing'
      else if (!traffic.ready) facts.reason = 'not_runnable'
      pool.set('tool.mitmproxy', {
        id: 'tool.mitmproxy',
        category: 'tool',
        status: traffic.ready ? 'ok' : 'warn',
        value: traffic.installed ? traffic.lib_path : '',
        facts,
      })
    }

    const overrideNames = Object.keys(overrides || {})
    pool.set('config.tool_overrides', {
      id: 'config.tool_overrides',
      category: 'config',
      status: overrideNames.length ? 'warn' : 'ok',
      value: overrideNames.join(', '),
      facts: { count: overrideNames.length },
    })

    const useProxyForDownload = viewModel?.settings?.useProxyForDownload === true
    const envProxyFacts = (pool.get('env.proxy')?.facts || {}) as Record<string, unknown>
    pool.set('config.proxy_download', {
      id: 'config.proxy_download',
      category: 'config',
      // Downloading through a dead proxy always fails — that is a defect, not a
      // caveat, which is exactly the [WinError 10061] case.
      status: useProxyForDownload && envProxyFacts.reachable === false ? 'fail' : 'ok',
      value: '',
      facts: { enabled: useProxyForDownload },
    })

    pool.set('env.app', {
      id: 'env.app',
      category: 'env',
      status: 'ok',
      value: [
        build?.appVersion ? `v${build.appVersion}` : '',
        build?.electronVersion ? `Electron ${build.electronVersion}` : '',
      ].filter(Boolean).join(' · '),
    })

    const ordered: SelfCheckItem[] = []
    const seen = new Set<string>()
    for (const id of SELF_CHECK_ORDER) {
      const item = pool.get(id)
      if (item) {
        ordered.push(item)
        seen.add(id)
      }
    }
    // Probes a future backend adds must still show up rather than vanish.
    for (const [id, item] of pool) if (!seen.has(id)) ordered.push(item)

    selfCheckBase.value = ordered
    selfCheckAt.value = Date.now()
  } catch (e) {
    log.error('Diagnostics: self-check failed', e)
  } finally {
    selfChecking.value = false
  }
}

// ---- Lifecycle --------------------------------------------------------------
onMounted(() => {
  refreshHealth()
  refreshTasks() // 首次拉取后由 scheduleTaskPoll 自续期
  refreshLogTail()
  void runSelfCheck()
})

onUnmounted(() => {
  taskPollStopped = true
  if (taskPoll) clearTimeout(taskPoll)
})
</script>

<style scoped>
.diagnostics-content { display: flex; flex-direction: column; gap: 16px; }
.diag-card { background: var(--app-card-bg); border-radius: 10px; text-align: left; transition: box-shadow 0.2s ease; }
.diag-card:hover { box-shadow: var(--app-shadow-md); }
.header-action { margin-left: auto; }

/* Health */
.health-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.health-label { font-size: var(--app-font-size-lg); font-weight: 600; color: var(--app-text-primary); }
.health-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.health-dot.dot-healthy { background: var(--app-green); }
.health-dot.dot-unhealthy { background: var(--app-red); animation: diag-pulse 1.5s infinite; }
.health-dot.dot-unknown { background: var(--app-text-dim); }
@keyframes diag-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* Tasks / logs shared */
.empty-hint { font-size: var(--app-font-size-md); color: var(--app-text-dim); padding: 8px 0; }

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
  font-family: var(--app-font-mono);
  font-size: var(--app-font-size-sm);
  line-height: 1.6;
  color: var(--app-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}
.log-meta { display: flex; align-items: center; gap: 8px; }
.log-meta-tag { margin-left: 4px; }

/* Self-check */
.sc-summary { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 2px 0 10px; border-bottom: 1px solid var(--app-card-border); }
.sc-count { display: inline-flex; align-items: center; gap: 6px; font-size: var(--app-font-size-md); color: var(--app-text-secondary); }
.sc-stamp { margin-left: auto; font-size: var(--app-font-size-sm); }
.sc-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex: none; }
.sc-dot-ok { background: var(--app-green); }
.sc-dot-warn { background: var(--app-yellow); }
.sc-dot-fail { background: var(--app-red); }

.sc-section { padding-top: 12px; }
.sc-section-title { font-size: var(--app-font-size-sm); font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--app-text-dim); margin-bottom: 4px; }
.sc-clean { display: flex; align-items: center; gap: 6px; font-size: var(--app-font-size-md); color: var(--app-text-dim); padding: 4px 0; }
.sc-list { display: flex; flex-direction: column; }

/* icon | label | value, with the hint wrapping onto a second row */
.sc-row {
  display: grid;
  grid-template-columns: 16px minmax(104px, 168px) minmax(0, 1fr);
  align-items: baseline;
  gap: 2px 10px;
  padding: 5px 0;
  font-size: var(--app-font-size-md);
}
.sc-row + .sc-row { border-top: 1px solid var(--app-card-border); }
.sc-icon { justify-self: center; align-self: start; margin-top: 3px; }
.sc-label { color: var(--app-text-primary); }
.sc-value { color: var(--app-text-secondary); font-family: var(--app-font-mono); font-size: var(--app-font-size-sm); overflow-wrap: anywhere; }
.sc-hint { grid-column: 2 / -1; font-size: var(--app-font-size-sm); color: var(--app-text-dim); }
</style>
