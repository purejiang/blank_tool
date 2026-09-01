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
              {{ task.progressLabel || t('task.running') }}
            </n-tag>
            <n-tag v-else-if="task.status === 'downloading'" type="info" size="tiny" :bordered="false">
              <template #icon><n-icon size="12"><Download /></n-icon></template>
              {{ task.progressLabel }}
            </n-tag>
            <n-tag v-else type="default" size="tiny" :bordered="false">
              {{ t('task.queued') }}
            </n-tag>
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
              type="info"
              :title="t('task.retryStage')"
              @click.stop="retryFailedStage(task)"
            >
              <template #icon><n-icon size="14"><RotateCcw /></n-icon></template>
            </n-button>
            <n-button
              v-if="task.status === 'failed' || task.status === 'cancelled'"
              size="tiny"
              quaternary
              type="warning"
              :title="t('task.rerunFromStart')"
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

        <!-- Progress bar: downloading = real %; running = indeterminate
             (operations emit no progress events — fake progress removed) -->
        <div v-if="task.status === 'downloading'" class="task-progress">
          <n-progress type="line" :percentage="task.progress" :height="3" color="#22C55E" :indicator-placement="'none'" />
        </div>
        <div v-else-if="task.status === 'running'" class="task-progress">
          <div class="indeterminate-bar"><div class="indeterminate-fill" /></div>
        </div>

        <!-- Expanded detail -->
        <div v-if="!task.collapsed" class="task-detail">
          <div v-if="task.error" class="task-error">{{ task.error }}</div>
          <div v-if="task.filePath" class="task-output">
            <n-icon size="14" color="var(--app-text-dim)"><FolderOpen /></n-icon>
            <span class="task-output-path">{{ t('task.source') }}: {{ task.filePath }}</span>
            <n-button size="tiny" quaternary @click.stop="openInExplorerChecked(task.filePath, task.fileName || t('task.source'), t('task.sourceFileMissing'))">
              <template #icon><n-icon size="13"><ExternalLink /></n-icon></template>
            </n-button>
          </div>
          <div v-if="task.outputPath" class="task-output">
            <n-icon size="14" color="var(--app-green)"><FolderOpen /></n-icon>
            <span class="task-output-path">{{ t('task.output') }}: {{ task.outputPath }}</span>
            <n-button size="tiny" quaternary type="info" @click.stop="openInExplorerChecked(task.outputPath, t('task.output'), t('task.outputMissing'))">
              <template #icon><n-icon size="13"><ExternalLink /></n-icon></template>
            </n-button>
          </div>
          <div v-if="task.operation === 'install' && task.deviceLabel" class="task-output">
            <n-icon size="14" color="var(--app-green)"><Smartphone /></n-icon>
            <span class="task-output-path">{{ t('task.installedToDevice', { label: task.deviceLabel }) }}</span>
          </div>
          <div v-if="task.result" class="task-result" v-html="task.result" @click="onResultCopy" />
          <!-- Unified task log: file log (terminal) or in-memory log (running) -->
          <div v-if="displayLog(task).length > 0" class="task-logs">
            <div class="task-logs-toolbar">
              <n-button
                size="tiny" quaternary
                :type="logSearchOpenMap.get(task.id) ? 'info' : 'default'"
                :title="t('task.logSearch')"
                @click.stop="toggleLogSearch(task)"
              >
                <template #icon><n-icon size="14"><Search /></n-icon></template>
              </n-button>
              <n-input
                v-if="logSearchOpenMap.get(task.id)"
                :value="logSearchMap.get(task.id) || ''"
                :placeholder="t('task.logSearch')"
                size="tiny"
                clearable
                style="flex:1; min-width:0"
                @update:value="(v: string) => logSearchMap.set(task.id, v)"
              />
              <div v-else class="task-logs-spacer" />
              <n-button size="tiny" quaternary :title="t('task.copyLog')" @click.stop="copyLog(task)">
                <template #icon><n-icon size="14"><Copy /></n-icon></template>
              </n-button>
              <n-button size="tiny" quaternary :title="t('task.exportLog')" @click.stop="exportTaskLog(task)">
                <template #icon><n-icon size="14"><Download /></n-icon></template>
              </n-button>
              <n-button
                size="tiny" quaternary
                :type="autoScrollMap.get(task.id) !== false ? 'info' : 'default'"
                :title="t('task.autoScroll')"
                @click.stop="autoScrollMap.set(task.id, autoScrollMap.get(task.id) === false)"
              >
                <template #icon><n-icon size="14"><ArrowDownToLine /></n-icon></template>
              </n-button>
              <template v-if="isTerminal(task.status)">
                <n-button v-if="!logExpandedMap.get(task.id)" size="tiny" quaternary :title="t('task.logFullView')" @click.stop="loadFullTaskLog(task)">
                  <template #icon><n-icon size="14"><ChevronDown /></n-icon></template>
                </n-button>
                <n-button v-else size="tiny" quaternary :title="t('task.logTailView')" @click.stop="collapseTaskLog(task)">
                  <template #icon><n-icon size="14"><ChevronUp /></n-icon></template>
                </n-button>
              </template>
            </div>
            <div v-if="showTruncation(task)" class="task-log-trunc-hint">
              <n-icon size="13"><AlertTriangle /></n-icon>
              <span>{{ t('task.logTruncatedHint') }}</span>
            </div>
            <n-virtual-list
              :ref="(el: any) => onLogListRef(task.id, el)"
              :key="'log-' + task.id + '-' + (logExpandedMap.get(task.id) ? 'full' : 'tail')"
              :items="displayLog(task)"
              :item-size="18"
              item-resizable
              style="max-height: 170px"
            >
              <template #default="{ item }">
                <div class="task-log-line">{{ item.text }}</div>
              </template>
            </n-virtual-list>
          </div>
        </div>

        <!-- Bottom-left meta: creation time + duration -->
        <div class="task-meta-row">
          <span class="task-time">{{ formatTime(task.createdAt) }}</span>
          <span v-if="task.startedAt || task.createdAt" class="task-duration">{{ formatDuration(task) }}</span>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon, NVirtualList, useDialog, NInput } from 'naive-ui'
import {
  Play, Link, FolderOpen, CheckCircle, XCircle, Loader,
  ChevronDown, ChevronRight, ChevronUp, Trash2, Inbox, ExternalLink, StopCircle, AlertCircle, Download, RefreshCw, Smartphone,
  Search, Copy, AlertTriangle, RotateCcw, ArrowDownToLine
} from 'lucide-vue-next'
import { useNotification } from '@composables/useNotification'
import { useTaskStore } from '@stores/index'
import { useSignatureStore } from '@stores/signatureStore'
import { useDeviceStore } from '@stores/deviceStore'
import type { Task } from '@stores/taskStore'
import { formatDuration as formatDurationUtil } from '@utils/formatDuration'
import { log as logUtil } from '@utils/logger'
import serviceManager from '@services/ServiceManager'
import { enqueueTask } from '@services/TaskExecutionService'

const { t } = useI18n()
const dialog = useDialog()
const taskStore = useTaskStore()
const sigStore = useSignatureStore()
const deviceStore = useDeviceStore()
if (sigStore.configs.length === 0) sigStore.loadConfigs()

const { showError, showWarning, showSuccess } = useNotification()

const OP_TAG_MAP: Record<Task['operation'], string> = {
  analyze: 'info', install: 'success', decompile: 'warning', recompile: 'warning', resign: 'error'
}

const activeIntervals = new Set<ReturnType<typeof setInterval>>()


// Reactive clock for real-time duration display.
// Updated every 1s when there are active (non-terminal) tasks.
const now = ref(Date.now())
let nowIv: ReturnType<typeof setInterval> | null = null
const taskLogCache = ref<Map<number, { key: number; text: string }[]>>(new Map())
const logExpandedMap = ref<Map<number, boolean>>(new Map())
// Log UI enhancement (Batch 2): per-task search / auto-scroll / truncation state + virtual-list refs
const logSearchMap = ref<Map<number, string>>(new Map())
const logSearchOpenMap = ref<Map<number, boolean>>(new Map())
const autoScrollMap = ref<Map<number, boolean>>(new Map())
const logTruncatedMap = ref<Map<number, boolean>>(new Map())
const logListRefs = new Map<number, any>()

/** Toggle the inline log search box; closing it clears the active filter. */
function toggleLogSearch(task: Task) {
  const open = !logSearchOpenMap.value.get(task.id)
  logSearchOpenMap.value.set(task.id, open)
  if (!open) logSearchMap.value.set(task.id, '')
}

function getLogArray(task: Task): { key: number; text: string }[] {
  if (isTerminal(task.status) && taskLogCache.value.has(task.id) && taskLogCache.value.get(task.id)?.length) {
    return taskLogCache.value.get(task.id)!
  }
  return task.logs.map((text, i) => ({ key: i, text }))
}

function displayLog(task: Task): { key: number; text: string }[] {
  const arr = getLogArray(task)
  const q = (logSearchMap.value.get(task.id) || '').trim().toLowerCase()
  if (!q) return arr
  return arr.filter((l) => l.text.toLowerCase().includes(q))
}

function showTruncation(task: Task): boolean {
  return isTerminal(task.status) && !logExpandedMap.value.get(task.id) && logTruncatedMap.value.get(task.id) === true
}

function onLogListRef(taskId: number, el: any) {
  if (el) logListRefs.set(taskId, el)
  else logListRefs.delete(taskId)
}

function scrollLogToBottom(taskId: number) {
  const task = taskStore.tasks.find((t) => t.id === taskId)
  if (!task) return
  const el = logListRefs.get(taskId)
  if (!el || typeof el.scrollTo !== 'function') return
  const len = displayLog(task).length
  if (len > 0) {
    try { el.scrollTo({ index: len - 1 }) } catch { /* ignore */ }
  }
}

async function copyLog(task: Task) {
  const lines = displayLog(task).map((l) => l.text)
  if (lines.length === 0) return
  const text = lines.join('\n')
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const api = window.electronAPI as any
      if (api?.writeClipboardText) await api.writeClipboardText(text)
    }
    showSuccess(t('task.copyLog'), t('task.logCopied'))
  } catch (e) {
    showWarning(t('task.copyLog'), String(e))
  }
}

// Delegated click handler for the analysis result card (rendered via v-html).
// The FB Hash Key row carries a `data-fb-hash` attribute; clicking the copy
// affordance next to it copies that value to the clipboard.
function onResultCopy(e: MouseEvent) {
  const el = e.target as HTMLElement | null
  const hash = el?.getAttribute?.('data-fb-hash')
  if (!hash) return
  const copy = async () => {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(hash)
    } else {
      const api = window.electronAPI as any
      if (api?.writeClipboardText) await api.writeClipboardText(hash)
      else throw new Error('clipboard unavailable')
    }
  }
  copy()
    .then(() => showSuccess(t('task.fbHashKey'), t('task.logCopied')))
    .catch((err) => showWarning(t('task.fbHashKey'), String(err)))
}

async function exportTaskLog(task: Task) {
  try {
    const api = window.electronAPI as any
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
    const def = `task-${task.id}-${ts}.log`
    let filePath = ''
    if (api?.showSaveDialog) {
      const res = await api.showSaveDialog({ title: t('task.exportLog'), defaultPath: def, filters: [{ name: 'Log', extensions: ['log', 'txt'] }] })
      if (!res || res.canceled) return
      filePath = res.filePath || ''
    }
    if (!filePath) return
    const result = await api.callBackendAPI('task.export_log', { task_id: String(task.id), file_path: filePath })
    if (result?.success) {
      showSuccess(t('task.exportLog'), result.file_path || '')
    } else {
      showError(t('task.exportLog'), result?.error || 'failed')
    }
  } catch (e) {
    showError(t('task.exportLog'), String(e))
  }
}

// Log buffering: batch high-volume stream events to avoid UI jank
const logBuffers = new Map<number, string[]>()
const logTimers = new Map<number, ReturnType<typeof setTimeout>>()

function flushLogBuffer(taskId: number) {
  const buf = logBuffers.get(taskId)
  if (buf && buf.length > 0) {
    taskStore.appendLogBatch(taskId, [...buf])
    buf.length = 0
    if (autoScrollMap.value.get(taskId) !== false) {
      nextTick(() => scrollLogToBottom(taskId))
    }
  }
  logTimers.delete(taskId)
}

function startNowTimer() {
  if (nowIv !== null) return
  const iv = setInterval(() => { now.value = Date.now() }, 100)
  activeIntervals.add(iv)
  nowIv = iv
}

function stopNowTimer() {
  if (nowIv !== null) {
    clearInterval(nowIv)
    activeIntervals.delete(nowIv)
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

onMounted(() => {
  logUtil.debug('任务管理页面已挂载')
  // 重启后自动回读已展开的已完成任务的磁盘日志，避免日志框空白
  for (const task of taskStore.tasks) {
    if (!task.collapsed && isTerminal(task.status) && !taskLogCache.value.has(task.id)) {
      loadTaskLog(task)
    }
  }
})

onUnmounted(() => {
  stopNowTimer()
  activeIntervals.forEach(clearInterval)
  activeIntervals.clear()
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

// getFileStats returns {success:false} for ANY stat error (ENOENT, EACCES —
// wording is slightly imprecise for permission errors but acceptable)
async function openInExplorerChecked(filePath: string, missingTitle: string, missingMsg: string) {
  try {
    const svc = await serviceManager.getService('system') as any
    if (svc && typeof svc.getFileStats === 'function') {
      const result = await svc.getFileStats(filePath)
      if (result?.success !== true) {
        showWarning(missingTitle, missingMsg)
        return
      }
    }
    await openInExplorer(filePath)
  } catch (e) {
    await openInExplorer(filePath)
  }
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
    logTruncatedMap.value.set(task.id, result.truncated === true)
    const content = (result.content || '').trim()
    if (content) {
      taskLogCache.value.set(task.id, splitLogLines(content))
    }
    if (autoScrollMap.value.get(task.id) !== false) {
      await nextTick()
      scrollLogToBottom(task.id)
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
    logExpandedMap.value.set(task.id, true)
    if (autoScrollMap.value.get(task.id) !== false) {
      await nextTick()
      scrollLogToBottom(task.id)
    }
  } catch (e) {
    // keep existing cache on error
  }
}

function collapseTaskLog(task: Task) {
  // Switch back to tail view WITHOUT dropping the cache: re-read the tail so
  // the virtual list shows the truncated tail again, but the cache Map entry
  // stays alive (no delete) for cheap re-expand.
  logExpandedMap.value.set(task.id, false)
  loadTaskLog(task)
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
    logUtil.error('pickLocalFile error:', e)
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

  // Queue the task — TaskExecutionService starts it when a slot frees up
  // (bounded concurrency, default 3). The task stays 'queued' until then.
  enqueueTask(task.id, () => executeTask(task))
}

async function executeTask(task: Task, opts: { skipDownload?: boolean } = {}) {
  try {
    let localPath = task.filePath
    const api = window.electronAPI as any

    const taskStream = await serviceManager.getService('taskStream') as any
    // bind is idempotent (retry auto-unbinds stale)
    taskStream.bindTask(String(task.id))
    taskStream.setCallbacks(String(task.id), {
      onDownloadProgress: (p: number, _dl: number, _tot: number, _spd: number) => {
        taskStore.transition(task.id, 'download_progress', { progress: p })
      },
      onComplete: (payload: any, phase: string) => {
        if (phase === 'download') {
          taskStore.transition(task.id, 'download_complete', payload)
        } else {
          // Extract operation-specific fields from the complete payload.
          // Backend payloads (per apk_handler.py):
          //   analyze    → {package_name, permissions, native_libs, application_label, ...}
          //   decompile  → {output_dir}
          //   recompile  → {output_apk}
          //   sign       → {apk_path}
          const transitionPayload: any = {}
          if (payload?.output_dir) transitionPayload.output_dir = payload.output_dir
          if (payload?.output_apk) transitionPayload.output_apk = payload.output_apk
          if (payload?.apk_path) transitionPayload.apk_path = payload.apk_path
          // analyze: render the rich analysis card HTML via renderApkInfo
          if (payload?.package_name) transitionPayload.result = renderApkInfo(payload)
          // install: attach device label (model + serial) for notification & display
          if (task.operation === 'install' && payload?.device_id) {
            const dev = deviceStore.selectedDevice
            const model = deviceStore.deviceInfo.model || dev?.name || dev?.id || payload.device_id
            const serial = deviceStore.deviceInfo.serial || payload.device_id
            transitionPayload.deviceLabel = `${model} (${serial})`
            taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] ${t('task.installedToDevice', { label: transitionPayload.deviceLabel })}`)
          }
          taskStore.transition(task.id, 'operation_complete', transitionPayload)
        }
      },
      onError: (msg: string, phase: string) => {
        taskStore.transition(task.id, 'operation_error', { message: msg, failedPhase: phase })
      },
      onCancelled: () => {
        taskStore.transition(task.id, 'cancel_ack')
      },
      onLog: (line: string) => {
        // Backend-mirrored task log line (apk/install/aab handlers).
        // The Python backend already persisted it, so we only mirror it
        // into memory for live display — batched to avoid UI jank.
        const buf = logBuffers.get(task.id) ?? []
        buf.push(line)
        logBuffers.set(task.id, buf)
        if (!logTimers.has(task.id)) {
          logTimers.set(task.id, setTimeout(() => flushLogBuffer(task.id), 200))
        }
      },
    })

    // Note: latch pattern in TaskStreamService guarantees events arriving
    // before await waitForPhase() are not lost — they're stashed and resolved immediately.

    // --- Download phase (URL source only) ---
    // "Retry failed stage" skips a completed download and reuses the file
    // already fetched in the previous attempt.
    if (opts.skipDownload && task.source === 'url') {
      log(task, t('task.reuseDownloaded'))
    } else if (task.source === 'url' && task.url) {
      taskStore.transition(task.id, 'start_download')
      taskStream.setPhase(String(task.id), 'download')
      log(task, t('task.downloading') + ' ' + task.url)

      if (!api || typeof api.downloadFile !== 'function') throw new Error(t('task.downloadAPINotAvailable'))
      api.downloadFile(task.url, task.fileName, String(task.id))

      const dlResult: any = await taskStream.waitForPhase(String(task.id), 'download')
      localPath = dlResult.file_path
      log(task, t('task.completed') + ` (${(dlResult.size / 1024 / 1024).toFixed(1)}MB)`)
    }

    // --- Operation phase ---
    taskStore.transition(task.id, 'start_operation')
    taskStream.setPhase(String(task.id), 'operation')
    log(task, t('task.running') + ' ' + task.operationLabel)

    // No fake progress: operations emit no real progress events, so the
    // progress bar renders as indeterminate (see template) until completion.
    await runOperation(task, localPath)
    await taskStream.waitForPhase(String(task.id), 'operation')
  } catch (e: any) {
    const isCancelled = e?.message === 'cancelled' || e?.message === 'unbound'
    if (!isCancelled) {
      const errMsg = e.message || String(e)
      const currentTask = taskStore.tasks.find(t => t.id === task.id)
      if (currentTask && currentTask.status !== 'failed') {
        const failedPhase = currentTask?.phase === 'download' ? 'download' : 'operation'
        taskStore.transition(task.id, 'operation_error', { message: errMsg, failedPhase })
      }
      log(task, t('task.failed') + ': ' + errMsg)
      showError(task.operationLabel, errMsg)
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
      taskStore.transition(task.id, 'cancel_request')
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
          logUtil.error('Cancel error:', e)
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
  // Full re-run from scratch: reset task state to queued, keep existing logs
  // and append below them. URL tasks re-download; queued via the executor.
  taskStore.appendLog(task.id, `--- ${t('task.rerunFromStart')} ---`)
  taskStore.transition(task.id, 'reset_for_retry')
  task.collapsed = true
  enqueueTask(task.id, () => executeTask(task))
}

async function retryFailedStage(task: Task) {
  // Stage-level retry: if the download already succeeded in the previous
  // attempt (or the source is local), skip straight to the operation phase
  // and reuse the fetched file. Otherwise this equals a full re-run.
  taskStore.appendLog(task.id, `--- ${t('task.retryStage')} ---`)
  taskStore.transition(task.id, 'reset_for_retry')
  task.collapsed = true
  const skipDownload = task.source === 'url' ? !!task.filePath : false
  enqueueTask(task.id, () => executeTask(task, { skipDownload }))
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
  if (del === true && isTerminal) {
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

  log(task, ingLabel + logExtra)

  // Call the service — returns {stream_id} immediately
  // Result comes via TaskStreamService → phaseResolve
  try {
    await svc[methodName](localPath, opts || { task_id: String(task.id) })
  } catch (err) {
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
    return `<span class="apk-archchip" style="background:${color}18;color:${color};border:1px solid ${color}40">${esc(abi)}</span>`
  }).join('')

  const permBadge = (p: string, danger: boolean) => {
    const name = p.replace('android.permission.', '')
    const cls = danger ? 'apk-badge apk-badge--danger' : 'apk-badge apk-badge--normal'
    return `<span title="${esc(p)}" class="${cls}">${esc(name)}</span>`
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

  const metaData = data.meta_data
  const fileMd5 = data.file_md5
  const sigMd5 = data.sig_md5
  const sigSha1 = data.sig_sha1
  const sigSha256 = data.sig_sha256
  const hasAnyHash = (fileMd5 && fileMd5 !== '-') || (sigMd5 && sigMd5 !== '-') || (sigSha1 && sigSha1 !== '-') || (sigSha256 && sigSha256 !== '-')
  const hasSoCompFull = soComp && !soComp.single_arch && !soComp.no_native && soComp.arches && Object.keys(soComp.arches).length > 0
  const hasComp = comp && Object.keys(comp).length > 0
  const hasPage16 = page16 && !page16.no_64bit_native && Object.keys(page16).filter(k => k !== 'skipped').length > 0

  const stat = (k: string, v: string) =>
    `<div class="apk-stat"><div class="apk-stat-k">${k}</div><div class="apk-stat-v">${v}</div></div>`
  const hashRow = (k: string, v: string) =>
    `<div class="apk-hashrow"><span class="k">${k}</span><span class="v">${esc(v)}</span></div>`

  let html = '<div class="apk-info">'

  // ===== IDENTITY CARD =====
  html += '<div class="apk-card">'
  html += `<div class="apk-name">${esc(data.application_label)}</div>`
  html += `<div class="apk-pkg">${esc(data.package_name)}</div>`
  html += '<div class="apk-statgrid">'
  html += stat(label('version'), `${esc(data.version_name)} <span style="color:var(--app-text-dim);font-weight:400">(${esc(data.version_code)})</span>`)
  html += stat(label('fileSize'), fmtSize(data.file_size))
  html += stat(`${label('minSdk')} / ${label('targetSdk')}`, `${esc(data.min_sdk_version)} / ${esc(data.target_sdk_version)}`)
  if (archChips) html += stat(label('architecture'), archChips)
  html += '</div>'
  if (data.warnings && Array.isArray(data.warnings) && data.warnings.length > 0) {
    html += `<div class="apk-warn"><b>${label('warnings')}</b>：${data.warnings.map((w: any) => esc(String(w))).join('；')}</div>`
  }
  html += '</div>'

  // ===== SIGNATURE CARD =====
  if (hasAnyHash) {
    html += '<details class="apk-card" open>'
    html += `<summary>${label('signatureInfo')}<span class="chev">▸</span></summary>`
    html += '<div class="apk-card-body">'
    if (fileMd5 && fileMd5 !== '-') html += hashRow(label('apkMd5'), fileMd5)
    if (sigMd5 && sigMd5 !== '-') html += hashRow(label('sigMd5'), sigMd5)
    if (sigSha1 && sigSha1 !== '-') html += hashRow(label('sigSha1'), sigSha1)
    if (sigSha256 && sigSha256 !== '-') html += hashRow(label('sigSha256'), sigSha256)
    const fbHashKey = data.fb_hash_key
    if (fbHashKey && fbHashKey !== '-') {
      html += `<div class="apk-hashrow"><span class="k">${label('fbHashKey')}</span><span class="v">${esc(fbHashKey)}</span><span class="apk-copy" data-fb-hash="${esc(fbHashKey)}" title="${label('copyLog')}">${label('copyLog')}</span></div>`
    }
    if (sigMd5 === '-' || sigSha1 === '-' || sigSha256 === '-') {
      html += `<div class="apk-warn">${label('unsignedApk')}</div>`
    }
    html += '</div></details>'
  }

  // ===== SO COMPARISON =====
  if (hasSoCompFull) {
    html += '<details class="apk-card" open>'
    html += `<summary>${soCompSummary}<span class="chev">▸</span></summary>`
    html += '<div class="apk-card-body">'
    for (const [arch, info] of Object.entries(soComp.arches)) {
      const a = info as any
      const archColor = Object.keys(archColors).find(k => arch.startsWith(k)) || '#6b7280'
      const count = a.count || a.so_files?.length || 0
      const missing = a.missing || []
      html += '<div class="apk-so-row">'
      html += `<span class="apk-so-arch" style="color:${archColor}">${esc(arch)}</span>`
      html += `<span class="apk-muted">${count} .so</span>`
      if (missing.length > 0) {
        html += `<span class="apk-so-miss">${label('missingInArch', { arch, count: missing.length })}: `
        html += missing.map((s: string) => `<span class="apk-mini">${esc(s)}</span>`).join('')
        html += '</span>'
      } else {
        html += '<span style="color:var(--app-green)">✓</span>'
      }
      html += '</div>'
    }
    html += '</div></details>'
  } else if (soComp && soComp.single_arch) {
    html += `<div class="apk-card"><div class="apk-card-h">${label('soComparison')}</div><div class="apk-muted">${label('singleArch')}</div></div>`
  } else if (soComp && soComp.no_native) {
    html += `<div class="apk-card"><div class="apk-card-h">${label('soComparison')}</div><div class="apk-muted">${label('noNativeLibs')}</div></div>`
  }

  // ===== COMPRESSION =====
  if (hasComp) {
    html += '<details class="apk-card" open>'
    html += `<summary>${compSummary}<span class="chev">▸</span></summary>`
    html += '<div class="apk-card-body">'
    for (const [category, info] of Object.entries(comp)) {
      const c = info as any
      const stored = c.stored || 0
      const deflated = c.deflated || 0
      const storedSize = c.stored_size || 0
      html += `<div class="apk-row"><span class="apk-row-k">${esc(category)}</span>`
      html += `<span class="apk-muted">${label('stored')}：${stored}</span>`
      html += `<span class="apk-muted">${label('compressed')}：${deflated}</span>`
      if (storedSize > 0) html += `<span class="apk-warn-inline">${label('storedSize', { size: fmtSize(storedSize) })}</span>`
      html += '</div>'
    }
    html += '</div></details>'
  }

  // ===== 16KB PAGE =====
  if (hasPage16) {
    html += '<details class="apk-card" open>'
    html += `<summary>${label('pageSize16kb')} (${pageSummary})<span class="chev">▸</span></summary>`
    html += '<div class="apk-card-body">'
    for (const [arch, files] of Object.entries(page16)) {
      if (arch === 'skipped') continue
      html += `<div class="apk-sub">${esc(arch)}</div>`
      for (const [file, info] of Object.entries(files as any)) {
        const fi = info as any
        const ok = fi.supports_16kb
        html += '<div class="apk-so-row" style="padding-left:8px">'
        html += `<span class="apk-file">${esc(file)}</span>`
        if (ok) html += `<span class="apk-badge apk-badge--ok">${label('supports16kb')}</span>`
        else html += `<span class="apk-badge apk-badge--danger">${label('notSupports16kb')}</span>`
        if (fi.max_align) html += `<span class="apk-muted">0x${fi.max_align.toString(16)}</span>`
        html += '</div>'
      }
    }
    if (page16.skipped && page16.skipped.length > 0) {
      html += `<div class="apk-muted" style="margin-top:4px">${label('pageSizeSkipped', { count: page16.skipped.length })}</div>`
    }
    html += '</div></details>'
  }

  // ===== META DATA =====
  if (metaData && Array.isArray(metaData) && metaData.length > 0) {
    html += '<details class="apk-card" open>'
    html += `<summary>${label('metaData')} (${metaData.length})<span class="chev">▸</span></summary>`
    html += '<div class="apk-card-body">'
    html += '<table class="apk-meta"><thead><tr><th>Parent</th><th>Name</th><th>Value</th><th>Resource</th></tr></thead><tbody>'
    for (const item of metaData) {
      const parent = item.parent || 'unknown'
      const name = item.name || ''
      const value = item.value || ''
      const resValue = item.resource_value || ''
      const resContent = item.resource_content
      const resResolved = item.resource_resolved
      html += '<tr>'
      html += `<td><span class="apk-parent">&lt;${esc(parent)}&gt;</span></td>`
      html += `<td>${esc(name)}</td>`
      html += '<td>'
      if (value && !value.startsWith('@')) html += esc(value)
      else if (resValue) html += esc(resValue)
      else html += '-'
      html += '</td>'
      html += '<td>'
      if (resResolved || (resContent && resContent.length > 0)) {
        if (resResolved) html += `<div class="apk-muted">${esc(resResolved)}</div>`
        if (resContent && resContent.length > 0) {
          for (const ci of resContent) html += `<div class="apk-res">${esc(ci.element)}: ${esc(ci.name)} → ${esc(ci.value)}</div>`
        }
      }
      html += '</td>'
      html += '</tr>'
    }
    html += '</tbody></table></div></details>'
  }

  // ===== PERMISSIONS =====
  if (perms.length > 0) {
    html += '<div class="apk-card">'
    html += `<div class="apk-card-h">${label('permissions')}<span class="apk-count">${perms.length}</span></div>`
    if (dangerous.length > 0) {
      html += `<div class="apk-badge-wrap" style="margin-bottom:6px">${dangerous.map(p => permBadge(p, true)).join('')}</div>`
    }
    if (normal.length > 0) {
      html += '<details><summary>' + label('otherPermsShow', { count: normal.length }) + '<span class="chev">▸</span></summary>'
      html += `<div class="apk-badge-wrap">${normal.map(p => permBadge(p, false)).join('')}</div>`
      html += '</details>'
    }
    html += '</div>'
  } else {
    html += `<div class="apk-card"><div class="apk-card-h">${label('permissions')}</div><div class="apk-muted">${label('noPermissions')}</div></div>`
  }

  html += '</div>'
  return html
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
.task-duration { font-size: 11px; color: var(--app-text-muted); font-family: monospace; }
/* Bottom-left meta line: creation time + duration, always visible on the card */
.task-meta-row {
  display: flex; align-items: center; gap: 6px;
  padding: 0 14px 8px;
}
.task-detail ~ .task-meta-row { padding-top: 4px; }

.task-progress { padding: 0 14px; height: 3px; }
/* Indeterminate progress: operations emit no real progress events, so the
   bar shows a sliding stripe instead of a meaningless percentage. */
.indeterminate-bar {
  position: relative;
  height: 3px;
  border-radius: 2px;
  background: rgba(128, 128, 128, 0.18);
  overflow: hidden;
}
.indeterminate-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 40%;
  border-radius: 2px;
  background: #22C55E;
  animation: indeterminate-slide 1.4s ease-in-out infinite;
}
@keyframes indeterminate-slide {
  0% { left: -40%; }
  100% { left: 100%; }
}

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
.task-logs-toolbar { display: flex; align-items: center; gap: 4px; margin-bottom: 6px; }
.task-logs-spacer { flex: 1; }
.task-logs-toolbar .n-button { flex: 0 0 auto; }
.task-log-trunc-hint {
  display: flex; align-items: center; gap: 6px;
  color: var(--app-warning, #d97706);
  background: rgba(217, 119, 6, 0.1);
  border-radius: 4px;
  padding: 4px 8px;
  margin-bottom: 6px;
  font-size: 11px;
  line-height: 1.5;
}

</style>

<style>
/* APK analysis result card — NON-SCOPED on purpose.
   The card is rendered via v-html (task.result is a persisted HTML string),
   so scoped styles in this SFC do not reach its dynamic DOM. */
.apk-info { display: flex; flex-direction: column; gap: 8px; font-size: 13px; line-height: 1.6; }
.apk-card { background: var(--app-card-bg); border: 1px solid var(--app-card-border); border-radius: 10px; padding: 10px 14px; }
.apk-card > summary {
  list-style: none; cursor: pointer; user-select: none;
  display: flex; align-items: center; justify-content: space-between;
  color: var(--app-text-secondary); font-size: 13px; font-weight: 600;
}
.apk-card > summary::-webkit-details-marker { display: none; }
.apk-card[open] > .apk-card-body { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--app-card-border); }
.apk-card-body { display: flex; flex-direction: column; gap: 4px; }

.apk-name { font-size: 16px; font-weight: 700; color: var(--app-text-primary); word-break: break-all; }
.apk-pkg { font-family: monospace; font-size: 12px; color: var(--app-text-dim); margin-top: 2px; word-break: break-all; }

.apk-statgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
.apk-stat { display: flex; flex-direction: column; gap: 2px; }
.apk-stat-k { font-size: 11px; color: var(--app-text-dim); }
.apk-stat-v { font-size: 13px; color: var(--app-text-secondary); font-weight: 500; word-break: break-word; }
.apk-archchip { display: inline-block; font-size: 11px; font-weight: 600; border-radius: 4px; padding: 1px 6px; margin: 1px 3px 1px 0; }

.apk-warn { background: rgba(217,119,6,0.1); border: 1px solid rgba(217,119,6,0.25); color: var(--app-warning, #d97706); border-radius: 6px; padding: 6px 10px; font-size: 12px; margin-top: 6px; }
.apk-warn-inline { color: var(--app-warning, #d97706); font-size: 12px; }

.apk-hashrow { display: flex; align-items: baseline; gap: 8px; padding: 3px 0; font-size: 12px; }
.apk-hashrow .k { color: var(--app-text-dim); flex: 0 0 auto; min-width: 64px; }
.apk-hashrow .v { font-family: monospace; color: var(--app-text-secondary); word-break: break-all; flex: 1; }
.apk-copy { flex: 0 0 auto; margin-left: 4px; color: var(--app-green); cursor: pointer; font-size: 11px; }
.apk-copy:hover { text-decoration: underline; }

.apk-card-h { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--app-text-secondary); margin-bottom: 6px; }
.apk-count { background: rgba(128,128,128,0.14); color: var(--app-text-secondary); font-size: 11px; font-weight: 600; border-radius: 10px; padding: 1px 8px; }

.apk-so-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 3px 0; }
.apk-so-arch { font-weight: 600; font-size: 12px; }
.apk-so-miss { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; color: var(--app-warning, #d97706); font-size: 12px; }
.apk-mini { display: inline-block; font-family: monospace; font-size: 11px; background: rgba(217,119,6,0.12); color: var(--app-warning, #d97706); border-radius: 3px; padding: 0 5px; }

.apk-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 3px 0; font-size: 12px; }
.apk-row-k { font-weight: 600; color: var(--app-text-secondary); }

.apk-sub { font-size: 12px; font-weight: 600; color: var(--app-text-dim); margin: 6px 0 2px; }
.apk-file { font-family: monospace; font-size: 12px; color: var(--app-text-secondary); word-break: break-all; }

.apk-badge { display: inline-block; font-size: 11px; border-radius: 4px; padding: 2px 7px; margin: 2px 4px 2px 0; line-height: 1.4; }
.apk-badge--danger { background: rgba(239,68,68,0.12); color: var(--app-red); border: 1px solid rgba(239,68,68,0.3); }
.apk-badge--normal { background: rgba(128,128,128,0.12); color: var(--app-text-secondary); border: 1px solid var(--app-card-border); }
.apk-badge--ok { background: rgba(34,197,94,0.12); color: var(--app-green); border: 1px solid rgba(34,197,94,0.3); }
/* permission badges: wrap horizontally instead of stretching full-width
   (a flex-column container would stretch each inline-block badge to 100%) */
.apk-badge-wrap { display: flex; flex-wrap: wrap; }

.apk-meta { width: 100%; border-collapse: collapse; font-size: 12px; }
.apk-meta th { text-align: left; color: var(--app-text-dim); font-weight: 600; font-size: 11px; border-bottom: 1px solid var(--app-card-border); padding: 4px 6px; }
.apk-meta td { padding: 4px 6px; border-bottom: 1px solid var(--app-card-border); color: var(--app-text-secondary); vertical-align: top; word-break: break-word; }
.apk-meta tr:last-child td { border-bottom: none; }
.apk-parent { font-family: monospace; font-size: 11px; color: var(--app-text-dim); white-space: nowrap; }
.apk-res { font-size: 11px; color: var(--app-text-muted); font-family: monospace; }

.apk-muted { color: var(--app-text-dim); font-size: 12px; }

.chev { color: var(--app-text-dim); transition: transform .2s; }
details[open] > summary .chev { transform: rotate(90deg); }

/* nested details (e.g. "other permissions") */
.apk-card details > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; gap: 6px; color: var(--app-text-dim); font-size: 12px; }
.apk-card details > summary::-webkit-details-marker { display: none; }
</style>
