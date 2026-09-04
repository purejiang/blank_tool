<template>
  <div class="package-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('package.title') }}</h1>
        <p class="page-subtitle">{{ t('package.subtitle') }}</p>
      </div>
    </div>

    <!-- New Task Bar -->
    <div class="new-task-bar">
      <div class="task-bar-row">
        <!-- Single source input: http(s):// -> remote download, anything else
             -> local path. No more radio switching. -->
        <n-input
          v-model:value="newTarget"
          :placeholder="t('task.inputPlaceholder')"
          size="small"
          clearable
          class="task-source-input"
          @dragover.prevent
          @drop.prevent="onPathDrop"
        >
          <template #suffix>
            <!-- Browse only makes sense for local targets. -->
            <n-icon
              v-if="!isUrlLike"
              class="task-pick-btn"
              :title="needsDirectory ? t('task.selectDir') : t('task.selectFile')"
              @click="pickLocalFile"
            >
              <FolderOpen />
            </n-icon>
          </template>
        </n-input>

        <n-select v-model:value="newOperation" :options="operationOptions" size="small" style="width:120px" />

        <n-tooltip :disabled="canStart" trigger="hover">
          <template #trigger>
            <span class="task-start-wrap">
              <n-button type="primary" size="small" @click="startNewTask" :disabled="!canStart">
                <template #icon><n-icon><Play /></n-icon></template>
                {{ t('task.start') }}
              </n-button>
            </span>
          </template>
          {{ startDisabledHint }}
        </n-tooltip>

        <n-button size="small" quaternary type="error" @click="confirmClearAll" :disabled="taskStore.tasks.length === 0">
          <template #icon><n-icon><Trash2 /></n-icon></template>
          {{ t('task.clearAll') }}
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
          <div v-if="task.result && task.operation === 'analyze'" class="task-result-bar">
            <n-button
              size="tiny"
              quaternary
              type="info"
              :title="t('task.exportReport')"
              @click.stop="exportReport(task)"
            >
              <template #icon><n-icon size="14"><FileDown /></n-icon></template>
              <span>{{ t('task.exportReport') }}</span>
            </n-button>
          </div>
          <div v-if="task.result" class="task-result" v-html="task.result" @click="onResultClick" />
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
            </div>
            <div v-if="logTruncatedMap.get(task.id)" class="task-log-trunc-hint">
              {{ t('task.logTruncatedHint') }}
            </div>
            <n-virtual-list
              :ref="(el: any) => onLogListRef(task.id, el)"
              :key="'log-' + task.id"
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
  ChevronDown, ChevronRight, Trash2, Inbox, ExternalLink, StopCircle, AlertCircle, Download, RefreshCw, Smartphone,
  Search, Copy, RotateCcw, FileDown
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
// Per-task inline log search state + virtual-list refs
const logSearchMap = ref<Map<number, string>>(new Map())
const logSearchOpenMap = ref<Map<number, boolean>>(new Map())
// Per-task flag: log panel default-truncates (tail 100KB); export yields the full file.
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
// - Clicking the app icon (`.apk-icon`) opens a lightbox zoom.
// - Clicking any element carrying `data-copy` copies that value to the
//   clipboard; `data-fb-hash` is kept as a fallback.
let lightboxKeyHandler: ((ev: KeyboardEvent) => void) | null = null

function openIconLightbox(src: string) {
  if (!src) return
  let overlay = document.getElementById('apk-icon-lightbox') as HTMLElement | null
  if (!overlay) {
    overlay = document.createElement('div')
    overlay.id = 'apk-icon-lightbox'
    overlay.className = 'apk-lightbox'
    overlay.addEventListener('click', closeIconLightbox)
    document.body.appendChild(overlay)
  }
  overlay.innerHTML = `<img class="apk-lightbox-img" src="${src}" alt="app icon">`
  overlay.style.display = 'flex'
  lightboxKeyHandler = (ev: KeyboardEvent) => {
    if (ev.key === 'Escape') closeIconLightbox()
  }
  document.addEventListener('keydown', lightboxKeyHandler)
}

function closeIconLightbox() {
  const overlay = document.getElementById('apk-icon-lightbox')
  if (overlay) overlay.style.display = 'none'
  if (lightboxKeyHandler) {
    document.removeEventListener('keydown', lightboxKeyHandler)
    lightboxKeyHandler = null
  }
}

function onResultClick(e: MouseEvent) {
  const el = e.target as HTMLElement | null
  // App icon → lightbox zoom (handled first so it doesn't trigger copy).
  const icon = el?.closest?.('.apk-icon') as HTMLImageElement | null
  if (icon && icon.src) {
    // The icon lives inside <summary>, so stop the click from also toggling
    // the parent <details> open/closed when we only want the lightbox.
    e.preventDefault()
    e.stopPropagation()
    openIconLightbox(icon.src)
    return
  }
  const node = el?.closest?.('[data-copy], [data-fb-hash]') as HTMLElement | null
  const value = node?.getAttribute('data-copy') ?? node?.getAttribute('data-fb-hash')
  if (!value) return
  const copy = async () => {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value)
    } else {
      const api = window.electronAPI as any
      if (api?.writeClipboardText) await api.writeClipboardText(value)
      else throw new Error('clipboard unavailable')
    }
  }
  copy()
    .then(() => showSuccess(t('task.copyLog'), t('task.logCopied')))
    .catch((err) => showWarning(t('task.copyLog'), String(err)))
}

// Lazy-load APK launcher icons whose path is persisted in task.result (instead
// of an inline base64 blob). For each <img data-icon-path> we fetch the bytes
// via IPC and inline them as a data URL, then drop the attribute so the pass
// is idempotent. Falls back silently when the file is gone (e.g. task deleted).
function fallbackIcon(img: HTMLImageElement) {
  const alt = img.getAttribute('alt') || ''
  const ch = (alt.trim()[0] || 'A').toUpperCase()
  const span = document.createElement('span')
  span.className = 'apk-icon apk-icon--fallback'
  span.textContent = ch
  span.title = img.getAttribute('title') || ''
  img.replaceWith(span)
}

// Lazy-load APK launcher icons whose path is persisted in task.result (instead
// of an inline base64 blob). For each <img data-icon-path> we fetch the bytes
// via IPC and inline them as a data URL, then drop the attribute so the pass
// is idempotent. Falls back to a letter tile when the file is gone (e.g. task deleted).
function hydrateResultIcons() {
  const imgs = document.querySelectorAll('.task-result img.apk-icon[data-icon-path]') as NodeListOf<HTMLImageElement>
  imgs.forEach((img) => {
    const p = img.getAttribute('data-icon-path')
    if (!p) return
    const api = window.electronAPI as any
    if (!api?.readImageAsDataURL) {
      fallbackIcon(img)
      return
    }
    api.readImageAsDataURL(p)
      .then((res: any) => {
        if (res && res.success && res.dataUrl) {
          img.src = res.dataUrl
          img.removeAttribute('data-icon-path')
        } else {
          fallbackIcon(img)
        }
      })
      .catch(() => fallbackIcon(img))
  })
}

// Re-hydrate whenever any task's result HTML (re)renders OR a task is
// expanded/collapsed. Fresh analyses hydrate fine because the task is expanded
// while it runs, but tasks restored from the persisted store default to
// collapsed — their result <img> only enters the DOM once the detail panel is
// shown, so we must also react to `collapsed` flips, not just `result` changes.
watch(
  () => taskStore.tasks.flatMap((t) => [t?.id, t?.collapsed, t?.result]),
  async () => {
    await nextTick()
    hydrateResultIcons()
  },
  { immediate: true }
)

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

// ===== Standalone report.html =====
// The report fragment (task.result) is persisted in renderer localStorage,
// which prunes history beyond 100 terminal tasks. To keep a durable second
// copy we wrap the fragment in a self-contained HTML document (inline CSS +
// base64 icons) and write it next to the task's other files on disk.
//
// KEEP IN SYNC with the global <style> block at the bottom of this file —
// REPORT_DOC_CSS must stay a superset of the selectors the report HTML uses.
const REPORT_DOC_CSS = `
:root {
  --app-card-bg: #ffffff; --app-card-border: #e2e8f0;
  --app-text-secondary: #1e293b; --app-text-dim: #64748b; --app-text-muted: #94a3b8;
  --app-red: #dc2626; --app-green: #16a34a; --app-warning: #d97706; --apk-accent: #3b82f6;
}
@media (prefers-color-scheme: dark) {
  :root {
    --app-card-bg: #16202f; --app-card-border: #27354a;
    --app-text-secondary: #e2e8f0; --app-text-dim: #94a3b8; --app-text-muted: #64748b;
    --app-red: #f87171; --app-green: #4ade80; --app-warning: #fbbf24; --apk-accent: #60a5fa;
  }
}
body { margin: 0; padding: 16px; background: #f4f6f8; color: var(--app-text-secondary);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif; }
@media (prefers-color-scheme: dark) { body { background: #0d141f; } }
.apk-info { display: flex; flex-direction: column; gap: 8px; font-size: 13px; line-height: 1.6; }
.apk-card { background: var(--app-card-bg); border: 1px solid var(--app-card-border); border-radius: 10px; padding: 10px 14px; }
.apk-card > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--app-text-secondary); font-size: 13px; font-weight: 600; }
.apk-card > summary::-webkit-details-marker { display: none; }
.apk-card[open] > .apk-card-body { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--app-card-border); }
.apk-card-body { display: flex; flex-direction: column; gap: 6px; }
.apk-card-h { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--app-text-secondary); }
.apk-sum-grp { display: flex; align-items: center; gap: 8px; min-width: 0; }
.apk-group { background: var(--app-card-bg); border: 1px solid var(--app-card-border); border-left: 3px solid var(--apk-accent, var(--app-card-border)); border-radius: 10px; padding: 10px 14px; }
.apk-group > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--app-text-secondary); font-size: 13px; font-weight: 700; }
.apk-group > summary::-webkit-details-marker { display: none; }
.apk-group[open] > .apk-group-body { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--app-card-border); display: flex; flex-direction: column; gap: 10px; }
.apk-group-body .apk-card { background: transparent; border: none; border-radius: 0; padding: 0; }
.apk-group-body .apk-card[open] > .apk-card-body { margin-top: 6px; padding-top: 6px; }
.apk-icon { width: 38px; height: 38px; border-radius: 8px; object-fit: contain; box-shadow: 0 1px 2px rgba(0,0,0,.18); flex: 0 0 auto; }
.apk-icon--fallback { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: 8px; background: var(--app-card-border); color: var(--app-text-dim); font-weight: 600; font-size: 15px; flex: 0 0 auto; }
.apk-sum { font-size: 11px; color: var(--app-text-dim); font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.apk-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.apk-table th { text-align: left; color: var(--app-text-dim); font-weight: 600; font-size: 11px; border-bottom: 1px solid var(--app-card-border); padding: 5px 8px; white-space: nowrap; }
.apk-table td { padding: 5px 8px; border-bottom: 1px solid var(--app-card-border); color: var(--app-text-secondary); vertical-align: top; word-break: break-word; }
.apk-table tr:last-child td { border-bottom: none; }
.apk-table tbody tr:hover { background: rgba(128,128,128,0.07); }
.apk-table .mono { font-family: monospace; }
.apk-table .nowrap { white-space: nowrap; }
.apk-parent { font-family: monospace; font-size: 11px; color: var(--app-text-dim); white-space: nowrap; }
.apk-res { font-size: 11px; color: var(--app-text-muted); font-family: monospace; }
.apk-archchip { display: inline-block; font-size: 11px; font-weight: 600; border-radius: 4px; padding: 1px 6px; margin: 1px 3px 1px 0; }
.apk-lv { display: inline-block; font-size: 11px; border-radius: 4px; padding: 1px 7px; font-weight: 600; white-space: nowrap; }
.apk-lv--danger { background: rgba(239,68,68,0.12); color: var(--app-red); }
.apk-lv--normal { background: rgba(128,128,128,0.12); color: var(--app-text-dim); }
.apk-lv--ok { background: rgba(34,197,94,0.12); color: var(--app-green); }
.apk-mini { display: inline-block; font-family: monospace; font-size: 11px; background: rgba(217,119,6,0.12); color: var(--app-warning, #d97706); border-radius: 3px; padding: 0 5px; margin: 0 2px; }
.apk-warn { background: rgba(217,119,6,0.1); border: 1px solid rgba(217,119,6,0.25); color: var(--app-warning, #d97706); border-radius: 6px; padding: 6px 10px; font-size: 12px; margin-top: 6px; }
.apk-muted { color: var(--app-text-dim); font-size: 12px; }
.apk-copy { color: var(--app-text-dim); opacity: 0.4; margin-left: 6px; display: inline-flex; align-items: center; vertical-align: middle; }
.apk-copy svg { display: block; }
.chev { color: var(--app-text-dim); transition: transform .2s; }
details[open] > summary .chev { transform: rotate(90deg); }
.apk-card details > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; gap: 6px; color: var(--app-text-dim); font-size: 12px; }
.apk-card details > summary::-webkit-details-marker { display: none; }
`

function escDoc(s: string): string {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string)
}

// Wrap the report fragment into a self-contained document: inline CSS plus
// base64-inlined disk icons (img[data-icon-path] would otherwise be broken
// outside the app, since the lazy hydration only runs in the renderer).
async function buildReportDocument(resultHtml: string, docTitle = ''): Promise<string> {
  const dom = new DOMParser().parseFromString(resultHtml, 'text/html')
  const imgs = Array.from(dom.querySelectorAll('img.apk-icon[data-icon-path]')) as HTMLImageElement[]
  const api = window.electronAPI as any
  for (const img of imgs) {
    const p = img.getAttribute('data-icon-path')
    if (!p) continue
    const toFallback = () => {
      const alt = img.getAttribute('alt') || ''
      const span = dom.createElement('span')
      span.className = 'apk-icon apk-icon--fallback'
      span.textContent = (alt.trim()[0] || 'A').toUpperCase()
      img.replaceWith(span)
    }
    if (!api?.readImageAsDataURL) { toFallback(); continue }
    try {
      const res = await api.readImageAsDataURL(p)
      if (res?.success && res.dataUrl) {
        img.src = res.dataUrl
        img.removeAttribute('data-icon-path')
      } else {
        toFallback()
      }
    } catch {
      toFallback()
    }
  }
  const body = dom.body.innerHTML
  const title = escDoc(docTitle || 'APK Report')
  return `<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>${title}</title>\n<style>\n${REPORT_DOC_CSS}\n</style>\n</head>\n<body>\n${body}\n</body>\n</html>\n`
}

// Auto-persist a durable copy right after an analyze completes (best-effort,
// fire-and-forget — a failure only costs the on-disk copy, never the UI).
async function persistReportFile(task: Task, resultHtml: string): Promise<void> {
  try {
    const api = window.electronAPI as any
    if (!resultHtml || !api?.callBackendAPI) return
    const doc = await buildReportDocument(resultHtml, `${task.fileName || task.id} · Report`)
    const res = await api.callBackendAPI('task.save_report', { task_id: String(task.id), html: doc })
    if (!res?.success) logUtil.warn('[report] persist report.html failed', res?.error || 'unknown')
  } catch (e) {
    logUtil.warn('[report] persist report.html failed', e)
  }
}

async function exportReport(task: Task) {
  try {
    const api = window.electronAPI as any
    if (!task?.result) return
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`
    const base = (task.fileName || `task-${task.id}`).replace(/\.(apk|aab)$/i, '')
    let filePath = ''
    if (api?.showSaveDialog) {
      const res = await api.showSaveDialog({
        title: t('task.exportReport'),
        defaultPath: `${base}-report-${ts}.html`,
        filters: [{ name: 'HTML', extensions: ['html'] }],
      })
      if (!res || res.canceled) return
      filePath = res.filePath || ''
    }
    if (!filePath) return
    const doc = await buildReportDocument(task.result, `${base} · Report`)
    const result = await api.callBackendAPI('task.save_report', { task_id: String(task.id), html: doc, target: filePath })
    if (result?.success) {
      showSuccess(t('task.exportReport'), result.file_path || filePath)
    } else {
      showError(t('task.exportReport'), result?.error || 'failed')
    }
  } catch (e) {
    showError(t('task.exportReport'), String(e))
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
    nextTick(() => scrollLogToBottom(taskId))
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
const newOperation = ref<Task['operation']>('analyze')
// Single merged source input: http(s):// -> remote URL, anything else -> local
// path. Kept in one field so users can paste either without switching modes.
const newTarget = ref('')
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

const canStart = computed(() => !!newTarget.value.trim())

// http(s):// -> remote download; everything else is treated as a local path.
const isUrlLike = computed(() => /^https?:\/\//i.test(newTarget.value.trim()))

// recompile consumes a decompiled project directory; every other op a file.
const needsDirectory = computed(() => newOperation.value === 'recompile')

const startDisabledHint = computed(() => t('task.startHint'))

/** Resolve a path's existence + type via the main process (null = not found). */
async function statLocalPath(p: string) {
  try {
    const svc = await serviceManager.getService('system') as any
    if (svc && typeof svc.getFileStats === 'function') {
      const r = await svc.getFileStats(p)
      if (r?.success === true) return r as { isFile: boolean; isDirectory: boolean }
    }
  } catch {
    // An IPC failure is treated the same as "path not found".
  }
  return null
}

// Switching the operation can invalidate an already-picked path (e.g. a file
// held while switching to recompile, which needs a directory). Drop it instead
// of letting startNewTask run with the wrong kind of target. URL targets are
// unaffected — they have no file/dir duality.
watch(newOperation, async () => {
  if (isUrlLike.value) return
  const p = newTarget.value.trim()
  if (!p) return
  const st = await statLocalPath(p)
  if (!st) return // non-existent paths are validated on start
  if (needsDirectory.value ? !st.isDirectory : !st.isFile) {
    newTarget.value = ''
    showWarning(t('task.pathTypeMismatch'), needsDirectory.value ? t('task.pathNeedDir') : t('task.pathNeedFile'))
  }
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
    // Default to a truncated tail (100KB) so the panel stays light; the export
    // button calls task.export_log which copies the *full* file to disk.
    const result = await api.callBackendAPI('task.read_log', {
      task_id: String(task.id),
      tail_bytes: 100 * 1024,
    })
    const content = (result.content || '').trim()
    logTruncatedMap.value.set(task.id, !!result.truncated)
    if (content) {
      taskLogCache.value.set(task.id, splitLogLines(content))
    }
    await nextTick()
    scrollLogToBottom(task.id)
  } catch (e) {
    logTruncatedMap.value.set(task.id, false)
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

async function pickLocalFile() {
  try {
    const svc = await serviceManager.getService('system') as any
    const result = needsDirectory.value
      ? await svc.selectDirectory({ title: t('task.selectDir') })
      : await svc.selectFile({ title: t('task.selectFile'), filters: [{ name: 'APK/AAB', extensions: ['apk', 'aab'] }] })
    if (result && !result.canceled && result.filePaths?.length) {
      newTarget.value = result.filePaths[0]
    }
  } catch (e) {
    logUtil.error('pickLocalFile error:', e)
  }
}

// Dropping a file onto the path input fills in its absolute path. Chromium
// gives no useful default behaviour here, so we read it off the File object.
function onPathDrop(e: DragEvent) {
  const file = e.dataTransfer?.files?.[0] as (File & { path?: string }) | undefined
  if (file?.path) newTarget.value = file.path
}

async function startNewTask() {
  const raw = newTarget.value.trim()
  if (!raw) return
  let source: Task['source'], url: string | undefined, fp: string, fn: string

  if (/^https?:\/\//i.test(raw)) {
    source = 'url'
    url = raw
    // Strip any query/hash: the backend replaces '?' with '_' when sanitizing
    // the name, which would silently destroy the extension (app.apk?x=1 ->
    // app.apk_x=1).
    fn = (url.split('/').pop() || 'app.apk').split('?')[0].split('#')[0] || 'app.apk'
    fp = ''
  } else {
    source = 'local'
    fp = raw
    // A hand-typed or stale path is validated before it reaches the backend.
    const st = await statLocalPath(fp)
    if (!st) {
      showWarning(t('task.pathNotExist'), fp)
      return
    }
    if (needsDirectory.value && !st.isDirectory) {
      showWarning(t('task.pathNeedDir'), fp)
      return
    }
    if (!needsDirectory.value && !st.isFile) {
      showWarning(t('task.pathNeedFile'), fp)
      return
    }
    fn = fp.split(/[/\\]/).pop() || 'file'
  }

  const opLabel = operationOptions.value.find(o => o.value === newOperation.value)?.label || newOperation.value
  const task = taskStore.createTask({ source, url, filePath: fp, fileName: fn, operation: newOperation.value, operationLabel: opLabel })

  // Clear inputs
  newTarget.value = ''

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
          // Persist a standalone report.html next to the task's other files so
          // the report survives renderer localStorage pruning (100-task cap).
          if (transitionPayload.result) {
            void persistReportFile(task, transitionPayload.result)
          }
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
      const rawMsg = e?.message ?? String(e ?? '')
      // Guard against a literal "null"/"None"/empty message ever being shown
      // or persisted as the task error.
      const errMsg = (rawMsg && rawMsg !== 'null' && rawMsg !== 'None')
        ? rawMsg
        : t('task.operationFailed')
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
      onPositiveClick: () => { taskLogCache.value.delete(task.id); logTruncatedMap.value.delete(task.id); taskStore.removeTask(task.id) }
    })
  } else {
    taskLogCache.value.delete(task.id)
    logTruncatedMap.value.delete(task.id)
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

  const lv = (danger: boolean) =>
    `<span class="apk-lv ${danger ? 'apk-lv--danger' : 'apk-lv--normal'}">${danger ? label('levelDanger') : label('levelNormal')}</span>`

  const soComp = data.so_comparison
  const comp = data.compression_analysis
  const page16 = data.page_size_16kb

  // summaries computed inline per section below

  const metaData = data.meta_data
  const fileMd5 = data.file_md5
  const sigMd5 = data.sig_md5
  const sigSha1 = data.sig_sha1
  const sigSha256 = data.sig_sha256
  const hasAnyHash = (fileMd5 && fileMd5 !== '-') || (sigMd5 && sigMd5 !== '-') || (sigSha1 && sigSha1 !== '-') || (sigSha256 && sigSha256 !== '-')
  const unsigned = sigMd5 === '-' || sigSha1 === '-' || sigSha256 === '-'
  const hasSoCompFull = soComp && !soComp.single_arch && !soComp.no_native && soComp.arches && Object.keys(soComp.arches).length > 0
  const hasComp = comp && Object.keys(comp).length > 0
  const hasPage16 = page16 && !page16.no_64bit_native && Object.keys(page16).filter(k => k !== 'skipped').length > 0

  const table = (headers: string[], rows: string[]) =>
    `<table class="apk-table"><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`
  const trow = (cells: string[]) => `<tr>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`
  const head = (title: string, summary = '', icon = '') =>
    `<summary><span class="apk-sum-grp">${icon}${title}${summary ? `<span class="apk-sum">${summary}</span>` : ''}</span><span class="chev">▸</span></summary>`
  const card = (title: string, summary: string, body: string) =>
    `<details class="apk-card" open>${head(title, summary)}<div class="apk-card-body">${body}</div></details>`
  const simpleCard = (title: string, summary: string, body: string) =>
    `<div class="apk-card"><div class="apk-card-h">${title}${summary ? `<span class="apk-sum">${summary}</span>` : ''}</div>${body}</div>`
  // Parent section that groups several related sub-analyses under one
  // collapsible card (e.g. native libraries: SO / compression / 16KB).
  const group = (title: string, summary: string, body: string, icon = '', accent = '', open = true) =>
    `<details class="apk-group"${open ? ' open' : ''}${accent ? ` style="--apk-accent:${accent}"` : ''}>${head(title, summary, icon)}<div class="apk-group-body">${body}</div></details>`

  // dim, subtle copy affordance appended after values for one-click copy
  const COPY_ICO = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="5.5" y="5.5" width="8" height="8" rx="1.4"/><path d="M3.5 10.5h-1a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v1"/></svg>'
  const copyBtn = (value: string) =>
    `<span class="apk-copy" data-copy="${esc(value)}" title="${label('copyLog')}">${COPY_ICO}</span>`

  let html = '<div class="apk-info">'

  // ===== BASIC INFO =====
  {
    const rows: string[] = []
    rows.push(trow([label('version'), `${esc(data.version_name)} <span style="color:var(--app-text-dim);font-weight:400">(${esc(data.version_code)})</span>`]))
    rows.push(trow([label('fileSize'), fmtSize(data.file_size)]))
    rows.push(trow([`${label('minSdk')} / ${label('targetSdk')}`, `${esc(data.min_sdk_version)} / ${esc(data.target_sdk_version)}`]))
    if (archChips) rows.push(trow([label('architecture'), archChips]))
    let body = table([label('colItem'), label('colValue')], rows)
    if (data.warnings && Array.isArray(data.warnings) && data.warnings.length > 0) {
      body += `<div class="apk-warn"><b>${label('warnings')}</b>：${data.warnings.map((w: any) => esc(String(w))).join('；')}</div>`
    }
    const appIconTitle = [data.application_label, data.package_name].filter(Boolean).join(' · ')
    // Disk-path icons (persisted result HTML only stores the short path to
    // keep localStorage small); the data: URIs are legacy/inline fallbacks.
    const isDataUri = data.app_icon && data.app_icon.startsWith('data:')
    const appIconFallbackChar = (data.application_label || 'A').trim()[0] || 'A'
    const appIcon = (data.app_icon && data.app_icon !== '-')
      ? (isDataUri
          ? `<img class="apk-icon" src="${esc(data.app_icon)}" alt="${esc(data.application_label || 'app')}" title="${esc(appIconTitle)}">`
          : `<img class="apk-icon" data-icon-path="${esc(data.app_icon)}" alt="${esc(data.application_label || 'app')}" title="${esc(appIconTitle)}">`)
      : `<span class="apk-icon apk-icon--fallback" title="${esc(appIconTitle)}">${esc(appIconFallbackChar)}</span>`
    // Basic info becomes the first top-level group so all four sections share
    // one collapsible-card style (icon + app name in the header, package name
    // as the summary, the detail table inside the body).
    html += group(esc(data.application_label), esc(data.package_name), body, appIcon, '#3b82f6')
  }

  // ===== SIGNATURE (accumulated into the Security group) =====
  // perms/dangerous/normal are classified at function scope, so permissions
  // can be folded into the same Security group right here, next to signing.
  let securityBody = ''
  let signStatus = ''
  let signPill = ''
  if (hasAnyHash) {
    const rows: string[] = []
    if (fileMd5 && fileMd5 !== '-') rows.push(trow([label('apkMd5'), `<span class="mono">${esc(fileMd5)}</span>` + copyBtn(fileMd5)]))
    if (sigMd5 && sigMd5 !== '-') rows.push(trow([label('sigMd5'), `<span class="mono">${esc(sigMd5)}</span>` + copyBtn(sigMd5)]))
    if (sigSha1 && sigSha1 !== '-') rows.push(trow([label('sigSha1'), `<span class="mono">${esc(sigSha1)}</span>` + copyBtn(sigSha1)]))
    if (sigSha256 && sigSha256 !== '-') rows.push(trow([label('sigSha256'), `<span class="mono">${esc(sigSha256)}</span>` + copyBtn(sigSha256)]))
    const fbHashKey = data.fb_hash_key
    if (fbHashKey && fbHashKey !== '-') {
      rows.push(trow(['Facebook Hash Key', `<span class="mono">${esc(fbHashKey)}</span>` + copyBtn(fbHashKey)]))
    }
    let body = table([label('colField'), label('colValue')], rows)
    if (unsigned) body += `<div class="apk-warn">${label('unsignedApk')}</div>`
    signStatus = unsigned ? label('unsigned') : label('signed')
    // Signing status as a status pill (same language as 16KB / permission
    // levels) so the security posture reads at a glance instead of as plain text.
    const signPillLocal = unsigned
      ? '<span class="apk-lv apk-lv--danger">' + label('unsigned') + '</span>'
      : '<span class="apk-lv apk-lv--ok">' + label('signed') + '</span>'
    signPill = signPillLocal
    securityBody += card(label('signatureInfo'), signPill, body)
  }
  // Permissions folded into the Security group (dangerous first, then normal).
  {
    const prows: string[] = []
    for (const p of dangerous) {
      prows.push(trow([`<span class="mono" title="${esc(p)}">${esc(p.replace('android.permission.', ''))}</span>`, lv(true)]))
    }
    for (const p of normal) {
      prows.push(trow([`<span class="mono" title="${esc(p)}">${esc(p.replace('android.permission.', ''))}</span>`, lv(false)]))
    }
    const permCard = perms.length > 0
      ? card(label('permissions'), label('permCount', { count: perms.length, danger: dangerous.length }), table([label('permissions'), label('colLevel')], prows))
      : simpleCard(label('permissions'), '', `<div class="apk-muted">${label('noPermissions')}</div>`)
    const secSummary = signStatus
      ? `${signPill} · ${label('permsSummary', { count: perms.length, danger: dangerous.length })}`
      : label('permsSummary', { count: perms.length, danger: dangerous.length })
    html += group(label('signingSecurity'), secSummary, securityBody + permCard, '', '#22c55e', false)
  }

  // ===== NATIVE LIBRARIES (SO comparison + 16KB page) =====
  // Grouped under one collapsible parent so the related binary analyses read as
  // a single section. Compression is deliberately NOT here: only its `lib`
  // category is native — assets/dex are whole-package concerns, so it gets its
  // own top-level group further down.
  let nativeBody = ''
  const nativeSum: string[] = []
  if (hasSoCompFull) {
    const rows: string[] = []
    for (const [arch, info] of Object.entries(soComp.arches)) {
      const a = info as any
      const archColor = Object.keys(archColors).find(k => arch.startsWith(k)) || '#6b7280'
      const count = a.count || a.so_files?.length || 0
      const missing = a.missing || []
      const status = missing.length > 0
        ? label('missingCount', { count: missing.length }) + missing.map(s => `<span class="apk-mini">${esc(s)}</span>`).join('')
        : '<span style="color:var(--app-green)">✓ ' + label('complete') + '</span>'
      rows.push(trow([`<span style="color:${archColor};font-weight:600">${esc(arch)}</span>`, `${count} .so`, status]))
    }
    const sum = `${Object.keys(soComp.arches).length} ${label('architecture')} · ${soComp.baseline?.length || 0} .so`
    nativeBody += card(label('soComparison'), sum, table([label('architecture'), label('colSoCount'), label('colStatus')], rows))
    nativeSum.push(sum)
  } else if (soComp && soComp.single_arch) {
    nativeBody += simpleCard(label('soComparison'), label('singleArch'), `<div class="apk-muted">${label('singleArch')}</div>`)
    nativeSum.push(label('singleArch'))
  } else if (soComp && soComp.no_native) {
    nativeBody += simpleCard(label('soComparison'), label('noNativeLibs'), `<div class="apk-muted">${label('noNativeLibs')}</div>`)
    nativeSum.push(label('noNativeLibs'))
  }
  if (hasPage16) {
    const rows: string[] = []
    let total = 0, supported = 0
    for (const [arch, files] of Object.entries(page16)) {
      if (arch === 'skipped') continue
      for (const [file, info] of Object.entries(files as any)) {
        const fi = info as any
        const ok = fi.supports_16kb
        total++; if (ok) supported++
        const st = ok
          ? '<span class="apk-lv apk-lv--ok">' + label('supported') + '</span>'
          : '<span class="apk-lv apk-lv--danger">' + label('notSupported') + '</span>'
        const align = fi.max_align ? `0x${fi.max_align.toString(16)}` : '-'
        rows.push(trow([`<span style="color:var(--app-text-dim)">${esc(arch)}</span>`, `<span class="mono">${esc(file)}</span>`, st, align !== '-' ? align : '-']))
      }
    }
    let body = table([label('architecture'), label('colFile'), label('colStatus'), label('colAlignment')], rows)
    if (page16.skipped && page16.skipped.length > 0) {
      body += `<div class="apk-muted" style="margin-top:4px">${label('pageSizeSkipped', { count: page16.skipped.length })}</div>`
    }
    const sum = label('page16Supported', { supported, total })
    nativeBody += card(label('pageSize16kb'), sum, body)
    nativeSum.push(sum)
  }
  if (nativeBody) html += group(label('nativeAnalysis'), nativeSum.join(' · '), nativeBody, '', '#8b5cf6', false)

  // ===== COMPRESSION (whole-package: assets / dex / lib) =====
  // Own top-level group, not nested under native libraries: only the `lib`
  // category is a native-library concern, while assets/dex describe the whole
  // APK — sharing the native parent misrepresented their scope.
  if (hasComp) {
    const rows: string[] = []
    let totUnc = 0
    let totCmp = 0
    let totStored = 0
    let totDeflated = 0
    const savedPct = (unc: number, cmp: number) =>
      unc > 0 ? ((1 - cmp / unc) * 100).toFixed(1) + '%' : '-'
    for (const [category, info] of Object.entries(comp)) {
      const c = info as any
      const uncompressed = c.uncompressed || 0
      const compressed = c.compressed || 0
      const stored = c.stored || 0
      const deflated = c.deflated || 0
      totUnc += uncompressed
      totCmp += compressed
      totStored += stored
      totDeflated += deflated
      rows.push(trow([
        esc(category),
        uncompressed > 0 ? fmtSize(uncompressed) : '-',
        compressed > 0 ? fmtSize(compressed) : '-',
        savedPct(uncompressed, compressed),
        `${stored}`,
        `${deflated}`,
      ]))
    }
    // Totals across all categories — overall compression health at a glance.
    rows.push(trow([
      `<b>${esc(label('total'))}</b>`,
      `<b>${totUnc > 0 ? fmtSize(totUnc) : '-'}</b>`,
      `<b>${totCmp > 0 ? fmtSize(totCmp) : '-'}</b>`,
      `<b>${savedPct(totUnc, totCmp)}</b>`,
      `<b>${totStored}</b>`,
      `<b>${totDeflated}</b>`,
    ]))
    const compSum = `${label('catCount', { count: Object.keys(comp).length })} · ${label('compressionDesc')}`
    html += group(
      label('compressionAnalysis'),
      compSum,
      table(
        [label('colCategory'), label('colUncompressed'), label('colCompressed'), label('colSaved'), label('colStoredCount'), label('colDeflatedCount')],
        rows,
      ),
      '',
      '#0ea5e9',
      false,
    )
  }

  // ===== META DATA =====
  if (metaData && Array.isArray(metaData) && metaData.length > 0) {
    const rows: string[] = []
    for (const item of metaData) {
      const parent = item.parent || 'unknown'
      const name = item.name || ''
      const value = item.value || ''
      const resValue = item.resource_value || ''
      const resContent = item.resource_content
      const resResolved = item.resource_resolved
      let valCell = ''
      if (value && !value.startsWith('@')) valCell = esc(value)
      else if (resValue) valCell = esc(resValue)
      else valCell = '-'
      let resCell = ''
      if (resResolved || (resContent && resContent.length > 0)) {
        if (resResolved) resCell += `<div class="apk-muted">${esc(resResolved)}</div>`
        if (resContent && resContent.length > 0) {
          for (const ci of resContent) resCell += `<div class="apk-res">${esc(ci.element)}: ${esc(ci.name)} → ${esc(ci.value)}</div>`
        }
      }
      rows.push(trow([
        `<span class="apk-parent">&lt;${esc(parent)}&gt;</span>`,
        esc(name),
        valCell,
        resCell
      ]))
    }
    const metaCard = card(label('metaData'), label('itemCount', { count: metaData.length }), table([label('colParent'), label('colName'), label('colValue'), label('colResource')], rows))
    html += group(label('manifestResources'), label('itemCount', { count: metaData.length }), metaCard, '', '#f59e0b', false)
  }

  html += '</div>'
  return html
}


</script>

<style scoped>
.package-page { max-width: var(--page-max-width); margin: 0 auto; height: calc(100vh - 48px); display: flex; flex-direction: column; }
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
  flex-wrap: wrap;
  gap: 10px;
}
/* Bound by class, not position: inserting an element before the input used to
   silently steal this flex from it via :nth-child(2). */
.task-source-input { flex: 1 1 240px; min-width: 0; }
.task-pick-btn { cursor: pointer; color: var(--app-text-dim); transition: color .2s; }
.task-pick-btn:hover { color: var(--app-green); }
.task-start-wrap { display: inline-flex; }
.task-bar-opts {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--app-card-border);
}
.op-desc { font-size: 12px; color: var(--app-text-dim); }
.op-label { font-size: 11px; color: var(--app-text-dim); white-space: nowrap; }

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
.task-result-bar { display: flex; justify-content: flex-end; margin: 2px 0 6px; }
.task-logs {
  background: var(--app-code-bg);
  border-radius: 6px;
  padding: 8px 10px;
  font-family: 'Fira Code', monospace;
  font-size: 11px;
  line-height: 1.6;
}
.task-log-line { color: var(--app-text-secondary); white-space: pre-wrap; overflow-wrap: anywhere; }
.task-logs-toolbar { display: flex; align-items: center; gap: 4px; margin-bottom: 6px; }
.task-logs-spacer { flex: 1; }
.task-logs-toolbar .n-button { flex: 0 0 auto; }
.task-log-trunc-hint {
  margin: 0 0 6px;
  font-family: var(--app-font, system-ui);
  font-size: 11px;
  color: var(--app-text-tertiary, #888);
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
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  color: var(--app-text-secondary); font-size: 13px; font-weight: 600;
}
.apk-card > summary::-webkit-details-marker { display: none; }
.apk-card[open] > .apk-card-body { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--app-card-border); }
.apk-card-body { display: flex; flex-direction: column; gap: 6px; }

.apk-card-h { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--app-text-secondary); }
.apk-sum-grp { display: flex; align-items: center; gap: 8px; min-width: 0; }

/* parent section grouping several related sub-analyses (e.g. native libs).
   --apk-accent (set per section via group()'s 5th arg) paints a left stripe
   so the four top-level blocks are scannable at a glance. */
.apk-group { background: var(--app-card-bg); border: 1px solid var(--app-card-border); border-left: 3px solid var(--apk-accent, var(--app-card-border)); border-radius: 10px; padding: 10px 14px; }
.apk-group > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--app-text-secondary); font-size: 13px; font-weight: 700; }
.apk-group > summary::-webkit-details-marker { display: none; }
.apk-group[open] > .apk-group-body { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--app-card-border); display: flex; flex-direction: column; gap: 10px; }
/* nested sub-cards lose their own box so the group is the single container */
.apk-group-body .apk-card { background: transparent; border: none; border-radius: 0; padding: 0; }
.apk-group-body .apk-card[open] > .apk-card-body { margin-top: 6px; padding-top: 6px; }
.apk-icon { width: 38px; height: 38px; border-radius: 8px; object-fit: contain; box-shadow: 0 1px 2px rgba(0,0,0,.18); flex: 0 0 auto; cursor: zoom-in; }
.apk-icon--fallback { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; border-radius: 8px; background: var(--app-card-border); color: var(--app-text-dim); font-weight: 600; font-size: 15px; flex: 0 0 auto; cursor: default; }

/* click-to-zoom lightbox for the app icon (overlay lives on <body>) */
.apk-lightbox { position: fixed; inset: 0; z-index: 9999; display: none; align-items: center; justify-content: center; background: rgba(0,0,0,.72); cursor: zoom-out; }
/* Show at the icon's NATURAL size and only shrink if it exceeds the cap —
   width/height:auto (not a fixed box) prevents object-fit from upscaling a
   small source and turning it blurry. */
.apk-lightbox-img { width: auto; height: auto; max-width: min(420px, 80vw); max-height: min(420px, 80vh); border-radius: 20px; box-shadow: 0 8px 40px rgba(0,0,0,.5); background: transparent; }
.apk-sum { font-size: 11px; color: var(--app-text-dim); font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* uniform table for every analysis section */
.apk-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.apk-table th { text-align: left; color: var(--app-text-dim); font-weight: 600; font-size: 11px; border-bottom: 1px solid var(--app-card-border); padding: 5px 8px; white-space: nowrap; }
.apk-table td { padding: 5px 8px; border-bottom: 1px solid var(--app-card-border); color: var(--app-text-secondary); vertical-align: top; word-break: break-word; }
.apk-table tr:last-child td { border-bottom: none; }
/* hover affordance so long tables (permissions / metadata) stay scannable */
.apk-table tbody tr:hover { background: rgba(128,128,128,0.07); }
.apk-table .mono { font-family: monospace; }
.apk-table .nowrap { white-space: nowrap; }

/* metadata parent column stays on one line */
.apk-parent { font-family: monospace; font-size: 11px; color: var(--app-text-dim); white-space: nowrap; }
.apk-res { font-size: 11px; color: var(--app-text-muted); font-family: monospace; }

.apk-archchip { display: inline-block; font-size: 11px; font-weight: 600; border-radius: 4px; padding: 1px 6px; margin: 1px 3px 1px 0; }

.apk-lv { display: inline-block; font-size: 11px; border-radius: 4px; padding: 1px 7px; font-weight: 600; white-space: nowrap; }
.apk-lv--danger { background: rgba(239,68,68,0.12); color: var(--app-red); }
.apk-lv--normal { background: rgba(128,128,128,0.12); color: var(--app-text-dim); }
.apk-lv--ok { background: rgba(34,197,94,0.12); color: var(--app-green); }

.apk-mini { display: inline-block; font-family: monospace; font-size: 11px; background: rgba(217,119,6,0.12); color: var(--app-warning, #d97706); border-radius: 3px; padding: 0 5px; margin: 0 2px; }

.apk-warn { background: rgba(217,119,6,0.1); border: 1px solid rgba(217,119,6,0.25); color: var(--app-warning, #d97706); border-radius: 6px; padding: 6px 10px; font-size: 12px; margin-top: 6px; }
.apk-muted { color: var(--app-text-dim); font-size: 12px; }

.apk-copy { color: var(--app-text-dim); opacity: 0.4; cursor: pointer; margin-left: 6px; display: inline-flex; align-items: center; vertical-align: middle; transition: opacity .15s, color .15s; }
.apk-copy:hover { opacity: 1; color: var(--app-green); }
.apk-copy svg { display: block; }

.chev { color: var(--app-text-dim); transition: transform .2s; }
details[open] > summary .chev { transform: rotate(90deg); }

/* nested details (e.g. "other permissions") */
.apk-card details > summary { list-style: none; cursor: pointer; user-select: none; display: flex; align-items: center; gap: 6px; color: var(--app-text-dim); font-size: 12px; }
.apk-card details > summary::-webkit-details-marker { display: none; }
</style>
