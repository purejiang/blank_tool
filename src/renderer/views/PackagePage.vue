<template>
  <div class="package-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('package.title') }}</h1>
        <p class="page-subtitle">{{ t('package.subtitle') }}</p>
      </div>
      <n-space :size="8">
        <n-button size="tiny" quaternary @click="confirmClearCompleted" :disabled="!taskStore.hasCompleted">
          {{ t('task.clearCompleted') }}
        </n-button>
        <n-button size="tiny" quaternary type="error" @click="confirmClearAll" :disabled="taskStore.tasks.length === 0">
          {{ t('task.clearAll') }}
        </n-button>
      </n-space>
    </div>

    <!-- New Task Bar -->
    <div class="new-task-bar">
      <div class="task-bar-row">
        <n-radio-group v-model:value="newSource" size="small">
          <n-radio-button value="url" :disabled="taskStore.hasRunning">{{ t('task.url') }}</n-radio-button>
          <n-radio-button value="local">{{ t('task.local') }}</n-radio-button>
        </n-radio-group>

        <n-input
          v-if="newSource === 'url'"
          v-model:value="newUrl"
          :placeholder="t('task.urlPlaceholder')"
          size="small"
          clearable
        />
        <div v-else class="local-file-picker" @click="pickLocalFile">
          <n-icon size="16"><FolderOpen /></n-icon>
          <span>{{ newLocalName || t('task.selectFile') }}</span>
        </div>

        <n-select v-model:value="newOperation" :options="operationOptions" size="small" style="width:120px" />

        <n-button type="primary" size="small" @click="startNewTask" :disabled="!canStart">
          <template #icon><n-icon><Play /></n-icon></template>
          {{ t('task.start') }}
        </n-button>
      </div>

      <div class="task-bar-opts">
        <span class="op-desc">{{ t('task.' + newOperation + 'Desc') }}</span>

        <template v-if="newOperation === 'resign' || newOperation === 'recompile'">
          <span class="op-label">{{ t('task.signConfig') }}</span>
          <n-select v-model:value="newSignId" :options="signOptions" size="tiny" style="width:180px" :placeholder="t('signature.select')" />
        </template>

        <template v-if="newOperation === 'decompile'">
          <span class="op-label">{{ t('task.decompileOpts') }}</span>
          <n-checkbox v-model:checked="decompileResources" size="small">{{ t('task.decompileResources') }}</n-checkbox>
          <n-checkbox v-model:checked="decompileSources" size="small">{{ t('task.decompileSources') }}</n-checkbox>
        </template>
      </div>
    </div>

    <!-- Task List Area (scrollable) -->
    <div class="task-list-area">
    <div v-if="taskStore.tasks.length === 0" class="empty-state">
      <n-icon size="48" color="var(--app-text-dim)"><Inbox /></n-icon>
      <p class="empty-title">{{ t('task.empty') }}</p>
      <p class="empty-desc">{{ t('task.emptyDesc') }}</p>
    </div>

    <div v-else class="task-list">
      <div v-for="task in taskStore.tasks"
        :key="task.id"
        class="task-card"
        :class="'task-' + task.status"
      >
        <div class="task-header" @click="toggleTask(task)">
          <div class="task-header-left">
            <span class="task-id">#{{ task.id }}</span>
            <n-icon size="16" :color="task.source === 'url' ? 'var(--app-blue)' : 'var(--app-text-dim)'">
              <Link v-if="task.source === 'url'" />
              <FolderOpen v-else />
            </n-icon>
            <n-tag :type="opTagType(task.operation)" size="tiny" :bordered="false">
              {{ task.operationLabel }}
            </n-tag>
            <span class="task-filename" :title="task.fileName">{{ task.fileName }}</span>
          </div>
          <div class="task-header-right">
            <n-tag v-if="task.status === 'completed'" type="success" size="tiny" :bordered="false">
              <template #icon><n-icon size="12"><CheckCircle /></n-icon></template>
              {{ t('task.completed') }}
            </n-tag>
            <n-tag v-else-if="task.status === 'failed'" type="error" size="tiny" :bordered="false">
              <template #icon><n-icon size="12"><XCircle /></n-icon></template>
              {{ t('task.failed') }}
            </n-tag>
            <n-tag v-else-if="task.status === 'cancelled'" type="warning" size="tiny" :bordered="false">
              <template #icon><n-icon size="12"><AlertCircle /></n-icon></template>
              {{ t('task.cancelled') }}
            </n-tag>
            <n-tag v-else-if="task.status === 'cancelling'" type="warning" size="tiny" :bordered="false">
              <template #icon><n-icon size="12"><Loader /></n-icon></template>
              {{ t('task.cancelling') }}
            </n-tag>
            <n-tag v-else-if="task.status === 'running'" type="success" size="tiny" :bordered="false">
              <template #icon><n-icon size="12"><Loader /></n-icon></template>
              {{ task.progressLabel }}
            </n-tag>
            <n-tag v-else-if="task.status === 'downloading'" type="info" size="tiny" :bordered="false">
              <template #icon><n-icon size="12"><Download /></n-icon></template>
              {{ task.progressLabel }}
            </n-tag>
            <n-tag v-else type="default" size="tiny" :bordered="false">
              {{ t('task.queued') }}
            </n-tag>
            <span class="task-time">{{ formatTime(task.createdAt) }}</span>
            <span v-if="task.startedAt || task.createdAt" class="task-duration">{{ formatDuration(task) }}</span>
            <n-button
              v-if="task.status === 'running' || task.status === 'downloading'"
              size="tiny"
              quaternary
              type="warning"
              :title="t('task.cancel')"
              @click.stop="cancelTask(task)"
            >
              <template #icon><n-icon size="14"><StopCircle /></n-icon></template>
            </n-button>
            <n-button
              v-if="task.status === 'failed' || task.status === 'cancelled'"
              size="tiny"
              quaternary
              type="warning"
              :title="t('app.retry')"
              @click.stop="retryTask(task)"
            >
              <template #icon><n-icon size="14"><RefreshCw /></n-icon></template>
            </n-button>
            <n-button
              v-if="task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled'"
              size="tiny"
              quaternary
              type="error"
              @click.stop="confirmRemoveTask(task)"
            >
              <template #icon><n-icon size="14"><Trash2 /></n-icon></template>
            </n-button>
            <n-icon size="16" color="var(--app-text-dim)">
              <ChevronDown v-if="!task.collapsed" />
              <ChevronRight v-else />
            </n-icon>
          </div>
        </div>

        <!-- Progress bar -->
        <div v-if="task.status === 'running' || task.status === 'downloading'" class="task-progress">
          <n-progress type="line" :percentage="task.progress" :height="3" color="#22C55E" :indicator-placement="'none'" />
        </div>

        <!-- Expanded detail -->
        <div v-if="!task.collapsed" class="task-detail">
          <div v-if="task.error" class="task-error">{{ task.error }}</div>
          <div v-if="task.filePath" class="task-output">
            <n-icon size="14" color="var(--app-text-dim)"><FolderOpen /></n-icon>
            <span class="task-output-path">{{ t('task.source') }}: {{ task.filePath }}</span>
            <n-button size="tiny" quaternary @click.stop="openInExplorer(task.filePath)">
              <template #icon><n-icon size="13"><ExternalLink /></n-icon></template>
            </n-button>
          </div>
          <div v-if="task.outputPath" class="task-output">
            <n-icon size="14" color="var(--app-green)"><FolderOpen /></n-icon>
            <span class="task-output-path">{{ t('task.output') }}: {{ task.outputPath }}</span>
            <n-button size="tiny" quaternary type="info" @click.stop="openInExplorer(task.outputPath)">
              <template #icon><n-icon size="13"><ExternalLink /></n-icon></template>
            </n-button>
          </div>
          <div v-if="task.result" class="task-result" v-html="task.result" />
          <!-- Terminal task: has file log content → show it with refresh -->
          <div v-if="isTerminal(task.status) && taskLogCache.has(task.id) && taskLogCache.get(task.id)?.length" class="task-logs">
            <div class="task-logs-header" style="display:flex;justify-content:flex-end;margin-bottom:4px;">
              <n-button size="tiny" quaternary @click.stop="refreshTaskLog(task)">↻</n-button>
              <n-button size="tiny" quaternary @click.stop="loadFullTaskLog(task)">📄</n-button>
            </div>
            <n-virtual-list
              :items="taskLogCache.get(task.id) || []"
              :item-size="18"
              item-resizable
              style="max-height: 170px"
            >
              <template #default="{ item }">
                <div class="task-log-line">{{ item.text }}</div>
              </template>
            </n-virtual-list>
          </div>
          <!-- Fallback: show in-memory logs (running tasks, OR terminal tasks without file log) -->
          <div v-else-if="task.logs.length > 0" class="task-logs">
            <div v-if="isTerminal(task.status)" class="task-logs-header" style="display:flex;justify-content:flex-end;margin-bottom:4px;">
              <n-button size="tiny" quaternary @click.stop="refreshTaskLog(task)">↻</n-button>
              <n-button size="tiny" quaternary @click.stop="loadFullTaskLog(task)">📄</n-button>
            </div>
            <n-virtual-list
              v-if="task.logs.length > 100"
              :items="task.logs.map((text, i) => ({ key: i, text }))"
              :item-size="18"
              item-resizable
              style="max-height: 170px"
            >
              <template #default="{ item }">
                <div class="task-log-line">{{ item.text }}</div>
              </template>
            </n-virtual-list>
            <div v-else>
              <div v-for="(line, i) in task.logs" :key="i" class="task-log-line">{{ line }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon, NVirtualList, useDialog } from 'naive-ui'
import {
  Play, Link, FolderOpen, CheckCircle, XCircle, Loader,
  ChevronDown, ChevronRight, Trash2, Inbox, ExternalLink, StopCircle, AlertCircle, Download, RefreshCw
} from 'lucide-vue-next'
import { useNotification } from '@composables/useNotification'
import { useTaskStore } from '@stores/index'
import { useSignatureStore } from '@stores/signatureStore'
import type { Task } from '@stores/taskStore'
import { formatDuration as formatDurationUtil } from '@utils/formatDuration'
import serviceManager from '@services/ServiceManager'

const { t } = useI18n()
const dialog = useDialog()
const taskStore = useTaskStore()
const sigStore = useSignatureStore()
if (sigStore.configs.length === 0) sigStore.loadConfigs()

const OP_TAG_MAP: Record<Task['operation'], string> = {
  analyze: 'info', install: 'success', decompile: 'warning', recompile: 'warning', resign: 'error'
}

const activeIntervals = new Set<ReturnType<typeof setInterval>>()
const activeStreamCleanups = new Set<() => void>()
// Active progress interval for the currently-executing task operation phase.
// Set by runOperation(), read by onStream's complete/error handlers in executeTask().
let activeIv: ReturnType<typeof setInterval> | null = null

// Reactive clock for real-time duration display.
// Updated every 1s when there are active (non-terminal) tasks.
const now = ref(Date.now())
let nowIv: ReturnType<typeof setInterval> | null = null
const taskLogCache = ref<Map<number, { key: number; text: string }[]>>(new Map())

// Log buffering: batch high-volume stream events to avoid UI jank
const logBuffers = new Map<number, string[]>()
const logTimers = new Map<number, ReturnType<typeof setTimeout>>()

function flushLogBuffer(taskId: number) {
  const buf = logBuffers.get(taskId)
  if (buf && buf.length > 0) {
    taskStore.appendLogBatch(taskId, [...buf])
    buf.length = 0
  }
  logTimers.delete(taskId)
}

function startNowTimer() {
  if (nowIv !== null) return
  const iv = setInterval(() => { now.value = Date.now() }, 1000)
  activeIntervals.add(iv)
  nowIv = iv
}

function stopNowTimer() {
  if (nowIv !== null) {
    clearIntervalAndForget(nowIv)
    nowIv = null
  }
}

function syncNowTimer() {
  const activeStatuses = ['running', 'downloading', 'queued', 'cancelling']
  const hasActive = taskStore.tasks.some(t => activeStatuses.includes(t.status))
  if (hasActive && nowIv === null) {
    startNowTimer()
  } else if (!hasActive && nowIv !== null) {
    stopNowTimer()
  }
}

onUnmounted(() => {
  stopNowTimer()
  activeIntervals.forEach(clearInterval)
  activeIntervals.clear()
  activeStreamCleanups.forEach(fn => fn())
  activeStreamCleanups.clear()
})

// Reactively start/stop the duration clock based on active tasks
watch(() => taskStore.tasks, () => { syncNowTimer() }, { deep: true })

// New task form
const newSource = ref<'url' | 'local'>('local')
const newUrl = ref('')
const newOperation = ref<Task['operation']>('analyze')
const newLocalPath = ref('')
const newLocalName = ref('')
const newSignId = ref('')
const decompileResources = ref(true)
const decompileSources = ref(true)

const signOptions = computed(() =>
  sigStore.configs.map((c: any) => ({ label: c.name, value: c.id }))
)

const OPERATIONS_ORDERED: Task['operation'][] = ['analyze', 'install', 'decompile', 'recompile', 'resign']
const operationOptions = computed(() =>
  OPERATIONS_ORDERED.map(op => ({ label: t(`task.${op}`), value: op }))
)

const canStart = computed(() => {
  if (newSource.value === 'url') return !!newUrl.value.trim()
  return !!newLocalPath.value
})

function opTagType(op: string) {
  return OP_TAG_MAP[op as Task['operation']] || 'default'
}

function formatTime(ts: number) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}-${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function formatDuration(task: Task): string {
  return formatDurationUtil(task, now.value)
}

async function openInExplorer(filePath: string) {
  try {
    const svc = await serviceManager.getService('system') as any
    if (svc && typeof svc.openPath === 'function') svc.openPath(filePath)
  } catch (e) { /* ignore */ }
}

function isTerminal(status: string): boolean {
  return ['completed', 'failed', 'cancelled'].includes(status)
}

function toggleTask(task: Task) {
  task.collapsed = !task.collapsed
  if (!task.collapsed && isTerminal(task.status) && !taskLogCache.value.has(task.id)) {
    loadTaskLog(task)
  }
}

async function loadTaskLog(task: Task) {
  try {
    const api = window.electronAPI as any
    const result = await api.callBackendAPI('task.read_log', { task_id: String(task.id), tail_bytes: 100 * 1024 })
    const content = (result.content || '').trim()
    if (content) {
      taskLogCache.value.set(task.id, splitLogLines(content))
    }
  } catch (e) {
    taskLogCache.value.set(task.id, [{ key: 0, text: `[Error loading log: ${e}]` }])
  }
}

function splitLogLines(content: string): { key: number; text: string }[] {
  return content.split('\n').map((text, i) => ({ key: i, text }))
}

async function refreshTaskLog(task: Task) {
  taskLogCache.value.delete(task.id)
  await loadTaskLog(task)
}

async function loadFullTaskLog(task: Task) {
  try {
    const api = window.electronAPI as any
    const result = await api.callBackendAPI('task.read_log', { task_id: String(task.id) })
    const content = (result.content || '').trim()
    if (content) {
      taskLogCache.value.set(task.id, splitLogLines(content))
    }
  } catch (e) {
    // keep existing cache on error
  }
}

async function pickLocalFile() {
  try {
    const svc = await serviceManager.getService('system') as any
    const isDir = newOperation.value === 'recompile'
    const result = isDir
      ? await svc.selectDirectory({ title: t('task.selectDir') })
      : await svc.selectFile({ title: t('task.selectFile'), filters: [{ name: 'APK/AAB', extensions: ['apk', 'aab'] }] })
    if (result && !result.canceled && result.filePaths?.length) {
      const fp = result.filePaths[0]
      newLocalPath.value = fp
      newLocalName.value = fp.split(/[/\\]/).pop() || 'file'
    }
  } catch (e) {
    console.error('pickLocalFile error:', e)
  }
}

async function startNewTask() {
  let source: Task['source'], url: string | undefined, fp: string, fn: string

  if (newSource.value === 'url') {
    source = 'url'
    url = newUrl.value.trim()
    fn = url.split('/').pop() || 'app.apk'
    fp = ''
  } else {
    source = 'local'
    fp = newLocalPath.value
    fn = newLocalName.value || fp.split(/[/\\]/).pop() || 'file'
  }

  const opLabel = operationOptions.value.find(o => o.value === newOperation.value)?.label || newOperation.value
  const task = taskStore.createTask({ source, url, filePath: fp, fileName: fn, operation: newOperation.value, operationLabel: opLabel })

  // Clear inputs
  newUrl.value = ''
  newLocalName.value = ''
  newLocalPath.value = ''

  // Execute task
  await executeTask(task)
}

async function executeTask(task: Task) {
  const { showError } = useNotification()
  let streamCleanup: (() => void) | null = null
  try {
    let localPath = task.filePath
    const api = window.electronAPI as any
    let phase: 'download' | 'operation' = task.source === 'url' ? 'download' : 'operation'
    let phaseResolve: ((v: any) => void) | null = null
    let phaseReject: ((e: Error) => void) | null = null

    const onStream = (raw: any) => {
      if (!raw) return
      const data = raw.data || raw
      const tid = data.task_id || (data.payload?.['task_id'])
      if (tid !== String(task.id)) return
      if (data.type === 'progress' && data.payload) {
        taskStore.updateTask(task.id, { progress: data.payload.progress || 0, progressLabel: data.payload.label || `${data.payload.progress || 0}%` })
      }
      if (data.type === 'complete' && phaseResolve) {
        const payload = data.payload || data
        if (phase === 'operation') {
          if (activeIv) finishProgress(task, activeIv)
          const updates: any = { status: 'completed', progress: 100, progressLabel: t('task.completed'), finishedAt: Date.now() }
          if (payload.output_dir) updates.outputPath = payload.output_dir
          if (payload.output_apk) updates.outputPath = payload.output_apk
          if (payload.package_name) updates.result = renderApkInfo(payload)
          if (payload.apk_path) updates.outputPath = payload.apk_path
          taskStore.updateTask(task.id, updates)
          log(task, t(`task.${task.operation}Done`) + (updates.outputPath ? ' → ' + updates.outputPath : ''))
        }
        phaseResolve(payload)
      }
      if (data.type === 'cancelled') {
        if (phaseReject) phaseReject(new Error('cancelled'))
        taskStore.updateTask(task.id, { status: 'cancelled', progressLabel: t('task.cancelled'), finishedAt: Date.now() })
        log(task, t('task.cancelled'))
      }
      if (data.type === 'error' && phaseReject) {
        const msg = (data.payload?.message) || data.message || t('task.streamOpFailed')
        console.log('[PackagePage] stream error received:', msg, 'phase:', phase)
        if (phase === 'operation') {
          if (activeIv) clearIntervalAndForget(activeIv)
        }
        taskStore.updateTask(task.id, { status: 'failed', error: msg, finishedAt: Date.now() })
        log(task, t('task.failed') + ': ' + msg)
        try {
          const phaseLabel = phase === 'download' ? t('task.download') : task.operationLabel
          showError(phaseLabel, msg)
        } catch (e) { console.warn('[PackagePage] showError failed:', e) }
        phaseReject(new Error(msg))
      }
      const line = data.line || data.message || data.output || ''
      if (line) {
        if (!logBuffers.has(task.id)) logBuffers.set(task.id, [])
        logBuffers.get(task.id)!.push(line)
        if (logBuffers.get(task.id)!.length >= 20) {
          flushLogBuffer(task.id)
        } else if (!logTimers.has(task.id)) {
          logTimers.set(task.id, setTimeout(() => flushLogBuffer(task.id), 100))
        }
      }
    }

    if (api?.onStreamEvent) {
      streamCleanup = api.onStreamEvent(onStream)
      if (streamCleanup) activeStreamCleanups.add(streamCleanup)
    }

    // Download if URL source
    if (task.source === 'url' && task.url) {
      taskStore.updateTask(task.id, { status: 'downloading', progress: 0, progressLabel: t('task.downloading') })
      log(task, t('task.downloading') + ' ' + task.url)
      if (!api || typeof api.downloadFile !== 'function') throw new Error(t('task.downloadAPINotAvailable'))
      const dlPromise = new Promise<any>((resolve, reject) => { phaseResolve = resolve; phaseReject = reject })
      api.downloadFile(task.url, task.fileName, String(task.id))
      const dlResult = await dlPromise
      localPath = dlResult.file_path
      taskStore.updateTask(task.id, { filePath: dlResult.file_path, progress: 100, progressLabel: t('task.completed') })
      log(task, t('task.completed') + ` (${(dlResult.size / 1024 / 1024).toFixed(1)}MB)`)
      phase = 'operation'
    }

    // Execute operation as streaming
    taskStore.updateTask(task.id, { status: 'running', progress: 0, progressLabel: t('task.running') })
    log(task, t('task.running') + ' ' + task.operationLabel)

    // Create new promise for operation phase
    const opPromise = new Promise<any>((resolve, reject) => { phaseResolve = resolve; phaseReject = reject })
    await runOperation(task, localPath)
    await opPromise
  } catch (e: any) {
    const isCancelled = e?.message === 'cancelled'
    if (!isCancelled) {
      const errMsg = e.message || String(e)
      taskStore.updateTask(task.id, { status: 'failed', error: errMsg, finishedAt: Date.now() })
      log(task, t('task.failed') + ': ' + errMsg)
      showError(task.operationLabel, errMsg)
    }
  } finally {
    if (streamCleanup) {
      streamCleanup()
      activeStreamCleanups.delete(streamCleanup)
    }
  }
}

function log(task: Task, msg: string) {
  taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] ${msg}`)
}

async function cancelTask(task: Task) {
  const name = task.fileName || task.operationLabel
  const prevStatus = task.status
  dialog.warning({
    title: t('task.cancel'),
    content: t('task.cancelConfirm', { name }),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      const api = window.electronAPI as any
      taskStore.updateTask(task.id, { status: 'cancelling' as any, progressLabel: t('task.cancelling') })
      if (api && typeof api.cancelApkTask === 'function') {
        try {
          const result = await api.cancelApkTask(String(task.id))
          if (result && !result.cancelled) {
            // Task already finished — restore previous status
            const current = taskStore.tasks.find(t => t.id === task.id)
            if (current?.status === ('cancelling' as any)) {
              taskStore.updateTask(task.id, { status: prevStatus, progressLabel: '' })
            }
            const { showInfo } = useNotification()
            showInfo(name, t('task.alreadyFinished'))
          }
        } catch (e) {
          console.error('Cancel error:', e)
          // Restore on error too
          const current = taskStore.tasks.find(t => t.id === task.id)
          if (current?.status === ('cancelling' as any)) {
            taskStore.updateTask(task.id, { status: prevStatus, progressLabel: '' })
          }
        }
      }
    }
  })
}

async function retryTask(task: Task) {
  // Reset task state to queued, keep existing logs and append below them
  taskStore.appendLog(task.id, `--- ${t('app.retry')} ---`)
  // Clean up any lingering progress interval from the failed attempt
  if (activeIv) { clearIntervalAndForget(activeIv); activeIv = null }
  taskStore.updateTask(task.id, {
    status: 'queued',
    error: '',
    result: '',
    progress: 0,
    progressLabel: '',
    startedAt: Date.now(),
    finishedAt: null,
  })
  task.collapsed = true
  // Re-execute the same task
  await executeTask(task)
}

async function confirmClearCompleted() {
  const del = await window.electronAPI?.appConfig?.get('autoDeleteOutputOnTaskRemove')
  dialog.warning({
    title: t('task.clearCompleted'),
    content: del === true ? t('task.clearCompletedConfirmDelete') : t('task.clearCompletedConfirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => { taskStore.clearCompleted() }
  })
}

async function confirmClearAll() {
  const del = await window.electronAPI?.appConfig?.get('autoDeleteOutputOnTaskRemove')
  dialog.error({
    title: t('task.clearAll'),
    content: del === true ? t('task.clearAllConfirmDelete') : t('task.clearAllConfirm'),
    positiveText: t('common.confirm'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => { taskStore.clearAll() }
  })
}

async function confirmRemoveTask(task: Task) {
  const del = await window.electronAPI?.appConfig?.get('autoDeleteOutputOnTaskRemove')
  const isTerminal = ['completed', 'failed', 'cancelled'].includes(task.status)
  if (del === true && isTerminal && task.outputPath) {
    dialog.warning({
      title: t('task.clearCompleted'),
      content: t('task.removeConfirmDelete'),
      positiveText: t('common.confirm'),
      negativeText: t('common.cancel'),
      onPositiveClick: () => { taskLogCache.value.delete(task.id); taskStore.removeTask(task.id) }
    })
  } else {
    taskLogCache.value.delete(task.id)
    taskStore.removeTask(task.id)
  }
}

async function runOperation(task: Task, localPath: string) {
  const op = task.operation
  const ingLabel = t(`task.${op}ing`)
  const svcName = op === 'install' ? 'device' : 'apk'
  const methodName = op === 'analyze' ? 'analyzeApk'
    : op === 'install' ? 'installApp'
    : op === 'decompile' ? 'decompileApk'
    : op === 'recompile' ? 'recompileApk'
    : 'signApk'

  const svc = await serviceManager.getService(svcName) as any
  if (typeof svc?.[methodName] !== 'function') throw new Error(t(`task.${op}SvcUnavailable`))

  // Prepare operation-specific options (include task_id for cancellation)
  let opts: any = undefined
  let logExtra = ''
  if (op === 'decompile') {
    opts = { resources: decompileResources.value, sources: decompileSources.value, task_id: String(task.id) }
    logExtra = ` (${t('task.decompileResources')}:${opts.resources}, ${t('task.decompileSources')}:${opts.sources})`
  } else if (op === 'recompile') {
    opts = { sign: false, align: true, optimize: true, task_id: String(task.id) }
    const cfg = sigStore.configs.find((c: any) => c.id === newSignId.value) || sigStore.configs[0]
    if (cfg) {
      opts = { ...opts, sign: true, v2: true, keystore: { path: cfg.path, alias: cfg.alias, storepass: cfg.storepass, keypass: cfg.keypass } }
      logExtra = ` (${t('task.resign')}:${cfg.name})`
    }
  } else if (op === 'resign') {
    const cfg = sigStore.configs.find((c: any) => c.id === newSignId.value) || sigStore.configs[0]
    if (!cfg) throw new Error(t('task.noSignConfig'))
    opts = { path: cfg.path, alias: cfg.alias, storepass: cfg.storepass, keypass: cfg.keypass, task_id: String(task.id) }
    logExtra = ` (${cfg.name})`
  } else if (op === 'install') {
    opts = { task_id: String(task.id) }
  }

  const iv = startProgress(task, ingLabel)
  activeIv = iv
  log(task, ingLabel + logExtra)

  // Call the service — returns {stream_id} immediately
  // Result comes via onStream → phaseResolve
  try {
    await svc[methodName](localPath, opts || { task_id: String(task.id) })
  } catch (err) {
    clearIntervalAndForget(iv)
    throw err
  }
}

function renderApkInfo(data: any) {
  if (!data) return ''
  const perms: string[] = data.permissions || []
  const nativeLibs: string[] = data.native_libs || []

  // Classify permissions
  const DANGEROUS = new Set([
    'android.permission.READ_CONTACTS', 'android.permission.WRITE_CONTACTS', 'android.permission.GET_ACCOUNTS',
    'android.permission.READ_CALENDAR', 'android.permission.WRITE_CALENDAR',
    'android.permission.CAMERA',
    'android.permission.BODY_SENSORS',
    'android.permission.ACCESS_FINE_LOCATION', 'android.permission.ACCESS_COARSE_LOCATION', 'android.permission.ACCESS_BACKGROUND_LOCATION',
    'android.permission.RECORD_AUDIO',
    'android.permission.READ_PHONE_STATE', 'android.permission.READ_PHONE_NUMBERS', 'android.permission.CALL_PHONE', 'android.permission.ANSWER_PHONE_CALLS',
    'android.permission.READ_CALL_LOG', 'android.permission.WRITE_CALL_LOG',
    'android.permission.SEND_SMS', 'android.permission.RECEIVE_SMS', 'android.permission.READ_SMS', 'android.permission.RECEIVE_MMS', 'android.permission.RECEIVE_WAP_PUSH',
    'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE', 'android.permission.MANAGE_EXTERNAL_STORAGE',
    'android.permission.ACTIVITY_RECOGNITION',
    'android.permission.BLUETOOTH_CONNECT', 'android.permission.BLUETOOTH_SCAN', 'android.permission.BLUETOOTH_ADVERTISE',
    'android.permission.POST_NOTIFICATIONS',
    'android.permission.READ_MEDIA_IMAGES', 'android.permission.READ_MEDIA_VIDEO', 'android.permission.READ_MEDIA_AUDIO',
    'android.permission.NEARBY_WIFI_DEVICES',
    'android.permission.UWB_RANGING',
  ])
  const dangerous = perms.filter(p => DANGEROUS.has(p))
  const normal = perms.filter(p => !DANGEROUS.has(p))

  const label = (k: string, params?: any) => t(`task.${k}`, params)
  const esc = (s: string) => s ? s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : '-'
  const fmtSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '-'
    const u = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + ' ' + u[i]
  }

  const archColors: Record<string, string> = {
    arm64: '#22c55e', armeabi: '#3b82f6', x86_64: '#f59e0b', x86: '#ef4444', mips: '#8b5cf6', riscv: '#ec4899'
  }
  const archChips = nativeLibs.map(abi => {
    const prefix = Object.keys(archColors).find(k => abi.startsWith(k)) || ''
    const color = archColors[prefix] || '#6b7280'
    return `<span style="display:inline-block;background:${color}18;color:${color};border:1px solid ${color}40;border-radius:4px;padding:1px 7px;font-size:11px;font-family:monospace;margin-right:4px">${esc(abi)}</span>`
  }).join('')

  const permBadge = (p: string, danger: boolean) => {
    const name = p.replace('android.permission.', '')
    const style = danger
      ? 'display:inline-block;background:rgba(220,38,38,0.1);color:var(--app-red);border:1px solid rgba(220,38,38,0.25);border-radius:3px;padding:1px 6px;font-size:11px;font-family:monospace;margin:1px 2px'
      : 'display:inline-block;background:var(--app-card-border);color:var(--app-text-dim);border-radius:3px;padding:1px 6px;font-size:11px;font-family:monospace;margin:1px 2px'
    return `<span title="${esc(p)}" style="${style}">${esc(name)}</span>`
  }

  const soComp = data.so_comparison
  const comp = data.compression_analysis
  const page16 = data.page_size_16kb

  // Compute summaries for deep analysis toggle text
  let soCompSummary = ''
  if (soComp && !soComp.single_arch && !soComp.no_native && soComp.arches && Object.keys(soComp.arches).length > 0) {
    soCompSummary = `${label('soComparison')} (${Object.keys(soComp.arches).length} arches / ${soComp.baseline?.length || 0} unique .so)`
  }

  let compSummary = ''
  if (comp && Object.keys(comp).length > 0) {
    const compParts: string[] = []
    for (const [cat, info] of Object.entries(comp)) {
      const c = info as any
      compParts.push(`${cat}: ${c.stored||0}s/${c.deflated||0}c`)
    }
    compSummary = `${label('compressionAnalysis')} (${compParts.join(', ')})`
  }

  let pageSummaryParts: string[] = []
  if (page16) {
    for (const [arch, files] of Object.entries(page16)) {
      if (arch === 'skipped') continue
      const entries = Object.values(files as any) as any[]
      const total = entries.length
      const supported = entries.filter((e: any) => e.supports_16kb).length
      pageSummaryParts.push(`${esc(arch)}: ${supported}/${total}`)
    }
  }
  const pageSummary = pageSummaryParts.join(', ')

  let html = `<div style="display:flex;flex-direction:column;gap:6px;font-size:13px;line-height:1.6">`

  // ===== BASIC INFO CARD =====
  html += '<div style="background:var(--app-card-bg);border:1px solid var(--app-card-border);border-radius:8px;padding:10px 14px;margin-top:6px">'
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;font-size:13px">'
  // Row 1: appName | packageName
  html += `<div><span style="color:var(--app-text-dim)">${label('appName')}：</span><span style="color:var(--app-text-primary)">${esc(data.application_label)}</span></div>`
  html += `<div><span style="color:var(--app-text-dim)">${label('packageName')}：</span><span style="color:var(--app-text-secondary);font-family:monospace;font-size:12px">${esc(data.package_name)}</span></div>`
  // Row 2: version | fileSize
  html += `<div><span style="color:var(--app-text-dim)">${label('version')}：</span><span style="color:var(--app-text-secondary)">${esc(data.version_name)} (${esc(data.version_code)})</span></div>`
  html += `<div><span style="color:var(--app-text-dim)">${label('fileSize')}：</span><span style="color:var(--app-text-secondary);font-weight:600">${fmtSize(data.file_size)}</span></div>`
  // Row 3: minSdk + targetSdk | architecture
  html += `<div><span style="color:var(--app-text-dim)">${label('minSdk')}：</span><span style="color:var(--app-text-secondary)">${esc(data.min_sdk_version)}</span> <span style="color:var(--app-text-dim)">${label('targetSdk')}：</span><span style="color:var(--app-text-secondary)">${esc(data.target_sdk_version)}</span></div>`
  if (archChips) {
    html += `<div><span style="color:var(--app-text-dim)">${label('architecture')}：</span>${archChips}</div>`
  } else {
    html += '<div></div>'
  }
  html += '</div>'

  // Warnings (inside basic info card)
  if (data.warnings && Array.isArray(data.warnings) && data.warnings.length > 0) {
    html += '<div style="margin-top:6px;padding:5px 8px;background:rgba(250,204,21,0.08);border:1px solid rgba(250,204,21,0.25);border-radius:4px;font-size:11px">'
    html += `<span style="color:var(--app-yellow,#ca8a04);font-weight:600">${label('warnings')}：</span>`
    for (const w of data.warnings) {
      html += `<span style="color:var(--app-text-dim);margin-left:4px">${esc(String(w))}</span>`
    }
    html += '</div>'
  }
  html += '</div>'

  // ===== DEEP ANALYSIS CARD =====
  const hasSoCompFull = soComp && !soComp.single_arch && !soComp.no_native && soComp.arches && Object.keys(soComp.arches).length > 0
  const hasSoCompFallback = (soComp && soComp.single_arch) || (soComp && soComp.no_native)
  const hasComp = comp && Object.keys(comp).length > 0
  const hasPage16 = page16 && !page16.no_64bit_native && Object.keys(page16).filter(k => k !== 'skipped').length > 0
  if (hasSoCompFull || hasSoCompFallback || hasComp || hasPage16) {
    html += '<div style="background:var(--app-card-bg);border:1px solid var(--app-card-border);border-radius:8px;padding:8px 14px;margin-top:6px">'

    // SO Comparison
    if (hasSoCompFull) {
      html += `<details style="margin-top:4px"><summary style="cursor:pointer;color:var(--app-text-dim);font-size:12px;font-weight:600;user-select:none">${soCompSummary}</summary>`
      html += '<div style="margin-top:4px;display:flex;flex-direction:column;gap:4px">'
      for (const [arch, info] of Object.entries(soComp.arches)) {
        const a = info as any
        const archColor = Object.keys(archColors).find(k => arch.startsWith(k)) || '#6b7280'
        const chip = `<span style="display:inline-block;background:${archColor}18;color:${archColor};border:1px solid ${archColor}40;border-radius:4px;padding:0 7px;font-size:11px;font-family:monospace">${esc(arch)}</span>`
        const count = a.count || a.so_files?.length || 0
        const missing = a.missing || []
        html += '<div style="display:flex;align-items:center;gap:6px;font-size:12px">'
        html += chip
        html += `<span style="color:var(--app-text-dim)">${count} .so</span>`
        if (missing.length > 0) {
          html += `<span style="color:var(--app-red)">${label('missingInArch', { arch, count: missing.length })}: `
          html += missing.map((s: string) => `<span style="display:inline-block;background:rgba(239,68,68,0.1);color:var(--app-red);border-radius:3px;padding:0 5px;font-size:10px;font-family:monospace;margin:0 1px">${esc(s)}</span>`).join('')
          html += '</span>'
        } else {
          html += '<span style="color:var(--app-green)">\u2713</span>'
        }
        html += '</div>'
      }
      html += '</div></details>'
    } else if (soComp && soComp.single_arch) {
      html += `<div style="margin-top:4px;font-size:12px;color:var(--app-text-dim)">${label('soComparison')}：${label('singleArch')}</div>`
    } else if (soComp && soComp.no_native) {
      html += `<div style="margin-top:4px;font-size:12px;color:var(--app-text-dim)">${label('soComparison')}：${label('noNativeLibs')}</div>`
    }

    // Compression
    if (hasComp) {
      html += `<details style="margin-top:4px"><summary style="cursor:pointer;color:var(--app-text-dim);font-size:12px;font-weight:600;user-select:none">${compSummary}</summary>`
      html += '<div style="margin-top:4px;display:flex;flex-direction:column;gap:2px;font-size:12px">'
      for (const [category, info] of Object.entries(comp)) {
        const c = info as any
        const stored = c.stored || 0
        const deflated = c.deflated || 0
        const storedSize = c.stored_size || 0
        html += `<div style="display:flex;align-items:center;gap:6px"><span style="color:var(--app-text-primary);font-weight:500;min-width:50px">${esc(category)}</span>`
        html += `<span style="color:var(--app-text-dim)">${label('stored')}：${stored}</span>`
        html += `<span style="color:var(--app-text-dim)">${label('compressed')}：${deflated}</span>`
        if (storedSize > 0) {
          html += `<span style="color:var(--app-yellow,#ca8a04);font-size:11px">${label('storedSize', { size: fmtSize(storedSize) })}</span>`
        }
        html += '</div>'
      }
      html += '</div></details>'
    }

    // 16KB
    if (hasPage16) {
      html += `<details style="margin-top:4px"><summary style="cursor:pointer;color:var(--app-text-dim);font-size:12px;font-weight:600;user-select:none">${label('pageSize16kb')} (${pageSummary})</summary>`
      html += '<div style="margin-top:4px;display:flex;flex-direction:column;gap:3px;font-size:12px">'
      for (const [arch, files] of Object.entries(page16)) {
        if (arch === 'skipped') continue
        html += `<div style="color:var(--app-text-primary);font-weight:500;margin-bottom:2px">${esc(arch)}</div>`
        for (const [file, info] of Object.entries(files as any)) {
          const fi = info as any
          const ok = fi.supports_16kb
          html += '<div style="display:flex;align-items:center;gap:6px;padding-left:8px">'
          html += `<span style="color:var(--app-text-dim);font-family:monospace;font-size:11px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(file)}</span>`
          if (ok) {
            html += `<span style="display:inline-block;background:rgba(34,197,94,0.1);color:var(--app-green);border:1px solid rgba(34,197,94,0.3);border-radius:3px;padding:1px 6px;font-size:10px">${label('supports16kb')}</span>`
          } else {
            html += `<span style="display:inline-block;background:rgba(239,68,68,0.1);color:var(--app-red);border:1px solid rgba(239,68,68,0.3);border-radius:3px;padding:1px 6px;font-size:10px">${label('notSupports16kb')}</span>`
          }
          if (fi.max_align) {
            html += `<span style="color:var(--app-text-dim);font-family:monospace;font-size:10px">0x${fi.max_align.toString(16)}</span>`
          }
          html += '</div>'
        }
      }
      // Skipped files note
      if (page16.skipped && page16.skipped.length > 0) {
        html += `<div style="color:var(--app-text-dim);font-size:11px;margin-top:2px">${label('pageSizeSkipped', { count: page16.skipped.length })}</div>`
      }
      html += '</div></details>'
    }

    // v2.1.1: Meta Data
    const metaData = data.meta_data
    if (metaData && Array.isArray(metaData) && metaData.length > 0) {
      // Group by parent
      const grouped: Record<string, any[]> = {}
      for (const m of metaData) {
        const p = m.parent || 'unknown'
        if (!grouped[p]) grouped[p] = []
        grouped[p].push(m)
      }
      const metaCount = metaData.length
      html += `<details style="margin-top:4px"><summary style="cursor:pointer;color:var(--app-text-dim);font-size:12px;font-weight:600;user-select:none">${label('metaData')} (${metaCount} entries)</summary>`
      html += '<div style="margin-top:6px;display:flex;flex-direction:column;gap:8px;font-size:12px">'

      for (const [parent, entries] of Object.entries(grouped)) {
        const e = entries as any[]
        html += '<div>'
        html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">'
        html += `<span style="display:inline-block;background:var(--app-green);color:#fff;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600;line-height:1.4">&lt;${esc(parent)}&gt;</span>`
        html += `<span style="color:var(--app-text-dim);font-size:11px">${e.length} entries</span>`
        html += '</div>'
        html += '<div style="padding-left:6px;border-left:2px solid var(--app-card-border)">'

        for (const item of e) {
          const name = item.name || ''
          const value = item.value || ''
          const resContent = item.resource_content
          const resResolved = item.resource_resolved

          html += '<div style="display:flex;align-items:flex-start;gap:6px;padding:3px 6px;border-radius:3px">'
          html += `<span style="color:var(--app-text-primary);font-family:monospace;font-size:11px;min-width:120px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex-shrink:0" title="${esc(name)}">${esc(name)}</span>`

          if (value && !value.startsWith('@')) {
            html += `<span style="color:var(--app-text-dim);flex-shrink:0">=</span>`
            html += `<span style="color:var(--app-text-secondary);font-family:monospace;font-size:11px;word-break:break-all;flex:1;min-width:0">${esc(value)}</span>`
          }

          // Scalar resource value (string/integer resolved from aapt2 dump resources)
          if (item.resource_value) {
            if (!value) html += `<span style="color:var(--app-text-dim);flex-shrink:0">=</span>`
            html += `<span style="color:var(--app-text-secondary);font-family:monospace;font-size:11px;word-break:break-all;flex:1;min-width:0">${esc(item.resource_value)}</span>`
          }

          // Resource reference with resolved content
          if (resContent && resContent.length > 0) {
            if (!value) html += `<span style="color:var(--app-text-dim);flex-shrink:0">=</span>`
            html += '<span style="display:flex;flex-direction:column;gap:1px;flex:1;min-width:0">'
            if (resResolved) {
              html += `<span style="color:var(--app-text-dim);font-size:10px">${esc(resResolved)}</span>`
            }
            for (const ci of resContent) {
              html += `<span style="color:var(--app-text-secondary);font-size:11px;padding-left:8px">${esc(ci.element)}: ${esc(ci.name)} → ${esc(ci.value)}</span>`
            }
            html += '</span>'
          } else if (!value) {
            html += `<span style="color:var(--app-text-dim);flex-shrink:0">=</span>`
            html += `<span style="color:var(--app-text-dim);font-style:italic;font-size:11px">-</span>`
          }

          html += '</div>'
        }
        html += '</div></div>'
      }
      html += '</div></details>'
    }

    html += '</div>'
  }

  // ===== PERMISSIONS CARD =====
  if (dangerous.length > 0 || normal.length > 0) {
    html += '<div style="background:var(--app-card-bg);border:1px solid var(--app-card-border);border-radius:8px;padding:10px 14px;margin-top:6px">'

    if (dangerous.length > 0) {
      html += `<div style="font-size:13px;margin-bottom:4px"><span style="color:var(--app-text-dim)">${label('dangerousPerms')} (${dangerous.length})</span></div>`
      html += `<div style="display:flex;flex-wrap:wrap;gap:2px;margin-bottom:2px">${dangerous.map(p => permBadge(p, true)).join('')}</div>`
    }

    if (normal.length > 0) {
      const showLabel = t('task.otherPermsShow', { count: normal.length })
      html += `<details><summary style="cursor:pointer;color:var(--app-text-dim);font-size:12px;user-select:none">${showLabel}</summary>`
      html += `<div style="display:flex;flex-wrap:wrap;gap:2px;margin-top:3px">${normal.map(p => permBadge(p, false)).join('')}</div></details>`
    }

    if (perms.length === 0) {
      html += `<div style="font-size:12px"><span style="color:var(--app-text-dim)">${label('noPermissions')}</span></div>`
    }

    html += '</div>'
  }

  html += `</div>`
  return html
}

function startProgress(task: Task, label: string) {
  let p = 0
  const iv = setInterval(() => {
    if (p >= 85) { clearInterval(iv); activeIntervals.delete(iv); return }
    // Stop updating if task was cancelled
    const current = taskStore.tasks.find(t => t.id === task.id)
    if (current && (current.status === 'cancelled' || current.status === 'cancelling' as any)) {
      clearInterval(iv); activeIntervals.delete(iv); return
    }
    if (p < 30) p += 2
    else if (p < 60) p += 1
    else p += 0.5
    taskStore.updateTask(task.id, { progress: Math.round(Math.min(p, 85)), progressLabel: label })
  }, 500)
  activeIntervals.add(iv)
  return iv
}

function clearIntervalAndForget(iv: ReturnType<typeof setInterval>) {
  clearInterval(iv)
  activeIntervals.delete(iv)
}

function finishProgress(task: Task, iv: ReturnType<typeof setInterval>) {
  clearIntervalAndForget(iv)
  taskStore.updateTask(task.id, { progress: 100, progressLabel: t('task.completed') })
}
</script>

<style scoped>
.package-page { max-width: 960px; margin: 0 auto; height: calc(100vh - 48px); display: flex; flex-direction: column; }
.task-list-area { flex: 1; overflow-y: auto; min-height: 0; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-family: Inter, sans-serif; font-size: 22px; font-weight: 700; color: var(--app-text-primary); margin: 0; letter-spacing: -0.02em; }
.page-subtitle { font-size: 13px; color: var(--app-text-muted); margin: 4px 0 0; }

/* New Task Bar */
.new-task-bar {
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.task-bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.task-bar-row > :nth-child(2) { flex: 1; min-width: 0; }
.task-bar-opts {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--app-card-border);
}
.op-desc { font-size: 12px; color: var(--app-text-dim); }
.op-label { font-size: 11px; color: var(--app-text-dim); white-space: nowrap; }

.local-file-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  background: var(--app-input-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--app-text-dim);
  overflow: hidden;
  transition: border-color .2s;
}
.local-file-picker span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.local-file-picker:hover { border-color: var(--app-green); }
.local-file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hidden-input { display: none; }

/* Empty */
.empty-state {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 80px 16px; text-align: center;
}
.empty-title { font-size: 15px; font-weight: 600; color: var(--app-text-muted); margin: 0; }
.empty-desc { font-size: 13px; color: var(--app-text-dim); margin: 0; max-width: 360px; }

/* Task Cards */
.task-list { display: flex; flex-direction: column; gap: 8px; }
.task-card {
  background: var(--app-card-bg);
  border: 1px solid var(--app-card-border);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color .2s;
}
.task-card.task-running { border-color: rgba(34,197,94,0.4); }
.task-card.task-failed { border-color: rgba(239,68,68,0.4); }

.task-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  gap: 10px;
}
.task-header:hover { background: var(--app-hover); }
.task-header-left, .task-header-right { display: flex; align-items: center; gap: 8px; }
.task-id { font-size: 11px; color: var(--app-text-dim); font-weight: 600; min-width: 24px; }
.task-filename {
  font-size: 13px; color: var(--app-text-secondary);
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.task-time { font-size: 11px; color: var(--app-text-dim); }
.task-duration { font-size: 11px; color: var(--app-text-muted); margin-left: 6px; font-family: monospace; }

.task-progress { padding: 0 14px; height: 3px; }

.task-detail {
  padding: 10px 14px;
  border-top: 1px solid var(--app-card-border);
  display: flex; flex-direction: column; gap: 8px;
}
.task-error {
  font-size: 12px; color: var(--app-red);
  padding: 8px 10px; background: rgba(239,68,68,0.08); border-radius: 6px;
}
.task-output {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--app-green);
}
.task-output-path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.task-result { font-size: 13px; }
.task-logs {
  background: var(--app-code-bg);
  border-radius: 6px;
  padding: 8px 10px;
  max-height: 200px;
  overflow-y: auto;
  font-family: 'Fira Code', monospace;
  font-size: 11px;
  line-height: 1.6;
}
.task-log-line { color: var(--app-text-secondary); white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
