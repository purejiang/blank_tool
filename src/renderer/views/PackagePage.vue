<template>
  <div class="package-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('package.title') }}</h1>
        <p class="page-subtitle">{{ t('package.subtitle') }}</p>
      </div>
      <n-space :size="8">
        <n-button size="tiny" quaternary @click="taskStore.clearCompleted" :disabled="!hasCompleted">
          {{ t('task.clearCompleted') }}
        </n-button>
        <n-button size="tiny" quaternary type="error" @click="taskStore.clearAll" :disabled="tasks.length === 0">
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
          placeholder="https://example.com/app.apk"
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

    <!-- Task List -->
    <div v-if="tasks.length === 0" class="empty-state">
      <n-icon size="48" color="var(--app-text-dim)"><Inbox /></n-icon>
      <p class="empty-title">{{ t('task.empty') }}</p>
      <p class="empty-desc">{{ t('task.emptyDesc') }}</p>
    </div>

    <div v-else class="task-list">
      <div v-for="task in tasks"
        :key="task.id"
        class="task-card"
        :class="'task-' + task.status"
      >
        <div class="task-header" @click="task.collapsed = !task.collapsed">
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
            <n-button
              v-if="task.status === 'completed' || task.status === 'failed'"
              size="tiny"
              quaternary
              type="error"
              @click.stop="taskStore.removeTask(task.id)"
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
          <div v-if="task.outputPath" class="task-output">
            <n-icon size="14" color="var(--app-green)"><FolderOpen /></n-icon>
            <span class="task-output-path">{{ t('task.output') }}: {{ task.outputPath }}</span>
            <n-button size="tiny" quaternary type="info" @click.stop="openInExplorer(task.outputPath)">
              <template #icon><n-icon size="13"><ExternalLink /></n-icon></template>
            </n-button>
          </div>
          <div v-if="task.result" class="task-result" v-html="task.result" />
          <div v-if="task.logs.length > 0" class="task-logs">
            <div v-for="(line, i) in task.logs" :key="i" class="task-log-line">{{ line }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import {
  Play, Link, FolderOpen, Download, CheckCircle, XCircle, Loader,
  ChevronDown, ChevronRight, Trash2, Inbox, ExternalLink
} from 'lucide-vue-next'
import { useNotification } from '@composables/useNotification'
import { useTaskStore } from '@stores/index'
import { useSignatureStore } from '@stores/signatureStore'
import type { Task } from '@stores/taskStore'
import serviceManager from '@services/ServiceManager'
import unifiedApi from '@api/unifiedApi'

const { t } = useI18n()
const taskStore = useTaskStore()
const { tasks, hasCompleted } = taskStore
const { showError } = useNotification()
const sigStore = useSignatureStore()
sigStore.loadConfigs()

// New task form
const newSource = ref<'url' | 'local'>('local')
const newUrl = ref('')
const newOperation = ref<Task['operation']>('analyze')
const newLocalPath = ref('')
const newLocalName = ref('')
const localFileInput = ref<HTMLInputElement | null>(null)
const newSignId = ref('')
const decompileResources = ref(true)
const decompileSources = ref(true)

const signOptions = computed(() =>
  sigStore.configs.map((c: any) => ({ label: c.name, value: c.id }))
)

const operationOptions = computed(() => [
  { label: t('task.analyze'), value: 'analyze' },
  { label: t('task.install'), value: 'install' },
  { label: t('task.decompile'), value: 'decompile' },
  { label: t('task.recompile'), value: 'recompile' },
  { label: t('task.resign'), value: 'resign' },
])

const canStart = computed(() => {
  if (newSource.value === 'url') return !!newUrl.value.trim()
  return !!newLocalPath.value
})

const hasOpts = computed(() =>
  ['resign', 'recompile', 'decompile'].includes(newOperation.value)
)

function opTagType(op: string) {
  const map: Record<string, string> = { analyze: 'info', install: 'success', decompile: 'warning', recompile: 'warning', resign: 'error' }
  return map[op] || 'default'
}

function formatTime(ts: number) {
  const d = new Date(ts)
  return `${d.getMonth() + 1}-${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

async function openInExplorer(filePath: string) {
  try {
    const api = window.electronAPI as any
    if (api && typeof api.openPath === 'function') {
      await api.openPath(filePath)
    }
  } catch (e) {
    console.error('openInExplorer error:', e)
  }
}

async function pickLocalFile() {
  try {
    const api = window.electronAPI as any
    const result = await api.selectFile({
      title: t('task.selectFile'),
      filters: [{ name: 'APK/AAB', extensions: ['apk', 'aab'] }]
    })
    if (result && !result.canceled && result.filePaths?.length) {
      const fp = result.filePaths[0]
      newLocalPath.value = fp
      newLocalName.value = fp.split(/[/\\]/).pop() || 'file'
    }
  } catch (e) {
    console.error('pickLocalFile error:', e)
  }
}

function onLocalFilePicked(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    newLocalName.value = file.name
    const fp = (file as any).path
    newLocalPath.value = (fp && fp !== file.name) ? fp : file.name
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
  try {
    let localPath = task.filePath

    // Set up streaming listener BEFORE any operations
    const api = window.electronAPI as any
    let streamResolve: ((v: any) => void) | null = null
    let streamReject: ((e: Error) => void) | null = null

    const onStream = (raw: any) => {
      if (!raw) return
      // Main process wraps stream events as { stream_id, data: {...} }
      const data = raw.data || raw
      const tid = data.task_id || (data.payload && data.payload.task_id)
      if (tid !== String(task.id)) return
      // Handle progress events (download or operation)
      if (data.type === 'progress' && data.payload) {
        const pct = data.payload.progress || 0
        taskStore.updateTask(task.id, { progress: pct, progressLabel: data.payload.label || `${pct}%` })
      }
      // Handle stream completion (download done)
      if (data.type === 'complete' && streamResolve) {
        streamResolve(data.payload || data)
      }
      // Handle stream error
      if (data.type === 'error' && streamReject) {
        const msg = (data.payload && data.payload.message) || data.message || '流式操作失败'
        streamReject(new Error(msg))
      }
      // Handle log lines
      const line = data.line || data.message || data.output || ''
      if (line) taskStore.appendLog(task.id, line)
    }
    if (api && typeof api.onStreamEvent === 'function') {
      api.onStreamEvent(onStream)
    }

    // Step 1: Download if URL source
    if (task.source === 'url' && task.url) {
      taskStore.updateTask(task.id, { status: 'downloading', progress: 0, progressLabel: '下载中...' })
      taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 开始下载 ${task.url}`)
      if (!api || typeof api.downloadFile !== 'function') throw new Error('下载API不可用')

      const dlPromise = new Promise((resolve, reject) => {
        streamResolve = resolve
        streamReject = reject
      })
      // Fire the download (returns stream_id immediately)
      api.downloadFile(task.url, task.fileName, String(task.id))
      // Wait for streaming complete/error
      const dlResult = await dlPromise
      localPath = dlResult.file_path
      taskStore.updateTask(task.id, { progress: 100, progressLabel: '下载完成' })
      taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 下载完成 (${(dlResult.size / 1024 / 1024).toFixed(1)}MB)`)
      // Clear stream handlers
      streamResolve = null
      streamReject = null
    }

    // Step 2: Execute operation
    taskStore.updateTask(task.id, { status: 'running', progress: 0, progressLabel: '执行中...' })
    taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 开始执行 ${task.operationLabel}`)

    switch (task.operation) {
      case 'analyze':
        await runAnalyze(task, localPath)
        break
      case 'install':
        await runInstall(task, localPath)
        break
      case 'decompile':
        await runDecompile(task, localPath)
        break
      case 'recompile':
        await runRecompile(task, localPath)
        break
      case 'resign':
        await runResign(task, localPath)
        break
      default:
        taskStore.updateTask(task.id, { status: 'completed', progress: 100, progressLabel: '完成', finishedAt: Date.now() })
        taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 此功能开发中`)
        break
    }
  } catch (e: any) {
    taskStore.updateTask(task.id, { status: 'failed', error: e.message || String(e), finishedAt: Date.now() })
    taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 错误: ${e.message || e}`)
  }
}

async function runAnalyze(task: Task, localPath: string) {
  const svc = await serviceManager.getService('apk') as any
  if (typeof svc?.analyzeApk !== 'function') throw new Error('分析服务不可用')
  const iv = startProgress(task, '分析中')
  taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 正在分析 ${task.fileName}...`)
  const result = await svc.analyzeApk(localPath)
  if (result.success) {
    finishProgress(task, iv)
    const html = renderApkInfo(result.data)
    taskStore.updateTask(task.id, { status: 'completed', progress: 100, progressLabel: '完成', result: html, finishedAt: Date.now() })
    taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 分析完成`)
  } else {
    clearInterval(iv)
    throw new Error(result.error || '分析失败')
  }
}

async function runInstall(task: Task, localPath: string) {
  const svc = await serviceManager.getService('device') as any
  if (typeof svc?.installApp !== 'function') throw new Error('安装服务不可用')
  const iv = startProgress(task, '安装中')
  taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 正在安装到设备...`)
  const result = await svc.installApp(localPath)
  if (result.success) {
    finishProgress(task, iv)
    taskStore.updateTask(task.id, { status: 'completed', progress: 100, progressLabel: '完成', finishedAt: Date.now() })
    taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 安装成功`)
  } else {
    clearInterval(iv)
    throw new Error(result.error || '安装失败')
  }
}

async function runDecompile(task: Task, localPath: string) {
  const svc = await serviceManager.getService('apk') as any
  if (typeof svc?.decompileApk !== 'function') throw new Error('反编译服务不可用')
  const opts = { resources: decompileResources.value, sources: decompileSources.value }
  const iv = startProgress(task, '反编译中')
  taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 正在反编译 (资源:${opts.resources}, 源码:${opts.sources})...`)
  const result = await svc.decompileApk(localPath, opts)
  if (result.success) {
    finishProgress(task, iv)
    taskStore.updateTask(task.id, { status: 'completed', progress: 100, progressLabel: '完成', outputPath: result.outputPath, finishedAt: Date.now() })
    taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 反编译完成 → ${result.outputPath}`)
  } else {
    clearInterval(iv)
    throw new Error(result.error || '反编译失败')
  }
}

async function runRecompile(task: Task, localPath: string) {
  const svc = await serviceManager.getService('apk') as any
  if (typeof svc?.recompileApk !== 'function') throw new Error('重编译服务不可用')

  let signOpts: any = { sign: false, align: true, optimize: true }
  const cfg = sigStore.configs.find((c: any) => c.id === newSignId.value) || sigStore.configs[0]
  if (cfg) {
    signOpts.sign = true
    signOpts.v2 = true
    signOpts.keystore = { path: cfg.path, alias: cfg.alias, storepass: cfg.storepass, keypass: cfg.keypass }
    taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 正在重编译 (签名:${cfg.name})...`)
  } else {
    taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 正在重编译 (无签名)...`)
  }
  const iv = startProgress(task, '重编译中')
  const result = await svc.recompileApk(localPath, signOpts)
  if (result.success) {
    finishProgress(task, iv)
    taskStore.updateTask(task.id, { status: 'completed', progress: 100, progressLabel: '完成', outputPath: result.outputPath, finishedAt: Date.now() })
    taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 重编译完成 → ${result.outputPath}`)
  } else {
    clearInterval(iv)
    throw new Error(result.error || '重编译失败')
  }
}

async function runResign(task: Task, localPath: string) {
  const cfg = sigStore.configs.find((c: any) => c.id === newSignId.value) || sigStore.configs[0]
  if (!cfg) throw new Error('没有签名配置，请先在设置中添加签名配置')

  const svc = await serviceManager.getService('apk') as any
  if (typeof svc?.signApk !== 'function') throw new Error('签名服务不可用')
  taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 正在签名 (${cfg.name})...`)
  const iv = startProgress(task, '签名中')
  const keystore = { path: cfg.path, alias: cfg.alias, storepass: cfg.storepass, keypass: cfg.keypass }
  const result = await svc.signApk(localPath, keystore, { v2: true })
  if (result.success) {
    finishProgress(task, iv)
    taskStore.updateTask(task.id, { status: 'completed', progress: 100, progressLabel: '完成', outputPath: result.outputPath, finishedAt: Date.now() })
    taskStore.appendLog(task.id, `[${new Date().toLocaleTimeString()}] 签名完成 → ${result.outputPath}`)
  } else {
    clearInterval(iv)
    throw new Error(result.error || '签名失败')
  }
}

function renderApkInfo(data: any) {
  if (!data) return ''
  const perms = data.permissions || []
  return `<div style="display:flex;flex-direction:column;gap:5px;font-size:13px;line-height:1.6">
    <div><span style="color:var(--app-text-dim)">名称：</span><span style="color:var(--app-text-primary)">${data.applicationLabel || '-'}</span></div>
    <div><span style="color:var(--app-text-dim)">包名：</span><span style="color:var(--app-text-secondary);font-family:monospace">${data.packageName || '-'}</span></div>
    <div><span style="color:var(--app-text-dim)">版本：</span><span style="color:var(--app-text-secondary)">${data.versionName || '-'} (${data.versionCode || '-'})</span></div>
    <div><span style="color:var(--app-text-dim)">最小 SDK：</span><span style="color:var(--app-text-secondary)">${data.minSdkVersion || '-'}</span></div>
    <div><span style="color:var(--app-text-dim)">目标 SDK：</span><span style="color:var(--app-text-secondary)">${data.targetSdkVersion || '-'}</span></div>
    <div><span style="color:var(--app-text-dim)">权限 (${perms.length})：</span><span style="color:var(--app-text-dim);font-size:12px">${perms.length ? perms.slice(0, 20).join(', ') + (perms.length > 20 ? '...' : '') : '无'}</span></div>
  </div>`
}

function startProgress(task: Task, label: string) {
  let p = 0
  const iv = setInterval(() => {
    if (p < 30) p += 2
    else if (p < 60) p += 1
    else if (p < 85) p += 0.5
    else { /* hold at 85, jump on complete */ return }
    taskStore.updateTask(task.id, { progress: Math.round(Math.min(p, 85)), progressLabel: label })
  }, 500)
  return iv
}

function finishProgress(task: Task, iv: ReturnType<typeof setInterval>) {
  clearInterval(iv)
  taskStore.updateTask(task.id, { progress: 100, progressLabel: '完成' })
}
</script>

<style scoped>
.package-page { max-width: 960px; margin: 0 auto; }
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
.task-log-line { color: var(--app-text-secondary); white-space: pre-wrap; word-break: break-all; }
</style>
