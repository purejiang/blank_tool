import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Task {
  id: number
  source: 'url' | 'local'
  url?: string
  filePath: string
  fileName: string
  operation: 'analyze' | 'install' | 'decompile' | 'recompile' | 'resign'
  operationLabel: string
  status: 'downloading' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'cancelling'
  progress: number
  progressLabel: string
  result: string
  outputPath: string
  logs: string[]
  error: string
  collapsed: boolean
  createdAt: number
  finishedAt: number | null
  taskDir: string
}

let nextId = 1

const STORAGE_KEY = 'task-history'

function loadTasks(): Task[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as Task[]
  } catch {}
  return []
}

function saveTasks(tasks: Task[]) {
  try {
    const toSave = tasks.filter(t => t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled').slice(0, 100)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
  } catch {}
}

// Collect deletable task IDs from terminal tasks (completed/failed/cancelled).
// Deduped.
function collectDeletableTaskIds(list: Task[]): string[] {
  const seen = new Set<string>()
  for (const t of list) {
    if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
      const id = String(t.id)
      if (id.length > 0) seen.add(id)
    }
  }
  return Array.from(seen)
}

// Fire-and-forget best-effort deletion of task dirs via the backend.
// Never throws; only console.errors on failure. Respects the
// `autoDeleteOutputOnTaskRemove` toggle.
async function tryDeleteTaskDirs(ids: string[]): Promise<void> {
  if (ids.length === 0) return
  if (!window.electronAPI?.appConfig?.get) return
  try {
    const enabled = await window.electronAPI.appConfig.get('autoDeleteOutputOnTaskRemove')
    if (enabled !== true) return
    for (const id of ids) {
      if (!id) continue
      try {
        await window.electronAPI.callBackendAPI('task.delete_task_dir', { task_id: id })
      } catch (err) {
        console.error('[taskStore] auto-delete task dir failed for', id, err)
      }
    }
  } catch (err) {
    console.error('[taskStore] auto-delete config check failed', err)
  }
}

// Fire-and-forget best-effort persistence of a single log line to the
// per-task log file via the backend.  Never throws.
async function persistLine(id: number, line: string): Promise<void> {
  if (!window.electronAPI?.callBackendAPI) return
  try {
    await window.electronAPI.callBackendAPI('task.append_log', { task_id: String(id), line })
  } catch {
    // silently ignore — persistence is best-effort
  }
}

// Fire-and-forget OS notification when a task reaches a terminal state.
// Never throws; only console.errors on failure. Respects the
// `enableNotifications` toggle. Uses plain strings (store stays i18n-decoupled).
async function notifyTaskTerminal(task: Task): Promise<void> {
  const notify = window.electronAPI?.showSystemNotification as
    | ((title: string, body: string) => Promise<boolean>)
    | undefined
  if (!window.electronAPI?.appConfig?.get || typeof notify !== 'function') return
  try {
    const enabled = await window.electronAPI.appConfig.get('enableNotifications')
    if (enabled !== true) return
    const title = `${task.operationLabel || 'Task'} ${task.fileName || ''}`.trim()
    let body: string
    if (task.status === 'completed') {
      body = '已完成'
    } else if (task.status === 'failed') {
      body = `失败${task.error ? ': ' + task.error : ''}`
    } else {
      body = '已取消'
    }
    await notify(title, body)
  } catch (err) {
    console.error('[taskStore] notify failed', err)
  }
}

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<Task[]>(loadTasks())
  const maxTasks = 50

  // Restore nextId from saved tasks
  if (tasks.value.length > 0) {
    const maxId = Math.max(...tasks.value.map(t => t.id), 0)
    nextId = maxId + 1
  }

  const runningCount = computed(() => tasks.value.filter(t => t.status === 'running').length)
  const hasRunning = computed(() => runningCount.value > 0)
  const hasCompleted = computed(() => tasks.value.some(t => t.status === 'completed' || t.status === 'failed'))

  function createTask(partial: Pick<Task, 'source' | 'url' | 'filePath' | 'fileName' | 'operation' | 'operationLabel'>): Task {
    const task: Task = {
      id: nextId++,
      ...partial,
      status: partial.source === 'url' ? 'downloading' : 'queued',
      progress: 0,
      progressLabel: '',
      result: '',
      outputPath: '',
      logs: [],
      error: '',
      collapsed: false,
      createdAt: Date.now(),
      finishedAt: null,
      taskDir: '',
    }
    tasks.value.unshift(task)
    if (tasks.value.length > maxTasks) tasks.value.pop()
    persist()
    return task
  }

  function persist() {
    saveTasks(tasks.value)
  }

  function updateTask(id: number, updates: Partial<Task>) {
    const idx = tasks.value.findIndex(t => t.id === id)
    if (idx !== -1) {
      Object.assign(tasks.value[idx], updates)
      // Persist and notify when task reaches a terminal state
      if (updates.status === 'completed' || updates.status === 'failed' || updates.status === 'cancelled') {
        persist()
        void notifyTaskTerminal(tasks.value[idx])
      }
    }
  }

  function appendLog(id: number, line: string) {
    const task = tasks.value.find(t => t.id === id)
    if (task) {
      task.logs.push(line)
      if (task.logs.length > 500) task.logs.shift()
    }
    // Persist to per-task log file (fire-and-forget, best-effort)
    void persistLine(id, line)
  }

  function appendLogBatch(id: number, lines: string[]) {
    const task = tasks.value.find(t => t.id === id)
    if (task) {
      task.logs.push(...lines)
      if (task.logs.length > 500) task.logs.splice(0, task.logs.length - 500)
    }
    // Persist lines in background (fire-and-forget, best-effort)
    for (const line of lines) void persistLine(id, line)
  }

  function removeTask(id: number) {
    const idx = tasks.value.findIndex(t => t.id === id)
    if (idx !== -1) {
      const task = tasks.value[idx]
      void tryDeleteTaskDirs(collectDeletableTaskIds([task]))
      tasks.value.splice(idx, 1)
      persist()
    }
  }

  function clearCompleted() {
    const removed = tasks.value.filter(t => t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled')
    void tryDeleteTaskDirs(collectDeletableTaskIds(removed))
    tasks.value = tasks.value.filter(t => t.status !== 'completed' && t.status !== 'failed' && t.status !== 'cancelled')
    persist()
  }

  function clearAll() {
    void tryDeleteTaskDirs(collectDeletableTaskIds(tasks.value))
    tasks.value = []
    persist()
  }

  return { tasks, runningCount, hasRunning, hasCompleted, maxTasks, createTask, updateTask, appendLog, appendLogBatch, removeTask, clearCompleted, clearAll }
})
